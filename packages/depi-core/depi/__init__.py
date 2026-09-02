"""
depi - a type-hint driven dependency injection container for Python.

Core is dependency-free and framework-agnostic. Web framework support ships as
separate distributions, each with its own top-level module, so importing
``depi`` never pulls in a web framework:

    pip install pydepi[flask]        # or: pip install pydepi-flask

    from depi_flask import FlaskInjector

Adapters build on :mod:`depi.context` and :mod:`depi.integration`.
"""

from .context import (
    NoActiveScopeError,
    current_scope,
    get_current_scope,
    reset_current_scope,
    set_current_scope,
    use_scope,
)
from .services import (
    ConstructorDependency,
    DependencyRegistration,
    Lifetime,
    ServiceCollection,
    ServiceProvider,
    ServiceScope,
)

__all__ = [
    # Container
    'ServiceCollection',
    'ServiceProvider',
    'ServiceScope',
    'Lifetime',
    'ConstructorDependency',
    'DependencyRegistration',

    # Ambient scope
    'NoActiveScopeError',
    'current_scope',
    'get_current_scope',
    'set_current_scope',
    'reset_current_scope',
    'use_scope',
]
