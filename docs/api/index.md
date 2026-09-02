# API reference

The reference pages are generated from the source tree with
[mkdocstrings](https://mkdocstrings.github.io/). Signatures and docstrings come
straight from the code, so they cannot drift from the implementation.

## What is public

The public surface of the core package is exactly the names in
`depi.__all__`, plus `depi.integration` and `depi.context` for anyone writing a
new framework adapter. Everything else under `depi.services` — the private
methods on `ServiceProvider` and `ServiceScope`, `get_signature`, the
`_resolver_fn` closure — is implementation detail and may change without a major
version bump.

| Area | Module | Page |
| --- | --- | --- |
| Container, lifetimes, registrations | `depi` (`depi.services`) | [Container](container.md) |
| Ambient request scope | `depi.context` | [Ambient scope](context.md) |
| Exception hierarchy | `depi.exceptions` | [Exceptions](exceptions.md) |
| Base class for adapters | `depi.integration` | [Integration base](integration.md) |
| Flask adapter | `depi_flask` | [Flask adapter](flask.md) |
| Quart adapter | `depi_quart` | [Quart adapter](quart.md) |
| FastAPI adapter | `depi_fastapi` | [FastAPI adapter](fastapi.md) |
| Django adapter | `depi_django` | [Django adapter](django.md) |

## Coverage

Every name exported from a distribution's top-level module is documented:

- **`depi`** — `ServiceCollection`, `ServiceProvider`, `ServiceScope`,
  `Lifetime`, `ConstructorDependency`, `DependencyRegistration`;
  `current_scope`, `get_current_scope`, `set_current_scope`,
  `reset_current_scope`, `use_scope`; and the eleven exception classes.
- **`depi.integration`** — `BaseInjector`, `injectable_parameters`.
- **`depi_flask`** — `FlaskInjector`.
- **`depi_quart`** — `QuartInjector`.
- **`depi_fastapi`** — `FastAPIInjector`.
- **`depi_django`** — `DjangoInjector`, `DepiScopeMiddleware`,
  `NoInjectorRegisteredError`.

`Lifetime` is a plain class holding three string constants
(`Lifetime.Singleton == "singleton"`), not an `enum.Enum`. There are no other
enums, protocols, or dataclasses in the public API.
