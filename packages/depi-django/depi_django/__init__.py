"""
Django integration.

Django constructs middleware itself from a dotted path in ``MIDDLEWARE``, so
unlike the other integrations the middleware cannot be handed a provider at
construction time. Instead the injector registers itself once at startup and
the middleware reads it from there:

    # apps.py
    class MyAppConfig(AppConfig):
        def ready(self):
            injector = DjangoInjector(build_provider())
            injector.setup()

    # settings.py
    MIDDLEWARE = ['depi_django.DepiScopeMiddleware', ...]

Both sync and async request paths are supported; Django picks which by
inspecting the middleware, so the sync/async decision is made per deployment
rather than being forced here.
"""

from typing import Optional

from asgiref.sync import iscoroutinefunction, markcoroutinefunction

from depi.context import reset_current_scope, set_current_scope
from depi.integration import BaseInjector

__all__ = ['DjangoInjector', 'DepiScopeMiddleware', 'NoInjectorRegisteredError']

_active_injector: Optional['DjangoInjector'] = None


class NoInjectorRegisteredError(RuntimeError):
    """Raised when DepiScopeMiddleware runs before any injector registered itself."""


class DjangoInjector(BaseInjector):
    """
    Per-request dependency scopes for a Django project.

    Example:
        injector = DjangoInjector(provider)
        injector.setup()

        @injector.inject
        def my_view(request, provider):
            return JsonResponse(provider.resolve(DataService).payload())

    With ``autowire=True`` the view takes services directly::

        @injector.inject
        def my_view(request, service: DataService):
            return JsonResponse(service.payload())
    """

    def setup(self, app=None) -> None:
        """
        Register this injector as the one ``DepiScopeMiddleware`` resolves from.

        Django has no application object to attach to, so ``app`` is accepted
        and ignored to keep the integration interface uniform. Call this from
        ``AppConfig.ready()``.
        """
        global _active_injector
        _active_injector = self


def get_active_injector() -> 'DjangoInjector':
    """Return the registered injector, raising if setup() never ran."""
    if _active_injector is None:
        raise NoInjectorRegisteredError(
            "No depi injector registered. Call DjangoInjector(provider).setup() "
            "during startup, typically from AppConfig.ready(), before a request "
            "reaches DepiScopeMiddleware."
        )
    return _active_injector


def DepiScopeMiddleware(get_response):
    """
    Django middleware opening a dependency scope per request.

    Returns a sync or async middleware to match ``get_response``, so it does not
    force Django to adapt between the two.
    """
    if iscoroutinefunction(get_response):

        async def async_middleware(request):
            scope = get_active_injector().create_scope()
            token = set_current_scope(scope)
            try:
                return await get_response(request)
            finally:
                reset_current_scope(token)
                await scope.__aexit__(None, None, None)

        markcoroutinefunction(async_middleware)
        return async_middleware

    def sync_middleware(request):
        scope = get_active_injector().create_scope()
        token = set_current_scope(scope)
        try:
            return get_response(request)
        finally:
            reset_current_scope(token)
            scope.dispose()

    return sync_middleware
