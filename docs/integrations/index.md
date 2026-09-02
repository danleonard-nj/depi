# Framework integrations

Four adapters, each its own distribution:

| Framework | Install | Import | Guide |
| --- | --- | --- | --- |
| Flask | `pip install pydepi-flask` | `depi_flask` | [Flask](flask.md) |
| Quart | `pip install pydepi-quart` | `depi_quart` | [Quart](quart.md) |
| FastAPI | `pip install pydepi-fastapi` | `depi_fastapi` | [FastAPI](fastapi.md) |
| Django | `pip install pydepi-django` | `depi_django` | [Django](django.md) |

Each adapter depends on `pydepi` and its framework, and on nothing else.
`pip install pydepi[flask]` is accepted as an alias, but the distribution name
is the accurate form — these are separately versioned packages, not extras of
core.

There is no aiohttp adapter. It is [on the backlog](https://github.com/danleonard-nj/depi/blob/main/BACKLOG.md),
not shipped.

## What every adapter does

Three things, once per request:

1. open a [`ServiceScope`][depi.ServiceScope] from the provider,
2. bind it to the ambient context ([`set_current_scope`][depi.set_current_scope]),
   so `current_scope()` works anywhere in the request,
3. dispose it when the request ends — running scoped
   [disposal](../concepts/disposal.md).

Everything above that — authentication, response shaping, blueprint conventions
— is the application's, not the adapter's. The adapter is the thin piece at the
HTTP boundary in the [Architecture](../architecture/index.md) picture.

## Two injection modes

### Provider injection (default)

The request scope is passed to the view; you resolve from it explicitly.

```python
@app.route("/users/<user_id>")
@injector.inject
def get_user(user_id, provider):
    return provider.resolve(UserService).get(user_id)
```

Works on every adapter. Rename the injected argument with
`param_name="container"` if that fits your conventions better.

### Autowire (opt-in)

Parameters annotated with registered types are resolved and passed individually;
parameters the container does not know about are left for the framework (URL
converters, query args).

```python
injector = FlaskInjector(provider, autowire=True)

@app.route("/users/<user_id>")
@injector.inject
def get_user(user_id, users: UserService):   # user_id stays Flask's
    return users.get(user_id)
```

Available on Flask, Quart, and Django. **Not on FastAPI** — FastAPI reads the
endpoint signature to build request parsing and the OpenAPI schema, and rejects
any annotation it cannot treat as a Pydantic field. FastAPI uses `Depends`
instead; see [FastAPI](fastapi.md).

## Behavioural contract

Every adapter is tested against the same service set and asserts the same
behaviour:

- the scope is injected (or autowired) into the view,
- a scoped service is the same instance within one request,
- a scoped service differs across requests,
- a singleton is shared across requests,
- the scope is disposed when the request ends,
- no scope leaks to the next request on a reused worker thread.

## Calling a view in a test

A view wrapped with `@injector.inject` is directly callable — pass the scope,
and only the arguments you omit are filled from the ambient context:

```python
with provider.create_scope() as scope:
    body = get_user("user-1", provider=scope)
```
