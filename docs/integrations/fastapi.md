# FastAPI

```bash
pip install pydepi-fastapi
```

Requires `fastapi>=0.100`. Import as `depi_fastapi`.

FastAPI derives request parsing and the OpenAPI schema from the endpoint
signature. So this adapter does **not** touch signatures: injection is through
`Depends`, and `depi` stays out of the schema entirely.

## Setup

```python
from fastapi import Depends, FastAPI
from depi_fastapi import FastAPIInjector

from composition import build_container

app = FastAPI()
injector = FastAPIInjector(build_container())
injector.setup(app)
```

`setup(app)` adds a **pure ASGI middleware** (not an `@app.middleware("http")`
function). Two reasons:

- the scope contextvar is set in the same context the endpoint coroutine runs
  in, so `current_scope()` works inside the endpoint,
- disposal happens after the response body is sent, not when the handler
  returns.

## Injecting the scope

```python
@app.get("/users/{user_id}")
async def get_user(user_id: str, scope=Depends(injector.get_scope)):
    return scope.resolve(UserService).get(user_id)
```

[`get_scope`][depi_fastapi.FastAPIInjector.get_scope] returns the request scope;
`Depends` wires it in the way FastAPI expects. `user_id` is a normal path
parameter — it appears in the OpenAPI schema, `scope` does not.

Use `await scope.resolve_async(...)` for async factories.

## Autowire and `inject` are not available

```python
FastAPIInjector(provider, autowire=True)
# ValueError: FastAPIInjector does not support autowire=True ...

injector.inject(view)
# NotImplementedError: ... Use Depends(injector.get_scope) ...
```

FastAPI raises `FastAPIError` at *decoration* time for any parameter annotation
it cannot treat as a Pydantic field. Hiding a service parameter would mean
rewriting `__signature__` before FastAPI sees the endpoint, which is fragile
across FastAPI releases. The constraint is asserted by a test, so a future
FastAPI that relaxes it would surface as a failure rather than silent breakage.

`Depends(injector.get_scope)` is the supported path and has none of that
fragility.

## Lifecycle and scope behaviour

- Scope opened by the ASGI middleware for `http` and `websocket` requests;
  lifespan and other ASGI traffic pass through untouched.
- Disposal runs through `__aexit__` after the response body is sent, so async
  cleanup on scoped instances is awaited — even when the endpoint raised.
- Scoped / singleton / transient behaviour matches the other adapters.

## `depi` vs FastAPI's own `Depends`

They coexist. FastAPI `Depends` is good at request-derived values — the current
user from a token, pagination params, a validated body. `depi` is good at the
application's service graph — repositories, domain services, clients — wired
once in a composition root. Resolve services from the `depi` scope; keep
request-shaped dependencies in FastAPI `Depends`. See the
[comparison](../comparison/index.md#framework-native-di-fastapi-depends).

## API

[`FastAPIInjector`](../api/fastapi.md)
