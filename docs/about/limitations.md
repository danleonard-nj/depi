# Limitations and non-goals

What `depi` does not do, stated plainly. Everything here reflects the current
state of the code, not a roadmap.

## Non-goals

### No provider-level disposal

[`ServiceProvider`][depi.ServiceProvider] has no `dispose()` or `close()`.
Singletons are never cleaned up by `depi` — a singleton connection pool or
client stays open until it is garbage-collected. Deterministic shutdown of
process-wide resources is the application's job: hold the reference in the
composition root and close it after the app stops. See
[Releasing resources](../guides/resource-teardown.md). Only **scoped** instances
are disposed, and only when their scope ends.

### No injection without annotations

Every constructor parameter must have a resolvable type annotation, or the type
must be registered with a [factory](../concepts/factories.md). There is no
support for injection by parameter name, by string token, or by configuration
key. `**kwargs` and `*args` are not injected.

### No optional dependencies

An annotated parameter is always resolved; a default value does not make it
"resolve if registered, else skip". Optional dependencies require a factory that
catches `UnregisteredDependencyError`.

### No multi-binding / collection injection

You cannot register several implementations under one key and inject them as a
list. Register each by a distinct key (its concrete type, or separate
interfaces) and depend on them individually.

### No named or keyed registrations

One registration per type. Registering a type twice replaces the first. There is
no `add_singleton(Cache, RedisCache, name="primary")`.

### No decorator/interception layer

`depi` constructs objects; it does not wrap them in proxies, apply
cross-cutting decorators, or intercept method calls. Decoration is done by
registering a decorator class that takes the inner service as a constructor
parameter.

### No auto-registration / scanning

There is no "register every class in this package". Registration is explicit
Python; `register_many([...])` is as automatic as it gets.

### Not a service locator, by intent

`ServiceProvider` can be called from anywhere, but the design intent is that it
is not — see [Design philosophy](index.md#why-the-container-stays-at-the-composition-boundary).
The library does not enforce this.

### `Lifetime` is not an enum

It is a class with three string constants (`Lifetime.Singleton == "singleton"`).
There are no `enum.Enum`, `Protocol`, or dataclass types in the public API.

## Known gaps in the current release

These are tracked in
[BACKLOG.md](https://github.com/danleonard-nj/depi/blob/main/BACKLOG.md).

### Cycle detection does not see through factories

The [build-time cycle check](../concepts/dependency-graph.md) walks constructor
signatures. A cycle formed through a factory that resolves its own type is not
caught at build time and recurses at resolve time.

### Missing transient/scoped dependencies are not caught at build time

`build_provider()` only fails on missing dependencies of **singletons**. A
transient or scoped type whose dependency was never registered raises
`UnregisteredDependencyError` on first resolve instead.

### Cycle messages name types, not parameters

`Order -> Invoice -> Customer -> Order` tells you the types in the cycle but not
which constructor parameter formed each edge — which is what you edit to break
it.

### Django async is unproven end-to-end

The Django adapter's async path is tested at the middleware level (that
`DepiScopeMiddleware` returns a coroutine function for an async `get_response`),
but has never served a request through a real ASGI server (uvicorn, daphne).

### Benchmark figures are from one noisy machine

The performance numbers in the [README](https://github.com/danleonard-nj/depi#performance)
are a single run on a laptop that was also running test suites. Repeat runs
differed by 8–54% in absolute terms; the *ratios* held within a few percent,
which is why the README leads with ratios.

### No aiohttp adapter

Four adapters exist (Flask, Quart, FastAPI, Django). aiohttp is on the backlog,
not shipped.

## Maturity

- **Version:** `pydepi` 0.1.0; the four adapters 0.1.0. All marked
  `Development Status :: 4 - Beta` in package metadata.
- **Not yet on PyPI.** At the time these docs were written the distributions
  had not been published. `pip install pydepi` is the intended command once
  they are; until then, install from the repository.
- **CI has not completed a full run.** The workflows are written and their YAML
  parses; most matrix cells (the full Python version matrix, every job on Linux,
  several framework versions) have only been verified locally on Windows /
  Python 3.11. Expect one adjustment pass on the first real run.
- **Trove classifiers stop at Python 3.12** although `requires-python` is
  `>=3.10` and CI targets 3.13 (with 3.14 as a non-blocking canary). Support for
  3.13+ is not claimed in metadata until CI confirms it.
- **No `LICENSE` file** is present at the repository root, though `pyproject.toml`
  and the READMEs state MIT.
- The **container design** itself is older than the packaging: developed since
  2020, with a same-design predecessor in production since 2022. The 0.1.0 label
  is on the *distribution*, not the approach.

## Versioning

The project states it follows semantic versioning and keeps backwards
compatibility within a major version. Adapters pin `pydepi>=0.1,<0.2`; a core
change to `depi.integration` or `depi.context` is a breaking change for all
four.
