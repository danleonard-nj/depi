# Backlog

Work identified during the package split and release setup, not yet done. Ordered by what blocks or risks the most, not by size.

Roadmap items intended as public-facing feature direction live in the [README](README.md#roadmap); this file is the working list, including the unglamorous parts.

---

## Blocking the first release

### Publish waves 1 and 2

PyPI allows only 3 pending publishers at a time. Wave 1 (`pydepi`, `pydepi-flask`, `pydepi-quart`) is registered. Publishing those frees the slots for `pydepi-fastapi` and `pydepi-django`. Core must go first — the adapters pin `pydepi>=0.1,<0.2`, and the release workflow's smoke test enforces it. Full sequence in [RELEASING.md](RELEASING.md).

**Done when**: all five distributions are on PyPI and `pip install pydepi[all]` works from a clean environment.

---

## Unverified — CI has never actually run

The workflows are written and their YAML parses, but no run has happened on GitHub. Everything below was verified locally, on Windows, on Python 3.11.

### Most CI matrix cells have never executed

Run locally in clean virtualenvs: core (framework-free), Flask 2.2 floor and 3.1, Quart 0.18 floor and 0.22, FastAPI 0.100 floor and 0.141, Django 4.2 floor and 5.2.

**Never run**: Flask 2.3 / 3.0 · Quart 0.19 / 0.20 / 0.23 · FastAPI 0.110 / 0.115 · Django 6.0 / 6.1 · the entire core Python matrix except 3.11 · every job on Linux.

The old-version cells encode reconstructed transitive pins — Flask 2.2 and Quart 0.18 declare `Werkzeug>=x` with no upper bound, so those cells pin `werkzeug<3` explicitly. That strategy is proven on the cells that ran, but expect one adjustment pass on the first real run.

**Done when**: a full CI run is green, or the failing cells are fixed or removed with a reason recorded.

### Python 3.13 / 3.14 classifiers

`requires-python` is `>=3.10` and CI tests 3.13 (with 3.14 as a non-blocking canary), but the trove classifiers stop at 3.12 — deliberately, since claiming support for an untested interpreter is the exact kind of drift this cleanup removed.

**Done when**: CI shows 3.13 green, and `Programming Language :: Python :: 3.13` is added to all five `pyproject.toml` files.

### Django is unproven end-to-end

Coverage is middleware-level: the sync request path is exercised through Django's test client, and the async path only asserts that `DepiScopeMiddleware` returns a coroutine function when handed an async `get_response`. It has never served a request through a real ASGI server.

**Done when**: an async view resolving scoped services is exercised under uvicorn or daphne, with scope disposal asserted after the response.

---

## Release process gaps

### No GitHub Release is created

Tags trigger publishing, but release notes are manual. The workflow deliberately never takes `contents: write`, so adding this means a separate job with narrower scope than the publish job.

**Done when**: a tag produces a GitHub Release whose body is that package's new CHANGELOG section.

### No TestPyPI rehearsal configured

`release.yml` supports `workflow_dispatch` to TestPyPI, but it needs pending publishers registered on TestPyPI (separate site, separate account) with `testpypi-` prefixed environments. Worth doing once, for `pydepi` alone.

**Done when**: a dispatch run publishes `pydepi` to TestPyPI successfully — or the option is removed from the workflow as unused.

---

## Quality and correctness

### Benchmark figures come from one noisy machine

The README's numbers are a single run on a laptop that was simultaneously running test suites. Repeat runs differed by 8–54% in absolute terms, though ratios held within a few percent — which is why the README leads with ratios and says so explicitly.

**Done when**: figures come from a quiet machine or a dedicated CI job, reporting min-of-N rather than mean, with the run conditions recorded.

### Pre-existing lint findings in the historical test suite

`ruff check tests --select F,E9` reports 33 findings, nearly all unused locals (`F841`) in `tests/core/test_depi.py`, inherited from before the restructure. The lint gate is scoped to `packages/` so these do not block merges.

**Done when**: `tests/` is clean enough to add to the lint gate, or the remaining findings are explicitly ignored with a reason.

### Cycle messages could name the injecting parameter

Cycle errors now report the full chain (`Order -> Invoice -> Customer -> Order`). They name types, not the constructor parameter that formed each edge, which is what you actually edit to break the cycle.

**Done when**: the chain shows the parameter names, or this is closed as not worth the message length.

---

## Feature work

- **aiohttp adapter** — the fifth integration. `depi.integration.BaseInjector` and `depi.context` are the contract; `depi_django` is the closest model, since aiohttp middleware is also constructed by the framework.
- **Performance** — Cython optimisation targeting ~90–100ns resolution, to close the ~2.5x gap with `dependency-injector`.
- **Memory** — metadata storage and allocation patterns.
- **Tooling** — dependency graph visualisation and debug output.

---

## Housekeeping

- `tests/benchmark_results.json` (51MB) and `tests/benchmark_results_new.json` (50MB) sit in the working tree. Both are gitignored, so they are local-only clutter — `benchmark_results.json` is regenerated by the benchmark command, and `_new` is a stale artifact from before the restructure that nothing references.
- Commit `3ec3c33` is titled "Add integration tests for Flask and Quart, remove Django and FastAPI tests". The Django and FastAPI tests were rewritten, not removed — the message reads backwards from what the commit does.
