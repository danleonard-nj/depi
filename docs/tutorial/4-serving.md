# 4. Serving it over HTTP

The application, the composition root, and the domain do not change. A web
framework is added at the edge: a thin adapter opens a request scope, and each
view resolves a use case from it.

## Flask

```bash
pip install pydepi-flask
```

> File: `shortlinks/web_flask.py`

```python
# shortlinks/web_flask.py
from flask import Flask, redirect, request

from depi_flask import FlaskInjector

from shortlinks.composition import build_provider
from shortlinks.service import CreateLink, FollowLink, UnknownCode


def create_app() -> Flask:
    app = Flask(__name__)
    injector = FlaskInjector(build_provider())   # (1)!
    injector.setup(app)                          # (2)!

    @app.post("/links")
    @injector.inject                             # (3)!
    def create(provider):
        target = request.get_json()["target"]
        link = provider.resolve(CreateLink)(target)
        return {"code": link.code, "url": request.host_url + link.code}, 201

    @app.get("/<code>")
    @injector.inject
    def follow(code, provider):                  # (4)!
        try:
            return redirect(provider.resolve(FollowLink)(code))
        except UnknownCode:
            return {"error": "unknown code"}, 404

    return app


app = create_app()
```

1. `build_provider()` runs once, at startup.
2. `setup(app)` installs a `before_request` hook that opens a scope and a
   `teardown_request` hook that disposes it — so `SqlLikeLinkRepository.dispose()`
   flushes at the end of every request.
3. `@injector.inject` passes the request scope to the view as `provider`.
4. `code` comes from the URL; Flask fills it. `provider` is the scope.

```bash
flask --app shortlinks.web_flask run
```

```bash
curl -s -X POST localhost:5000/links -H 'content-type: application/json' \
     -d '{"target": "https://peps.python.org/pep-0020/"}'
# {"code":"a1b2c3","url":"http://localhost:5000/a1b2c3"}

curl -si localhost:5000/a1b2c3 | grep -i location
# location: https://peps.python.org/pep-0020/
```

Each request gets its own `SqlLikeLinkRepository`; the `LinkStore` and
`AppConfig` singletons are shared across all of them.

## The same, other frameworks

Only the adapter and the view signatures change. `build_provider()`,
`CreateLink`, `FollowLink`, and the domain are untouched.

=== "Quart"

    ```bash
    pip install pydepi-quart
    ```

    ```python
    # shortlinks/web_quart.py
    from quart import Quart, redirect, request
    from depi_quart import QuartInjector

    from shortlinks.composition import build_provider
    from shortlinks.service import CreateLink, FollowLink, UnknownCode

    app = Quart(__name__)
    injector = QuartInjector(build_provider())
    injector.setup(app)

    @app.post("/links")
    @injector.inject
    async def create(provider):
        target = (await request.get_json())["target"]
        link = provider.resolve(CreateLink)(target)
        return {"code": link.code}, 201

    @app.get("/<code>")
    @injector.inject
    async def follow(code, provider):
        try:
            return redirect(provider.resolve(FollowLink)(code))
        except UnknownCode:
            return {"error": "unknown code"}, 404
    ```

    Full details: [Quart integration](../integrations/quart.md).

=== "FastAPI"

    ```bash
    pip install pydepi-fastapi
    ```

    ```python
    # shortlinks/web_fastapi.py
    from fastapi import Depends, FastAPI, HTTPException
    from fastapi.responses import RedirectResponse
    from depi_fastapi import FastAPIInjector

    from shortlinks.composition import build_provider
    from shortlinks.service import CreateLink, FollowLink, UnknownCode

    app = FastAPI()
    injector = FastAPIInjector(build_provider())
    injector.setup(app)

    @app.post("/links", status_code=201)
    async def create(body: dict, scope=Depends(injector.get_scope)):
        link = scope.resolve(CreateLink)(body["target"])
        return {"code": link.code}

    @app.get("/{code}")
    async def follow(code: str, scope=Depends(injector.get_scope)):
        try:
            return RedirectResponse(scope.resolve(FollowLink)(code))
        except UnknownCode:
            raise HTTPException(404, "unknown code")
    ```

    FastAPI injects the scope with `Depends`, not a decorator — see
    [FastAPI integration](../integrations/fastapi.md).

=== "Django"

    ```bash
    pip install pydepi-django
    ```

    ```python
    # shortlinks/apps.py
    from django.apps import AppConfig
    from depi_django import DjangoInjector
    from shortlinks.composition import build_provider

    injector = DjangoInjector(build_provider())

    class ShortlinksConfig(AppConfig):
        name = "shortlinks"
        def ready(self):
            injector.setup()

    # settings.py:  MIDDLEWARE = ["depi_django.DepiScopeMiddleware", ...]
    ```

    ```python
    # shortlinks/views.py
    from django.http import HttpResponseRedirect, JsonResponse
    from shortlinks.apps import injector
    from shortlinks.service import CreateLink, FollowLink, UnknownCode

    @injector.inject
    def create(request, provider):
        import json
        target = json.loads(request.body)["target"]
        return JsonResponse({"code": provider.resolve(CreateLink)(target).code}, status=201)

    @injector.inject
    def follow(request, code, provider):
        try:
            return HttpResponseRedirect(provider.resolve(FollowLink)(code))
        except UnknownCode:
            return JsonResponse({"error": "unknown code"}, status=404)
    ```

    The middleware is built by Django from a dotted path, so the injector
    registers itself in `AppConfig.ready()` — see
    [Django integration](../integrations/django.md).

## Where the framework stops

In every version the view does two things: pull request data out of the
framework, and call a use case. `CreateLink` and `FollowLink` take a string and
return a `Link` or a URL — they never see a request or response object. Swapping
Flask for FastAPI is a new file at the edge, not a change to the app.

## A note on async

The use cases here are synchronous, so the async views above just call
`provider.resolve(...)`. If a use case did async I/O — an async database driver,
an HTTP call — you would register an [async factory](../concepts/async.md) and
use `await provider.resolve_async(...)` (or `await scope.resolve_async(...)`).
The Quart and FastAPI adapters dispose the scope through `__aexit__`, so a
scoped service with an `async def __aexit__` gets awaited cleanup.

## Checkpoint

`POST /links` returns a code; `GET /{code}` redirects to the stored URL. Next:
tests that replace the storage and the code generator.
