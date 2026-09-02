"""
Ambient scope tracking.

Framework integrations bind a :class:`~depi.services.ServiceScope` to the
current request or task context so view functions can reach it without it being
threaded through every call.

This lives in core rather than in an integration on purpose: every integration
needs the *same* contextvar. If each one owned a private one, a scope opened by
the Flask integration would be invisible to anything reading through another,
and nested/mixed stacks (an ASGI app mounting a WSGI app, say) would silently
resolve against the wrong scope.
"""

from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import TYPE_CHECKING, Iterator, Optional

if TYPE_CHECKING:
    from .services import ServiceScope

__all__ = [
    'NoActiveScopeError',
    'current_scope',
    'get_current_scope',
    'set_current_scope',
    'reset_current_scope',
    'use_scope',
]


_current_scope: ContextVar[Optional['ServiceScope']] = ContextVar(
    'depi_current_scope', default=None
)


class NoActiveScopeError(RuntimeError):
    """
    Raised when a scope is required but none is bound to the current context.

    Subclasses RuntimeError so existing ``except RuntimeError`` handlers keep
    working.
    """


def get_current_scope() -> Optional['ServiceScope']:
    """Return the scope bound to the current context, or None if there is none."""
    return _current_scope.get()


def current_scope() -> 'ServiceScope':
    """
    Return the scope bound to the current context.

    Raises:
        NoActiveScopeError: if no scope is bound.
    """
    scope = _current_scope.get()
    if scope is None:
        raise NoActiveScopeError(
            "No active depi scope. Ensure the integration's setup(app) ran and that "
            "this code runs inside a request handled by its middleware."
        )
    return scope


def set_current_scope(scope: Optional['ServiceScope']) -> Token:
    """
    Bind a scope to the current context.

    Returns the token needed to restore the previous value; pass it to
    :func:`reset_current_scope`. Prefer :func:`use_scope` where the bind and
    restore happen in the same frame.
    """
    return _current_scope.set(scope)


def reset_current_scope(token: Token) -> None:
    """Restore the scope that was bound before ``token`` was issued."""
    _current_scope.reset(token)


@contextmanager
def use_scope(scope: 'ServiceScope') -> Iterator['ServiceScope']:
    """
    Bind ``scope`` for the duration of the block, then restore the previous one.

    Note this only binds the scope; it does not dispose it. Disposal stays with
    whoever created the scope, since integrations differ on when it is safe
    (Flask at teardown_request, ASGI after the response body is sent).
    """
    token = _current_scope.set(scope)
    try:
        yield scope
    finally:
        _current_scope.reset(token)
