from framework.logger import get_logger
from threading import Lock
from functools import wraps
from typing import Any, Callable, Optional, Type
import asyncio
import inspect

logger = get_logger(__name__)


class Lifetime:
    Singleton = 'singleton'
    Transient = 'transient'
    Scoped = 'scoped'


class ConstructorDependency:
    def __init__(self, name: str, _type: type):
        self.name = name
        self.dependency_type = _type


class DependencyRegistration:
    def __hash__(self):
        return hash(self.implementation_type)

    def __eq__(self, other):
        return isinstance(other, DependencyRegistration) and self.implementation_type == other.implementation_type

    def __init__(
        self,
        dependency_type: type,
        lifetime: str,
        implementation_type: type = None,
        instance: Any = None,
        factory: Callable = None,
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
        if not self.constructor_params:
            return {}
        with cache_lock:
            if self.implementation_type in cache:
                return cache[self.implementation_type]
        constructor_params = {}
        for param in self.constructor_params:
            param_dependency = dependency_lookup.get(param.dependency_type)
            if param_dependency is None:
                raise Exception(
                    f"Could not find dependency for '{param.dependency_type.__name__}' when activating '{self._type_name}' constructor params"
                )
            constructor_params[param.name] = param_dependency.activate(dependency_lookup, cache, cache_lock)
        with cache_lock:
            cache[self.implementation_type] = constructor_params
        return constructor_params

    async def get_activate_constructor_params_async(
        self,
        dependency_lookup: dict[type, 'DependencyRegistration'],
        cache: dict,
        cache_lock: Lock
    ) -> dict[str, Any]:
        if not self.constructor_params:
            return {}
        with cache_lock:
            if self.implementation_type in cache:
                return cache[self.implementation_type]
        constructor_params = {}
        for param in self.constructor_params:
            param_dependency = dependency_lookup.get(param.dependency_type)
            if param_dependency is None:
                raise Exception(
                    f"Could not find dependency for '{param.dependency_type.__name__}' when activating '{self._type_name}' constructor params"
                )
            constructor_params[param.name] = await param_dependency.activate_async(dependency_lookup, cache, cache_lock)
        with cache_lock:
            cache[self.implementation_type] = constructor_params
        return constructor_params

    def activate(
        self,
        dependency_lookup: dict[type, 'DependencyRegistration'],
        cache: dict,
        cache_lock: Lock
    ) -> Any:
        if self.lifetime == Lifetime.Singleton and self.instance is not None:
            return self.instance
        if self.factory:
            return self.factory(self)
        if not self.constructor_params:
            instance = self.implementation_type()
        else:
            constructor_params = self.get_activate_constructor_params(dependency_lookup, cache, cache_lock)
            instance = self.implementation_type(**constructor_params)
        if self.lifetime == Lifetime.Singleton:
            self.instance = instance
        return instance

    async def activate_async(
        self,
        dependency_lookup: dict[type, 'DependencyRegistration'],
        cache: dict,
        cache_lock: Lock
    ) -> Any:
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
            constructor_params = await self.get_activate_constructor_params_async(dependency_lookup, cache, cache_lock)
            instance = self.implementation_type(**constructor_params)
        if self.lifetime == Lifetime.Singleton:
            self.instance = instance
        return instance


class ServiceCollection:
    def __init__(self):
        self._container: dict[type, DependencyRegistration] = {}

    def get_type_dependencies(self, _type: type) -> list:
        params = inspect.signature(_type).parameters
        types = []
        for name, param in params.items():
            if param.annotation == inspect.Parameter.empty:
                raise Exception(f"Parameter '{name}' in {_type.__name__} has no annotation")
            constructor_dependency = ConstructorDependency(name=name, _type=param.annotation)
            types.append(constructor_dependency)
        return types

    def add(self, dependency_type: type, implementation_type: Optional[type] = None, **kwargs):
        kwargs.setdefault('lifetime', Lifetime.Transient)
        self._register_dependency(dependency_type, implementation_type, **kwargs)

    def add_singleton(
        self,
        dependency_type: type,
        implementation_type: Optional[type] = None,
        instance: Any = None,
        factory: Optional[Callable] = None
    ) -> None:
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
        factory: Optional[Callable] = None
    ) -> None:
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
        factory: Optional[Callable] = None
    ) -> None:
        self._register_dependency(
            dependency_type=dependency_type,
            implementation_type=implementation_type,
            lifetime=Lifetime.Scoped,
            factory=factory
        )

    def register_many(self, types: list[type], lifetime: str = Lifetime.Transient):
        for t in types:
            getattr(self, f"add_{lifetime.lower()}")(t)

    def _register_dependency(
        self,
        dependency_type: type,
        implementation_type: Optional[type],
        **kwargs
    ) -> None:
        implementation_type = implementation_type or dependency_type
        constructor_params = (
            self.get_type_dependencies(implementation_type)
            if kwargs.get('factory') is None else []
        )
        dependency = DependencyRegistration(
            implementation_type=implementation_type,
            dependency_type=dependency_type,
            constructor_params=constructor_params,
            **kwargs
        )
        self._container[dependency_type] = dependency

    def build_provider(self) -> 'ServiceProvider':
        provider = ServiceProvider(self)
        provider.build()
        return provider


class ServiceProvider:
    def __init__(self, service_collection: ServiceCollection):
        self._service_collection = service_collection
        self._dependency_lookup = service_collection.get_container()
        self._dependencies = list(self._dependency_lookup.values())
        self._singleton_instances = {}
        self._cache = {}
        self._cache_lock = Lock()
        self._initialize_provider()

    def _initialize_provider(self) -> None:
        self._singletons = [d for d in self._dependencies if d.lifetime == Lifetime.Singleton and not d.factory]
        self._factories = [d for d in self._dependencies if d.lifetime == Lifetime.Singleton and d.factory]
        self._transients = [d for d in self._dependencies if d.lifetime == Lifetime.Transient]

    def resolve(self, _type: type) -> Any:
        registration = self._get_registered_dependency(_type)
        if registration.lifetime == Lifetime.Singleton:
            with self._cache_lock:
                if _type in self._singleton_instances:
                    return self._singleton_instances[_type]
            if registration.instance is not None:
                with self._cache_lock:
                    self._singleton_instances[_type] = registration.instance
                return registration.instance
            if registration.factory:
                instance = registration.factory(self)
                registration.instance = instance
                with self._cache_lock:
                    self._singleton_instances[_type] = instance
                return instance
            instance = registration.activate(self._dependency_lookup, self._cache, self._cache_lock)
            with self._cache_lock:
                self._singleton_instances[_type] = instance
            return instance
        if registration.lifetime == Lifetime.Transient:
            if registration.factory:
                return registration.factory(self)
            return registration.activate(self._dependency_lookup, self._cache, self._cache_lock)
        if registration.lifetime == Lifetime.Scoped:
            raise Exception("Scoped resolution requires a scope.")
        raise Exception(f"Unknown lifetime: {registration.lifetime}")

    async def resolve_async(self, _type: type) -> Any:
        registration = self._get_registered_dependency(_type)
        if registration.lifetime == Lifetime.Singleton:
            with self._cache_lock:
                if _type in self._singleton_instances:
                    return self._singleton_instances[_type]
            if registration.instance is not None:
                with self._cache_lock:
                    self._singleton_instances[_type] = registration.instance
                return registration.instance
            if registration.factory:
                instance = registration.factory(self)
                if asyncio.iscoroutine(instance):
                    instance = await instance
                registration.instance = instance
                with self._cache_lock:
                    self._singleton_instances[_type] = instance
                return instance
            instance = await registration.activate_async(self._dependency_lookup, self._cache, self._cache_lock)
            with self._cache_lock:
                self._singleton_instances[_type] = instance
            return instance
        if registration.lifetime == Lifetime.Transient:
            if registration.factory:
                instance = registration.factory(self)
                if asyncio.iscoroutine(instance):
                    return await instance
                return instance
            return await registration.activate_async(self._dependency_lookup, self._cache, self._cache_lock)
        if registration.lifetime == Lifetime.Scoped:
            raise Exception("Scoped resolution requires a scope.")
        raise Exception(f"Unknown lifetime: {registration.lifetime}")

    def _get_registered_dependency(
        self,
        implementation_type: type,
        requesting_type: Optional[DependencyRegistration] = None
    ) -> DependencyRegistration:
        registration = self._dependency_lookup.get(implementation_type)
        if registration is not None:
            return registration
        if requesting_type is not None:
            raise Exception(
                f"Failed to locate registration for type '{implementation_type.__name__}' when instantiating type '{requesting_type._type_name}'"
            )
        else:
            raise Exception(f"Failed to locate registration for type '{implementation_type.__name__}'")

    def _verify_singleton(self, registration: DependencyRegistration) -> None:
        for param in registration.constructor_params:
            req_reg = self._get_registered_dependency(param.dependency_type, registration)
            if req_reg.lifetime == Lifetime.Transient:
                raise Exception(
                    f"Cannot inject dependency '{param.dependency_type.__name__}' with transient lifetime into singleton '{registration._type_name}'"
                )

    def _topological_sort(self, dependencies: list[DependencyRegistration]) -> list[DependencyRegistration]:
        visited = set()
        visiting = set()
        order = []

        def dfs(dep: DependencyRegistration):
            if dep in visited:
                return
            if dep in visiting:
                raise Exception(f"Cyclic dependency detected involving '{dep._type_name}'")
            visiting.add(dep)
            for param in dep.constructor_params:
                required_dep = self._get_registered_dependency(param.dependency_type, dep)
                dfs(required_dep)
            visiting.remove(dep)
            visited.add(dep)
            order.append(dep)

        for dep in dependencies:
            dfs(dep)
        return order

    def build(self) -> 'ServiceProvider':
        all_to_build = [d for d in self._dependencies if d.lifetime == Lifetime.Singleton]
        sorted_deps = self._topological_sort(all_to_build)
        for reg in sorted_deps:
            if reg.instance is not None:
                continue
            if reg.factory:
                instance = reg.factory(self)
                if asyncio.iscoroutine(instance):
                    instance = asyncio.get_event_loop().run_until_complete(instance)
            else:
                instance = reg.activate(self._dependency_lookup, self._cache, self._cache_lock)
            reg.instance = instance
            with self._cache_lock:
                self._singleton_instances[reg.dependency_type] = instance
        return self

    async def build_async(self) -> 'ServiceProvider':
        all_to_build = [d for d in self._dependencies if d.lifetime == Lifetime.Singleton]
        sorted_deps = self._topological_sort(all_to_build)
        for reg in sorted_deps:
            if reg.instance is not None:
                continue
            if reg.factory:
                instance = reg.factory(self)
                if asyncio.iscoroutine(instance):
                    instance = await instance
            else:
                instance = await reg.activate_async(self._dependency_lookup, self._cache, self._cache_lock)
            reg.instance = instance
            with self._cache_lock:
                self._singleton_instances[reg.dependency_type] = instance
        return self

    def create_scope(self) -> 'ServiceScope':
        return ServiceScope(self)


class ServiceScope:
    def __init__(self, provider: ServiceProvider):
        self._provider = provider
        self._scoped_instances: dict[type, Any] = {}
        self._dependency_lookup = provider._dependency_lookup
        self._cache = {}
        self._cache_lock = Lock()

    def __enter__(self) -> 'ServiceScope':
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.dispose()

    async def __aenter__(self) -> 'ServiceScope':
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        for instance in self._scoped_instances.values():
            if hasattr(instance, '__aexit__'):
                await instance.__aexit__(exc_type, exc_value, traceback)
        self.dispose()

    def resolve(self, _type: type) -> Any:
        registration = self._provider._get_registered_dependency(implementation_type=_type)
        if registration.lifetime == Lifetime.Singleton:
            return self._provider.resolve(_type)
        if registration.lifetime == Lifetime.Transient:
            if registration.factory:
                return registration.factory(self)
            return registration.activate(self._dependency_lookup, self._cache, self._cache_lock)
        if registration.lifetime == Lifetime.Scoped:
            if _type in self._scoped_instances:
                return self._scoped_instances[_type]
            if registration.factory:
                instance = registration.factory(self)
            else:
                instance = registration.activate(self._dependency_lookup, self._cache, self._cache_lock)
            self._scoped_instances[_type] = instance
            return instance
        raise Exception(f"Unknown lifetime: {registration.lifetime}")

    async def resolve_async(self, _type: type) -> Any:
        registration = self._provider._get_registered_dependency(implementation_type=_type)
        if registration.lifetime == Lifetime.Singleton:
            return await self._provider.resolve_async(_type)
        if registration.lifetime == Lifetime.Transient:
            if registration.factory:
                instance = registration.factory(self)
                if asyncio.iscoroutine(instance):
                    return await instance
                return instance
            return await registration.activate_async(self._dependency_lookup, self._cache, self._cache_lock)
        if registration.lifetime == Lifetime.Scoped:
            if _type in self._scoped_instances:
                return self._scoped_instances[_type]
            if registration.factory:
                instance = registration.factory(self)
                if asyncio.iscoroutine(instance):
                    instance = await instance
            else:
                instance = await registration.activate_async(self._dependency_lookup, self._cache, self._cache_lock)
            self._scoped_instances[_type] = instance
            return instance
        raise Exception(f"Unknown lifetime: {registration.lifetime}")

    def dispose(self) -> None:
        self._scoped_instances.clear()
        self._cache.clear()


class DependencyInjector:
    def __init__(self, provider: ServiceProvider, strict: bool = False):
        self._provider = provider
        self._strict = strict

    def create_scope(self) -> ServiceScope:
        return self._provider.create_scope()

    def inject(self, fn: Callable) -> Callable:
        sig = inspect.signature(fn)

        @wraps(fn)
        async def wrapper(*args, **kwargs):
            if not hasattr(wrapper, '_scope'):
                raise Exception("ServiceScope not set. Ensure DI middleware is applied.")
            scope = wrapper._scope
            for name, param in sig.parameters.items():
                if name not in kwargs and param.annotation != inspect.Parameter.empty:
                    try:
                        if asyncio.iscoroutinefunction(fn):
                            kwargs[name] = await scope.resolve_async(param.annotation)
                        else:
                            kwargs[name] = scope.resolve(param.annotation)
                    except Exception as e:
                        if self._strict:
                            raise Exception(f"Failed to resolve dependency '{param.annotation.__name__}' for parameter '{name}': {e}")
                        logger.debug(f"Parameter '{name}' not resolved by DI: {e}")
                        pass
            if asyncio.iscoroutinefunction(fn):
                return await fn(*args, **kwargs)
            return fn(*args, **kwargs)

        wrapper._scope = None
        return wrapper

    def setup_fastapi(self, app):
        from fastapi import Request

        @app.middleware("http")
        async def di_middleware(request: Request, call_next):
            with self.create_scope() as scope:
                request.state.scope = scope
                for route in app.routes:
                    if hasattr(route.endpoint, '_scope'):
                        route.endpoint._scope = scope
                response = await call_next(request)
                return response

    def setup_flask(self, app):
        from flask import g

        @app.before_request
        def before_request():
            g.scope = self.create_scope()

        @app.teardown_request
        def teardown_request(exception=None):
            if hasattr(g, 'scope'):
                g.scope.dispose()

        for rule in app.url_map.iter_rules():
            endpoint = app.view_functions[rule.endpoint]
            if hasattr(endpoint, '_scope'):
                @wraps(endpoint)
                def wrapped_view(*args, **kwargs):
                    endpoint._scope = g.scope
                    return endpoint(*args, **kwargs)
                app.view_functions[rule.endpoint] = wrapped_view
