from typing import Any, Callable, Optional
import inspect
from framework.logger import get_logger


logger = get_logger(__name__)


class Lifetime:
    Singleton = 'singleton'
    Transient = 'transient'
    Scoped = 'scoped'


class ConstructorDependency:
    @property
    def type_name(self) -> str:
        return self.dependency_type.__name__

    def __init__(self, name: str, _type: type):
        self.name = name
        self.dependency_type = _type

    def __repr__(self) -> str:
        return self.dependency_type.__name__


class DependencyRegistration:
    def __hash__(self):
        return hash(self.implementation_type)

    def __eq__(self, other):
        return isinstance(other, DependencyRegistration) and self.implementation_type == other.implementation_type

    @property
    def type_name(self) -> str:
        return self._type_name

    @property
    def is_factory(self) -> bool:
        return self.factory is not None

    @property
    def required_types(self) -> list[type]:
        return self._required_types

    @property
    def built(self) -> bool:
        return self.instance is not None

    @property
    def is_parameterless(self) -> bool:
        return len(self.constructor_params) == 0

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

        self.configure_dependency()

    def configure_dependency(self) -> None:
        self._required_types = [dep.dependency_type for dep in self.constructor_params]
        self._type_name = self.implementation_type.__name__

    def get_activate_constructor_params(
        self,
        dependency_lookup: dict[type, 'DependencyRegistration']
    ) -> dict[str, Any]:
        constructor_params = {}
        for param in self.constructor_params:
            param_dependency = dependency_lookup.get(param.dependency_type)
            if param_dependency is None:
                raise Exception(
                    f"Could not find dependency for '{param.dependency_type}' when activating '{self.type_name}' constructor params"
                )
            constructor_params[param.name] = param_dependency.activate(dependency_lookup)
        return constructor_params

    def activate(
        self,
        dependency_lookup: dict[type, 'DependencyRegistration']
    ) -> Any:
        # If we've already built this instance, return it
        if self.lifetime == Lifetime.Singleton and self.built:
            return self.instance

        # If it's not built and has no parameters, create it directly
        if self.is_parameterless:
            instance = self.implementation_type()

        # Build the instance using the constructor parameters
        else:
            constructor_params = self.get_activate_constructor_params(dependency_lookup)
            instance = self.implementation_type(**constructor_params)

        if self.lifetime == Lifetime.Singleton:
            self.instance = instance

        return instance


class ServiceCollection:
    def __init__(self):
        self._container: dict[type, DependencyRegistration] = {}

    # Add this method to support the test case
    def resolve(self, _type: type) -> Any:
        """This is a helper method to support factory functions that need to resolve dependencies
        during the registration phase. In production code, this would likely use a different approach."""
        registration = self._container.get(_type)
        if registration is None:
            raise Exception(f"Failed to locate registration for type '{_type.__name__}'")
        if registration.instance is not None:
            return registration.instance
        return registration.implementation_type()

    def get_type_dependencies(self, _type: type) -> list:
        params = inspect.signature(_type).parameters
        types = []
        for name, param in params.items():
            if param.annotation == inspect._empty:
                raise Exception(f"Parameter '{name}' in {_type.__name__} has no annotation")
            constructor_dependency = ConstructorDependency(name=name, _type=param.annotation)
            types.append(constructor_dependency)
        return types

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

    def get_container(self) -> dict[type, DependencyRegistration]:
        return self._container

    def build_provider(self) -> 'ServiceProvider':
        provider = ServiceProvider(self)
        provider.build()
        return provider


class ServiceProvider:
    def __init__(self, service_collection: ServiceCollection):
        self._service_collection = service_collection
        self._dependency_lookup = service_collection.get_container()
        self._dependencies = list(self._dependency_lookup.values())
        self._built = {}  # key: implementation_type, value: DependencyRegistration
        self._singleton_instances = {}  # Cache for singleton instances
        self._built_types = []  # <-- ADD THIS
        self._built_dependencies = []  # <-- AND THIS

        self._initialize_provider()

    def _initialize_provider(self) -> None:
        deps = self._dependencies
        self._singletons = [d for d in deps if d.lifetime == Lifetime.Singleton and not d.is_factory]
        self._factories = [d for d in deps if d.lifetime == Lifetime.Singleton and d.is_factory]
        self._transients = [d for d in deps if d.lifetime == Lifetime.Transient]
        # Scoped registrations will be handled per-scope.

    def resolve(self, _type: type) -> Any:
        registration = self._get_registered_dependency(_type)

        # For singletons, check if we already have an instance in our cache
        if registration.lifetime == Lifetime.Singleton:
            # Check if we have it cached
            if _type in self._singleton_instances:
                return self._singleton_instances[_type]

            # If it's not in cache but instance is present, cache and return it
            if registration.instance is not None:
                self._singleton_instances[_type] = registration.instance
                return registration.instance

            # If it's a factory, create instance, cache, and return
            if registration.is_factory:
                instance = registration.factory(self)
                registration.instance = instance  # Update registration too
                self._singleton_instances[_type] = instance
                return instance

            # Otherwise, create using normal activation
            instance = registration.activate(self._dependency_lookup)
            self._singleton_instances[_type] = instance
            return instance

        # For transients, always create a new instance
        if registration.lifetime == Lifetime.Transient:
            if registration.is_factory:
                return registration.factory(self)
            return registration.activate(self._dependency_lookup)

        if registration.lifetime == Lifetime.Scoped:
            raise Exception("Scoped resolution requires a scope.")

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
                f"Failed to locate registration for type '{implementation_type.__name__}' when instantiating type '{requesting_type.type_name}'"
            )
        else:
            raise Exception(f"Failed to locate registration for type '{implementation_type.__name__}'")

    def _verify_singleton(self, registration: DependencyRegistration) -> None:
        for required_type in registration.required_types:
            req_reg = self._get_registered_dependency(implementation_type=required_type, requesting_type=registration)
            if req_reg.lifetime == Lifetime.Transient:
                raise Exception(
                    f"Cannot inject dependency '{required_type.__name__}' with transient lifetime into singleton '{registration.type_name}'"
                )

    def _can_build(self, registration: DependencyRegistration) -> bool:
        self._verify_singleton(registration)
        return all(req in self._built for req in registration.required_types)

    def _topological_sort(self, dependencies: list[DependencyRegistration]) -> list[DependencyRegistration]:
        visited = set()
        visiting = set()
        order = []

        def dfs(dep: DependencyRegistration):
            if dep in visited:
                return
            if dep in visiting:
                raise Exception(f"Cyclic dependency detected involving '{dep.type_name}'")

            visiting.add(dep)
            for required_type in dep.required_types:
                required_dep = self._get_registered_dependency(required_type, dep)
                dfs(required_dep)
            visiting.remove(dep)
            visited.add(dep)
            order.append(dep)

        for dep in dependencies:
            dfs(dep)

        return order

    def build(self) -> 'ServiceProvider':
        # Combine all singleton and factory registrations
        all_to_build = self._singletons + self._factories
        sorted_deps = self._topological_sort(all_to_build)

        for reg in sorted_deps:
            if reg.built:
                continue

            if reg.lifetime == Lifetime.Singleton:
                # Handle both factory and non-factory singletons
                if reg.is_factory:
                    instance = reg.factory(self)
                else:
                    instance = reg.activate(self._dependency_lookup)

                reg.instance = instance
                self._singleton_instances[reg.dependency_type] = instance
            else:
                # Transient or scoped: mark as built, no caching
                reg.activate(self._dependency_lookup)

            self._built[reg.implementation_type] = reg
            self._built_types.append(reg.implementation_type)
            self._built_dependencies.append(reg)

        return self

    def create_scope(self) -> 'ServiceScope':
        return ServiceScope(self)


class ServiceScope:
    """
    Represents a scope in which scoped dependencies are resolved once per scope.
    Within the same scope the same instance is returned for scoped dependencies.
    """

    def __init__(self, provider: ServiceProvider):
        self._provider = provider
        self._scoped_instances: dict[type, Any] = {}
        self._dependency_lookup = provider._dependency_lookup

    def __enter__(self) -> 'ServiceScope':
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.dispose()

    def resolve(self, _type: type) -> Any:
        registration = self._provider._get_registered_dependency(implementation_type=_type)
        lifetime = registration.lifetime

        # For singletons, always use the provider's resolve method
        # which handles caching and factory logic
        if lifetime == Lifetime.Singleton:
            return self._provider.resolve(_type)

        # For transients, always create a new instance
        if lifetime == Lifetime.Transient:
            if registration.is_factory:
                return registration.factory(self)
            else:
                return registration.activate(self._dependency_lookup)

        # For scoped, create one instance per scope
        if lifetime == Lifetime.Scoped:
            if _type in self._scoped_instances:
                return self._scoped_instances[_type]

            if registration.is_factory:
                instance = registration.factory(self)
            else:
                instance = registration.activate(self._dependency_lookup)

            self._scoped_instances[_type] = instance
            return instance

        raise Exception(f"Unknown lifetime: {lifetime}")

    def dispose(self) -> None:
        self._scoped_instances.clear()
