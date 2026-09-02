# Tutorial

This builds a small but complete application — a URL shortener — one layer at a
time, and wires it with `depi`. By the end you will have run it as a script, put
it behind a web framework, and tested it with the infrastructure swapped out.

It is slower-paced than [Getting started](../getting-started.md) and covers more
ground: the three lifetimes, a factory, a request scope, disposal, and a
framework integration, in the context of an app rather than in isolation.

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

The code in each step is written to run. Copy it into the file named at the top
of the step and you can execute the checkpoint at the end.

!!! note "Relationship to the Architecture chapter"

    The [Architecture](../architecture/index.md) chapter builds a *different*
    app (user registration) with the same layering, as a reference for the
    structure. This tutorial is the hands-on version: a different domain, more
    steps, runnable checkpoints. Read either first.
