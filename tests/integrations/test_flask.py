"""Flask integration tests."""

import pytest

from depi import NoActiveScopeError, current_scope
from depi_flask import FlaskInjector

from .conftest import DISPOSED, Config, Disposable, Ephemeral, Greeter, RequestId

pytestmark = pytest.mark.integration

flask = pytest.importorskip('flask')


@pytest.fixture
def app():
    application = flask.Flask(__name__)
    application.config['TESTING'] = True
    return application


def test_scope_injected_as_provider_kwarg(app, provider):
    injector = FlaskInjector(provider)
    injector.setup(app)

    @app.route('/greet')
    @injector.inject
    def greet(provider):
        return {'message': provider.resolve(Greeter).greet()}

    assert app.test_client().get('/greet').json == {'message': 'hello from config'}


def test_param_name_is_configurable(app, provider):
    """The MetaBlueprint style names it `container`; that must not require a fork."""
    injector = FlaskInjector(provider, param_name='container')
    injector.setup(app)

    @app.route('/greet')
    @injector.inject
    def greet(container):
        return {'message': container.resolve(Greeter).greet()}

    assert app.test_client().get('/greet').json == {'message': 'hello from config'}


def test_autowire_resolves_annotated_parameters(app, provider):
    injector = FlaskInjector(provider, autowire=True)
    injector.setup(app)

    @app.route('/greet')
    @injector.inject
    def greet(greeter: Greeter):
        return {'message': greeter.greet()}

    assert app.test_client().get('/greet').json == {'message': 'hello from config'}


def test_autowire_leaves_url_parameters_to_flask(app, provider):
    """Unregistered annotations belong to the framework, not to depi."""
    injector = FlaskInjector(provider, autowire=True)
    injector.setup(app)

    @app.route('/echo/<key>')
    @injector.inject
    def echo(key: str, greeter: Greeter):
        return {'key': key, 'message': greeter.greet()}

    body = app.test_client().get('/echo/abc').json
    assert body == {'key': 'abc', 'message': 'hello from config'}


def test_scoped_instance_is_shared_within_a_request(app, provider):
    injector = FlaskInjector(provider)
    injector.setup(app)

    @app.route('/scoped')
    @injector.inject
    def scoped(provider):
        return {'first': provider.resolve(RequestId).id,
                'second': provider.resolve(RequestId).id}

    body = app.test_client().get('/scoped').json
    assert body['first'] == body['second']


def test_scoped_instance_differs_across_requests(app, provider):
    injector = FlaskInjector(provider)
    injector.setup(app)

    @app.route('/scoped')
    @injector.inject
    def scoped(provider):
        return {'id': provider.resolve(RequestId).id}

    client = app.test_client()
    assert client.get('/scoped').json['id'] != client.get('/scoped').json['id']


def test_singleton_is_shared_across_requests(app, provider):
    injector = FlaskInjector(provider)
    injector.setup(app)

    @app.route('/singleton')
    @injector.inject
    def singleton(provider):
        return {'id': id(provider.resolve(Config))}

    client = app.test_client()
    assert client.get('/singleton').json['id'] == client.get('/singleton').json['id']


def test_transient_is_new_each_resolve(app, provider):
    injector = FlaskInjector(provider)
    injector.setup(app)

    @app.route('/transient')
    @injector.inject
    def transient(provider):
        return {'first': provider.resolve(Ephemeral).id,
                'second': provider.resolve(Ephemeral).id}

    body = app.test_client().get('/transient').json
    assert body['first'] != body['second']


def test_scope_is_disposed_after_the_request(app, provider):
    injector = FlaskInjector(provider)
    injector.setup(app)

    @app.route('/disposable')
    @injector.inject
    def disposable(provider):
        return {'id': provider.resolve(Disposable).id}

    resolved = app.test_client().get('/disposable').json['id']
    assert DISPOSED == [resolved]


def test_scope_does_not_leak_between_requests_on_a_reused_thread(app, provider):
    """
    Werkzeug reuses worker threads, and a contextvar set without a matching
    reset would survive into the next request served by that thread.
    """
    injector = FlaskInjector(provider)
    injector.setup(app)

    @app.route('/ok')
    @injector.inject
    def ok(provider):
        return {'ok': True}

    client = app.test_client()
    client.get('/ok')
    with pytest.raises(NoActiveScopeError):
        current_scope()


def test_current_scope_raises_outside_a_request(provider):
    FlaskInjector(provider)
    with pytest.raises(NoActiveScopeError):
        current_scope()


def test_inject_preserves_function_identity(app, provider):
    """
    The decorator has to compose inside a stack (route, auth, response handler)
    without the outer layers losing the view's name.
    """
    injector = FlaskInjector(provider)

    @injector.inject
    def my_view(provider):
        """Original docstring."""

    assert my_view.__name__ == 'my_view'
    assert my_view.__doc__ == 'Original docstring.'
    assert my_view.__wrapped__.__name__ == 'my_view'


def test_explicitly_passed_scope_wins(app, provider):
    """Lets a view be called directly from a test with a hand-built scope."""
    injector = FlaskInjector(provider)

    @injector.inject
    def view(provider):
        return provider.resolve(Greeter).greet()

    with provider.create_scope() as scope:
        assert view(provider=scope) == 'hello from config'


# --------------------------------------------------------------------------
# Request lifecycle under failure and concurrency
# --------------------------------------------------------------------------

def test_scope_is_disposed_when_the_view_raises(app, provider):
    """Disposal happens in teardown_request, so a failing view still cleans up."""
    injector = FlaskInjector(provider)
    injector.setup(app)

    @app.route('/boom')
    @injector.inject
    def boom(provider):
        provider.resolve(Disposable)
        raise RuntimeError('handler failed')

    try:
        app.test_client().get('/boom')
    except RuntimeError:
        pass

    assert len(DISPOSED) == 1
    with pytest.raises(NoActiveScopeError):
        current_scope()


def test_unmatched_route_does_not_break_teardown(app, provider):
    """teardown_request runs for a 404 too; popping absent keys must be safe."""
    injector = FlaskInjector(provider)
    injector.setup(app)

    assert app.test_client().get('/no-such-route').status_code == 404
    assert DISPOSED == []


def test_concurrent_requests_get_separate_scopes(app, provider):
    """
    Werkzeug serves requests on a thread pool. Each must see its own scope, and
    none may observe another's.
    """
    import threading

    injector = FlaskInjector(provider)
    injector.setup(app)

    @app.route('/id')
    @injector.inject
    def ident(provider):
        return {'id': provider.resolve(RequestId).id}

    seen = []

    def hit():
        with app.test_client() as client:
            seen.append(client.get('/id').json['id'])

    threads = [threading.Thread(target=hit) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(seen) == 8
    assert len(set(seen)) == 8, 'threads shared a scope'


def test_autowire_ignores_variadic_parameters(app, provider):
    injector = FlaskInjector(provider, autowire=True)
    injector.setup(app)

    @app.route('/kw/<key>')
    @injector.inject
    def kw(key, greeter: Greeter, **extra):
        return {'key': key, 'message': greeter.greet(), 'extra': sorted(extra)}

    assert app.test_client().get('/kw/abc').json == {
        'key': 'abc', 'message': 'hello from config', 'extra': []}


def test_autowire_lets_the_caller_override_a_service(provider):
    """Makes an autowired view unit-testable with a stub, without a request."""
    injector = FlaskInjector(provider, autowire=True)

    @injector.inject
    def view(greeter: Greeter):
        return greeter

    class StubGreeter:
        def greet(self):
            return 'stubbed'

    stub = StubGreeter()
    assert view(greeter=stub) is stub
