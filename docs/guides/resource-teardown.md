# Releasing resources

**Goal:** close what you open. `depi` disposes scoped instances; process-wide
resources are your responsibility.

Background: [Disposal](../concepts/disposal.md).

## Per-request resources: make them scoped

A scoped instance with a `dispose()` method has it called when the scope ends:

```python
class UnitOfWork:
    def __init__(self, pool: ConnectionPool):
        self._conn = pool.acquire()
        self._tx = self._conn.begin()

    def commit(self) -> None:
        self._tx.commit()

    def dispose(self) -> None:
        self._tx.rollback_if_open()
        self._conn.release()

services.add_scoped(UnitOfWork)
```

```python
with provider.create_scope() as scope:
    uow = scope.resolve(UnitOfWork)
    ...
    uow.commit()
# dispose(): rolls back if commit() never ran, releases the connection
```

Under a web framework the adapter creates and disposes the request scope, so
`UnitOfWork` is cleaned up at the end of every request with no extra code.

## Async per-request resources: use `__aexit__`

```python
class DbSession:
    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self._session.close()

services.add_scoped(DbSession)
```

An `async with` scope — and the async web adapters (Quart, FastAPI, async
Django) — await `__aexit__` before `dispose()`. The sync adapters do not; they
call `dispose()` only.

If a service holds both sync and async resources, put the async cleanup in
`__aexit__` and the sync cleanup in `dispose()`; both run under an async scope.

## Disposal errors are logged, not raised

If a scoped instance's `dispose()` raises, `depi` catches it, logs a warning
(`logging.getLogger("depi.services")`), and continues disposing the rest. Do not
rely on a `dispose()` exception propagating.

## Process-wide resources: close them yourself

`depi` never disposes singletons. A singleton connection pool, HTTP client, or
Kafka producer stays open until garbage-collected. For deterministic shutdown,
hold the reference in the composition root and close it after the app stops:

```python
def main() -> None:
    provider = build_container()
    pool = provider.resolve(ConnectionPool)
    try:
        provider.resolve(App).run()
    finally:
        pool.close()
```

For an async app:

```python
async def main() -> None:
    provider = build_container()
    client = await provider.resolve_async(AsyncClient)
    try:
        await provider.resolve_async(App).run()
    finally:
        await client.aclose()
```

There is no `provider.dispose()` to do this for you — see
[Limitations](../about/limitations.md#no-provider-level-disposal).
