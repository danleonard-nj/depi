"""
depi – A Modern, Type-Safe Dependency Injection Framework for Python
"""

from .services import (
    ServiceCollection,
    ServiceProvider,
    ServiceScope,
    Lifetime,
    ConstructorDependency,
    DependencyRegistration
)

from .injectors import (
    BaseInjector,
    FlaskInjector,
    QuartInjector,
    FastAPIInjector,
    DependencyInjector,  # Backward compatibility
    create_fastapi_injector,
    create_flask_injector,
    create_quart_injector
)

__all__ = [
    # Core services
    'ServiceCollection',
    'ServiceProvider',
    'ServiceScope',
    'Lifetime',
    'ConstructorDependency',
    'DependencyRegistration',

    # Framework-specific injectors
    'BaseInjector',
    'FlaskInjector',
    'QuartInjector',
    'FastAPIInjector',
    'create_fastapi_injector',
    'create_flask_injector',
    'create_quart_injector',

    # Legacy (deprecated)
    'DependencyInjector',
]
