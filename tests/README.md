# depi Test Suite

All packages in the monorepo are tested from here, so a framework release that breaks an adapter is visible immediately. The directories are meant to be run as **separate CI jobs**, which is what keeps a broken adapter from turning the core suite red.

```
core/          the container itself — no web framework installed, no third-party imports
integrations/  one module per adapter, each guarding its framework's quirks
benchmarks/    performance measurement, compared against `dependency-injector`
```

## Running

```bash
pytest tests/core
```

Core is the job that must always be green. It needs nothing but `pytest`, and asserts the container, lifetimes, scopes, thread safety, async resolution, and the ambient-scope contextvar in `test_context.py`.

```bash
pytest tests/integrations
```

Needs the adapters installed (`pip install -r requirements-dev.txt`). In CI this should be one job per framework, with a version matrix — that is where framework version ranges belong, not in package metadata.

```bash
pytest tests/benchmarks
```

Needs `dependency-injector` and `psutil`. Results are informational; these do not gate merges.

## Conventions

- `integrations/conftest.py` defines one set of services (`Config`, `RequestId`, `Ephemeral`, `Disposable`, `Greeter`) covering all three lifetimes plus a disposal hook. Every adapter is exercised against the same services, so a difference in results points at the adapter rather than at the container.
- Integration modules are marked `pytest.mark.integration` and guarded with `pytest.importorskip`, so they skip rather than error when a framework is absent.
- Each adapter asserts the same behavioural contract: scope injected, autowire where supported, scoped shared within a request, scoped distinct across requests, singleton shared across requests, scope disposed at request end, and no contextvar leak afterwards.

## Framework-specific regressions worth knowing about

- **FastAPI** — `test_fastapi_still_rejects_a_bare_service_annotation` asserts that FastAPI raises `FastAPIError` at *decoration* time for an unannotatable service parameter. That constraint is the reason autowire is unsupported there; if a future FastAPI makes it legal, this test fails and the design can be revisited. `test_openapi_schema_does_not_leak_injected_parameters` covers what the old signature-rewriting injector existed to do.
- **Flask** — `test_scope_does_not_leak_between_requests_on_a_reused_thread` exists because Werkzeug reuses worker threads, so a contextvar set without a matching reset would survive into the next request on that thread.
- **Quart** — `test_async_cleanup_hooks_are_awaited_on_disposal` covers disposal going through `__aexit__` rather than plain `dispose()`.
- **Django** — settings are configured at module import and the URLconf is the test module itself, mirroring a real project where the provider is built once in `AppConfig.ready()`.
