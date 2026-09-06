# Async dependencies

**Goal:** register services that need `await` to construct or tear down, and
resolve them correctly.

Background: [Async](../concepts/async.md).

## An async dependency inside a larger graph

```python
from dataclasses import dataclass
from depi import ServiceCollection

@dataclass
class Credentials:
    token: str

class CredentialProvider:
    async def obtain(self) -> Credentials:
        # Network or process I/O would happen here.
        return Credentials(token="ready")

class ApiClient:
    def __init__(self, credentials: Credentials):
        self.credentials = credentials

class ReportService:
    def __init__(self, client: ApiClient):
        self.client = client

async def make_credentials(scope) -> Credentials:
    provider = scope.resolve(CredentialProvider)
    return await provider.obtain()

services = ServiceCollection()
services.add_singleton(CredentialProvider)
services.add_scoped(Credentials, factory=make_credentials)
services.add_transient(ApiClient)
services.add_transient(ReportService)
provider = services.build_provider()
```

```python
async with provider.create_scope() as scope:
    reports = await scope.resolve_async(ReportService)
    assert reports.client.credentials.token == "ready"
```

`ReportService` and `ApiClient` have ordinary synchronous constructors. The
async path reaches the `Credentials` factory several levels down, awaits it, and
then finishes the graph. `scope.resolve(ReportService)` would raise
[`AsyncFactoryError`][depi.AsyncFactoryError] when it reached that factory.

For a **singleton** async factory, `build_provider()` runs the coroutine to
completion once. Scoped and transient async factories run during resolution and
must be reached through `resolve_async`.

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

A singleton dependency chain can call `resolve_async` recursively without a
global-lock deadlock. Concurrent calls for the same uninitialized singleton
produce one instance; unrelated types have separate locks and can initialize at
the same time.

## What has no async form

- `build_provider()` is synchronous — it will construct an async singleton
  factory for you (running its coroutine to completion). `ServiceProvider` also
  has a coroutine `build_async()`; the async test suite builds such providers
  with `await collection.build_provider().build_async()`.
- Scope creation, `dispose()`, `current_scope()` / `use_scope` are synchronous.
