# Tutorial

Build a URL shortener one step at a time, wire it with `depi`, run it as a
script, serve it through a web framework, and replace its storage in tests.

The tutorial covers all three lifetimes, a factory, a request scope, disposal,
and a framework integration. For the reasoning behind the composition boundary,
see [Architecture](../architecture/index.md).

## What we build

Two endpoints:

| Method | Path | Does |
| --- | --- | --- |
| `POST /links` | `{"target": "https://..."}` | stores the URL, returns a short code |
| `GET /{code}` | — | 302-redirects to the stored URL, counts the hit |

## The plan

1. **[The domain](1-the-domain.md)** — the `Link` entity and the interfaces the
   application depends on. No `depi`.
2. **[The application service](2-the-service.md)** — the create/follow logic, as
   plain classes. Tested without a container.
3. **[Wiring it together](3-wiring.md)** — the infrastructure, a composition
   root, and a script that runs the whole thing.
4. **[Serving it over HTTP](4-serving.md)** — Flask, then the same for Quart,
   FastAPI, and Django.
5. **[Tests](5-testing.md)** — a test container that replaces the storage and
   the code generator, and a request-level test.

## Layout

By the end the project looks like this:

```text
shortlinks/
    domain.py           step 1 — entity + interfaces, imports nothing
    service.py          step 2 — application logic, imports domain
    infrastructure.py   step 3 — concrete implementations, imports domain
    composition.py      step 3 — the one module that imports depi
    cli.py              step 3 — a script entry point
    web_flask.py        step 4 — the HTTP layer
tests/
    test_shortlinks.py  step 5
```

## Prerequisites

```bash
pip install pydepi
```

Step 4 also needs a web framework — `pip install pydepi-flask` (or `-quart`,
`-fastapi`, `-django`). Everything before that is plain Python.

The code in each step is written to run. Copy it into the named file, then use
the checkpoint at the end of the step.
