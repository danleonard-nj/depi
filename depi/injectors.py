"""
Clean, fast framework-specific dependency injectors.

Flask/Quart: Pass ServiceScope directly as parameter
FastAPI: UPse Depends(get_scope) to inject ServiceScope
"""

from contextvars import ContextVar
from typing import Optional, TYPE_CHECKING
from abc import ABC, abstractmethod

if TYPE_CHECKING:
    from .services import ServiceProvider, ServiceScope

# Global context for current scope
_current_scope: ContextVar[Optional['ServiceScope']] = ContextVar('di_scope', default=None)


class BaseInjector(ABC):
    """Base injector with common functionality."""

    def __init__(self, provider: 'ServiceProvider'):
        self._provider = provider

    def create_scope(self) -> 'ServiceScope':
        """Create a new dependency scope."""
        return self._provider.create_scope()

    def get_current_scope(self) -> 'ServiceScope':
        """Get current scope (creates one if none exists)."""
        scope = _current_scope.get()
        if scope is None:
            # Fallback: create a temporary scope
            scope = self.create_scope()
        return scope

    @abstractmethod
    def setup(self, app):
        """Set up framework integration."""
        pass


class FlaskInjector(BaseInjector):
    """Flask injector - passes ServiceScope as 'provider' parameter."""

    def setup(self, app):
        """Set up Flask request scope management."""
        @app.before_request
        def setup_di_scope():
            scope = self.create_scope()
            _current_scope.set(scope)

        @app.teardown_request
        def teardown_di_scope(exception=None):
            scope = _current_scope.get()
            if scope:
                scope.dispose()
                _current_scope.set(None)

    def with_provider(self, fn):
        """Decorator that injects scope as 'provider' parameter."""
        def wrapper(*args, **kwargs):
            if 'provider' not in kwargs:
                kwargs['provider'] = self.get_current_scope()
            return fn(*args, **kwargs)

        wrapper.__name__ = fn.__name__
        wrapper.__module__ = fn.__module__
        wrapper.__doc__ = fn.__doc__
        return wrapper


class QuartInjector(BaseInjector):
    """Quart injector - passes ServiceScope as 'provider' parameter."""

    def setup(self, app):
        """Set up Quart request scope management."""
        @app.before_request
        async def setup_di_scope():
            scope = self.create_scope()
            _current_scope.set(scope)

        @app.teardown_request
        async def teardown_di_scope(exception=None):
            scope = _current_scope.get()
            if scope:
                if hasattr(scope, '__aexit__'):
                    await scope.__aexit__(None, None, None)
                else:
                    scope.dispose()
                _current_scope.set(None)

    def with_provider(self, fn):
        """Decorator that injects scope as 'provider' parameter."""
        async def wrapper(*args, **kwargs):
            if 'provider' not in kwargs:
                kwargs['provider'] = self.get_current_scope()
            return await fn(*args, **kwargs)

        wrapper.__name__ = fn.__name__
        wrapper.__module__ = fn.__module__
        wrapper.__doc__ = fn.__doc__
        return wrapper


class FastAPIInjector(BaseInjector):
    """FastAPI injector - uses Depends(get_provider)."""

    def setup(self, app):
        """Set up FastAPI middleware for scope management."""
        from fastapi import Request

        @app.middleware("http")
        async def di_middleware(request: Request, call_next):
            with self.create_scope() as scope:
                token = _current_scope.set(scope)
                try:
                    response = await call_next(request)
                    return response
                finally:
                    _current_scope.reset(token)

    def get_provider(self) -> 'ServiceScope':
        """FastAPI dependency function - use with Depends(injector.get_provider)."""
        return self.get_current_scope()


# Factory functions
def create_flask_injector(provider: 'ServiceProvider') -> FlaskInjector:
    """Create Flask injector."""
    return FlaskInjector(provider)


def create_quart_injector(provider: 'ServiceProvider') -> QuartInjector:
    """Create Quart injector."""
    return QuartInjector(provider)


def create_fastapi_injector(provider: 'ServiceProvider') -> FastAPIInjector:
    """Create FastAPI injector."""
    return FastAPIInjector(provider)


# =============================================================================
# Backward Compatibility - Update Existing DependencyInjector
# =============================================================================

class DependencyInjector:
    """
    Updated existing class to use the new clean approach.
    Maintains backward compatibility while being much cleaner.
    """

    def __init__(self, provider: 'ServiceProvider', strict: bool = False):
        self._provider = provider
        self._strict = strict  # Keep for compatibility

        # Create framework-specific injectors
        self._flask_injector = FlaskInjector(provider)
        self._quart_injector = QuartInjector(provider)
        self._fastapi_injector = FastAPIInjector(provider)

    def create_scope(self) -> 'ServiceScope':
        """Create a new dependency scope."""
        return self._provider.create_scope()

    def setup_fastapi(self, app):
        """Set up FastAPI integration."""
        return self._fastapi_injector.setup(app)

    def setup_flask(self, app):
        """Set up Flask integration."""
        return self._flask_injector.setup(app)

    def setup_quart(self, app):
        """Set up Quart integration."""
        return self._quart_injector.setup(app)


# Legacy alias for backward compatibility
FastAPIDependencyInjector = DependencyInjector
FlaskDependencyInjector = DependencyInjector
QuartDependencyInjector = DependencyInjector
