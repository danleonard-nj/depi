# Disposal

Disposal is `depi` calling a cleanup method on the instances it created, when
their lifetime ends. It applies to **scoped instances only**, and the lifetime
that ends is the **scope**.

## What gets disposed

When a scope is disposed — `with` block exit, `async with` exit, or an explicit
[`scope.dispose()`][depi.ServiceScope.dispose] — `depi` walks the instances that
scope constructed:

- **synchronous:** every scoped instance with a callable `dispose()` attribute
  has it called. Exceptions from `dispose()` are caught and logged, so one
  failing cleanup does not stop the others. Then the scope's caches are cleared.
- **asynchronous (`async with`):** first, every scoped instance with an
  `__aexit__` has it awaited (`await inst.__aexit__(exc_type, exc, tb)`); then
  the synchronous `dispose()` pass runs.

```python
class UnitOfWork:
    def __init__(self, pool: ConnectionPool):
        self._conn = pool.acquire()

    def dispose(self) -> None:
        self._conn.release()

services.add_scoped(UnitOfWork)

with provider.create_scope() as scope:
    scope.resolve(UnitOfWork)
# UnitOfWork.dispose() called here
```

For an async resource:

```python
class DbSession:
    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self._session.close()

services.add_scoped(DbSession)

async with provider.create_scope() as scope:
    await scope.resolve_async(DbSession)
# DbSession.__aexit__ awaited here
```

## What does not get disposed

- **Singletons.** The provider has no disposal step and no `close()` method.
  A singleton lives until the provider is garbage-collected; anything it holds
  open (a pool, a client, a file) is not closed by `depi`. If you need
  deterministic singleton shutdown, keep a reference in the composition root and
  close it yourself after the application stops.
- **Transients.** `depi` does not track them after handing them back; they are
  cleaned up by normal garbage collection.
- **Scoped instances created by a factory that returned something without a
  `dispose` / `__aexit__`.** Only those two hooks are checked.
- **Objects you resolved and stored elsewhere.** Disposal is by scope
  membership, not reference tracking.

## Framework integrations

Each adapter disposes the request scope when the request ends — Flask in
`teardown_request`, the ASGI adapters after the response body is sent, Django in
the middleware's `finally`. The async adapters (Quart, FastAPI, Django async)
route disposal through `__aexit__`, so async cleanup hooks run. See
[Integrations](../integrations/index.md).

## Guidance

- Put teardown logic on scoped services, not singletons.
- For a resource that must be closed and is process-wide, make it a singleton
  *and* close it explicitly from the composition root at shutdown — do not rely
  on `depi`.
- See [Releasing resources](../guides/resource-teardown.md) for worked examples.
