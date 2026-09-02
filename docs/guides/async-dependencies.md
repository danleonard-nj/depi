# Async dependencies

**Goal:** register services that need `await` to construct or tear down, and
resolve them correctly.

Background: [Async](../concepts/async.md).

## An async factory for a client that connects

```python
async def make_search_client(provider) -> SearchClient:
    config = provider.resolve(AppConfig)
    client = SearchClient(config.search_url)
    await client.connect()
    return client

services.add_singleton(SearchClient, factory=make_search_client)
```

As a **singleton**, this runs once during `build_provider()` — `depi` executes
the coroutine to completion there — so application code just calls
`await provider.resolve_async(SearchClient)` (or even `resolve()`, since it is
already built) and gets the connected client.

As **scoped** or **transient**, it runs per resolution and *must* be reached
through `resolve_async`:

```python
services.add_scoped(SearchClient, factory=make_search_client)
# ...
client = await scope.resolve_async(SearchClient)
```

`scope.resolve(SearchClient)` here raises
[`AsyncFactoryError`][depi.AsyncFactoryError].

## Async cleanup on a scoped service

Give the scoped class an `async def __aexit__`. An `async with` scope awaits it
before disposing:

```python
class DbSession:
    def __init__(self, pool: AsyncPool):
        self._pool = pool
        self._session = None

    async def __aexit__(self, exc_type, exc, tb):
        if self._session is not None:
            await self._session.close()

services.add_scoped(DbSession)
```

```python
async with provider.create_scope() as scope:
    session = await scope.resolve_async(DbSession)
    ...
# DbSession.__aexit__ awaited, then dispose() if present
```

The async web adapters (Quart, FastAPI, async Django) route request-scope
disposal through `__aexit__`, so this cleanup runs at the end of every request
without extra wiring. The sync adapters (Flask, sync Django) call `dispose()`
only — do not rely on `__aexit__` there.

## Resolving under an async framework

```python
# FastAPI
@app.get("/search")
async def search(q: str, scope=Depends(injector.get_scope)):
    client = await scope.resolve_async(SearchClient)
    return await client.query(q)
```

```python
# Quart
@app.get("/search")
@injector.inject
async def search(provider):
    client = await provider.resolve_async(SearchClient)
    return await client.query(request.args["q"])
```

## Mixing sync and async resolution

Fine for singletons — one cache backs both paths:

```python
cfg_a = provider.resolve(AppConfig)
cfg_b = await provider.resolve_async(AppConfig)
assert cfg_a is cfg_b
```

A singleton constructor may `await provider.resolve_async(...)` for another
singleton; construction is serialised per type, so this does not deadlock.

## What has no async form

- `build_provider()` is synchronous — it will construct an async singleton
  factory for you (running its coroutine to completion). `ServiceProvider` also
  has a coroutine `build_async()`; the async test suite builds such providers
  with `await collection.build_provider().build_async()`.
- Scope creation, `dispose()`, `current_scope()` / `use_scope` are synchronous.
