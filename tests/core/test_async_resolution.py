"""
Async resolution paths.

`resolve_async` and `build_async` are a separate implementation from their
synchronous counterparts, so the guarantees the sync side is tested for have to
be asserted here too rather than assumed to carry over.
"""

import pytest

from depi import (
    Lifetime,
    ScopeRequiredError,
    ServiceCollection,
    ServiceProvider,
    UnregisteredDependencyError,
)


class Config:
    def __init__(self):
        self.name = 'config'


class Client:
    def __init__(self, config: Config):
        self.config = config


class Scoped:
    pass


class Unregistered:
    pass


# --------------------------------------------------------------------------
# resolve_async
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_async_singleton_is_cached_across_calls():
    services = ServiceCollection()
    services.add_singleton(Config)
    provider = services.build_provider()

    first = await provider.resolve_async(Config)
    second = await provider.resolve_async(Config)
    assert first is second


@pytest.mark.asyncio
async def test_async_resolution_returns_the_prebuilt_instance():
    """An instance registered up front must be handed back, not reconstructed."""
    instance = Config()
    services = ServiceCollection()
    services.add_singleton(Config, instance=instance)
    provider = services.build_provider()

    assert await provider.resolve_async(Config) is instance


@pytest.mark.asyncio
async def test_async_singleton_matches_its_sync_counterpart():
    services = ServiceCollection()
    services.add_singleton(Config)
    provider = services.build_provider()

    assert await provider.resolve_async(Config) is provider.resolve(Config)


@pytest.mark.asyncio
async def test_async_constructor_injection_resolves_dependencies():
    services = ServiceCollection()
    services.add_singleton(Config)
    services.add_transient(Client)
    provider = services.build_provider()

    client = await provider.resolve_async(Client)
    assert client.config.name == 'config'


@pytest.mark.asyncio
async def test_async_transient_is_new_each_time():
    services = ServiceCollection()
    services.add_singleton(Config)
    services.add_transient(Client)
    provider = services.build_provider()

    assert await provider.resolve_async(Client) is not await provider.resolve_async(Client)


@pytest.mark.asyncio
async def test_scoped_without_a_scope_raises_from_the_async_path_too():
    """The sync path guards this; the async path must not be laxer."""
    services = ServiceCollection()
    services.add_scoped(Scoped)
    provider = services.build_provider()

    with pytest.raises(ScopeRequiredError, match='requires a scope'):
        await provider.resolve_async(Scoped)


@pytest.mark.asyncio
async def test_unregistered_type_raises_from_the_async_path_too():
    provider = ServiceCollection().build_provider()

    with pytest.raises(UnregisteredDependencyError):
        await provider.resolve_async(Unregistered)


@pytest.mark.asyncio
async def test_unknown_lifetime_is_reported_from_the_async_path():
    from depi import UnknownLifetimeError

    services = ServiceCollection()
    services.add_singleton(Config)
    provider = services.build_provider()

    provider._get_registered_dependency(Config).lifetime = 'nonsense'
    with pytest.raises(UnknownLifetimeError, match='nonsense'):
        await provider.resolve_async(Config)


# --------------------------------------------------------------------------
# build_async
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_build_async_constructs_eager_and_factory_singletons():
    built = []

    async def async_factory(provider) -> Client:
        built.append('factory ran')
        return Client(provider.resolve(Config))

    services = ServiceCollection()
    services.add_singleton(Config)
    services.add_singleton(Client, factory=async_factory)

    provider = ServiceProvider(services)
    await provider.build_async()

    assert built == ['factory ran'], 'async factory was not awaited during build'
    assert isinstance(provider.resolve(Client), Client)


@pytest.mark.asyncio
async def test_build_async_is_idempotent_for_already_built_singletons():
    calls = []

    async def async_factory(provider) -> Config:
        calls.append(1)
        return Config()

    services = ServiceCollection()
    services.add_singleton(Config, factory=async_factory)

    provider = ServiceProvider(services)
    await provider.build_async()
    await provider.build_async()

    assert len(calls) == 1, 'build_async reconstructed an existing singleton'


# --------------------------------------------------------------------------
# Registration surface
# --------------------------------------------------------------------------

def test_add_defaults_to_transient():
    services = ServiceCollection()
    services.add(Config)
    provider = services.build_provider()

    assert provider.resolve(Config) is not provider.resolve(Config)


def test_add_accepts_an_explicit_lifetime():
    services = ServiceCollection()
    services.add(Config, lifetime=Lifetime.Singleton)
    provider = services.build_provider()

    assert provider.resolve(Config) is provider.resolve(Config)


def test_scope_reports_registration_the_same_way_the_provider_does():
    services = ServiceCollection()
    services.add_scoped(Scoped)
    provider = services.build_provider()
    scope = provider.create_scope()

    assert scope.is_registered(Scoped) is provider.is_registered(Scoped) is True
    assert scope.is_registered(Unregistered) is provider.is_registered(Unregistered) is False


@pytest.mark.asyncio
async def test_concurrent_async_resolution_creates_one_singleton():
    """
    Lazy singleton creation is guarded by a per-type asyncio.Lock. Contending
    coroutines must find the instance already built rather than each building
    their own.
    """
    import asyncio

    constructed = []

    class SlowSingleton:
        def __init__(self):
            constructed.append(1)

    async def slow_factory(provider) -> SlowSingleton:
        await asyncio.sleep(0.01)      # hold the lock long enough to contend
        return SlowSingleton()

    services = ServiceCollection()
    services.add_singleton(SlowSingleton, factory=slow_factory)
    provider = services.build_provider()

    results = await asyncio.gather(
        *(provider.resolve_async(SlowSingleton) for _ in range(10))
    )

    assert len(constructed) == 1, f'built {len(constructed)} times under contention'
    assert all(r is results[0] for r in results)


@pytest.mark.asyncio
async def test_build_async_constructs_eager_singletons_without_a_factory():
    """`eager_all` marks plain singletons for construction during build."""
    constructed = []

    class Eager:
        def __init__(self):
            constructed.append(1)

    services = ServiceCollection()
    services.add_singleton(Eager)
    for registration in services.get_container().values():
        registration.eager = True

    provider = ServiceProvider(services)
    await provider.build_async()

    assert constructed == [1], 'eager singleton was not built by build_async'
    assert provider.resolve(Eager) is provider.resolve(Eager)
