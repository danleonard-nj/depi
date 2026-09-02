# Handling errors at startup

**Goal:** a wiring mistake should stop the process at boot, with a message that
says what is wrong — not surface as a 500 on the first request that hits it.

Background: [Errors](../concepts/errors.md),
[The dependency graph](../concepts/dependency-graph.md).

## `build_provider()` is the checkpoint

Most wiring errors are raised there:

| Mistake | Exception |
| --- | --- |
| cycle in the graph | `CircularDependencyError` |
| singleton depends on scoped/transient | `InvalidLifetimeError` |
| a singleton's dependency was never registered | `UnregisteredDependencyError` |

`MissingAnnotationError` is raised even earlier, at the `add_*` call.

Transient and scoped dependencies that were never registered are *not* caught at
build time — they raise `UnregisteredDependencyError` on first resolve. If you
want those caught at startup too, resolve your top-level handlers once during
boot (a smoke resolve), or register them as `eager=True` where that makes sense.

## Fail the process

```python
from depi import RegistrationError

def main() -> None:
    try:
        provider = build_container()
    except RegistrationError as exc:
        raise SystemExit(f"container misconfigured: {exc}")
    provider.resolve(App).run()
```

Catch [`RegistrationError`][depi.RegistrationError] — the startup group — not
`DepiError`, so a resolve-time problem later is not masked by this handler.

## Distinguishing your bugs from depi's

`depi` does not wrap exceptions raised inside your code. A `KeyError` from a
factory, or a `ValueError` from a config validator, propagates as itself:

```python
def make_pool(provider) -> ConnectionPool:
    dsn = provider.resolve(AppConfig).database_dsn   # KeyError if missing
    return ConnectionPool(dsn)
```

```python
try:
    provider = build_container()
except DepiError:
    ...          # will NOT catch the KeyError above
```

So `except DepiError` is safe to use for "the container is wrong" without
swallowing "my factory has a bug".

## Eager singletons for fail-fast

By default singletons are constructed lazily. To have a bad configuration or an
unreachable database fail at startup instead of on first use:

```python
services.add_singleton(ConnectionPool, factory=make_pool, eager=True)
```

or make every singleton eager:

```python
provider = services.build_provider(eager_all=True)
```

An eager singleton whose factory or constructor raises fails `build_provider()`.
