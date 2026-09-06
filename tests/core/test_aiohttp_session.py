"""
Managing an aiohttp ClientSession through depi.

``aiohttp.ClientSession`` cannot be constructed at module import time: it binds
to the running event loop and must be closed before that loop goes away. Without
a container the usual workaround is a module-level ``session = None`` populated
in an ASGI startup hook and closed on shutdown.

depi replaces that with an async singleton factory -- but only if resolution
never quietly moves construction onto a different loop than the one the app
runs on. These tests pin that down:

- ``build_async`` / ``resolve_async`` build the session on the caller's loop,
- the singleton is shared across both resolution paths like any other,
- a scoped session is closed by async scope exit,
- and the one path that *does* disturb the loop -- the synchronous
  ``build_provider`` eagerly running an async factory while a loop is already
  running -- is called out, so the async docs' guidance stays honest.
"""

import asyncio

import pytest

from depi import AsyncFactoryError, ServiceCollection, ServiceProvider

aiohttp = pytest.importorskip('aiohttp')


def _session_collection() -> ServiceCollection:
    async def make_session(_) -> aiohttp.ClientSession:
        return aiohttp.ClientSession()

    services = ServiceCollection()
    services.add_singleton(aiohttp.ClientSession, factory=make_session)
    return services


@pytest.mark.asyncio
async def test_build_async_creates_the_session_on_the_running_loop():
    """The lifespan-startup pattern: build the provider inside the app's loop."""
    provider = ServiceProvider(_session_collection())
    await provider.build_async()

    session = provider.resolve(aiohttp.ClientSession)
    try:
        assert not session.closed
        assert session._loop is asyncio.get_running_loop()
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_lazy_singleton_is_built_on_the_loop_that_first_resolves_it():
    """No build step: the first ``resolve_async`` in a request constructs it."""
    provider = ServiceProvider(_session_collection())

    session = await provider.resolve_async(aiohttp.ClientSession)
    try:
        assert session._loop is asyncio.get_running_loop()
        # One cache backs both paths, so the session is a true singleton.
        assert provider.resolve(aiohttp.ClientSession) is session
        assert await provider.resolve_async(aiohttp.ClientSession) is session
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_sync_resolve_of_an_unbuilt_async_session_is_rejected():
    """A plain ``resolve()`` must not hand back an un-awaited coroutine."""
    provider = ServiceProvider(_session_collection())

    with pytest.raises(AsyncFactoryError, match='resolve_async'):
        provider.resolve(aiohttp.ClientSession)


@pytest.mark.asyncio
async def test_scoped_session_is_closed_by_async_scope_exit():
    """
    The per-request-session variant: a scoped wrapper owns the ClientSession and
    closes it in ``__aexit__``, which the async web adapters route request
    teardown through.
    """
    class RequestHttp:
        def __init__(self):
            self.session = aiohttp.ClientSession()

        async def __aexit__(self, *exc):
            await self.session.close()

    services = ServiceCollection()
    services.add_scoped(RequestHttp)
    provider = services.build_provider()

    async with provider.create_scope() as scope:
        http = await scope.resolve_async(RequestHttp)
        assert not http.session.closed
        assert http.session._loop is asyncio.get_running_loop()

    assert http.session.closed


@pytest.mark.asyncio
async def test_sync_build_provider_under_a_running_loop_moves_construction_off_it():
    """
    Why ``build_async`` / ``resolve_async`` and not ``build_provider`` under
    ASGI: the synchronous build eagerly runs the async factory, and when a loop
    is already running it offloads that to a worker thread with its own loop. A
    ClientSession built there would be bound to a loop that closes moments later.
    This pins the hazard rather than the fix.
    """
    captured = {}

    async def make_session(_) -> aiohttp.ClientSession:
        # Record the loop we would have bound to; construct nothing real.
        captured['loop'] = asyncio.get_running_loop()
        return object()

    services = ServiceCollection()
    services.add_singleton(aiohttp.ClientSession, factory=make_session)

    services.build_provider()  # synchronous build, from inside this running loop

    assert captured['loop'] is not asyncio.get_running_loop()
