# Flask

```bash
pip install pydepi-flask
```

Requires `flask>=2.2`. Import as `depi_flask`.

## Setup

```python
from flask import Flask
from depi import ServiceCollection
from depi_flask import FlaskInjector

from composition import build_container

app = Flask(__name__)
injector = FlaskInjector(build_container())
injector.setup(app)
```

[`setup(app)`][depi.integration.BaseInjector.setup] installs a `before_request`
hook that opens a [`ServiceScope`][depi.ServiceScope] and a `teardown_request`
hook that disposes it.

## Provider injection

```python
@app.route("/users/<user_id>")
@injector.inject
def get_user(user_id, provider):
    return provider.resolve(UserService).get(user_id)
```

`provider` is the request scope. `user_id` comes from the URL rule as normal.
Rename the injected argument:

```python
injector = FlaskInjector(build_container(), param_name="container")

@app.route("/users/<user_id>")
@injector.inject
def get_user(user_id, container):
    return container.resolve(UserService).get(user_id)
```

## Autowire

```python
injector = FlaskInjector(build_container(), autowire=True)
injector.setup(app)

@app.route("/users/<user_id>")
@injector.inject
def get_user(user_id, users: UserService):
    return users.get(user_id)
```

`UserService` is registered, so it is resolved and passed. `user_id` is not a
registered type, so Flask fills it from the URL. Signature inspection happens
once at decoration time, not per request.

## Lifecycle and scope behaviour

- **Scope opened** in `before_request`, **disposed** in `teardown_request`
  (which runs even if the view raises).
- **Scoped** services: one instance per request, shared across every `resolve`
  in that request.
- **Singletons**: shared across all requests.
- **Transients**: new on every `resolve`.
- Disposal calls `dispose()` on scoped instances. `__aexit__` is **not** awaited
  — Flask is synchronous; use Quart for async cleanup.

The scope and its contextvar token are stored on `flask.g`, and teardown resets
the contextvar. Werkzeug reuses worker threads, so a contextvar left set would
leak into the next request on that thread — the reset prevents it. This is
covered by a regression test.

## Reaching the scope elsewhere

```python
from depi import current_scope

def some_helper():
    return current_scope().resolve(AuditLog)
```

Valid anywhere inside a request. Outside one it raises
[`NoActiveScopeError`][depi.NoActiveScopeError].

## Where framework code ends

`injector.setup(app)` and the `@injector.inject` decorator are the entire
surface. The view resolves a service and returns a response; the service knows
nothing about Flask. Keep request parsing and status codes in the view — see
[Architecture](../architecture/index.md).

## Decorator composition

`inject` is built with `functools.wraps`, so it composes inside a decorator
stack (route registration, auth, response handling) without the outer layers
losing the view's name or docstring.

## API

[`FlaskInjector`](../api/flask.md)
