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
from functools import lru_cache
from functools import wraps
from typing import Any, Callable, Optional, Type
import asyncio
import inspect

logger = logging.getLogger(__name__)


@lru_cache(maxsize=None)
def get_signature(fn):
    return inspect.signature(fn)


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
    __slots__ = (
        "dependency_type", "implementation_type", "lifetime", "instance", "factory",
        "constructor_params", "_type_name", "_resolver_fn"
    )

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

    def activate(
        self,
        provider=None
    ) -> Any:
        """
        Instantiate this service according to its lifetime and factory/constructor logic.
        """
        if not self.constructor_params:
            instance = self.implementation_type()
        else:
            kwargs = {param.name: provider.resolve(param.dependency_type) for param in self.constructor_params}
            instance = self.implementation_type(**kwargs)
        return instance

    async def activate_async(
        self,
        provider=None
    ) -> Any:
        """
        Async variant of activate, supporting coroutine factories and constructors.
        """
        if not self.constructor_params:
            return self.implementation_type()
        else:
            kwargs = {}
            for param in self.constructor_params:
                kwargs[param.name] = await provider.resolve_async(param.dependency_type)
            return self.implementation_type(**kwargs)


class ServiceCollection:
    """
    Collects service registrations before building a ServiceProvider.
    """

    __slots__ = ("name", "dependency_type", "_container")

    def __init__(self):
        self._container: dict[type, DependencyRegistration] = {}

    def get_type_dependencies(self, _type: type) -> list[ConstructorDependency]:
        """
        Inspect __init__ signature to auto-discover constructor dependencies.
        """
        params = get_signature(_type).parameters
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

        constructor_params = (
            self.get_type_dependencies(impl)
            if kwargs.get('factory') is None else []
        )

        def resolver_fn(provider, *_):
            return impl(
                **{
                    param.name: provider.resolve(param.dependency_type)
                    for param in constructor_params
                }
            )

        reg = DependencyRegistration(
            dependency_type=dependency_type,
            implementation_type=impl,
            constructor_params=constructor_params,
            **kwargs
        )
        reg._resolver_fn = resolver_fn
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

    __slots__ = (
        '_service_collection', '_dependency_lookup', '_dependencies', '_singleton_instances',
        '_cache', '_cache_lock', '_singletons', '_factories', '_transients'
    )

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
        Optimized with fast path for singletons and minimal locking.
        """
        reg = self._get_registered_dependency(_type)
        lifetime = reg.lifetime

        if lifetime == Lifetime.Singleton:
            # Avoid repeated dict and attribute lookups
            cache = self._singleton_instances

            instance = cache.get(_type)
            if instance is not None:
                return instance

            with self._cache_lock:
                instance = cache.get(_type)
                if instance is not None:
                    return instance

                if reg.factory:
                    instance = reg.factory(self)
                elif reg.instance is not None:
                    instance = reg.instance
                else:
                    instance = reg.activate(self)

                cache[_type] = instance
                return instance

        elif lifetime == Lifetime.Transient:
            return reg.factory(self) if reg.factory else reg.activate(self)

        elif lifetime == Lifetime.Scoped:
            raise Exception("Scoped resolution requires a scope. Call provider.create_scope().")

        raise Exception(f"Unknown lifetime: {lifetime}")

    async def resolve_async(self, _type: type) -> Any:
        """
        Resolve a registered service asynchronously.
        Optimized with fast path for singletons and minimal locking.
        """
        reg = self._get_registered_dependency(_type)

        if reg.lifetime == Lifetime.Singleton:
            # Fast path: lock-free cache check (covers 99% of singleton calls)
            instance = self._singleton_instances.get(_type)
            if instance is not None:
                return instance

            # Slow path: need to create singleton (double-checked locking)
            with self._cache_lock:
                # Double-check in case another thread created it
                instance = self._singleton_instances.get(_type)
                if instance is not None:
                    return instance

                # Create new singleton
                if reg.factory:
                    inst = reg.factory(self)
                    if asyncio.iscoroutine(inst):
                        inst = await inst
                    instance = inst
                elif reg.instance is not None:
                    # Pre-built during build() phase
                    instance = reg.instance
                else:
                    # Lazy singleton
                    instance = await reg.activate_async(self)

                # Cache and return
                self._singleton_instances[_type] = instance
                return instance

        elif reg.lifetime == Lifetime.Transient:
            if reg.factory:
                inst = reg.factory(self)
                return await inst if asyncio.iscoroutine(inst) else inst
            else:
                return await reg.activate_async(self)

        elif reg.lifetime == Lifetime.Scoped:
            raise Exception("Scoped resolution requires a scope. Call provider.create_scope().")

        else:
            raise Exception(f"Unknown lifetime: {reg.lifetime}")

        if reg.lifetime == Lifetime.Transient:
            inst = reg.factory(self) if reg.factory else await reg.activate_async(self)
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
                    inst = reg.activate(self)
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
                    inst = await reg.activate_async(self)
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

    __slots__ = (
        '_provider', '_scoped_instances', '_dependency_lookup',
        '_cache', '_cache_lock'
    )

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
        provider = self._provider
        reg = provider._get_registered_dependency(_type)
        life = reg.lifetime

        # Singleton always via root provider
        if life is Lifetime.Singleton:
            return provider.resolve(_type)

        insts = self._scoped_instances

        # Scoped: return cached if present
        if life is Lifetime.Scoped:
            inst = insts.get(_type)
            if inst is not None:
                return inst

        # Transient or new Scoped instance
        factory = reg.factory
        if factory:
            inst = factory(self)
        else:
            # your precompiled sync resolver
            inst = reg._resolver_fn(self)

        # Cache scoped
        if life is Lifetime.Scoped:
            insts[_type] = inst

        return inst

    async def resolve_async(self, _type: type) -> Any:
        provider = self._provider
        reg = provider._get_registered_dependency(_type)
        life = reg.lifetime

        # Singleton via root provider
        if life is Lifetime.Singleton:
            return await provider.resolve_async(_type)

        insts = self._scoped_instances

        # Scoped: return cached if present
        if life is Lifetime.Scoped:
            inst = insts.get(_type)
            if inst is not None:
                return inst

        # Transient or new Scoped instance
        factory = reg.factory
        if factory:
            inst = factory(self)
            if asyncio.iscoroutine(inst):
                inst = await inst
        else:
            # fall back to the generic async activation
            inst = await reg.activate_async(self)

        # Cache scoped
        if life is Lifetime.Scoped:
            insts[_type] = inst

        return inst

    def dispose(self) -> None:
        """
        Clear scoped instances and internal cache. Call dispose on disposable instances.
        """
        # Dispose of any disposable instances
        for instance in self._scoped_instances.values():
            if hasattr(instance, 'dispose') and callable(getattr(instance, 'dispose')):
                try:
                    instance.dispose()
                except Exception as e:
                    logger.warning(f"Error disposing scoped instance: {e}")

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
        In strict mode, attempts to inject all annotated parameters.
        In non-strict mode, only injects parameters that are registered.
        """
        sig = get_signature(fn)
        is_async = asyncio.iscoroutinefunction(fn)

        # Create a new signature removing injectable parameters for FastAPI compatibility
        new_params = []
        injectable_params = {}

        for name, param in sig.parameters.items():
            # Check if this parameter should be injected
            if param.annotation != inspect.Parameter.empty:
                if self._strict:
                    # In strict mode, verify all annotated parameters are registered
                    if param.annotation not in self._provider._dependency_lookup:
                        raise ValueError(
                            f"Failed to resolve dependency '{param.annotation.__name__}' "
                            f"for parameter '{name}': dependency is not registered"
                        )
                    injectable_params[name] = param.annotation
                else:
                    # In non-strict mode, only inject registered parameters
                    if param.annotation in self._provider._dependency_lookup:
                        injectable_params[name] = param.annotation
                    else:
                        # Keep non-injectable parameters in the signature
                        new_params.append(param)
            else:
                # Keep non-annotated parameters in the signature
                new_params.append(param)

        # Create new signature without injectable parameters
        new_sig = sig.replace(parameters=new_params)

        if is_async:
            @wraps(fn)
            async def async_wrapper(*args, **kwargs):
                # Use scope if available, otherwise fall back to provider
                if hasattr(async_wrapper, '_scope') and async_wrapper._scope is not None:
                    resolver = async_wrapper._scope
                    resolve_method = resolver.resolve_async
                else:
                    resolver = self._provider
                    resolve_method = resolver.resolve_async

                # Inject dependencies
                for name, param_type in injectable_params.items():
                    if name not in kwargs:  # Don't override if already provided
                        try:
                            kwargs[name] = await resolve_method(param_type)
                        except Exception as e:
                            if self._strict:
                                raise ValueError(
                                    f"Failed to resolve dependency '{param_type.__name__}' "
                                    f"for '{name}': {e}"
                                )
                            logger.debug(f"Skipping DI for '{name}': {e}")

                return await fn(*args, **kwargs)

            # Set the new signature so FastAPI sees the clean version
            async_wrapper.__signature__ = new_sig
            async_wrapper._scope = None
            return async_wrapper
        else:
            @wraps(fn)
            def sync_wrapper(*args, **kwargs):
                # Use scope if available, otherwise fall back to provider
                if hasattr(sync_wrapper, '_scope') and sync_wrapper._scope is not None:
                    resolver = sync_wrapper._scope
                else:
                    resolver = self._provider

                # Inject dependencies
                for name, param_type in injectable_params.items():
                    if name not in kwargs:  # Don't override if already provided
                        try:
                            kwargs[name] = resolver.resolve(param_type)
                        except Exception as e:
                            if self._strict:
                                raise ValueError(
                                    f"Failed to resolve dependency '{param_type.__name__}' "
                                    f"for '{name}': {e}"
                                )
                            logger.debug(f"Skipping DI for '{name}': {e}")

                return fn(*args, **kwargs)

            # Set the new signature so FastAPI sees the clean version
            sync_wrapper.__signature__ = new_sig
            sync_wrapper._scope = None
            return sync_wrapper

    # TODO: Quart, Django, Flask, FastAPI integration helpers will ultimately be migrated to separate packages
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
