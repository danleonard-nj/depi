<figure class="depi-hero" markdown="span">
  ![DEPI](assets/depi-logo.png){ width="320" loading=lazy }
</figure>

# depi

`depi` is a dependency injection container for Python applications whose object
graphs have outgrown manual wiring. Constructor annotations describe
dependencies; ordinary Python registrations choose implementations and
lifetimes.

```bash
pip install pydepi
```

```python
from depi import ServiceCollection

class Config:
    database_url = "sqlite:///app.db"

class Repository:
    def __init__(self, config: Config):
        self.database_url = config.database_url

class UserService:
    def __init__(self, repository: Repository):
        self.repository = repository

services = ServiceCollection()
services.add_singleton(Config)
services.add_scoped(Repository)
services.add_transient(UserService)
provider = services.build_provider()

with provider.create_scope() as scope:
    users = scope.resolve(UserService)
```

The core is pure Python and has no third-party runtime dependencies. Framework
adapters are separate packages for Flask, Quart, FastAPI, and Django.

## What it handles

- **Nontrivial graphs:** deterministic dependency ordering, cycle detection,
  missing-registration checks, and lifetime validation.
- **Object lifetimes:** singleton, scoped, and transient registrations;
  factories; eager or lazy singleton construction; and scoped cleanup.
- **Async construction and teardown:** async factories, `resolve_async`, nested
  sync/async graphs, concurrency-safe singleton creation, and awaited scoped
  cleanup.
- **Python-native wiring:** annotations drive discovery, while registrations and
  environment choices remain ordinary Python. There is no separate configuration
  language or generated binding layer.
- **Request scopes:** first-party adapters connect the same core container to
  supported web frameworks without making the framework a core dependency.

The design evolved from application infrastructure used since 2020; its
predecessor has wired a production service with more than 120 registrations
since 2022. See [About](about/index.md) for provenance and
[Limitations](about/limitations.md) for the current boundaries.

## Keep the container at the boundary

Registration belongs in a composition module. Services receive normal
constructor arguments; they do not call `resolve()` or import `depi`. An entry
point or framework adapter resolves a service or handler, then application code
runs without container awareness. This works with a simple
data/core → services → presentation layout, a different layering scheme, or no
formal layers at all.

Read [Architecture](architecture/index.md) for a complete example.

## Start here

- [Getting started](getting-started.md) — install, register, build, and resolve.
- [Tutorial](tutorial/index.md) — build and serve a small application.
- [Concepts](concepts/index.md) — lifetimes, factories, async, disposal, and graph
  validation.
- [Integrations](integrations/index.md) — Flask, Quart, FastAPI, and Django.
- [API reference](api/index.md) — generated signatures and public API details.
- [Comparison](comparison/index.md) — tradeoffs against manual wiring and other
  DI approaches.
