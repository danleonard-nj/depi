"""
Scope disposal semantics and their edge cases.

These pin down behaviour that is easy to change by accident and hard to notice:
what happens when a disposer raises, what a scope does and does not own, and
what a disposed scope does next.
"""

import pytest

from depi import ServiceCollection


class Tracked:
    """Scoped, records its own disposal."""

    def __init__(self):
        self.disposed = False

    def dispose(self):
        self.disposed = True


class ExplodingDisposer:
    def dispose(self):
        raise ValueError('disposal failed')


class NoDispose:
    """Has no dispose(); disposal must skip it rather than fail."""


@pytest.fixture
def collection():
    services = ServiceCollection()
    services.add_scoped(Tracked)
    services.add_scoped(ExplodingDisposer)
    services.add_scoped(NoDispose)
    return services


def test_a_raising_disposer_does_not_abort_disposal(collection):
    """
    One bad disposer must not strand the rest. A scope is disposed in a
    finally/teardown, where an exception would escape into framework internals.
    """
    scope = collection.build_provider().create_scope()
    scope.resolve(ExplodingDisposer)
    tracked = scope.resolve(Tracked)

    scope.dispose()  # must not raise

    assert tracked.disposed, 'disposal stopped at the failing disposer'


def test_instances_without_dispose_are_skipped(collection):
    scope = collection.build_provider().create_scope()
    scope.resolve(NoDispose)
    scope.dispose()


def test_dispose_is_idempotent(collection):
    scope = collection.build_provider().create_scope()
    scope.resolve(Tracked)
    scope.dispose()
    scope.dispose()


def test_transients_are_not_owned_by_the_scope(collection):
    """
    Deliberate divergence from .NET, which this container is otherwise modelled
    on: Microsoft.Extensions.DependencyInjection tracks transient IDisposables
    on the scope and disposes them with it, which is a well-known way to
    accumulate objects for the lifetime of a long-lived scope.

    depi tracks only scoped instances. A transient's lifetime belongs to
    whoever asked for it.
    """
    services = ServiceCollection()
    services.add_transient(Tracked)
    scope = services.build_provider().create_scope()

    first = scope.resolve(Tracked)
    second = scope.resolve(Tracked)
    scope.dispose()

    assert first is not second
    assert not first.disposed and not second.disposed


def test_singletons_are_not_disposed_by_a_scope():
    """A singleton outlives any one scope, so a scope must not dispose it."""
    services = ServiceCollection()
    services.add_singleton(Tracked)
    provider = services.build_provider()

    scope = provider.create_scope()
    singleton = scope.resolve(Tracked)
    scope.dispose()

    assert not singleton.disposed
    assert provider.resolve(Tracked) is singleton


def test_scopes_are_independent_of_one_another(collection):
    provider = collection.build_provider()
    first, second = provider.create_scope(), provider.create_scope()

    a, b = first.resolve(Tracked), second.resolve(Tracked)
    assert a is not b

    first.dispose()
    assert a.disposed and not b.disposed
    assert second.resolve(Tracked) is b, 'disposing one scope disturbed another'


def test_a_disposed_scope_starts_over_rather_than_raising(collection):
    """
    Documenting current behaviour: dispose() clears the scope's instances but
    does not seal it, so a later resolve produces a fresh instance instead of
    raising. Framework adapters never reuse a scope, so this only shows up in
    hand-rolled code.
    """
    scope = collection.build_provider().create_scope()
    first = scope.resolve(Tracked)
    scope.dispose()

    second = scope.resolve(Tracked)
    assert first.disposed
    assert second is not first
    assert not second.disposed


def test_context_manager_disposes_on_exit(collection):
    provider = collection.build_provider()
    with provider.create_scope() as scope:
        tracked = scope.resolve(Tracked)
    assert tracked.disposed


def test_context_manager_disposes_when_the_block_raises(collection):
    provider = collection.build_provider()
    tracked = None
    with pytest.raises(RuntimeError):
        with provider.create_scope() as scope:
            tracked = scope.resolve(Tracked)
            raise RuntimeError('boom')
    assert tracked.disposed


@pytest.mark.asyncio
async def test_async_exit_awaits_cleanup_before_disposing():
    """__aexit__ must await async cleanup first, then run sync disposal."""
    order = []

    class AsyncResource:
        async def __aexit__(self, *exc):
            order.append('aexit')

        def dispose(self):
            order.append('dispose')

    services = ServiceCollection()
    services.add_scoped(AsyncResource)
    provider = services.build_provider()

    async with provider.create_scope() as scope:
        scope.resolve(AsyncResource)

    assert order == ['aexit', 'dispose']
