# Quart

```bash
pip install pydepi-quart
```

Requires `quart>=0.18`. Import as `depi_quart`.

Quart is the async counterpart to the [Flask adapter](flask.md) — same two
injection modes, same `param_name` option, async views.

## Setup

```python
from quart import Quart
from depi_quart import QuartInjector

from composition import build_container

app = Quart(__name__)
injector = QuartInjector(build_container())
injector.setup(app)
```

`setup(app)` installs async `before_request` / `teardown_request` hooks.

## Provider injection

```python
@app.route("/users/<user_id>")
@injector.inject
async def get_user(user_id, provider):
    users = await provider.resolve_async(UserService)
    return await users.get(user_id)
```

`provider` is the request scope. Use `resolve_async` for
[async factories](../concepts/async.md); `resolve` also works for anything
synchronous.

Rename the argument with `param_name`:

```python
injector = QuartInjector(build_container(), param_name="container")

@app.route("/users/<user_id>")
@injector.inject
async def get_user(user_id, container):
    users = await container.resolve_async(UserService)
    return await users.get(user_id)
```

## Autowire

```python
injector = QuartInjector(build_container(), autowire=True)

@app.route("/echo/<key>")
@injector.inject
async def echo(key, greeter: Greeter):     # key stays Quart's
    return {"key": key, "message": greeter.greet()}
```

## Lifecycle and scope behaviour

- Scope opened in `before_request`, disposed in `teardown_request`.
- Disposal goes through [`ServiceScope.__aexit__`][depi.ServiceScope]: scoped
  instances with an `async def __aexit__` get **awaited** cleanup before the
  synchronous `dispose()` runs. This is the reason to use Quart over Flask for
  async resources — see [Releasing resources](../guides/resource-teardown.md).
- Scoped / singleton / transient behaviour is otherwise identical to every other
  adapter.

## Decorator composition

`inject` uses `functools.wraps`, so it slots into a decorator stack without the
outer layers losing the view's identity — the same property the Flask adapter
has.

## API

[`QuartInjector`](../api/quart.md)
