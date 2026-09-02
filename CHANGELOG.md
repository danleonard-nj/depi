# Changelog

All five distributions in this repository are versioned and released independently, so each gets its own section. Entries follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Update the relevant section **before** tagging a release — the tag and the package's `pyproject.toml` version must agree, and the release workflow enforces that.

---

## pydepi

### [0.1.0] — 2026-09-02

First public release. The container itself has no dependencies.

#### Added

- `ServiceCollection` / `ServiceProvider` / `ServiceScope` with constructor injection resolved from type annotations.
- Singleton, transient, and scoped lifetimes. Scopes are sync and async context managers; `__aexit__` awaits async cleanup on scoped instances before disposing them.
- `resolve_async` and support for async factories.
- Registration by interface (`add_singleton(ILogger, ConsoleLogger)`), by instance, by factory, and in bulk via `register_many`.
- Cycle detection by static analysis at `build_provider()`, and lifetime validation that rejects a singleton depending on a scoped or transient service.
- `depi.context`: the ambient request scope — `current_scope`, `get_current_scope`, `set_current_scope`, `reset_current_scope`, `use_scope`. Framework adapters bind the same contextvar, so a scope opened by one is visible to all.
- `depi.integration.BaseInjector`: the contract every framework adapter builds on, including the `param_name` and `autowire` options.
- `depi.exceptions`: a typed hierarchy rooted at `DepiError`, split into `RegistrationError` (startup — the container was described wrongly) and `ResolutionError` (resolve time — it was asked for something it could not produce). Every class also derives from the type it previously raised, so `except Exception` and `except RuntimeError` handlers keep working.
- `ServiceProvider.is_registered` / `ServiceScope.is_registered`, used by adapters to tell a service parameter from one the web framework will supply.
- Autowire introspection evaluates annotations with `eval_str=True`, so it works under `from __future__ import annotations` (PEP 563), where every annotation is a string. A parameter whose annotation cannot be evaluated — an unimportable forward reference, a builtin with no retrievable signature — is left for the framework to supply rather than raising at import time.

#### Fixed

- `ServiceScope.resolve` had no guard against async factories, so a scoped or transient async factory resolved through a scope returned an un-awaited coroutine instead of raising. `ServiceProvider.resolve` had the guard; the scope path did not — and a scope is what every framework adapter resolves through, so this only surfaced inside a request, far from its cause.
- The async-factory guard now closes the coroutine before raising. Abandoning it emitted `RuntimeWarning: coroutine ... was never awaited` on top of the exception, pointing at the wrong thing.
- Cycle errors name the whole chain (`Order -> Invoice -> Customer -> Order`) instead of only the type where detection happened. The message is trimmed to the cycle itself, so a class that merely depends on a loop is not blamed for it.

#### Notes

- **A scope disposes what it owns.** Exiting a scope calls `dispose()` on the scoped instances it constructed. Transients are handed back untracked, and singletons belong to the provider, so neither is disposed by a scope. This differs from .NET, where a container disposes transients it created; depi does not hold that reference. Own a transient's cleanup yourself, or register it as scoped. See `docs/concepts/disposal.md`.

---

## pydepi-flask

### [0.1.0] — 2026-09-02

#### Added

- `FlaskInjector`: a request-scoped `ServiceScope` opened in `before_request` and disposed in `teardown_request`.
- `inject` decorator, in two modes — passing the scope as a keyword argument (default), or `autowire=True` to resolve registered types by annotation while leaving URL arguments to Flask.
- `param_name` to rename the injected argument, so an existing `container`-style convention needs no fork.
- Built with `functools.wraps`, so it composes inside a decorator stack (route registration, auth, response handling) without the outer layers losing the view's identity.

#### Notes

- The scope and its contextvar token are stored on `flask.g` so teardown restores exactly the context it replaced. Werkzeug reuses worker threads, and a contextvar set without a matching reset would leak into the next request served by that thread.

---

## pydepi-quart

### [0.1.0] — 2026-09-02

#### Added

- `QuartInjector`: the async counterpart to the Flask adapter, with the same two injection modes and `param_name` option.
- Disposal goes through `ServiceScope.__aexit__`, so scoped instances holding async resources get awaited cleanup before `dispose()` runs.

---

## pydepi-fastapi

### [0.1.0] — 2026-09-02

#### Added

- `FastAPIInjector`: scope management as a pure ASGI middleware, so the contextvar is set in the same context the endpoint coroutine runs in, and disposal happens after the response body is sent rather than when the handler returns.
- `get_scope`, for use as `Depends(injector.get_scope)`. depi never touches endpoint signatures, so OpenAPI schemas stay clean.

#### Notes

- `autowire=True` is rejected at construction, and `inject` raises. FastAPI builds request parsing and the OpenAPI schema from the endpoint signature and raises `FastAPIError` at *decoration* time for any annotation it cannot treat as a Pydantic field. Supporting either would require rewriting `__signature__` before FastAPI sees the endpoint, which is fragile across releases. The constraint is asserted by a test rather than assumed, so a future FastAPI that relaxes it will surface as a failure.

---

## pydepi-django

### [0.1.0] — 2026-09-02

#### Added

- `DjangoInjector` and `DepiScopeMiddleware`. Django builds middleware from a dotted path in `MIDDLEWARE`, so the injector registers itself at startup (from `AppConfig.ready()`) rather than being constructed inline.
- The middleware matches whatever `get_response` it is given, so both the sync and async request paths work without Django having to adapt between them.
- `NoInjectorRegisteredError`, raised with an explanation when the middleware runs before any injector registered itself.

---

## Notes for anyone using this from git before 0.1.0

The package was restructured before its first release. If you were importing from the repository directly:

- The distribution is **`pydepi`**, not `depi` — that name belongs to an unrelated project on PyPI. The import name is still `depi`.
- `depi.injectors` is **removed**. Framework adapters are now separate distributions with their own top-level modules: `depi_flask`, `depi_quart`, `depi_fastapi`, `depi_django`.
- `DependencyInjector`, `FastAPIDependencyInjector`, `FlaskDependencyInjector`, `QuartDependencyInjector` and the `create_*_injector` factories are **removed**. They aliased a class that had no `.inject` and silently ignored `strict`, so nothing written against the documented API actually worked.
- The `strict` parameter and `@di.inject` signature rewriting are **gone**. Provider injection is the default everywhere; `autowire=True` replaces the old non-strict behaviour on Flask, Quart and Django. FastAPI uses `Depends`.
- `FlaskInjector.with_provider` is now `FlaskInjector.inject`, and `setup_flask` / `setup_fastapi` / `setup_quart` are a single `setup(app)` per adapter.
