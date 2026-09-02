# Factories

A factory is a callable that builds a service. Register one with `factory=`:

```python
services.add_singleton(DatabaseConnection, factory=make_connection)
```

Use a factory when annotation-driven construction does not fit:

- the constructor has no annotations `depi` can read (common for third-party
  SDK clients),
- construction needs runtime information — an environment name, a feature flag,
  a value from config,
- the object needs setup after `__init__` (a connection opened, a pool warmed).

## What a factory receives

**One argument: the provider or the scope it is being resolved from.** Resolve
whatever the factory needs from it.

```python
def make_connection(provider) -> DatabaseConnection:
    config = provider.resolve(AppConfig)
    if config.env == "production":
        return PostgresConnection(config.dsn, pool_size=config.pool_size)
    return SqliteConnection(":memory:")

services.add_singleton(DatabaseConnection, factory=make_connection)
```

For a singleton or transient factory the argument is the
[`ServiceProvider`][depi.ServiceProvider]. For a scoped or transient factory
resolved inside a scope it is the [`ServiceScope`][depi.ServiceScope]. Both
expose `resolve` / `resolve_async` / `is_registered`, so a factory that only
calls those does not need to care which it got.

A factory registration has no constructor parameters as far as `depi` is
concerned, so the [`MissingAnnotationError`](errors.md) check and the
[singleton-lifetime check](dependency-graph.md#lifetime-validation) do not apply
to it. The return type annotation on the factory is not required and is not used.

## When a factory runs

| Lifetime | The factory runs... |
| --- | --- |
| singleton | once, during `build_provider()` |
| scoped | once per scope, on first resolve of that type in the scope |
| transient | on every resolve |

Because singleton factories run at build time, `resolve()` afterwards just
returns the finished object. A factory that raises will fail `build_provider()`
— which is usually what you want for misconfiguration.

## Async factories

A factory may be `async`. It must then be resolved with
[`resolve_async`][depi.ServiceProvider.resolve_async]:

```python
async def make_client(provider) -> ApiClient:
    client = ApiClient(provider.resolve(AppConfig).base_url)
    await client.connect()
    return client

services.add_singleton(ApiClient, factory=make_client)

client = await provider.resolve_async(ApiClient)
```

Singleton async factories are still constructed during `build_provider()`
(synchronously — `depi` runs the coroutine to completion), so `resolve_async`
afterwards returns the cached instance. A scoped or transient async factory runs
per resolution and must be awaited.

Calling the synchronous `resolve()` on a type with an async factory raises
[`AsyncFactoryError`][depi.AsyncFactoryError] rather than returning a coroutine
nobody awaited. See [Async](async.md).

## Cycles are not detected through factories

The [build-time cycle check](dependency-graph.md) walks constructor parameters.
A factory that resolves its own type, directly or transitively, is not caught at
build time and will recurse at resolve time. Keep factories acyclic.

## Factories and architecture

A factory is the seam where "which concrete thing, configured how" lives. That
belongs in the [composition root](registration.md#the-composition-root), next to
the registrations — not in application code. See
[Third-party clients and factories](../guides/third-party-clients.md) for the
common patterns at scale.
