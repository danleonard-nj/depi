# Comparison

Where `depi` sits relative to the alternatives, and where an alternative is the
better choice. The axes that actually differ between these tools:

- **Composition root** — is wiring centralised, or spread through the code?
- **Framework coupling** — does application code end up importing the DI tool or
  a web framework?
- **Container access from application code** — do domain objects call `resolve()`?
- **Scopes / lifetimes** — what per-request support exists?
- **Async** — are async factories and async teardown supported?
- **Explicit vs implicit wiring** — do you write bindings, or are they inferred
  from annotations?
- **Test substitution** — how is a dependency faked?
- **Complexity / learning cost** — how much API is there to learn?

## Manual constructor wiring

Constructing objects by hand: `service = OrderService(OrderRepo(pool), SystemClock())`.

| | Manual wiring | `depi` |
| --- | --- | --- |
| Composition root | wherever you write the constructors | one `ServiceCollection` |
| Wiring | fully explicit, by hand | inferred from annotations |
| Lifetimes | you manage them (module globals, closures) | singleton / scoped / transient |
| Learning cost | none | a small API |

**Use manual wiring when** the graph is small or flat. For a script, a library,
or a service with a handful of objects, writing the constructors out is shorter
than a container and has nothing to learn. The moment it becomes repetitive —
the same five objects rebuilt in three places, a new dependency touching many
call sites, per-request lifetime managed by hand — a container starts paying
for itself.

`depi` does not replace manual wiring so much as automate the tedious part of
it: it still calls your constructors with the arguments their annotations ask
for. Nothing stops you wiring one subsystem by hand and registering the rest.

## Service locator

A single object that hands out dependencies on request —
`Locator.get(OrderRepository)` — called from wherever a dependency is needed,
including inside domain code.

`depi`'s `ServiceProvider` *can* be used this way, and
[the docs argue against it](../concepts/resolution.md#who-should-call-resolve).
The difference is discipline, not capability:

| | Service locator | `depi` used well |
| --- | --- | --- |
| Where `resolve` is called | anywhere | composition root + framework adapter |
| Application code imports the tool | yes | no |
| Can the class be built in a plain test? | no — needs a configured locator | yes — it just takes constructor args |
| Dependencies of a class | hidden inside its body | visible in its signature |

**A service locator is never the better design**, but it is less work to
retrofit into an existing codebase that already reaches for globals. `depi`'s
position is that constructor injection is worth the up-front restructuring; if
you disagree for a given codebase, a locator and `depi`-as-locator are
equivalent.

## Dependency Injector

[`dependency-injector`](https://python-dependency-injector.ets-labs.org/) — the
most widely used DI library for Python.

| | Dependency Injector | `depi` |
| --- | --- | --- |
| Implementation | Cython extension (compiled) | pure Python |
| Wiring | explicit `Provider` objects in a `Container` class | inferred from constructor annotations |
| Injection into functions | `@inject` + `Provide[Container.x]` markers in signatures | resolve from the scope; or autowire by annotation |
| Application code coupling | `Provide[...]` markers appear in application signatures unless confined | none if you resolve at the edge |
| Scopes | `Resource` providers, `Singleton`/`Factory`/etc. | singleton / scoped / transient, `create_scope()` |
| Async | async resources and providers | async factories, async scope teardown |
| Resolution speed | faster (native code) | ~2.5x slower per resolve (see [README](https://github.com/danleonard-nj/depi#performance)) |
| Container build speed | slower | faster |
| Install | per-platform wheels | one `py3-none-any` wheel, no compiler |

**Use Dependency Injector when** you want its provider vocabulary
(`Configuration`, `Resource`, `Selector`, `List`, overriding), its maturity and
ecosystem, or its raw resolution speed matters (very hot paths, resolution in a
tight loop). **`depi` trades** that speed and that vocabulary for pure-Python
portability and wiring that comes from annotations rather than a container
class. Its explicit position is that the `Provide[...]` marker in application
signatures is the kind of framework coupling to avoid; Dependency Injector's
`.wire()` mechanism exists partly to manage that.

## Injector

[`injector`](https://injector.readthedocs.io/) — Guice-style, binding modules
and an `@inject` decorator.

| | Injector | `depi` |
| --- | --- | --- |
| Wiring | `Module` classes with `@provider` methods, or automatic for concrete types | `ServiceCollection` registrations |
| Injection | `@inject` on `__init__`, resolved from an `Injector` instance | annotations, no decorator on classes |
| Interface binding | `binder.bind(Interface, to=Impl)` | `add_singleton(Interface, Impl)` |
| Scopes | `singleton`, request scope via extensions | singleton / scoped / transient built in |
| Framework integrations | `flask-injector` and others, community | four first-party adapters |
| Container in app code | you inject an `Injector` or use `@inject` | not required |

**Use Injector when** you like the Guice module model and the `@inject`
decorator convention, or you are already using `flask-injector`. **`depi`
differs** in keeping the decorator off your classes entirely — a `depi`
application class is a plain class whose only DI-related property is that its
parameters are annotated — and in shipping the framework adapters itself rather
than relying on separate integration packages.

## Punq

[`punq`](https://github.com/bobthemighty/punq) — small, annotation-driven,
closest in spirit to `depi`.

| | Punq | `depi` |
| --- | --- | --- |
| Wiring | `container.register(...)`, resolved from annotations | `ServiceCollection`, resolved from annotations |
| Lifetimes | singleton and transient | singleton, transient, **scoped** |
| Per-request scopes | no first-class scope | `create_scope()` + ambient contextvar |
| Async | not supported | `resolve_async`, async factories, async teardown |
| Framework integrations | none | four adapters |
| Build-time validation | resolve-time errors | cycle + lifetime + missing-dependency checks at `build_provider()` |
| Learning cost | very small | small |

**Use Punq when** you want the smallest possible container and do not need
scopes, async, or web integration. **`depi` adds** exactly those three things,
plus a validation pass at build time, at the cost of a slightly larger API.

## Framework-native DI: FastAPI `Depends`

Not a container — a per-endpoint dependency mechanism.

| | FastAPI `Depends` | `depi` |
| --- | --- | --- |
| Scope | one endpoint's parameters | the whole application's service graph |
| Wiring | `Depends(callable)` in each endpoint signature | one composition root |
| Reuse across endpoints | repeat the `Depends` | resolve the service |
| Request-derived values (current user, pagination) | its strength | not its job |
| Coupling | endpoints and their dependency callables are FastAPI-shaped | application code is framework-free |

**Use `Depends` for** request-derived values and small apps where the
dependency graph is shallow. **Use `depi` alongside it for** the service graph —
repositories, domain services, clients — so those are wired once and testable
without FastAPI. The [FastAPI integration](../integrations/fastapi.md) is built
to let the two coexist: resolve services from the `depi` scope, keep
request-shaped dependencies in `Depends`.

## Summary

| If you want... | Reach for |
| --- | --- |
| a few objects, a script, a library | manual wiring |
| the smallest container, no scopes/async | Punq |
| the mature ecosystem, provider vocabulary, top speed | Dependency Injector |
| Guice-style modules and `@inject` | Injector |
| request-scoped values in a small FastAPI app | `Depends` |
| annotation-driven wiring, scopes, async, first-party web adapters, and the container kept at the edge | `depi` |
