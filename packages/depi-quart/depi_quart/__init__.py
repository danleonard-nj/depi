"""
Quart integration.

The async counterpart to the Flask integration. Disposal goes through
``ServiceScope.__aexit__`` so scoped instances holding async resources get
awaited cleanup before the sync ``dispose()`` runs.
"""

from quart import g

from depi.context import reset_current_scope, set_current_scope
from depi.integration import BaseInjector

__all__ = ['QuartInjector']

_SCOPE_KEY = '_depi_scope'
_TOKEN_KEY = '_depi_token'


class QuartInjector(BaseInjector):
    """
    Per-request dependency scopes for a Quart app.

    Example:
        injector = QuartInjector(provider, param_name='container')
        injector.setup(app)

        @app.route('/data/<key>')
        @injector.inject
        async def get_data(key, container):
            return await container.resolve_async(DataService).get(key)

    ``inject`` uses functools.wraps, so it composes inside a decorator stack --
    route registration, auth, response handling -- without the outer layers
    losing the view function's identity.
    """

    def setup(self, app) -> None:
        """Install before/teardown request hooks on ``app``."""

        @app.before_request
        async def _open_depi_scope():
            scope = self.create_scope()
            setattr(g, _SCOPE_KEY, scope)
            setattr(g, _TOKEN_KEY, set_current_scope(scope))

        @app.teardown_request
        async def _close_depi_scope(exception=None):
            token = g.pop(_TOKEN_KEY, None)
            scope = g.pop(_SCOPE_KEY, None)
            if token is not None:
                reset_current_scope(token)
            if scope is not None:
                await scope.__aexit__(None, None, None)
