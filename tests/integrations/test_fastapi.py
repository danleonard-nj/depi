"""
FastAPI integration tests.

The regression these guard against: FastAPI derives request parsing and the
OpenAPI schema from the endpoint signature, so anything depi does to a
signature shows up as a decoration-time error or a polluted schema.
"""

import pytest

from depi import NoActiveScopeError, current_scope
from depi_fastapi import FastAPIInjector

from .conftest import DISPOSED, Config, Disposable, Greeter, RequestId

pytestmark = pytest.mark.integration

fastapi = pytest.importorskip('fastapi')
from fastapi import Depends, FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture
def app():
    return FastAPI()


def test_scope_available_via_depends(app, provider):
    injector = FastAPIInjector(provider)
    injector.setup(app)

    @app.get('/greet')
    async def greet(scope=Depends(injector.get_scope)):
        return {'message': scope.resolve(Greeter).greet()}

    assert TestClient(app).get('/greet').json() == {'message': 'hello from config'}


def test_path_parameters_still_work_alongside_the_scope(app, provider):
    injector = FastAPIInjector(provider)
    injector.setup(app)

    @app.get('/echo/{key}')
    async def echo(key: str, scope=Depends(injector.get_scope)):
        return {'key': key, 'message': scope.resolve(Greeter).greet()}

    assert TestClient(app).get('/echo/abc').json() == {
        'key': 'abc', 'message': 'hello from config'}


def test_openapi_schema_does_not_leak_injected_parameters(app, provider):
    """
    The old signature-rewriting injector existed to keep services out of the
    schema. Depends() achieves the same thing without touching signatures.
    """
    injector = FastAPIInjector(provider)
    injector.setup(app)

    @app.get('/echo/{key}')
    async def echo(key: str, scope=Depends(injector.get_scope)):
        return {'key': key}

    params = app.openapi()['paths']['/echo/{key}']['get']['parameters']
    assert [p['name'] for p in params] == ['key']


def test_scoped_instance_is_shared_within_a_request(app, provider):
    injector = FastAPIInjector(provider)
    injector.setup(app)

    @app.get('/scoped')
    async def scoped(scope=Depends(injector.get_scope)):
        return {'first': scope.resolve(RequestId).id,
                'second': scope.resolve(RequestId).id}

    body = TestClient(app).get('/scoped').json()
    assert body['first'] == body['second']


def test_scoped_instance_differs_across_requests(app, provider):
    injector = FastAPIInjector(provider)
    injector.setup(app)

    @app.get('/scoped')
    async def scoped(scope=Depends(injector.get_scope)):
        return {'id': scope.resolve(RequestId).id}

    client = TestClient(app)
    assert client.get('/scoped').json()['id'] != client.get('/scoped').json()['id']


def test_singleton_is_shared_across_requests(app, provider):
    injector = FastAPIInjector(provider)
    injector.setup(app)

    @app.get('/singleton')
    async def singleton(scope=Depends(injector.get_scope)):
        return {'id': id(scope.resolve(Config))}

    client = TestClient(app)
    assert client.get('/singleton').json()['id'] == client.get('/singleton').json()['id']


def test_scope_is_disposed_after_the_response(app, provider):
    injector = FastAPIInjector(provider)
    injector.setup(app)

    @app.get('/disposable')
    async def disposable(scope=Depends(injector.get_scope)):
        return {'id': scope.resolve(Disposable).id}

    resolved = TestClient(app).get('/disposable').json()['id']
    assert DISPOSED == [resolved]


def test_scope_is_disposed_even_when_the_endpoint_raises(app, provider):
    injector = FastAPIInjector(provider)
    injector.setup(app)

    @app.get('/boom')
    async def boom(scope=Depends(injector.get_scope)):
        scope.resolve(Disposable)
        raise RuntimeError('boom')

    client = TestClient(app, raise_server_exceptions=False)
    client.get('/boom')
    assert len(DISPOSED) == 1


def test_scope_does_not_leak_after_the_request(app, provider):
    injector = FastAPIInjector(provider)
    injector.setup(app)

    @app.get('/ok')
    async def ok(scope=Depends(injector.get_scope)):
        return {'ok': True}

    TestClient(app).get('/ok')
    with pytest.raises(NoActiveScopeError):
        current_scope()


def test_non_http_asgi_traffic_passes_through(app, provider):
    """Lifespan messages must not have a request scope opened for them."""
    injector = FastAPIInjector(provider)
    injector.setup(app)

    started = []

    @app.on_event('startup')
    async def _startup():
        started.append(True)

    with TestClient(app):
        pass
    assert started == [True]
    assert DISPOSED == []


def test_middleware_accepts_app_as_a_keyword_argument(app, provider):
    """
    Starlette <= 0.27 instantiates middleware as cls(app=..., **options), with
    app passed by KEYWORD; newer Starlette passes it positionally. A middleware
    whose first parameter is named anything else breaks every FastAPI at or
    below the declared floor, and does so at request time rather than at setup.
    """
    injector = FastAPIInjector(provider)
    injector.setup(app)

    middleware_cls = app.user_middleware[0].cls
    instance = middleware_cls(app=lambda *a: None)   # must not raise
    assert instance is not None


def test_autowire_is_rejected_with_an_explanation(provider):
    with pytest.raises(ValueError, match='does not support autowire'):
        FastAPIInjector(provider, autowire=True)


def test_inject_is_rejected_with_a_pointer_to_depends(provider):
    injector = FastAPIInjector(provider)
    with pytest.raises(NotImplementedError, match='Depends'):
        injector.inject(lambda: None)


def test_fastapi_still_rejects_a_bare_service_annotation(app, provider):
    """
    The constraint that rules out autowire, asserted rather than assumed: if a
    future FastAPI makes this legal, this test fails and the design can be
    revisited.
    """
    with pytest.raises(fastapi.exceptions.FastAPIError):
        @app.get('/autowire')
        async def autowire(greeter: Greeter):
            return {}


# --------------------------------------------------------------------------
# The response lifecycle, which is why this is ASGI middleware
# --------------------------------------------------------------------------

def test_background_tasks_run_before_the_scope_is_disposed(app, provider):
    """
    The reason for pure ASGI middleware rather than an @app.middleware("http")
    decorator: background tasks run as part of the response cycle, so anything
    they captured from the scope must still be usable.
    """
    from fastapi import BackgroundTasks

    injector = FastAPIInjector(provider)
    injector.setup(app)

    observed = []

    @app.get('/bg')
    async def bg(tasks: BackgroundTasks, scope=Depends(injector.get_scope)):
        disposable = scope.resolve(Disposable)

        def after():
            observed.append(('task', disposable.disposed))

        tasks.add_task(after)
        return {'ok': True}

    TestClient(app).get('/bg')

    assert observed == [('task', False)], 'scope was torn down before the task ran'
    assert len(DISPOSED) == 1, 'scope was never disposed'


def test_scope_survives_a_streaming_response_body(app, provider):
    """Disposal must wait for the body to finish, not for the handler to return."""
    from fastapi.responses import StreamingResponse

    injector = FastAPIInjector(provider)
    injector.setup(app)

    @app.get('/stream')
    async def stream(scope=Depends(injector.get_scope)):
        disposable = scope.resolve(Disposable)

        async def chunks():
            for index in range(3):
                yield f'{index}:{disposable.disposed} '

        return StreamingResponse(chunks(), media_type='text/plain')

    body = TestClient(app).get('/stream').text

    assert body.strip() == '0:False 1:False 2:False'
    assert len(DISPOSED) == 1


def test_websocket_connections_get_their_own_scope(app, provider):
    from fastapi import WebSocket

    injector = FastAPIInjector(provider)
    injector.setup(app)

    @app.websocket('/ws')
    async def socket(websocket: WebSocket):
        await websocket.accept()
        scope = injector.get_scope()
        first = scope.resolve(RequestId)
        second = scope.resolve(RequestId)
        await websocket.send_json({'same_instance': first is second})
        await websocket.close()

    with TestClient(app).websocket_connect('/ws') as connection:
        assert connection.receive_json() == {'same_instance': True}

    with pytest.raises(NoActiveScopeError):
        current_scope()
