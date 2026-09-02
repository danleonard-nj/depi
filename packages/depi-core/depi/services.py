"""
depi – A Modern, Type-Safe Dependency Injection Framework for Python

Provides:
- Type-hinted constructor injection
- Singleton, Transient, and Scoped lifetimes
- Async factory and constructor support
"""

import logging
from threading import Lock, RLock
from functools import lru_cache
from typing import Any, Callable, Optional
import asyncio
import inspect

from .exceptions import (
    AsyncFactoryError,
    CircularDependencyError,
    InvalidLifetimeError,
    MissingAnnotationError,
    ScopeRequiredError,
    UnknownLifetimeError,
    UnregisteredDependencyError,
)

logger = logging.getLogger(__name__)



def _reject_awaitable(_type: type, instance: Any) -> None:
    """
    Raise AsyncFactoryError for a factory result that must be awaited.

    Closes the coroutine first. Without that, abandoning it un-awaited emits
    "coroutine ... was never awaited" into the caller's logs on top of the
    exception, which points at the wrong thing.
    """
    close = getattr(instance, 'close', None)
    if close is not None:
        try:
            close()
        except Exception:  # pragma: no cover - defensive
            pass
    raise AsyncFactoryError(
        f"Factory for '{_type.__name__}' returned an awaitable. "
        f"Use resolve_async() to resolve async factories."
    )

@lru_cache(maxsize=None)
def get_signature(fn):
    return inspect.signature(fn, eval_str=True)


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

    __slots__ = ("name", "dependency_type")

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
        "eager", "constructor_params", "_type_name", "_resolver_fn"
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
        eager: bool = False,
        constructor_params: list[ConstructorDependency] = None,
        resolver_fn: Optional[Callable] = None
    ):
        self.dependency_type = dependency_type
        self.lifetime = lifetime
        self.implementation_type = implementation_type or dependency_type
        self.instance = instance
        self.factory = factory
        self.eager = eager
        self.constructor_params = constructor_params or []
        self._type_name = self.implementation_type.__name__
        self._resolver_fn = resolver_fn

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

    __slots__ = ("_container",)

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
                raise MissingAnnotationError(
                    f"Missing type annotation for parameter '{name}' in {_type.__name__}")
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
        factory: Callable = None,
        eager: bool = False
    ) -> None:
        """
        Register a singleton service.

        `eager`: If True, construct the singleton during build()/build_async()
        instead of lazily on first resolve().
        """
        self._register_dependency(
            dependency_type=dependency_type,
            implementation_type=implementation_type,
            lifetime=Lifetime.Singleton,
            instance=instance,
            factory=factory,
            eager=eager
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
            self._register_dependency(
                dependency_type=t,
                implementation_type=None,
                lifetime=lifetime
            )

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
            resolver_fn=resolver_fn,
            **kwargs
        )
        self._container[dependency_type] = reg

    def get_container(self) -> dict[type, DependencyRegistration]:
        """Expose raw registration dictionary."""
        return self._container

    def build_provider(self, eager_all: bool = False) -> 'ServiceProvider':
        """
        Finalize registrations and return a built ServiceProvider.

        `eager_all`: If True, mark every singleton registration as eager so
        all singletons are constructed during build() (pre-lazy behavior),
        instead of only those explicitly registered with eager=True.
        """
        if eager_all:
            for reg in self._container.values():
                if reg.lifetime == Lifetime.Singleton:
                    reg.eager = True
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
        '_cache', '_cache_lock', '_singletons', '_factories', '_transients',
        '_async_singleton_locks', '_async_lock_dict_lock'
    )

    def __init__(self, service_collection: ServiceCollection):
        self._service_collection = service_collection
        self._dependency_lookup = service_collection.get_container()
        self._dependencies = list(self._dependency_lookup.values())
        self._singleton_instances: dict[type, Any] = {}
        self._cache: dict = {}
        # RLock (not Lock) is required: singleton A's constructor may call
        # resolve(B) while this lock is held. RLock lets the same thread
        # re-enter, preventing deadlock during recursive singleton construction.
        self._cache_lock = RLock()
        # Per-type asyncio.Lock objects for coroutine-safe lazy singleton
        # creation. Lazily populated; the dict itself is protected by a small
        # sync Lock held only while reading or inserting lock objects.
        self._async_singleton_locks: dict[type, asyncio.Lock] = {}
        self._async_lock_dict_lock = Lock()
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
            # Use registration.dependency_type as the consistent cache key.
            dep_type = reg.dependency_type
            cache = self._singleton_instances

            instance = cache.get(dep_type)
            if instance is not None:
                return instance

            # RLock allows the same thread to re-enter while constructing a
            # singleton whose constructor itself calls resolve() for another
            # singleton (e.g. A.__init__ calls resolve(B)).
            with self._cache_lock:
                instance = cache.get(dep_type)
                if instance is not None:
                    return instance

                if reg.factory:
                    instance = reg.factory(self)
                    if inspect.isawaitable(instance):
                        _reject_awaitable(_type, instance)
                elif reg.instance is not None:
                    instance = reg.instance
                else:
                    instance = reg.activate(self)

                cache[dep_type] = instance
                return instance

        elif lifetime == Lifetime.Transient:
            if reg.factory:
                instance = reg.factory(self)
                if inspect.isawaitable(instance):
                    _reject_awaitable(_type, instance)
                return instance
            return reg.activate(self)

        elif lifetime == Lifetime.Scoped:
            raise ScopeRequiredError("Scoped resolution requires a scope. Call provider.create_scope().")

        raise UnknownLifetimeError(f"Unknown lifetime: {lifetime}")

    async def resolve_async(self, _type: type) -> Any:
        """
        Resolve a registered service asynchronously.
        Optimized with fast path for singletons and minimal locking.
        """
        reg = self._get_registered_dependency(_type)

        if reg.lifetime == Lifetime.Singleton:
            # Use registration.dependency_type as the consistent cache key.
            dep_type = reg.dependency_type

            # Fast path: lock-free cache check (covers 99% of singleton calls)
            instance = self._singleton_instances.get(dep_type)
            if instance is not None:
                return instance

            # Per-type asyncio.Lock is required for coroutine-safe lazy singleton
            # construction. A single global async lock would deadlock when singleton
            # A's constructor awaits resolve_async(B) — both would compete for the
            # same lock. Per-type locks let independent singletons be built
            # concurrently without blocking each other.
            #
            # The dict lock is held only long enough to read or create the asyncio.Lock
            # object; it is never held across an await.
            with self._async_lock_dict_lock:
                lock = self._async_singleton_locks.get(dep_type)
                if lock is None:
                    lock = asyncio.Lock()
                    self._async_singleton_locks[dep_type] = lock

            async with lock:
                # Double-check after acquiring the per-type async lock.
                instance = self._singleton_instances.get(dep_type)
                if instance is not None:
                    return instance

                if reg.factory:
                    inst = reg.factory(self)
                    if inspect.isawaitable(inst):
                        inst = await inst
                    instance = inst
                elif reg.instance is not None:
                    # Pre-built during build() phase
                    instance = reg.instance
                else:
                    # Lazy singleton via async constructor injection
                    instance = await reg.activate_async(self)

                self._singleton_instances[dep_type] = instance
                return instance

        elif reg.lifetime == Lifetime.Transient:
            if reg.factory:
                inst = reg.factory(self)
                return await inst if inspect.isawaitable(inst) else inst
            else:
                return await reg.activate_async(self)

        elif reg.lifetime == Lifetime.Scoped:
            raise ScopeRequiredError("Scoped resolution requires a scope. Call provider.create_scope().")

        raise UnknownLifetimeError(f"Unknown lifetime: {reg.lifetime}")

    def is_registered(self, _type: type) -> bool:
        """
        Return True if ``_type`` has a registration.

        Integrations use this to decide whether an annotated view-function
        parameter is something depi owns, or something the web framework will
        supply (a path converter, a query argument).
        """
        return _type in self._dependency_lookup

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
            raise UnregisteredDependencyError(
                f"Failed to locate registration for '{implementation_type.__name__}' "
                f"while instantiating '{requesting_type._type_name}'"
            )
        raise UnregisteredDependencyError(
            f"Failed to locate registration for '{implementation_type.__name__}'")

    def _validate_dependencies(self) -> None:
        """
        Validate dependency lifetimes to prevent invalid lifetime combinations.

        Rules:
        - Singletons cannot depend on transient services (only a single instance
          of the transient dependency would be injected during instantiation of the
          singleton, which is not the intended behavior of a transient dependency)
        - Singletons cannot depend on scoped services (the scoped instance would be
          resolved once during singleton creation and reused, breaking scope isolation)
        """
        for reg in self._dependencies:
            if reg.lifetime == Lifetime.Singleton:
                # Only validate constructor-injected dependencies (not factory-based)
                # Factory-based registrations don't have constructor_params
                if not reg.constructor_params:
                    continue

                for param in reg.constructor_params:
                    dep_reg = self._dependency_lookup.get(param.dependency_type)
                    if dep_reg is None:
                        continue  # Missing dependency will be caught elsewhere

                    if dep_reg.lifetime == Lifetime.Transient:
                        raise InvalidLifetimeError(
                            f"Singleton '{reg._type_name}' cannot depend on transient "
                            f"'{dep_reg._type_name}'. Transient dependencies would only "
                            f"be instantiated once during singleton creation, which is "
                            f"not the intended behavior of a transient service."
                        )
                    if dep_reg.lifetime == Lifetime.Scoped:
                        raise InvalidLifetimeError(
                            f"Singleton '{reg._type_name}' cannot depend on scoped "
                            f"'{dep_reg._type_name}'. Scoped dependencies would only "
                            f"be instantiated once during singleton creation, breaking "
                            f"scope isolation."
                        )

    def _walk_dependencies(
        self,
        roots: list[DependencyRegistration],
        *,
        strict: bool,
        collect_order: bool,
    ) -> Optional[list[DependencyRegistration]]:
        """
        DFS over the dependency graph rooted at `roots`, raising on cycles.

        strict=True   -> raise on an unregistered dependency, with the requesting
                         type for context. Used for the singleton build pass, where a
                         missing dependency is a hard build-time error.
        strict=False  -> skip unregistered dependencies. Used for the whole-graph
                         cycle check, where missing transient/scoped deps are left to
                         surface at resolve time.
        collect_order -> when True, return registrations in dependency-first order (a
                         valid instantiation order); when False, return None.
        """
        visited: set = set()
        visiting: set = set()
        # `visiting` answers "is this on the current path" in O(1); `path` keeps
        # the same registrations in order so a cycle can be reported as the
        # chain that produced it rather than just the type it was noticed at.
        path: list = []
        order: Optional[list] = [] if collect_order else None

        def dfs(reg: DependencyRegistration):
            if reg in visited:
                return
            if reg in visiting:
                # Trim the path to where this type first appeared, then close
                # the loop, so the message shows only the cycle itself and not
                # whatever chain happened to lead into it.
                cycle = path[path.index(reg):] + [reg]
                chain = ' -> '.join(r._type_name for r in cycle)
                raise CircularDependencyError(f"Cyclic dependency detected: {chain}")
            visiting.add(reg)
            path.append(reg)
            for param in reg.constructor_params:
                if strict:
                    dep = self._get_registered_dependency(param.dependency_type, reg)
                else:
                    dep = self._dependency_lookup.get(param.dependency_type)
                    if dep is None:
                        continue
                dfs(dep)
            path.pop()
            visiting.discard(reg)
            visited.add(reg)
            if order is not None:
                order.append(reg)

        for reg in roots:
            dfs(reg)
        return order

    def build(self) -> 'ServiceProvider':
        """
        Validate and order every singleton registration, but only construct
        factories and singletons explicitly marked eager=True. Other
        singletons are validated/ordered here and constructed lazily on
        first resolve().
        """
        # Validate dependencies before building
        self._validate_dependencies()
        # whole-graph cycle check across every lifetime (lenient on missing deps)
        self._walk_dependencies(self._dependencies, strict=False, collect_order=False)

        to_build = [d for d in self._dependencies if d.lifetime == Lifetime.Singleton]
        # strict ordered pass validates/orders all singletons, even lazy ones
        sorted_deps = self._walk_dependencies(to_build, strict=True, collect_order=True)
        for reg in sorted_deps:
            if not (reg.factory or reg.eager):
                continue
            if reg.instance is None:
                if reg.factory:
                    inst = reg.factory(self)
                    # support coroutine factories
                    if asyncio.iscoroutine(inst):
                        try:
                            # Probe only: raises RuntimeError when there is no
                            # running loop, which the except branch below handles.
                            asyncio.get_running_loop()
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
                self._singleton_instances[reg.dependency_type] = reg.instance
        return self

    async def build_async(self) -> 'ServiceProvider':
        """
        Async variant of build(): validates/orders every singleton, but only
        constructs factories and singletons explicitly marked eager=True.
        """
        # Validate dependencies before building
        self._validate_dependencies()
        # whole-graph cycle check across every lifetime (lenient on missing deps)
        self._walk_dependencies(self._dependencies, strict=False, collect_order=False)

        to_build = [d for d in self._dependencies if d.lifetime == Lifetime.Singleton]
        # strict ordered pass validates/orders all singletons, even lazy ones
        sorted_deps = self._walk_dependencies(to_build, strict=True, collect_order=True)
        for reg in sorted_deps:
            if not (reg.factory or reg.eager):
                continue
            if reg.instance is None:
                if reg.factory:
                    inst = reg.factory(self)
                    if asyncio.iscoroutine(inst):
                        inst = await inst
                else:
                    inst = await reg.activate_async(self)
                reg.instance = inst
            with self._cache_lock:
                self._singleton_instances[reg.dependency_type] = reg.instance
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
        if life == Lifetime.Singleton:
            return provider.resolve(_type)

        insts = self._scoped_instances

        # Scoped: return cached if present
        if life == Lifetime.Scoped:
            inst = insts.get(_type)
            if inst is not None:
                return inst

        # Transient or new Scoped instance
        factory = reg.factory
        if factory:
            inst = factory(self)
            # Same guard ServiceProvider.resolve applies. Without it an async
            # factory resolved through a scope returns an un-awaited coroutine,
            # which then fails far away from its cause -- and scopes are what
            # every web integration resolves through.
            if inspect.isawaitable(inst):
                _reject_awaitable(_type, inst)
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

    def is_registered(self, _type: type) -> bool:
        """Return True if ``_type`` has a registration. See ServiceProvider.is_registered."""
        return _type in self._dependency_lookup

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
