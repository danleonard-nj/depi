# Async

`depi` has a coroutine resolution path alongside the synchronous one. You need
it when a service is produced by an `async` factory or has an async cleanup
step.

## `resolve_async`

[`ServiceProvider.resolve_async`][depi.ServiceProvider.resolve_async] and
[`ServiceScope.resolve_async`][depi.ServiceScope.resolve_async] are the
coroutine forms of `resolve`. They:

- await `async` factories,
- await async constructor activation for the dependency chain,
- otherwise behave exactly like `resolve` — same lifetimes, same caching.

```python
service = await provider.resolve_async(ReportBuilder)
```

Singletons share one cache across both paths, so mixing `resolve` and
`resolve_async` for the same singleton is fine and returns the same object.

## Async factories

```python
async def make_client(provider) -> HttpClient:
    client = HttpClient(provider.resolve(Config).base_url)
    await client.connect()
    return client

services.add_singleton(HttpClient, factory=make_client)
```

- **Singleton** async factories run during `build_provider()`. `depi` executes
  the coroutine to completion at build time (starting a temporary event loop, or
  a worker thread if one is already running), so `resolve()` afterwards returns
  the finished instance and does not need to be awaited.
- **Scoped / transient** async factories run per resolution and must be reached
  through `resolve_async`.

## The sync guard

Resolving an async factory through the synchronous `resolve()` raises
[`AsyncFactoryError`][depi.AsyncFactoryError]:

```python
services.add_transient(HttpClient, factory=make_client)   # async factory
provider.resolve(HttpClient)
# depi.AsyncFactoryError: Factory for 'HttpClient' returned an awaitable.
# Use resolve_async() to resolve async factories.
```

The guard applies on both the provider and the scope paths — the scope path
matters because every framework adapter resolves through a scope. `depi` closes
the abandoned coroutine before raising, so you do not also get a
`coroutine was never awaited` warning pointing at the wrong place.

`AsyncFactoryError` also subclasses `RuntimeError` (which is what this used to
raise), so older `except RuntimeError` handlers still catch it.

## Async scope exit

An async scope disposes async resources before the plain `dispose()`:

```python
async with provider.create_scope() as scope:
    session = await scope.resolve_async(DbSession)
    ...
# scope.__aexit__ runs: awaits __aexit__ on each scoped instance that defines
# it, then calls dispose()
```

So a scoped service can hold an async resource and clean it up with an
`async def __aexit__`. See [Disposal](disposal.md).

## Concurrency

- Concurrent `resolve_async` calls for the same uninitialised singleton produce
  one instance — construction is serialised by a per-type `asyncio.Lock`.
- Different singletons use different locks, so they can be built concurrently.
- A singleton constructor may `await resolve_async(...)` for another singleton
  without deadlocking.
