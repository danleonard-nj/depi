"""
The BaseInjector contract, tested without a web framework.

Every adapter inherits this behaviour, so it is worth pinning down once here
rather than four times over in the integration suites.
"""

import pytest

from depi import NoActiveScopeError, ServiceCollection, use_scope
from depi.integration import BaseInjector, injectable_parameters


class Greeter:
    def greet(self):
        return 'hello'


class Unregistered:
    pass


class StubInjector(BaseInjector):
    """Minimal concrete injector; adapters differ only in setup()."""

    def setup(self, app=None):
        pass


@pytest.fixture
def provider():
    services = ServiceCollection()
    services.add_transient(Greeter)
    return services.build_provider()


def test_provider_property_exposes_the_provider(provider):
    assert StubInjector(provider).provider is provider


def test_create_scope_returns_an_unbound_scope(provider):
    injector = StubInjector(provider)
    scope = injector.create_scope()
    assert scope.resolve(Greeter).greet() == 'hello'
    # Creating a scope must not bind it; binding is setup()'s job.
    with pytest.raises(NoActiveScopeError):
        injector.current_scope()


def test_current_scope_returns_the_bound_scope(provider):
    injector = StubInjector(provider)
    scope = injector.create_scope()
    with use_scope(scope):
        assert injector.current_scope() is scope


def test_setup_is_abstract():
    with pytest.raises(TypeError):
        BaseInjector(None)


# --------------------------------------------------------------------------
# injectable_parameters: deciding what depi owns and what the framework owns
# --------------------------------------------------------------------------

def test_only_registered_annotations_are_claimed(provider):
    def view(path_arg: str, greeter: Greeter, other: Unregistered):
        pass

    assert injectable_parameters(view, provider) == {'greeter': Greeter}


def test_unannotated_parameters_are_left_alone(provider):
    def view(path_arg, greeter: Greeter):
        pass

    assert injectable_parameters(view, provider) == {'greeter': Greeter}


def test_variadic_parameters_are_skipped(provider):
    def view(*args: Greeter, **kwargs: Greeter):
        pass

    assert injectable_parameters(view, provider) == {}


def test_typing_constructs_are_not_claimed(provider):
    """Optional[X] is not a class, so it is not something depi can construct."""
    from typing import Optional

    def view(b: Optional[Greeter], c: 42):
        pass

    assert injectable_parameters(view, provider) == {}


@pytest.mark.parametrize('annotation', [
    'not a type',                 # SyntaxError when evaluated
    'DoesNotExistAnywhere',       # NameError
    'sys.NoSuchAttribute',        # AttributeError
])
def test_an_unevaluatable_annotation_degrades_to_no_op(provider, annotation):
    """
    Signatures are evaluated with eval_str=True, so a string annotation can fail
    in several ways -- and it fails at decoration time, i.e. at import. Autowire
    must claim nothing rather than take the application down on the way up.
    """
    namespace = {}
    source = 'def view(thing: {!r}):\n    pass'.format(annotation)
    exec(source, namespace)

    assert injectable_parameters(namespace['view'], provider) == {}


def test_an_uninspectable_callable_degrades_to_no_op(provider):
    """Some builtins have no retrievable signature; that must not be fatal."""
    assert injectable_parameters(len, provider) == {}


def test_inspection_happens_once_at_decoration_not_per_call(provider):
    """
    The wrapper closes over the resolved parameter map, so a signature change
    after decoration has no effect. This is what keeps the request path cheap.
    """
    injector = StubInjector(provider, autowire=True)

    def view(greeter: Greeter):
        return greeter.greet()

    wrapped = injector.inject(view)
    with use_scope(injector.create_scope()):
        assert wrapped() == 'hello'


def test_default_mode_passes_the_scope_under_param_name(provider):
    injector = StubInjector(provider, param_name='container')

    @injector.inject
    def view(container):
        return container.resolve(Greeter).greet()

    with use_scope(injector.create_scope()):
        assert view() == 'hello'


def test_autowire_needs_no_scope_when_everything_is_supplied(provider):
    """
    The ambient scope is consulted lazily, so a fully-supplied call works with
    no request context at all.
    """
    injector = StubInjector(provider, autowire=True)

    @injector.inject
    def view(greeter: Greeter):
        return greeter.greet()

    class Stub:
        def greet(self):
            return 'stub'

    assert view(greeter=Stub()) == 'stub'


def test_a_view_with_nothing_to_inject_needs_no_scope(provider):
    injector = StubInjector(provider, autowire=True)

    @injector.inject
    def view(plain_arg):
        return plain_arg

    assert view('value') == 'value'
