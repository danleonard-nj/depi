"""
Exception hierarchy.

Every error depi raises derives from :class:`DepiError`, so an application can
catch depi's failures without catching everything. The classes are grouped by
*when* the failure happens, because that maps to who can fix it:

- :class:`RegistrationError` -- the container was described wrongly. Raised while
  registering services or building a provider, i.e. at startup, before traffic.
- :class:`ResolutionError` -- the container was asked for something it could not
  produce. Raised at resolve time.

These live in their own module so both :mod:`depi.services` and
:mod:`depi.context` can import them without a cycle.

Backwards compatibility: depi previously raised bare ``Exception`` and, for the
async-factory guard, ``RuntimeError``. Every class here still derives from the
type it used to be, so existing ``except Exception`` and ``except RuntimeError``
handlers keep working unchanged.
"""

__all__ = [
    'DepiError',
    'RegistrationError',
    'MissingAnnotationError',
    'CircularDependencyError',
    'InvalidLifetimeError',
    'UnknownLifetimeError',
    'ResolutionError',
    'UnregisteredDependencyError',
    'ScopeRequiredError',
    'AsyncFactoryError',
    'NoActiveScopeError',
]


class DepiError(Exception):
    """Base class for every error raised by depi."""


# --------------------------------------------------------------------------
# Registration / build time: the container was described wrongly.
# --------------------------------------------------------------------------

class RegistrationError(DepiError):
    """Raised while registering services or building a provider."""


class MissingAnnotationError(RegistrationError):
    """
    A constructor parameter has no type annotation.

    depi resolves by annotation, so an unannotated parameter cannot be resolved.
    Raised at registration rather than at resolution, so it surfaces at startup.
    """


class CircularDependencyError(RegistrationError):
    """
    A dependency cycle was found while building the provider.

    Detected by static analysis at build time, so a cycle cannot reach
    production as a recursion error at request time.
    """


class InvalidLifetimeError(RegistrationError):
    """
    Two registrations combine in a way that breaks one of their lifetimes.

    In practice this is a singleton depending on a transient or scoped service:
    the dependency would be constructed exactly once, inside the singleton, and
    would silently stop behaving like a transient or a scoped service.
    """


class UnknownLifetimeError(RegistrationError):
    """A registration carries a lifetime depi does not recognise."""


# --------------------------------------------------------------------------
# Resolution time: the container could not produce what was asked for.
# --------------------------------------------------------------------------

class ResolutionError(DepiError):
    """Raised while resolving a service."""


class UnregisteredDependencyError(ResolutionError):
    """
    No registration exists for the requested type.

    Either the service was never registered, or it was registered under a
    different type -- an interface rather than the implementation, typically.
    """


class ScopeRequiredError(ResolutionError):
    """
    A scoped service was resolved without a scope.

    Call ``provider.create_scope()``, or resolve from the scope a framework
    integration opened for the current request.
    """


class AsyncFactoryError(ResolutionError, RuntimeError):
    """
    An async factory was resolved through the synchronous API.

    Also derives from RuntimeError, which is what this used to be, so existing
    ``except RuntimeError`` handlers still catch it.
    """


class NoActiveScopeError(DepiError, RuntimeError):
    """
    A request scope was needed but none is bound to the current context.

    Raised by :func:`depi.context.current_scope` when no integration has opened
    a scope -- typically because ``setup(app)`` never ran, or because the code
    is executing outside a request.

    Also derives from RuntimeError for backwards compatibility.
    """
