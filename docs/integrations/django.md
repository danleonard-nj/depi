# Django

```bash
pip install pydepi-django
```

Requires `django>=4.2`. Import as `depi_django`.

Django builds middleware itself from a dotted path in `MIDDLEWARE`, so — unlike
the other adapters — the middleware cannot be handed a provider at construction.
The injector registers itself once at startup, and the middleware reads it from
there.

## Setup

```python
# myapp/apps.py
from django.apps import AppConfig
from depi_django import DjangoInjector

from composition import build_container

class MyAppConfig(AppConfig):
    name = "myapp"

    def ready(self):
        DjangoInjector(build_container()).setup()
```

```python
# settings.py
MIDDLEWARE = [
    "depi_django.DepiScopeMiddleware",
    # ... the rest
]
```

[`setup()`][depi.integration.BaseInjector.setup] takes no app argument here; it
records this injector as the one
[`DepiScopeMiddleware`][depi_django.DepiScopeMiddleware] resolves from. Call it
from `AppConfig.ready()`, before any request is served.

Only one injector is active per process — `setup()` replaces the previously
registered one.

## Views

Keep a module-level injector reference to decorate views with:

```python
# myapp/views.py
from django.http import JsonResponse
from myapp.apps import injector          # or rebuild / import from composition

@injector.inject
def get_user(request, user_id, provider):
    return JsonResponse(provider.resolve(UserService).get(user_id))
```

With autowire:

```python
@injector.inject
def get_user(request, user_id, service: UserService):
    return JsonResponse(service.get(user_id))
```

`request` and `user_id` (a URL kwarg) are left to Django; `service` is resolved
because `UserService` is registered.

## Sync and async

`DepiScopeMiddleware` returns a sync or async middleware to match whatever
`get_response` Django hands it, so the sync/async decision is made per
deployment, not forced by the adapter. The async path routes disposal through
`__aexit__`; the sync path calls `dispose()`.

The async request path is exercised at the middleware level in the test suite
but has not been run end-to-end through an ASGI server — see
[Limitations](../about/limitations.md#django-async-is-unproven-end-to-end).

## If the middleware runs with no injector

```python
# depi_django.NoInjectorRegisteredError:
# No depi injector registered. Call DjangoInjector(provider).setup() during
# startup, typically from AppConfig.ready(), before a request reaches
# DepiScopeMiddleware.
```

`NoInjectorRegisteredError` subclasses `RuntimeError` (not `DepiError` — it is
raised by the adapter, not the container).

## Lifecycle and scope behaviour

- Scope opened at the top of the middleware, disposed in its `finally` — so it
  is cleaned up even if the view raises.
- Scoped / singleton / transient behaviour matches the other adapters.
- No scope leaks after the response; `current_scope()` raises
  `NoActiveScopeError` outside a request.

## API

[`DjangoInjector`, `DepiScopeMiddleware`, `NoInjectorRegisteredError`](../api/django.md)
