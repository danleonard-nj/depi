"""
Flask integration.

Opens a request-scoped :class:`ServiceScope` in ``before_request`` and disposes
it in ``teardown_request``. The scope and its contextvar token are parked on
``flask.g`` so teardown restores exactly the context it replaced -- Werkzeug
reuses worker threads, so a contextvar set and never reset would leak into the
next request served by that thread.
"""

from flask import g

from depi.context import reset_current_scope, set_current_scope
from depi.integration import BaseInjector

__all__ = ['FlaskInjector']

_SCOPE_KEY = '_depi_scope'
_TOKEN_KEY = '_depi_token'


class FlaskInjector(BaseInjector):
    """
    Per-request dependency scopes for a Flask app.

    Example:
        injector = FlaskInjector(provider)
        injector.setup(app)

        @app.route('/data/<key>')
        @injector.inject
        def get_data(key, provider):
            return provider.resolve(DataService).get(key)

    With ``autowire=True``, registered types are resolved by annotation instead::

        injector = FlaskInjector(provider, autowire=True)

        @app.route('/data/<key>')
        @injector.inject
        def get_data(key, service: DataService):
            return service.get(key)

    ``key`` is left for Flask to fill from the URL rule, because DataService is
    registered and ``str`` is not.
    """

    def setup(self, app) -> None:
        """Install before/teardown request hooks on ``app``."""

        @app.before_request
        def _open_depi_scope():
            scope = self.create_scope()
            setattr(g, _SCOPE_KEY, scope)
            setattr(g, _TOKEN_KEY, set_current_scope(scope))

        @app.teardown_request
        def _close_depi_scope(exception=None):
            token = g.pop(_TOKEN_KEY, None)
            scope = g.pop(_SCOPE_KEY, None)
            if token is not None:
                reset_current_scope(token)
            if scope is not None:
                scope.dispose()
