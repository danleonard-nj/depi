"""
The contract every depi framework integration is built on.

This lives in core, and stays dependency-free: adapters ship as separate
distributions (pydepi-flask, pydepi-quart, ...) and all build against this.

Integrations are deliberately thin: they open a :class:`ServiceScope` per
request, bind it to the ambient context (see :mod:`depi.context`), dispose it
when the request ends, and offer a decorator to hand that scope to a view
function. Everything above that -- authentication, response shaping, blueprint
conventions -- belongs to the application, not to depi.
"""

import inspect
from abc import ABC, abstractmethod
from functools import wraps
from typing import TYPE_CHECKING, Any, Callable, Dict

from .context import current_scope
from .services import get_signature

if TYPE_CHECKING:
    from .services import ServiceProvider, ServiceScope

__all__ = ['BaseInjector', 'injectable_parameters']

_VARIADIC = (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)


def injectable_parameters(
    fn: Callable,
    provider: 'ServiceProvider'
) -> Dict[str, type]:
    """
    Map parameter name -> registered type for the parameters depi should supply.

    Parameters the provider does not know about are left alone, because the web
    framework almost certainly owns them (URL converters, query arguments). That
    is why autowire cannot fail fast on an unresolvable annotation: from here,
    "unregistered" and "supplied by the framework" look identical.

    Called once at decoration time, never per request.
    """
    try:
        parameters = get_signature(fn).parameters
    except (ValueError, TypeError, NameError):
        # Unintrospectable callable (some builtins) or an annotation that will
        # not evaluate. Nothing to autowire; the caller degrades to no-op.
        return {}

    injectable = {}
    for name, param in parameters.items():
        if param.kind in _VARIADIC:
            continue
        annotation = param.annotation
        if annotation is inspect.Parameter.empty:
            continue
        if isinstance(annotation, type) and provider.is_registered(annotation):
            injectable[name] = annotation
    return injectable


class BaseInjector(ABC):
    """Base class for framework integrations."""

    def __init__(
        self,
        provider: 'ServiceProvider',
        param_name: str = 'provider',
        autowire: bool = False
    ):
        """
        Args:
            provider: the built ServiceProvider to resolve from.
            param_name: the keyword argument the request scope is passed as in
                the default (non-autowire) mode. Name it to taste -- ``container``
                is a common alternative.
            autowire: when True, :meth:`inject` resolves registered types by
                annotation instead of passing the scope. Not supported by every
                integration; FastAPI rejects it outright.
        """
        self._provider = provider
        self._param_name = param_name
        self._autowire = autowire

    @property
    def provider(self) -> 'ServiceProvider':
        """The provider this injector resolves from."""
        return self._provider

    def create_scope(self) -> 'ServiceScope':
        """Create a new, unbound dependency scope."""
        return self._provider.create_scope()

    def current_scope(self) -> 'ServiceScope':
        """
        Return the scope bound to the current request context.

        Raises:
            NoActiveScopeError: if setup(app) never ran, or this is called
                outside a request.
        """
        return current_scope()

    @abstractmethod
    def setup(self, app) -> None:
        """Install per-request scope management onto ``app``."""

    def _make_inject_wrapper(self, fn: Callable) -> Callable:
        """
        Build the injecting wrapper for ``fn``.

        Resolution work that can be done once (signature inspection) is done
        here, at decoration time, so the per-request path stays a dict lookup.
        """
        param_name = self._param_name

        if self._autowire:
            targets = injectable_parameters(fn, self._provider)

            def apply(kwargs: Dict[str, Any]) -> None:
                # The ambient scope is fetched lazily, and only if something is
                # actually missing -- so a view whose services were all passed
                # in can be called straight from a test with no request context.
                scope = None
                for name, _type in targets.items():
                    if name in kwargs:
                        continue
                    if scope is None:
                        scope = current_scope()
                    kwargs[name] = scope.resolve(_type)
        else:
            def apply(kwargs: Dict[str, Any]) -> None:
                # An explicitly passed scope wins, which is what makes a view
                # callable directly from a test with a hand-built scope.
                if param_name not in kwargs:
                    kwargs[param_name] = current_scope()

        if inspect.iscoroutinefunction(fn):
            @wraps(fn)
            async def async_wrapper(*args, **kwargs):
                apply(kwargs)
                return await fn(*args, **kwargs)
            return async_wrapper

        @wraps(fn)
        def sync_wrapper(*args, **kwargs):
            apply(kwargs)
            return fn(*args, **kwargs)
        return sync_wrapper

    def inject(self, fn: Callable) -> Callable:
        """
        Decorator handing the request scope to ``fn``.

        Default mode passes the scope as the ``param_name`` keyword argument.
        With ``autowire=True``, parameters annotated with registered types are
        resolved and passed individually instead.

        Uses functools.wraps, so it composes inside a decorator stack (route
        registration, auth, response handling) without losing the wrapped
        function's identity.
        """
        return self._make_inject_wrapper(fn)
