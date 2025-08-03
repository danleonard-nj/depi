"""
depi – A Modern, Type-Safe Dependency Injection Framework for Python

Provides:
- Type-hinted constructor injection
- Singleton, Transient, and Scoped lifetimes
- Async factory and constructor support
- FastAPI and Flask integration via middleware
"""

import logging
from threading import Lock
from functools import wraps
from typing import Any, Callable, Optional, Type
import asyncio
import inspect

logger = logging.getLogger(__name__)


class Lifetime:
    """
    Supported lifetimes for registered dependencies.
    """
    Singleton = 'singleton'
    Transient = 'transient'
    Scoped = 'scoped'


class ConstructorDependency:
    """
    Represents a single constructor parameter dependency.

    Attributes:
        name:        Name of the parameter in the constructor.
        dependency_type: The type annotation required.
    """

    def __init__(self, name: str, _type: type):
        self.name = name
        self.dependency_type = _type


class DependencyRegistration:
    """
    Holds metadata and factory logic for a single registered service.

    Attributes:
        dependency_type:     The abstract/base type.
        implementation_type: The concrete class to instantiate.
        lifetime:            Lifetime.Singleton, Transient, or Scoped.
        instance:            Stored instance for singletons.
        factory:             Optional callable(provider) → instance.
        constructor_params:  List of ConstructorDependency for auto-injection.
    """

    def __hash__(self):
        return hash(self.implementation_type)

    def __eq__(self, other):
        return isinstance(other, DependencyRegistration) and \
            self.implementation_type == other.implementation_type

    def __init__(
        self,
        dependency_type: type,
        lifetime: str,
        implementation_type: Optional[type] = None,
        instance: Any = None,
        factory: Callable[['DependencyRegistration'], Any] = None,
        constructor_params: list[ConstructorDependency] = None
    ):
        self.dependency_type = dependency_type
        self.lifetime = lifetime
        self.implementation_type = implementation_type or dependency_type
        self.instance = instance
        self.factory = factory
        self.constructor_params = constructor_params or []
        self._type_name = self.implementation_type.__name__

    def get_activate_constructor_params(
        self,
        dependency_lookup: dict[type, 'DependencyRegistration'],
        cache: dict,
        cache_lock: Lock
    ) -> dict[str, Any]:
        """
        Resolve and cache constructor parameters synchronously.
        """
        if not self.constructor_params:
            return {}

        # Return from cache if already built
        with cache_lock:
            if self.implementation_type in cache:
                return cache[self.implementation_type]

        constructor_args = {}
        for param in self.constructor_params:
            reg = dependency_lookup.get(param.dependency_type)
            if reg is None:
                raise Exception(
                    f"Failed to locate registration for '{param.dependency_type.__name__}' "
                    f"when activating '{self._type_name}'"
                )
            constructor_args[param.name] = reg.activate(dependency_lookup, cache, cache_lock)

        # Cache for future resolves
        with cache_lock:
            cache[self.implementation_type] = constructor_args

        return constructor_args

    async def get_activate_constructor_params_async(
        self,
        dependency_lookup: dict[type, 'DependencyRegistration'],
        cache: dict,
        cache_lock: Lock
    ) -> dict[str, Any]:
        """
        Resolve and cache constructor parameters asynchronously.
        """
        if not self.constructor_params:
            return {}

        with cache_lock:
            if self.implementation_type in cache:
                return cache[self.implementation_type]

        constructor_args = {}
        for param in self.constructor_params:
            reg = dependency_lookup.get(param.dependency_type)
            if reg is None:
                raise Exception(
                    f"Failed to locate registration for '{param.dependency_type.__name__}' "
                    f"when activating '{self._type_name}'"
                )
            constructor_args[param.name] = await reg.activate_async(dependency_lookup, cache, cache_lock)

        with cache_lock:
            cache[self.implementation_type] = constructor_args

        return constructor_args

    def activate(
        self,
        dependency_lookup: dict[type, 'DependencyRegistration'],
        cache: dict,
        cache_lock: Lock
    ) -> Any:
        """
        Instantiate this service according to its lifetime and factory/constructor logic.
        """
        # Return existing singleton
        if self.lifetime == Lifetime.Singleton and self.instance is not None:
            return self.instance

        # Use factory if provided
        if self.factory:
            return self.factory(self)

        # No dependencies: direct instantiation
        if not self.constructor_params:
            instance = self.implementation_type()
        else:
            kwargs = self.get_activate_constructor_params(dependency_lookup, cache, cache_lock)
            instance = self.implementation_type(**kwargs)

        # Cache singleton instance
        if self.lifetime == Lifetime.Singleton:
            self.instance = instance

        return instance

    async def activate_async(
        self,
        dependency_lookup: dict[type, 'DependencyRegistration'],
        cache: dict,
        cache_lock: Lock
    ) -> Any:
        """
        Async variant of `activate`, supporting coroutine factories and constructors.
        """
        if self.lifetime == Lifetime.Singleton and self.instance is not None:
            return self.instance

        if self.factory:
            result = self.factory(self)
            if asyncio.iscoroutine(result):
                return await result
            return result

        if not self.constructor_params:
            instance = self.implementation_type()
        else:
            kwargs = await self.get_activate_constructor_params_async(dependency_lookup, cache, cache_lock)
            instance = self.implementation_type(**kwargs)

        if self.lifetime == Lifetime.Singleton:
            self.instance = instance

        return instance


class ServiceCollection:
    """
    Collects service registrations before building a ServiceProvider.
    """

    def __init__(self):
        self._container: dict[type, DependencyRegistration] = {}

    def get_type_dependencies(self, _type: type) -> list[ConstructorDependency]:
        """
        Inspect __init__ signature to auto-discover constructor dependencies.
        """
        params = inspect.signature(_type).parameters
        deps = []
        for name, param in params.items():
            if param.annotation == inspect.Parameter.empty:
                raise Exception(f"Missing type annotation for parameter '{name}' in {_type.__name__}")
            deps.append(ConstructorDependency(name=name, _type=param.annotation))
        return deps

    def add(
        self,
        dependency_type: type,
        implementation_type: Optional[type] = None,
        **kwargs
    ):
        """
        Shorthand to register a service (default: Transient).
        """
        kwargs.setdefault('lifetime', Lifetime.Transient)
        self._register_dependency(dependency_type, implementation_type, **kwargs)

    def add_singleton(
        self,
        dependency_type: type,
        implementation_type: Optional[type] = None,
        instance: Any = None,
        factory: Callable = None
    ) -> None:
        """Register a singleton service."""
        self._register_dependency(
            dependency_type=dependency_type,
            implementation_type=implementation_type,
            lifetime=Lifetime.Singleton,
            instance=instance,
            factory=factory
        )

    def add_transient(
        self,
        dependency_type: type,
        implementation_type: Optional[type] = None,
        factory: Callable = None
    ) -> None:
        """Register a transient service."""
        self._register_dependency(
            dependency_type=dependency_type,
            implementation_type=implementation_type,
            lifetime=Lifetime.Transient,
            factory=factory
        )

    def add_scoped(
        self,
        dependency_type: type,
        implementation_type: Optional[type] = None,
        factory: Callable = None
    ) -> None:
        """Register a scoped service."""
        self._register_dependency(
            dependency_type=dependency_type,
            implementation_type=implementation_type,
            lifetime=Lifetime.Scoped,
            factory=factory
        )

    def register_many(self, types: list[type], lifetime: str = Lifetime.Transient):
        """
        Bulk-register multiple types with the same lifetime.
        """
        for t in types:
            getattr(self, f"add_{lifetime.lower()}")(t)

    def _register_dependency(
        self,
        dependency_type: type,
        implementation_type: Optional[type],
        **kwargs
    ) -> None:
        """
        Internal helper to create and store a DependencyRegistration.
        """
        impl = implementation_type or dependency_type
        # Only inspect constructor if no factory is provided
        constructor_params = (
            self.get_type_dependencies(impl)
            if kwargs.get('factory') is None else []
        )
        reg = DependencyRegistration(
            dependency_type=dependency_type,
            implementation_type=impl,
            constructor_params=constructor_params,
            **kwargs
        )
        self._container[dependency_type] = reg

    def get_container(self) -> dict[type, DependencyRegistration]:
        """Expose raw registration dictionary."""
        return self._container

    def build_provider(self) -> 'ServiceProvider':
        """
        Finalize registrations and return a built ServiceProvider.
        """
        provider = ServiceProvider(self)
        provider.build()
        return provider


class ServiceProvider:
    """
    Resolves and caches instances according to registration metadata.

    Key methods:
      - resolve(type)      → sync instance
      - resolve_async(type)→ async instance
      - build() / build_async() → pre-instantiate singletons
      - create_scope() → new ServiceScope for scoped lifetimes
    """

    def __init__(self, service_collection: ServiceCollection):
        self._service_collection = service_collection
        self._dependency_lookup = service_collection.get_container()
        self._dependencies = list(self._dependency_lookup.values())
        self._singleton_instances: dict[type, Any] = {}
        self._cache: dict = {}
        self._cache_lock = Lock()
        self._initialize_provider()

    def _initialize_provider(self) -> None:
        """Partition registrations by lifetime and factory presence."""
        self._singletons = [
            d for d in self._dependencies
            if d.lifetime == Lifetime.Singleton and not d.factory
        ]
        self._factories = [
            d for d in self._dependencies
            if d.lifetime == Lifetime.Singleton and d.factory
        ]
        self._transients = [
            d for d in self._dependencies
            if d.lifetime == Lifetime.Transient
        ]

    def resolve(self, _type: type) -> Any:
        """
        Resolve a registered service synchronously.
        Raises if attempting to resolve Scoped outside of a scope.
        """
        reg = self._get_registered_dependency(_type)

        if reg.lifetime == Lifetime.Singleton:
            # Return cached or create & cache
            with self._cache_lock:
                if _type in self._singleton_instances:
                    return self._singleton_instances[_type]
            if reg.instance is not None:
                with self._cache_lock:
                    self._singleton_instances[_type] = reg.instance
                return reg.instance
            if reg.factory:
                instance = reg.factory(self)
                reg.instance = instance
                with self._cache_lock:
                    self._singleton_instances[_type] = instance
                return instance
            instance = reg.activate(self._dependency_lookup, self._cache, self._cache_lock)
            with self._cache_lock:
                self._singleton_instances[_type] = instance
            return instance

        if reg.lifetime == Lifetime.Transient:
            return reg.factory(self) if reg.factory else reg.activate(
                self._dependency_lookup, self._cache, self._cache_lock
            )

        if reg.lifetime == Lifetime.Scoped:
            raise Exception("Scoped resolution requires a scope. Call provider.create_scope().")

        raise Exception(f"Unknown lifetime: {reg.lifetime}")

    async def resolve_async(self, _type: type) -> Any:
        """
        Resolve a registered service asynchronously.
        """
        reg = self._get_registered_dependency(_type)

        if reg.lifetime == Lifetime.Singleton:
            with self._cache_lock:
                if _type in self._singleton_instances:
                    return self._singleton_instances[_type]
            if reg.instance is not None:
                with self._cache_lock:
                    self._singleton_instances[_type] = reg.instance
                return reg.instance
            if reg.factory:
                inst = reg.factory(self)
                if asyncio.iscoroutine(inst):
                    inst = await inst
                reg.instance = inst
                with self._cache_lock:
                    self._singleton_instances[_type] = inst
                return inst
            inst = await reg.activate_async(self._dependency_lookup, self._cache, self._cache_lock)
            with self._cache_lock:
                self._singleton_instances[_type] = inst
            return inst

        if reg.lifetime == Lifetime.Transient:
            inst = reg.factory(self) if reg.factory else await reg.activate_async(
                self._dependency_lookup, self._cache, self._cache_lock
            )
            return await inst if asyncio.iscoroutine(inst) else inst

        if reg.lifetime == Lifetime.Scoped:
            raise Exception("Scoped resolution requires a scope. Call provider.create_scope().")

        raise Exception(f"Unknown lifetime: {reg.lifetime}")

    def _get_registered_dependency(
        self,
        implementation_type: type,
        requesting_type: Optional[DependencyRegistration] = None
    ) -> DependencyRegistration:
        """
        Lookup registration or error out, optionally showing context.
        """
        reg = self._dependency_lookup.get(implementation_type)
        if reg:
            return reg
        if requesting_type:
            raise Exception(
                f"Failed to locate registration for '{implementation_type.__name__}' "
                f"while instantiating '{requesting_type._type_name}'"
            )
        raise Exception(f"Failed to locate registration for '{implementation_type.__name__}'")

    def _topological_sort(self, dependencies: list[DependencyRegistration]) -> list[DependencyRegistration]:
        """
        Perform DFS-based topological sort to detect cycles and order singletons.
        """
        visited = set()
        visiting = set()
        order: list[DependencyRegistration] = []

        def dfs(dep: DependencyRegistration):
            if dep in visited:
                return
            if dep in visiting:
                raise Exception(f"Cyclic dependency detected: {dep._type_name}")
            visiting.add(dep)
            for param in dep.constructor_params:
                next_dep = self._get_registered_dependency(param.dependency_type, dep)
                dfs(next_dep)
            visiting.remove(dep)
            visited.add(dep)
            order.append(dep)

        for d in dependencies:
            dfs(d)
        return order

    def build(self) -> 'ServiceProvider':
        """
        Instantiate all singletons in dependency order.
        """
        to_build = [d for d in self._dependencies if d.lifetime == Lifetime.Singleton]
        sorted_deps = self._topological_sort(to_build)
        for reg in sorted_deps:
            if reg.instance is None:
                if reg.factory:
                    inst = reg.factory(self)
                    # support coroutine factories
                    if asyncio.iscoroutine(inst):
                        try:
                            loop = asyncio.get_running_loop()
                            # run in separate thread if already in event loop
                            import concurrent.futures
                            with concurrent.futures.ThreadPoolExecutor() as ex:
                                inst = ex.submit(asyncio.run, inst).result()
                        except RuntimeError:
                            inst = asyncio.run(inst)
                else:
                    inst = reg.activate(self._dependency_lookup, self._cache, self._cache_lock)
                reg.instance = inst
                with self._cache_lock:
                    self._singleton_instances[reg.dependency_type] = inst
        return self

    async def build_async(self) -> 'ServiceProvider':
        """
        Async variant of build(), awaiting any coroutine constructors or factories.
        """
        to_build = [d for d in self._dependencies if d.lifetime == Lifetime.Singleton]
        sorted_deps = self._topological_sort(to_build)
        for reg in sorted_deps:
            if reg.instance is None:
                if reg.factory:
                    inst = reg.factory(self)
                    if asyncio.iscoroutine(inst):
                        inst = await inst
                else:
                    inst = await reg.activate_async(self._dependency_lookup, self._cache, self._cache_lock)
                reg.instance = inst
                with self._cache_lock:
                    self._singleton_instances[reg.dependency_type] = inst
        return self

    def create_scope(self) -> 'ServiceScope':
        """Begin a new scoped lifetime context."""
        return ServiceScope(self)


class ServiceScope:
    """
    Provides scoped resolution: Singleton → cascades to provider, Transient → new each call,
    Scoped → one per scope instance.
    """

    def __init__(self, provider: ServiceProvider):
        self._provider = provider
        self._scoped_instances: dict[type, Any] = {}
        self._dependency_lookup = provider._dependency_lookup
        self._cache: dict = {}
        self._cache_lock = Lock()

    def __enter__(self) -> 'ServiceScope':
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.dispose()

    async def __aenter__(self) -> 'ServiceScope':
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        # Allow async cleanup handlers on scoped instances
        for inst in self._scoped_instances.values():
            if hasattr(inst, '__aexit__'):
                await inst.__aexit__(exc_type, exc_value, traceback)
        self.dispose()

    def resolve(self, _type: type) -> Any:
        """
        Resolve within this scope.
        """
        reg = self._provider._get_registered_dependency(_type)
        if reg.lifetime == Lifetime.Singleton:
            return self._provider.resolve(_type)
        if reg.lifetime == Lifetime.Transient:
            return reg.factory(self) if reg.factory else reg.activate(
                self._dependency_lookup, self._cache, self._cache_lock
            )
        if reg.lifetime == Lifetime.Scoped:
            if _type not in self._scoped_instances:
                inst = reg.factory(self) if reg.factory else reg.activate(
                    self._dependency_lookup, self._cache, self._cache_lock
                )
                self._scoped_instances[_type] = inst
            return self._scoped_instances[_type]
        raise Exception(f"Unknown lifetime: {reg.lifetime}")

    async def resolve_async(self, _type: type) -> Any:
        """
        Async variant of resolve.
        """
        reg = self._provider._get_registered_dependency(_type)
        if reg.lifetime == Lifetime.Singleton:
            return await self._provider.resolve_async(_type)
        if reg.lifetime == Lifetime.Transient:
            inst = reg.factory(self) if reg.factory else await reg.activate_async(
                self._dependency_lookup, self._cache, self._cache_lock
            )
            if asyncio.iscoroutine(inst):
                return await inst
            return inst
        if reg.lifetime == Lifetime.Scoped:
            if _type not in self._scoped_instances:
                inst = reg.factory(self) if reg.factory else await reg.activate_async(
                    self._dependency_lookup, self._cache, self._cache_lock
                )
                self._scoped_instances[_type] = inst
            return self._scoped_instances[_type]
        raise Exception(f"Unknown lifetime: {reg.lifetime}")

    def dispose(self) -> None:
        """
        Clear scoped instances and internal cache.
        """
        self._scoped_instances.clear()
        self._cache.clear()


class DependencyInjector:
    """
    Decorator and middleware helper for auto-injecting dependencies
    into function parameters based on type annotations.
    """

    def __init__(self, provider: ServiceProvider, strict: bool = False):
        self._provider = provider
        self._strict = strict

    def create_scope(self) -> ServiceScope:
        """Expose ability to create a manual scope."""
        return self._provider.create_scope()

    def inject(self, fn: Callable) -> Callable:
        """
        Decorator for functions (sync or async). Fills annotated params
        from the active scope (attached via middleware).
        """
        sig = inspect.signature(fn)

        @wraps(fn)
        async def wrapper(*args, **kwargs):
            if not hasattr(wrapper, '_scope') or wrapper._scope is None:
                raise Exception("No active ServiceScope. Did you apply DI middleware?")
            scope: ServiceScope = wrapper._scope

            for name, param in sig.parameters.items():
                if name in kwargs or param.annotation == inspect.Parameter.empty:
                    continue
                try:
                    if asyncio.iscoroutinefunction(fn):
                        kwargs[name] = await scope.resolve_async(param.annotation)
                    else:
                        kwargs[name] = scope.resolve(param.annotation)
                except Exception as e:
                    if self._strict:
                        raise Exception(
                            f"Failed to resolve dependency '{param.annotation.__name__}' "
                            f"for '{name}': {e}"
                        )
                    logger.debug(f"Skipping DI for '{name}': {e}")

            return await fn(*args, **kwargs) if asyncio.iscoroutinefunction(fn) else fn(*args, **kwargs)

        # Placeholder for middleware to set
        wrapper._scope: Optional[ServiceScope] = None
        return wrapper

    def setup_fastapi(self, app):
        """
        Install FastAPI middleware to create a new scope per request,
        attach it to request.state.scope, and wire decorated endpoints.
        """
        from fastapi import Request

        @app.middleware("http")
        async def di_middleware(request: Request, call_next):
            with self.create_scope() as scope:
                request.state.scope = scope
                # Attach scope to all @inject endpoints
                for route in app.routes:
                    if hasattr(route.endpoint, '_scope'):
                        route.endpoint._scope = scope
                return await call_next(request)

    def setup_flask(self, app):
        """
        Install Flask hooks to manage a scope per request via flask.g.
        """
        from flask import g

        @app.before_request
        def before_request():
            g.scope = self.create_scope()

        @app.teardown_request
        def teardown_request(exception=None):
            if hasattr(g, 'scope'):
                g.scope.dispose()

        # Wrap each decorated view so it gets the current scope
        for rule in app.url_map.iter_rules():
            endpoint = app.view_functions[rule.endpoint]
            if hasattr(endpoint, '_scope'):
                @wraps(endpoint)
                def wrapped_view(*args, **kwargs):
                    endpoint._scope = g.scope
                    return endpoint(*args, **kwargs)
                app.view_functions[rule.endpoint] = wrapped_view
