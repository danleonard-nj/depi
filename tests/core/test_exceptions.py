"""
The exception hierarchy, and the compatibility promises it has to keep.

depi used to raise bare ``Exception``, and ``RuntimeError`` for the async-factory
guard. Code in the wild catches those. Every class here still derives from what
it used to be, and the tests below pin that down -- if someone later "tidies"
the bases, these fail rather than silently breaking callers.
"""

import pytest

from depi import (
    AsyncFactoryError,
    CircularDependencyError,
    DepiError,
    InvalidLifetimeError,
    MissingAnnotationError,
    NoActiveScopeError,
    RegistrationError,
    ResolutionError,
    ScopeRequiredError,
    ServiceCollection,
    UnknownLifetimeError,
    UnregisteredDependencyError,
    current_scope,
)

ALL_ERRORS = [
    RegistrationError,
    MissingAnnotationError,
    CircularDependencyError,
    InvalidLifetimeError,
    UnknownLifetimeError,
    ResolutionError,
    UnregisteredDependencyError,
    ScopeRequiredError,
    AsyncFactoryError,
    NoActiveScopeError,
]


# --------------------------------------------------------------------------
# Shape of the hierarchy
# --------------------------------------------------------------------------

@pytest.mark.parametrize('error', ALL_ERRORS)
def test_every_error_derives_from_depi_error(error):
    """One base means an application can catch depi without catching everything."""
    assert issubclass(error, DepiError)


@pytest.mark.parametrize('error', ALL_ERRORS)
def test_every_error_is_still_an_exception(error):
    """Backwards compatibility: depi used to raise bare Exception."""
    assert issubclass(error, Exception)


@pytest.mark.parametrize('error', [AsyncFactoryError, NoActiveScopeError])
def test_previously_runtime_errors_still_are(error):
    """These two were RuntimeError; existing handlers must keep catching them."""
    assert issubclass(error, RuntimeError)


@pytest.mark.parametrize('error', [
    MissingAnnotationError, CircularDependencyError,
    InvalidLifetimeError, UnknownLifetimeError,
])
def test_startup_failures_group_under_registration_error(error):
    assert issubclass(error, RegistrationError)


@pytest.mark.parametrize('error', [
    UnregisteredDependencyError, ScopeRequiredError, AsyncFactoryError,
])
def test_resolve_time_failures_group_under_resolution_error(error):
    assert issubclass(error, ResolutionError)


def test_registration_and_resolution_are_distinguishable():
    """
    The split is the point: a registration failure is a bug in how the container
    was described, a resolution failure is a bug in what was asked of it.
    """
    assert not issubclass(RegistrationError, ResolutionError)
    assert not issubclass(ResolutionError, RegistrationError)


# --------------------------------------------------------------------------
# What actually gets raised
# --------------------------------------------------------------------------

class Unannotated:
    def __init__(self, x):
        pass


class Missing:
    pass


class NeedsMissing:
    def __init__(self, m: Missing):
        pass


class Scoped:
    pass


class SingletonNeedsScoped:
    def __init__(self, s: Scoped):
        pass


class Cyclic:
    def __init__(self, other: 'Cyclic2'):
        pass


class Cyclic2:
    def __init__(self, other: Cyclic):
        pass


class Built:
    pass


async def async_factory(provider) -> Built:
    return Built()


def test_missing_annotation():
    with pytest.raises(MissingAnnotationError, match='Missing type annotation'):
        ServiceCollection().add_transient(Unannotated)


def test_circular_dependency():
    collection = ServiceCollection()
    collection.add_transient(Cyclic)
    collection.add_transient(Cyclic2)
    with pytest.raises(CircularDependencyError, match='Cyclic dependency detected'):
        collection.build_provider()


def test_invalid_lifetime_combination():
    collection = ServiceCollection()
    collection.add_scoped(Scoped)
    collection.add_singleton(SingletonNeedsScoped)
    with pytest.raises(InvalidLifetimeError, match='cannot depend on scoped'):
        collection.build_provider()


def test_unregistered_dependency():
    collection = ServiceCollection()
    collection.add_transient(NeedsMissing)
    with pytest.raises(UnregisteredDependencyError, match='Failed to locate registration'):
        collection.build_provider().resolve(NeedsMissing)


def test_scope_required():
    collection = ServiceCollection()
    collection.add_scoped(Scoped)
    with pytest.raises(ScopeRequiredError, match='requires a scope'):
        collection.build_provider().resolve(Scoped)


def test_async_factory_resolved_synchronously():
    collection = ServiceCollection()
    collection.add_transient(Built, factory=async_factory)
    with pytest.raises(AsyncFactoryError, match='resolve_async'):
        collection.build_provider().create_scope().resolve(Built)


def test_no_active_scope():
    with pytest.raises(NoActiveScopeError):
        current_scope()


# --------------------------------------------------------------------------
# Compatibility, exercised the way callers actually write it
# --------------------------------------------------------------------------

def test_old_style_except_exception_still_catches():
    collection = ServiceCollection()
    collection.add_transient(NeedsMissing)
    try:
        collection.build_provider().resolve(NeedsMissing)
    except Exception as exc:
        assert isinstance(exc, UnregisteredDependencyError)
    else:
        pytest.fail('expected a failure')


def test_old_style_except_runtime_error_still_catches_async_factory():
    collection = ServiceCollection()
    collection.add_transient(Built, factory=async_factory)
    try:
        collection.build_provider().create_scope().resolve(Built)
    except RuntimeError as exc:
        assert isinstance(exc, AsyncFactoryError)
    else:
        pytest.fail('expected a failure')


def test_catching_depi_error_does_not_swallow_unrelated_failures():
    """A user's own exception must pass straight through a depi handler."""
    class UserFactoryBug(Exception):
        pass

    def exploding_factory(provider):
        raise UserFactoryBug('bug inside the factory')

    collection = ServiceCollection()
    collection.add_transient(Built, factory=exploding_factory)
    provider = collection.build_provider()

    with pytest.raises(UserFactoryBug):
        try:
            provider.resolve(Built)
        except DepiError:
            pytest.fail('a bug in user code was misreported as a depi error')


# --------------------------------------------------------------------------
# Cycle messages report the chain, not just where detection happened
# --------------------------------------------------------------------------

class TwoA:
    def __init__(self, b: 'TwoB'):
        pass


class TwoB:
    def __init__(self, a: TwoA):
        pass


class ThreeX:
    def __init__(self, y: 'ThreeY'):
        pass


class ThreeY:
    def __init__(self, z: 'ThreeZ'):
        pass


class ThreeZ:
    def __init__(self, x: ThreeX):
        pass


class SelfReferential:
    def __init__(self, me: 'SelfReferential'):
        pass


class CleanEntry:
    def __init__(self, p: 'LoopP'):
        pass


class LoopP:
    def __init__(self, q: 'LoopQ'):
        pass


class LoopQ:
    def __init__(self, p: LoopP):
        pass


def _cycle_message(*types):
    collection = ServiceCollection()
    for t in types:
        collection.add_transient(t)
    with pytest.raises(CircularDependencyError) as exc:
        collection.build_provider()
    return str(exc.value)


def test_two_node_cycle_names_both_types_and_closes_the_loop():
    assert _cycle_message(TwoA, TwoB).endswith('TwoA -> TwoB -> TwoA')


def test_three_node_cycle_names_the_whole_chain():
    assert _cycle_message(ThreeX, ThreeY, ThreeZ).endswith(
        'ThreeX -> ThreeY -> ThreeZ -> ThreeX')


def test_self_reference_is_reported_as_a_cycle():
    assert _cycle_message(SelfReferential).endswith(
        'SelfReferential -> SelfReferential')


def test_lead_in_path_is_excluded_from_the_message():
    """
    Only the cycle belongs in the message. CleanEntry depends on the loop but is
    not part of it, so naming it would send the reader to an innocent class.
    """
    message = _cycle_message(CleanEntry, LoopP, LoopQ)
    assert message.endswith('LoopP -> LoopQ -> LoopP')
    assert 'CleanEntry' not in message


def test_message_keeps_its_historical_prefix():
    """Existing code and tests match on this substring."""
    assert _cycle_message(TwoA, TwoB).startswith('Cyclic dependency detected:')
