"""
FastAPI integration.

Scope management is a pure ASGI middleware rather than an ``http`` middleware
decorator, for two reasons: the contextvar is then set in the same context the
endpoint coroutine runs in, and disposal happens after the response body has
been sent rather than after the handler returns.

Injection is via ``Depends``. FastAPI derives request parsing and the OpenAPI
schema from the endpoint signature, so depi does not touch signatures here --
see :meth:`FastAPIInjector.inject`.
"""

from typing import TYPE_CHECKING

from depi.context import reset_current_scope, set_current_scope
from depi.integration import BaseInjector

if TYPE_CHECKING:
    from depi.services import ServiceProvider, ServiceScope

__all__ = ['FastAPIInjector']


class FastAPIInjector(BaseInjector):
    """
    Per-request dependency scopes for a FastAPI app.

    Example:
        injector = FastAPIInjector(provider)
        injector.setup(app)

        @app.get('/data/{key}')
        async def get_data(key: str, scope=Depends(injector.get_scope)):
            return scope.resolve(DataService).get(key)
    """

    def __init__(
        self,
        provider: 'ServiceProvider',
        param_name: str = 'provider',
        autowire: bool = False
    ):
        if autowire:
            raise ValueError(
                "FastAPIInjector does not support autowire=True. FastAPI builds "
                "request parsing and the OpenAPI schema from the endpoint "
                "signature, and raises FastAPIError at decoration time for any "
                "annotation it cannot treat as a Pydantic field. Hiding service "
                "parameters would mean rewriting __signature__ before FastAPI "
                "sees the endpoint, which is fragile across FastAPI releases. "
                "Use Depends(injector.get_scope) instead."
            )
        super().__init__(provider, param_name=param_name, autowire=autowire)

    def setup(self, app) -> None:
        """Install the ASGI scope middleware on ``app``."""
        provider = self._provider

        class _DepiScopeMiddleware:
            # The parameter must be named `app`: Starlette <= 0.27 instantiates
            # middleware as cls(app=..., **options) with app as a KEYWORD
            # argument, while newer Starlette passes it positionally. Naming it
            # anything else breaks every FastAPI at or below the declared floor.
            def __init__(self, app):
                self.app = app

            async def __call__(self, scope, receive, send):
                if scope['type'] not in ('http', 'websocket'):
                    await self.app(scope, receive, send)
                    return

                di_scope = provider.create_scope()
                token = set_current_scope(di_scope)
                try:
                    await self.app(scope, receive, send)
                finally:
                    reset_current_scope(token)
                    await di_scope.__aexit__(None, None, None)

        app.add_middleware(_DepiScopeMiddleware)

    def get_scope(self) -> 'ServiceScope':
        """
        FastAPI dependency returning the request scope.

        Use as ``Depends(injector.get_scope)``.
        """
        return self.current_scope()

    def inject(self, fn):
        """
        Not supported. Use ``Depends(get_scope)``.

        A wrapper built with functools.wraps sets ``__wrapped__``, and
        ``inspect.signature`` follows it by default -- so FastAPI would still
        see the injected parameter and fail on it. There is no version of this
        decorator that works without signature rewriting.
        """
        raise NotImplementedError(
            "FastAPIInjector.inject is not supported; FastAPI reads the endpoint "
            "signature to build request parsing and the OpenAPI schema. "
            "Use Depends(injector.get_scope) and resolve from the scope."
        )
