"""Quart integration tests."""

import pytest

from depi import NoActiveScopeError, current_scope
from depi_quart import QuartInjector

from .conftest import DISPOSED, Config, Disposable, Greeter, RequestId

pytestmark = pytest.mark.integration

quart = pytest.importorskip('quart')


@pytest.fixture
def app():
    application = quart.Quart(__name__)
    application.config['TESTING'] = True
    return application


@pytest.mark.asyncio
async def test_scope_injected_as_provider_kwarg(app, provider):
    injector = QuartInjector(provider)
    injector.setup(app)

    @app.route('/greet')
    @injector.inject
    async def greet(provider):
        return {'message': provider.resolve(Greeter).greet()}

    response = await app.test_client().get('/greet')
    assert await response.get_json() == {'message': 'hello from config'}


@pytest.mark.asyncio
async def test_param_name_is_configurable(app, provider):
    """Mirrors the MetaBlueprint convention of naming the scope `container`."""
    injector = QuartInjector(provider, param_name='container')
    injector.setup(app)

    @app.route('/greet')
    @injector.inject
    async def greet(container):
        return {'message': container.resolve(Greeter).greet()}

    response = await app.test_client().get('/greet')
    assert await response.get_json() == {'message': 'hello from config'}


@pytest.mark.asyncio
async def test_autowire_resolves_annotated_parameters(app, provider):
    injector = QuartInjector(provider, autowire=True)
    injector.setup(app)

    @app.route('/echo/<key>')
    @injector.inject
    async def echo(key, greeter: Greeter):
        return {'key': key, 'message': greeter.greet()}

    response = await app.test_client().get('/echo/abc')
    assert await response.get_json() == {'key': 'abc', 'message': 'hello from config'}


@pytest.mark.asyncio
async def test_resolve_async_works_under_a_request_scope(app, provider):
    injector = QuartInjector(provider)
    injector.setup(app)

    @app.route('/greet')
    @injector.inject
    async def greet(provider):
        greeter = await provider.resolve_async(Greeter)
        return {'message': greeter.greet()}

    response = await app.test_client().get('/greet')
    assert await response.get_json() == {'message': 'hello from config'}


@pytest.mark.asyncio
async def test_scoped_instance_is_shared_within_a_request(app, provider):
    injector = QuartInjector(provider)
    injector.setup(app)

    @app.route('/scoped')
    @injector.inject
    async def scoped(provider):
        return {'first': provider.resolve(RequestId).id,
                'second': provider.resolve(RequestId).id}

    body = await (await app.test_client().get('/scoped')).get_json()
    assert body['first'] == body['second']


@pytest.mark.asyncio
async def test_scoped_instance_differs_across_requests(app, provider):
    injector = QuartInjector(provider)
    injector.setup(app)

    @app.route('/scoped')
    @injector.inject
    async def scoped(provider):
        return {'id': provider.resolve(RequestId).id}

    client = app.test_client()
    first = await (await client.get('/scoped')).get_json()
    second = await (await client.get('/scoped')).get_json()
    assert first['id'] != second['id']


@pytest.mark.asyncio
async def test_singleton_is_shared_across_requests(app, provider):
    injector = QuartInjector(provider)
    injector.setup(app)

    @app.route('/singleton')
    @injector.inject
    async def singleton(provider):
        return {'id': id(provider.resolve(Config))}

    client = app.test_client()
    first = await (await client.get('/singleton')).get_json()
    second = await (await client.get('/singleton')).get_json()
    assert first['id'] == second['id']


@pytest.mark.asyncio
async def test_scope_is_disposed_after_the_request(app, provider):
    injector = QuartInjector(provider)
    injector.setup(app)

    @app.route('/disposable')
    @injector.inject
    async def disposable(provider):
        return {'id': provider.resolve(Disposable).id}

    body = await (await app.test_client().get('/disposable')).get_json()
    assert DISPOSED == [body['id']]


@pytest.mark.asyncio
async def test_async_cleanup_hooks_are_awaited_on_disposal(app, provider, services):
    """Disposal goes through __aexit__, so async cleanup gets a chance to run."""
    awaited = []

    class AsyncResource:
        def __init__(self):
            self.name = 'resource'

        async def __aexit__(self, exc_type, exc, tb):
            awaited.append(self.name)

    services.add_scoped(AsyncResource)
    built = services.build_provider()

    injector = QuartInjector(built)
    injector.setup(app)

    @app.route('/async-resource')
    @injector.inject
    async def async_resource(provider):
        return {'name': provider.resolve(AsyncResource).name}

    await app.test_client().get('/async-resource')
    assert awaited == ['resource']


@pytest.mark.asyncio
async def test_scope_does_not_leak_after_the_request(app, provider):
    injector = QuartInjector(provider)
    injector.setup(app)

    @app.route('/ok')
    @injector.inject
    async def ok(provider):
        return {'ok': True}

    await app.test_client().get('/ok')
    with pytest.raises(NoActiveScopeError):
        current_scope()


def test_inject_preserves_function_identity(provider):
    injector = QuartInjector(provider)

    @injector.inject
    async def my_view(provider):
        """Original docstring."""

    assert my_view.__name__ == 'my_view'
    assert my_view.__doc__ == 'Original docstring.'
