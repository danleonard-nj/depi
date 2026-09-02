"""
Django integration tests.

Django resolves middleware from a dotted path at startup and owns the URLconf,
so the provider and views are built once at module level here -- the same shape
a real project has, where the provider is built in AppConfig.ready().
"""

import pytest

from depi import NoActiveScopeError, ServiceCollection, current_scope

from .conftest import Config, Disposable, Ephemeral, Greeter, RequestId

pytestmark = pytest.mark.integration

django = pytest.importorskip('django')

from django.conf import settings  # noqa: E402

if not settings.configured:
    settings.configure(
        DEBUG=True,
        SECRET_KEY='depi-test-secret',
        ROOT_URLCONF=__name__,
        ALLOWED_HOSTS=['*'],
        INSTALLED_APPS=['django.contrib.contenttypes', 'django.contrib.auth'],
        MIDDLEWARE=['depi_django.DepiScopeMiddleware'],
        USE_TZ=True,
    )
    django.setup()

from django.http import JsonResponse  # noqa: E402
from django.test import Client  # noqa: E402
from django.urls import path  # noqa: E402

from depi_django import (  # noqa: E402
    DepiScopeMiddleware,
    DjangoInjector,
    NoInjectorRegisteredError,
)

# Disposal tracking is per-instance here rather than via the shared conftest
# list, because these services are registered once for the whole module.
DISPOSED: list = []


class TrackedDisposable(Disposable):
    def dispose(self):
        self.disposed = True
        DISPOSED.append(self.id)


_collection = ServiceCollection()
_collection.add_singleton(Config)
_collection.add_scoped(RequestId)
_collection.add_scoped(TrackedDisposable)
_collection.add_transient(Ephemeral)
_collection.add_transient(Greeter)
_provider = _collection.build_provider()

_injector = DjangoInjector(_provider)
_autowire = DjangoInjector(_provider, autowire=True)


@_injector.inject
def provider_view(request, provider):
    return JsonResponse({'message': provider.resolve(Greeter).greet()})


@_autowire.inject
def autowire_view(request, greeter: Greeter):
    return JsonResponse({'message': greeter.greet()})


@_autowire.inject
def autowire_url_arg_view(request, key, greeter: Greeter):
    return JsonResponse({'key': key, 'message': greeter.greet()})


@_injector.inject
def scoped_view(request, provider):
    return JsonResponse({'first': provider.resolve(RequestId).id,
                         'second': provider.resolve(RequestId).id,
                         'singleton': id(provider.resolve(Config))})


@_injector.inject
def disposable_view(request, provider):
    return JsonResponse({'id': provider.resolve(TrackedDisposable).id})


urlpatterns = [
    path('provider/', provider_view),
    path('autowire/', autowire_view),
    path('autowire/<str:key>/', autowire_url_arg_view),
    path('scoped/', scoped_view),
    path('disposable/', disposable_view),
]


@pytest.fixture(autouse=True)
def registered_injector():
    _injector.setup()
    DISPOSED.clear()
    yield
    import depi_django
    depi_django._active_injector = None


def test_scope_injected_as_provider_kwarg():
    response = Client().get('/provider/')
    assert response.json() == {'message': 'hello from config'}


def test_autowire_resolves_annotated_parameters():
    assert Client().get('/autowire/').json() == {'message': 'hello from config'}


def test_autowire_leaves_url_parameters_to_django():
    assert Client().get('/autowire/abc/').json() == {
        'key': 'abc', 'message': 'hello from config'}


def test_scoped_shared_within_request_and_singleton_across_requests():
    client = Client()
    first = client.get('/scoped/').json()
    second = client.get('/scoped/').json()
    assert first['first'] == first['second']
    assert first['first'] != second['first']
    assert first['singleton'] == second['singleton']


def test_scope_is_disposed_after_the_request():
    resolved = Client().get('/disposable/').json()['id']
    assert DISPOSED == [resolved]


def test_scope_does_not_leak_after_the_request():
    Client().get('/provider/')
    with pytest.raises(NoActiveScopeError):
        current_scope()


def test_middleware_without_a_registered_injector_explains_itself():
    import depi_django
    depi_django._active_injector = None

    middleware = DepiScopeMiddleware(lambda request: None)
    with pytest.raises(NoInjectorRegisteredError, match='AppConfig.ready'):
        middleware(object())


def test_middleware_matches_a_sync_get_response():
    from asgiref.sync import iscoroutinefunction
    assert not iscoroutinefunction(DepiScopeMiddleware(lambda request: None))


def test_middleware_matches_an_async_get_response():
    """Django inspects the middleware to decide whether it must adapt it."""
    from asgiref.sync import iscoroutinefunction

    async def async_get_response(request):
        return None

    assert iscoroutinefunction(DepiScopeMiddleware(async_get_response))


# --------------------------------------------------------------------------
# The async request path
#
# Django's async middleware is what runs under ASGI, and it is a separate code
# path from the sync one. Driving the middleware directly exercises it without
# standing up an ASGI server.
# --------------------------------------------------------------------------

class AsyncResource:
    """Scoped, with async cleanup, to prove __aexit__ is awaited."""

    def __init__(self):
        self.cleaned = False

    async def __aexit__(self, *exc):
        self.cleaned = True
        DISPOSED.append('aexit')


@pytest.fixture
def async_provider():
    collection = ServiceCollection()
    collection.add_singleton(Config)
    collection.add_scoped(RequestId)
    collection.add_scoped(TrackedDisposable)
    collection.add_scoped(AsyncResource)
    collection.add_transient(Greeter)
    return collection.build_provider()


@pytest.mark.asyncio
async def test_async_middleware_binds_and_disposes_a_scope(async_provider):
    DjangoInjector(async_provider).setup()
    DISPOSED.clear()

    async def get_response(request):
        scope = current_scope()
        scope.resolve(AsyncResource)
        scope.resolve(TrackedDisposable)
        return 'response'

    middleware = DepiScopeMiddleware(get_response)
    assert await middleware(object()) == 'response'

    # Async cleanup is awaited before synchronous disposal.
    assert DISPOSED[0] == 'aexit'
    assert len(DISPOSED) == 2
    with pytest.raises(NoActiveScopeError):
        current_scope()


@pytest.mark.asyncio
async def test_async_middleware_disposes_when_the_view_raises(async_provider):
    DjangoInjector(async_provider).setup()
    DISPOSED.clear()

    async def get_response(request):
        current_scope().resolve(TrackedDisposable)
        raise RuntimeError('view failed')

    middleware = DepiScopeMiddleware(get_response)
    with pytest.raises(RuntimeError, match='view failed'):
        await middleware(object())

    assert DISPOSED, 'scope was not disposed when the view raised'
    with pytest.raises(NoActiveScopeError):
        current_scope()


@pytest.mark.asyncio
async def test_concurrent_async_requests_do_not_share_a_scope(async_provider):
    """
    Each task copies the context at creation, so a scope bound inside one task
    must stay invisible to the others and survive its own awaits.
    """
    import asyncio

    DjangoInjector(async_provider).setup()
    observed = []

    async def get_response(request):
        before = current_scope()
        mine = before.resolve(RequestId)
        await asyncio.sleep(0.01)          # force the tasks to interleave
        after = current_scope()
        observed.append({
            'stable': before is after,
            'instance_stable': after.resolve(RequestId) is mine,
            'id': mine.id,
        })
        return None

    middleware = DepiScopeMiddleware(get_response)
    await asyncio.gather(*(middleware(object()) for _ in range(6)))

    assert len(observed) == 6
    assert all(o['stable'] for o in observed), 'a task lost its scope across an await'
    assert all(o['instance_stable'] for o in observed)
    assert len({o['id'] for o in observed}) == 6, 'tasks shared a scope'
    with pytest.raises(NoActiveScopeError):
        current_scope()
