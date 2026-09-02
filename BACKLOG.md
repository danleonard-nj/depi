# Backlog

Work identified during the package split and release setup, not yet done. Ordered by what blocks or risks the most, not by size.

Roadmap items intended as public-facing feature direction live in the [README](README.md#roadmap); this file is the working list, including the unglamorous parts.

---

## Blocking the first release

### Publish waves 1 and 2

PyPI allows only 3 pending publishers at a time, so the five distributions ship in waves.

`pydepi` **0.1.0 is live** — the first release run went green on the first attempt, converting the pending publisher into a real project and freeing a slot, which `pydepi-fastapi` now occupies. Pending: `pydepi-fastapi`, `pydepi-flask`, `pydepi-quart`. Still unregistered: `pydepi-django`.

Core going first is enforced, not just documented: the adapters pin `pydepi>=0.1,<0.2` and the release workflow installs the finished wheel into a clean virtualenv, so an adapter tagged before core exists fails before anything uploads.

Remaining: tag `pydepi-flask` and `pydepi-quart`, which frees the last slot for `pydepi-django`. Full sequence in [RELEASING.md](RELEASING.md).

**Done when**: all five distributions are on PyPI and `pip install pydepi[all]` works from a clean environment.

---

## Unverified

CI has now run in full and is green: core on 3.10–3.14, and every Flask, Quart,
FastAPI and Django cell. The items below are the gaps a green matrix does not
close.

### Python 3.13 classifiers on the Flask, FastAPI and Django adapters

The first full CI run was green everywhere except two Quart cells, which turned
out to be a test over-fitted to one Quart version rather than an adapter bug.
That closed the "matrix cells have never executed" item and unblocked this one,
but only partly. Core runs 3.10–3.13 plus a 3.14 canary and Quart runs 3.13 in
two cells, so `pydepi-quart` claims 3.13. Flask, FastAPI and Django only ever
run on 3.12, so they still stop there — claiming an untested interpreter is the
exact drift this cleanup removed.

`pydepi` 0.1.0 shipped before this was applied, so core's 3.13 / 3.14
classifiers have to wait for 0.1.1. Classifiers are frozen per release.

**Done when**: those three matrices gain a 3.13 cell and the classifier follows
the evidence.

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

- `tests/benchmark_results.json` (~53MB) sits in the working tree. Gitignored and regenerated by the benchmark command, so it is local-only clutter rather than a problem. (`benchmark_results_new.json` has been deleted.)
- Commit `3ec3c33` is titled "Add integration tests for Flask and Quart, remove Django and FastAPI tests". The Django and FastAPI tests were rewritten, not removed — the message reads backwards from what the commit does.
