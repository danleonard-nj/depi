<figure class="depi-hero" markdown="span">
  ![DEPI](assets/depi-logo.png){ width="320" loading=lazy }
</figure>

# depi

`depi` is a dependency injection container for Python. It reads constructor type
annotations and builds the object graph they describe.

```python
from depi import ServiceCollection

class Config:
    def __init__(self):
        self.dsn = "postgres://localhost/app"

class Database:
    def __init__(self, config: Config):     # resolved from the annotation
        self.dsn = config.dsn

class UserService:
    def __init__(self, db: Database):
        self.db = db

services = ServiceCollection()
services.add_singleton(Config)
services.add_scoped(Database)
services.add_transient(UserService)

provider = services.build_provider()
user_service = provider.resolve(UserService)
```

```bash
pip install pydepi
```

The core package has no dependencies. Framework support ships separately
(`pydepi-flask`, `pydepi-quart`, `pydepi-fastapi`, `pydepi-django`), so
installing the container never pulls in a web framework.

## The problem it solves

In an application with more than a handful of collaborating objects, the code
that constructs them — "which concrete class, built with which arguments, shared
or not" — tends to spread. It ends up inline in request handlers, in module-level
globals, in test fixtures that each rebuild a slightly different graph. Changing
one constructor means editing every call site.

A container centralises that wiring. You describe each type once; the container
works out construction order from the annotations and hands back finished
objects.

## The central idea

> Dependency injection without letting the container become the application
> architecture.

A container earns its place by removing wiring code. It starts to cost you when
application classes import it, when domain logic calls `resolve()`, when
business rules only run if a scope is active — at that point the DI framework
*is* your architecture, and the code cannot be read, tested, or reused without
it.

`depi` is built to stay at the edge:

- Application and domain classes take their dependencies as constructor
  parameters and never import `depi`.
- Registration happens in one place — a [composition root](concepts/registration.md#the-composition-root)
  — that the rest of the code does not import.
- The only code that holds a `ServiceProvider` is the composition root and the
  thin framework adapter at the HTTP boundary.

The [Architecture](architecture/index.md) chapter shows this in a complete
example, and marks the exact line where `depi` stops being imported.

## Who it is for

- Applications with enough services that manual construction has become
  repetitive or error-prone.
- Codebases that want constructor injection and a single composition root
  without adopting a framework-specific DI system.
- Teams coming from .NET's `Microsoft.Extensions.DependencyInjection`: the
  `ServiceCollection` / `ServiceProvider` split and the singleton / scoped /
  transient lifetimes are the same model.

## When you do not need it

- A script or library with a few objects. Passing arguments to constructors by
  hand is shorter and has no moving parts. See the
  [comparison with manual wiring](comparison/index.md#manual-constructor-wiring).
- An application already committed to a framework whose native DI (FastAPI's
  `Depends`, for instance) covers what you need.
- Code where the object graph is genuinely flat — a container adds indirection
  without removing any.

## Where to go next

- **[Getting started](getting-started.md)** — installation to a working example.
- **[Concepts](concepts/index.md)** — registration, resolution, lifetimes,
  scopes, factories, async, disposal, errors.
- **[Architecture](architecture/index.md)** — the clean-architecture example and
  what "the container becoming the architecture" means.
- **[Integrations](integrations/index.md)** — Flask, Quart, FastAPI, Django.
- **[API reference](api/index.md)** — generated from the source.
- **[Comparison](comparison/index.md)** — manual wiring, service locator,
  Dependency Injector, Injector, Punq.
- **[Limitations and non-goals](about/limitations.md)** — what it does not do,
  and its current maturity.

## Status

`pydepi` is at version 0.1.0 and its distribution metadata marks it Beta. The
container has been developed since 2020 and a
[predecessor of the same design](https://github.com/danleonard-nj/framework/tree/main/framework/di)
has run in a production service since 2022. The packaged distributions in this
repository have not yet been published to PyPI or exercised by a full CI run —
see [Limitations](about/limitations.md#maturity) for the detail.
