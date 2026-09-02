"""
Async factory resolution across every code path.

Regression coverage for a gap found during the package split: the guard that
turns "you resolved an async factory synchronously" into a clear RuntimeError
lived only on ServiceProvider.resolve. ServiceScope.resolve had no guard, so a
scoped or transient async factory resolved through a scope returned an
un-awaited coroutine instead — and a scope is what every web integration
resolves through, so this only ever surfaced inside a request, far from the
cause.
"""

import inspect

import pytest

from depi import ServiceCollection


class Client:
    def __init__(self):
        self.ready = True


async def async_factory(provider) -> Client:
    return Client()


def sync_factory(provider) -> Client:
    return Client()


@pytest.mark.parametrize('register', ['add_transient', 'add_scoped'])
def test_sync_resolve_through_a_scope_rejects_an_async_factory(register):
    collection = ServiceCollection()
    getattr(collection, register)(Client, factory=async_factory)
    scope = collection.build_provider().create_scope()

    with pytest.raises(RuntimeError, match='resolve_async'):
        scope.resolve(Client)


def test_sync_resolve_through_the_provider_rejects_an_async_factory():
    collection = ServiceCollection()
    collection.add_transient(Client, factory=async_factory)

    with pytest.raises(RuntimeError, match='resolve_async'):
        collection.build_provider().resolve(Client)


@pytest.mark.parametrize('register', ['add_transient', 'add_scoped'])
@pytest.mark.asyncio
async def test_async_resolve_through_a_scope_works(register):
    collection = ServiceCollection()
    getattr(collection, register)(Client, factory=async_factory)
    scope = collection.build_provider().create_scope()

    resolved = await scope.resolve_async(Client)
    assert isinstance(resolved, Client)
    assert resolved.ready


@pytest.mark.parametrize('register', ['add_transient', 'add_scoped'])
def test_sync_factories_are_untouched_by_the_guard(register):
    collection = ServiceCollection()
    getattr(collection, register)(Client, factory=sync_factory)
    scope = collection.build_provider().create_scope()

    resolved = scope.resolve(Client)
    assert isinstance(resolved, Client)
    assert not inspect.isawaitable(resolved)


def test_scoped_async_factory_is_cached_for_the_life_of_the_scope():
    collection = ServiceCollection()
    collection.add_scoped(Client, factory=async_factory)
    scope = collection.build_provider().create_scope()

    import asyncio

    async def resolve_twice():
        return await scope.resolve_async(Client), await scope.resolve_async(Client)

    first, second = asyncio.run(resolve_twice())
    assert first is second
