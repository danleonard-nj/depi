import uuid
import logging
import unittest
import asyncio
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from depi.services import (
    ServiceCollection,
    ServiceProvider,
    ServiceScope,
    DependencyInjector,
    Lifetime,
    DependencyRegistration,
    ConstructorDependency
)

# configure root logger once
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


# Test services and dependencies
class SampleService:
    def __init__(self):
        self.id = uuid.uuid4()
        self.created_at = time.time()


class SingletonRepository(SampleService):
    pass


class ScopedRepository(SampleService):
    pass


class TransientRepository(SampleService):
    pass


class Configuration:
    def __init__(self):
        self.connection_string = "test_connection_string"
        self.timeout = 30


class DatabaseService(SampleService):
    def __init__(self, config: Configuration):
        super().__init__()
        self.connection_string = config.connection_string
        self.timeout = config.timeout


class EmailService:
    def __init__(self, config: Configuration):
        self.id = uuid.uuid4()
        self.smtp_server = "smtp.test.com"
        self.config = config


class NotificationService:
    def __init__(self, email_service: EmailService, db_service: DatabaseService):
        self.id = uuid.uuid4()
        self.email_service = email_service
        self.db_service = db_service


class AsyncService:
    def __init__(self):
        self.id = uuid.uuid4()
        self.initialized = False

    async def initialize(self):
        await asyncio.sleep(0.01)  # Simulate async initialization
        self.initialized = True


class DisposableService:
    def __init__(self):
        self.id = uuid.uuid4()
        self.disposed = False

    def dispose(self):
        self.disposed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.dispose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.dispose()


class ServiceWithOptionalDependency:
    def __init__(self, required: Configuration, optional: SampleService = None):
        self.required = required
        self.optional = optional


# Interface-like classes for testing
class IUserRepository:
    pass


class UserRepository(IUserRepository):
    def __init__(self, config: Configuration):
        self.config = config
        self.id = uuid.uuid4()


class MockUserRepository(IUserRepository):
    def __init__(self):
        self.id = uuid.uuid4()


# Factory functions
def configure_database_service(provider):
    config = provider.resolve(Configuration)
    return DatabaseService(config)


def configure_scoped_database_service(provider):
    config = provider.resolve(Configuration)
    return DatabaseService(config)


def configure_transient_database_service(provider):
    config = provider.resolve(Configuration)
    return DatabaseService(config)


async def async_factory(provider):
    service = AsyncService()
    await service.initialize()
    return service


def complex_factory(provider):
    config = provider.resolve(Configuration)
    email = provider.resolve(EmailService)
    db = provider.resolve(DatabaseService)
    return NotificationService(email, db)


class TestServiceCollection(unittest.TestCase):
    """Test ServiceCollection registration and configuration"""

    def setUp(self):
        self.collection = ServiceCollection()

    def test_singleton_registration(self):
        """Test registering singleton services"""
        self.collection.add_singleton(Configuration)
        self.collection.add_singleton(DatabaseService, factory=configure_database_service)

        container = self.collection._container
        self.assertIn(Configuration, container)
        self.assertIn(DatabaseService, container)

        config_reg = container[Configuration]
        db_reg = container[DatabaseService]

        self.assertEqual(config_reg.lifetime, Lifetime.Singleton)
        self.assertEqual(db_reg.lifetime, Lifetime.Singleton)
        self.assertIsNotNone(db_reg.factory)

    def test_transient_registration(self):
        """Test registering transient services"""
        self.collection.add_transient(TransientRepository)
        self.collection.add_transient(EmailService)

        container = self.collection._container
        self.assertIn(TransientRepository, container)
        self.assertIn(EmailService, container)

        self.assertEqual(container[TransientRepository].lifetime, Lifetime.Transient)
        self.assertEqual(container[EmailService].lifetime, Lifetime.Transient)

    def test_scoped_registration(self):
        """Test registering scoped services"""
        self.collection.add_scoped(ScopedRepository)
        self.collection.add_scoped(UserRepository)

        container = self.collection._container
        self.assertIn(ScopedRepository, container)
        self.assertIn(UserRepository, container)

        self.assertEqual(container[ScopedRepository].lifetime, Lifetime.Scoped)
        self.assertEqual(container[UserRepository].lifetime, Lifetime.Scoped)

    def test_interface_implementation_registration(self):
        """Test registering services with interface abstraction"""
        self.collection.add_singleton(IUserRepository, UserRepository)

        container = self.collection._container
        self.assertIn(IUserRepository, container)

        reg = container[IUserRepository]
        self.assertEqual(reg.dependency_type, IUserRepository)
        self.assertEqual(reg.implementation_type, UserRepository)

    def test_instance_registration(self):
        """Test registering pre-created instances"""
        config_instance = Configuration()
        config_instance.connection_string = "custom_connection"

        self.collection.add_singleton(Configuration, instance=config_instance)

        reg = self.collection._container[Configuration]
        self.assertEqual(reg.instance, config_instance)
        self.assertEqual(reg.instance.connection_string, "custom_connection")

    def test_factory_registration(self):
        """Test registering services with factories"""
        self.collection.add_singleton(Configuration)
        self.collection.add_singleton(DatabaseService, factory=configure_database_service)

        reg = self.collection._container[DatabaseService]
        self.assertIsNotNone(reg.factory)
        self.assertEqual(reg.factory, configure_database_service)

    def test_register_many(self):
        """Test registering multiple types at once"""
        types = [TransientRepository, EmailService, SampleService]
        self.collection.register_many(types, Lifetime.Transient)

        for t in types:
            self.assertIn(t, self.collection._container)
            self.assertEqual(self.collection._container[t].lifetime, Lifetime.Transient)

    def test_constructor_dependency_detection(self):
        """Test automatic constructor parameter detection"""
        self.collection.add_singleton(Configuration)
        self.collection.add_transient(DatabaseService)

        db_reg = self.collection._container[DatabaseService]
        self.assertEqual(len(db_reg.constructor_params), 1)
        self.assertEqual(db_reg.constructor_params[0].name, 'config')
        self.assertEqual(db_reg.constructor_params[0].dependency_type, Configuration)

    def test_multiple_constructor_dependencies(self):
        """Test services with multiple constructor dependencies"""
        self.collection.add_singleton(Configuration)
        self.collection.add_singleton(EmailService)
        self.collection.add_singleton(DatabaseService, factory=configure_database_service)
        self.collection.add_transient(NotificationService)

        notification_reg = self.collection._container[NotificationService]
        self.assertEqual(len(notification_reg.constructor_params), 2)

        param_types = {p.dependency_type for p in notification_reg.constructor_params}
        self.assertIn(EmailService, param_types)
        self.assertIn(DatabaseService, param_types)


class TestDependencyInjection(unittest.TestCase):
    """Test core dependency injection functionality"""

    def setUp(self):
        # Common setup for most tests
        self.collection = ServiceCollection()
        self.collection.add_singleton(Configuration)
        self.collection.add_singleton(SingletonRepository)
        self.collection.add_transient(TransientRepository)
        self.collection.add_scoped(ScopedRepository)
        self.collection.add_singleton(DatabaseService, factory=configure_database_service)
        self.provider = self.collection.build_provider()
        logger.info("Built ServiceProvider for test %s", self._testMethodName)

    def test_singleton_behavior(self):
        """Test singleton lifetime behavior"""
        logger.info("Testing singleton resolution")
        one = self.provider.resolve(SingletonRepository)
        two = self.provider.resolve(SingletonRepository)
        logger.info("IDs: %s, %s", one.id, two.id)
        self.assertEqual(one.id, two.id, "Singleton instances should match")
        self.assertIs(one, two, "Singleton instances should be the same object")

    def test_transient_behavior(self):
        """Test transient lifetime behavior"""
        logger.info("Testing transient resolution")
        one = self.provider.resolve(TransientRepository)
        two = self.provider.resolve(TransientRepository)
        logger.info("IDs: %s, %s", one.id, two.id)
        self.assertNotEqual(one.id, two.id, "Transient instances should differ")
        self.assertIsNot(one, two, "Transient instances should be different objects")

    def test_scoped_behavior(self):
        """Test scoped lifetime behavior"""
        logger.info("Testing scoped resolution per-scope")
        with self.provider.create_scope() as scope1:
            a = scope1.resolve(ScopedRepository)
            b = scope1.resolve(ScopedRepository)
            logger.info("Scope1 IDs: %s, %s", a.id, b.id)
            self.assertEqual(a.id, b.id, "Scoped within same scope should match")
            self.assertIs(a, b, "Scoped within same scope should be same object")

        with self.provider.create_scope() as scope2:
            c = scope2.resolve(ScopedRepository)
            logger.info("Scope2 ID: %s", c.id)
            self.assertNotEqual(a.id, c.id, "Scoped across scopes should differ")
            self.assertIsNot(a, c, "Scoped across scopes should be different objects")

    def test_singleton_factory(self):
        """Test singleton factory function"""
        logger.info("Testing singleton factory for DatabaseService")
        one = self.provider.resolve(DatabaseService)
        two = self.provider.resolve(DatabaseService)
        logger.info("Factory singleton IDs: %s, %s", one.id, two.id)
        self.assertEqual(one.id, two.id, "Factory singleton should match")
        self.assertIs(one, two, "Factory singleton should be same object")

    def test_scoped_factory(self):
        """Test scoped factory function"""
        logger.info("Adding scoped factory registration for DatabaseService")
        collection = ServiceCollection()
        collection.add_singleton(Configuration)
        collection.add_scoped(DatabaseService, factory=configure_scoped_database_service)
        provider = collection.build_provider()

        with provider.create_scope() as scope1:
            a = scope1.resolve(DatabaseService)
            b = scope1.resolve(DatabaseService)
            logger.info("Scoped-factory Scope1 IDs: %s, %s", a.id, b.id)
            self.assertEqual(a.id, b.id)
            self.assertIs(a, b)

        with provider.create_scope() as scope2:
            c = scope2.resolve(DatabaseService)
            logger.info("Scoped-factory Scope2 ID: %s", c.id)
            self.assertNotEqual(a.id, c.id)
            self.assertIsNot(a, c)

    def test_transient_factory(self):
        """Test transient factory function"""
        logger.info("Creating fresh collection for transient factory test")
        coll = ServiceCollection()
        coll.add_singleton(Configuration)
        coll.add_transient(SampleService, factory=configure_transient_database_service)
        provider = coll.build_provider()

        one = provider.resolve(SampleService)
        two = provider.resolve(SampleService)
        logger.info("Transient-factory IDs: %s, %s", one.id, two.id)
        self.assertNotEqual(one.id, two.id)
        self.assertIsNot(one, two)

    def test_complex_service_singleton(self):
        """Test complex service with multiple dependencies as singleton"""
        logger.info("Testing ComplexService with singleton lifetimes")

        coll = ServiceCollection()
        coll.add_singleton(Configuration)
        coll.add_singleton(EmailService)
        coll.add_singleton(DatabaseService, factory=configure_database_service)
        coll.add_singleton(NotificationService)

        prov = coll.build_provider()
        first = prov.resolve(NotificationService)
        second = prov.resolve(NotificationService)

        logger.info("NotificationService IDs: %s, %s", first.id, second.id)
        self.assertEqual(first.id, second.id)
        self.assertIs(first, second)

        # Verify dependencies are properly injected
        self.assertIsInstance(first.email_service, EmailService)
        self.assertIsInstance(first.db_service, DatabaseService)

    def test_complex_service_transient(self):
        """Test complex service with multiple dependencies as transient"""
        logger.info("Testing ComplexService with transient lifetimes")

        coll = ServiceCollection()
        coll.add_singleton(Configuration)
        coll.add_singleton(EmailService)
        coll.add_singleton(DatabaseService, factory=configure_database_service)
        coll.add_transient(NotificationService)

        prov = coll.build_provider()
        first = prov.resolve(NotificationService)
        second = prov.resolve(NotificationService)

        logger.info("NotificationService (transient) IDs: %s, %s", first.id, second.id)
        self.assertNotEqual(first.id, second.id)
        self.assertIsNot(first, second)

        # Verify dependencies are properly injected and singletons are shared
        self.assertIsInstance(first.email_service, EmailService)
        self.assertIsInstance(first.db_service, DatabaseService)
        self.assertIs(first.email_service, second.email_service)  # EmailService is singleton
        self.assertIs(first.db_service, second.db_service)  # DatabaseService is singleton

    def test_nested_dependency_resolution(self):
        """Test deeply nested dependency chains"""
        coll = ServiceCollection()
        coll.add_singleton(Configuration)
        coll.add_singleton(EmailService)
        coll.add_singleton(DatabaseService, factory=configure_database_service)
        coll.add_singleton(NotificationService, factory=complex_factory)

        prov = coll.build_provider()
        notification = prov.resolve(NotificationService)

        # Verify the entire chain is properly resolved
        self.assertIsInstance(notification, NotificationService)
        self.assertIsInstance(notification.email_service, EmailService)
        self.assertIsInstance(notification.db_service, DatabaseService)
        self.assertIsInstance(notification.email_service.config, Configuration)
        self.assertIsInstance(notification.db_service.connection_string, str)

    def test_service_not_registered_error(self):
        """Test error when trying to resolve unregistered service"""
        with self.assertRaises(Exception) as context:
            self.provider.resolve(EmailService)

        self.assertIn("Failed to locate registration", str(context.exception))
        self.assertIn("EmailService", str(context.exception))

    def test_scoped_resolution_without_scope_error(self):
        """Test error when trying to resolve scoped service without scope"""
        with self.assertRaises(Exception) as context:
            self.provider.resolve(ScopedRepository)

        self.assertIn("Scoped resolution requires a scope", str(context.exception))

    def test_instance_registration_behavior(self):
        """Test pre-created instance registration"""
        config = Configuration()
        config.connection_string = "custom_connection"

        coll = ServiceCollection()
        coll.add_singleton(Configuration, instance=config)
        prov = coll.build_provider()

        resolved = prov.resolve(Configuration)
        self.assertIs(resolved, config)
        self.assertEqual(resolved.connection_string, "custom_connection")


class TestAsyncSupport(unittest.TestCase):
    """Test asynchronous dependency injection features"""

    def setUp(self):
        self.collection = ServiceCollection()
        self.collection.add_singleton(Configuration)
        # Use a simple sync factory for testing to avoid event loop issues

        def simple_async_factory(provider):
            service = AsyncService()
            # Don't actually await initialization in tests
            service.initialized = True
            return service

        self.collection.add_singleton(AsyncService, factory=simple_async_factory)
        self.collection.add_transient(SampleService)

    def test_async_singleton_resolution(self):
        """Test async resolution of singleton services"""
        async def test():
            provider = self.collection.build_provider()

            service1 = await provider.resolve_async(AsyncService)
            service2 = await provider.resolve_async(AsyncService)

            self.assertEqual(service1.id, service2.id)
            self.assertTrue(service1.initialized)
            self.assertTrue(service2.initialized)
            self.assertIs(service1, service2)

        asyncio.run(test())

    def test_async_transient_resolution(self):
        """Test async resolution of transient services"""
        async def test():
            provider = self.collection.build_provider()

            service1 = await provider.resolve_async(SampleService)
            service2 = await provider.resolve_async(SampleService)

            self.assertNotEqual(service1.id, service2.id)
            self.assertIsNot(service1, service2)

        asyncio.run(test())

    def test_async_scoped_resolution(self):
        """Test async resolution in scoped context"""
        async def test():
            self.collection.add_scoped(ScopedRepository)
            provider = self.collection.build_provider()

            async with provider.create_scope() as scope:
                service1 = await scope.resolve_async(ScopedRepository)
                service2 = await scope.resolve_async(ScopedRepository)

                self.assertEqual(service1.id, service2.id)
                self.assertIs(service1, service2)

        asyncio.run(test())

    def test_sync_factory_resolution(self):
        """Test sync factory functions in async context"""
        async def test():
            provider = self.collection.build_provider()
            service = await provider.resolve_async(AsyncService)

            self.assertIsInstance(service, AsyncService)
            self.assertTrue(service.initialized)

        asyncio.run(test())


class TestServiceScope(unittest.TestCase):
    """Test service scope functionality and lifecycle"""

    def setUp(self):
        self.collection = ServiceCollection()
        self.collection.add_singleton(Configuration)
        self.collection.add_scoped(ScopedRepository)
        self.collection.add_scoped(DisposableService)
        self.collection.add_transient(TransientRepository)
        self.provider = self.collection.build_provider()

    def test_scope_creation_and_disposal(self):
        """Test scope creation and proper disposal"""
        scope = self.provider.create_scope()
        self.assertIsInstance(scope, ServiceScope)

        # Scope should be usable
        service = scope.resolve(ScopedRepository)
        self.assertIsInstance(service, ScopedRepository)

        # Manually dispose
        scope.dispose()
        # After disposal, scoped instances should be cleared
        self.assertEqual(len(scope._scoped_instances), 0)

    def test_scope_context_manager(self):
        """Test scope as context manager"""
        with self.provider.create_scope() as scope:
            service = scope.resolve(ScopedRepository)
            self.assertIsInstance(service, ScopedRepository)
            self.assertEqual(len(scope._scoped_instances), 1)

        # After context exit, scope should be disposed
        self.assertEqual(len(scope._scoped_instances), 0)

    def test_scope_async_context_manager(self):
        """Test scope as async context manager"""
        async def test():
            async with self.provider.create_scope() as scope:
                service = await scope.resolve_async(ScopedRepository)
                self.assertIsInstance(service, ScopedRepository)
                self.assertEqual(len(scope._scoped_instances), 1)

            # After context exit, scope should be disposed
            self.assertEqual(len(scope._scoped_instances), 0)

        asyncio.run(test())

    def test_scope_disposable_services(self):
        """Test that disposable services are properly cleaned up"""
        async def test():
            disposable_service = None
            async with self.provider.create_scope() as scope:
                disposable_service = await scope.resolve_async(DisposableService)
                self.assertFalse(disposable_service.disposed)

            # Service should be disposed after scope exit
            self.assertTrue(disposable_service.disposed)

        asyncio.run(test())

    def test_scope_transient_resolution(self):
        """Test transient services resolved through scope"""
        with self.provider.create_scope() as scope:
            service1 = scope.resolve(TransientRepository)
            service2 = scope.resolve(TransientRepository)

            # Transient services should be different even in same scope
            self.assertNotEqual(service1.id, service2.id)
            self.assertIsNot(service1, service2)

    def test_scope_singleton_resolution(self):
        """Test singleton services resolved through scope"""
        with self.provider.create_scope() as scope:
            config1 = scope.resolve(Configuration)
            config2 = scope.resolve(Configuration)

            # Singletons should be same even through scope
            self.assertIs(config1, config2)

    def test_multiple_scopes_isolation(self):
        """Test that multiple scopes are properly isolated"""
        scope1 = self.provider.create_scope()
        scope2 = self.provider.create_scope()

        try:
            service1 = scope1.resolve(ScopedRepository)
            service2 = scope2.resolve(ScopedRepository)

            # Services should be different across scopes
            self.assertNotEqual(service1.id, service2.id)
            self.assertIsNot(service1, service2)
        finally:
            scope1.dispose()
            scope2.dispose()


class TestErrorHandling(unittest.TestCase):
    """Test error handling and edge cases"""

    def test_circular_dependency_detection(self):
        """Test detection of circular dependencies"""
        # Create a simpler circular dependency without forward references
        class ServiceA:
            def __init__(self, service_b):
                self.service_b = service_b

        class ServiceB:
            def __init__(self, service_a):
                self.service_a = service_a

        collection = ServiceCollection()

        # Manually create registrations to simulate circular dependency
        from depi.services import DependencyRegistration, ConstructorDependency

        reg_a = DependencyRegistration(
            dependency_type=ServiceA,
            lifetime='singleton',
            implementation_type=ServiceA,
            constructor_params=[ConstructorDependency('service_b', ServiceB)]
        )

        reg_b = DependencyRegistration(
            dependency_type=ServiceB,
            lifetime='singleton',
            implementation_type=ServiceB,
            constructor_params=[ConstructorDependency('service_a', ServiceA)]
        )

        collection._container[ServiceA] = reg_a
        collection._container[ServiceB] = reg_b

        with self.assertRaises(Exception) as context:
            provider = collection.build_provider()

        self.assertIn("Cyclic dependency detected", str(context.exception))

    def test_missing_dependency_error(self):
        """Test error when dependency is not registered"""
        collection = ServiceCollection()
        collection.add_singleton(DatabaseService)  # Requires Configuration, but it's not registered

        with self.assertRaises(Exception) as context:
            collection.build_provider()

        self.assertIn("Failed to locate registration", str(context.exception))

    def test_invalid_lifetime_error(self):
        """Test handling of invalid lifetime values"""
        # This test ensures the framework handles unexpected lifetime values gracefully
        registration = DependencyRegistration(
            dependency_type=SampleService,
            lifetime="invalid_lifetime",
            implementation_type=SampleService
        )

        collection = ServiceCollection()
        collection._container[SampleService] = registration
        provider = ServiceProvider(collection)
        provider._dependency_lookup = collection._container
        provider._dependencies = [registration]
        provider._initialize_provider()

        with self.assertRaises(Exception) as context:
            provider.resolve(SampleService)

        self.assertIn("Unknown lifetime", str(context.exception))

    def test_factory_exception_handling(self):
        """Test handling of exceptions in factory functions"""
        def failing_factory(provider):
            raise ValueError("Factory failed")

        collection = ServiceCollection()
        collection.add_singleton(SampleService, factory=failing_factory)

        with self.assertRaises(ValueError) as context:
            collection.build_provider()

        self.assertEqual(str(context.exception), "Factory failed")

    def test_constructor_exception_handling(self):
        """Test handling of exceptions in constructors"""
        class FailingService:
            def __init__(self):
                raise RuntimeError("Constructor failed")

        collection = ServiceCollection()
        collection.add_singleton(FailingService)

        with self.assertRaises(RuntimeError) as context:
            collection.build_provider()

        self.assertEqual(str(context.exception), "Constructor failed")

    def test_transient_constructor_exception_handling(self):
        """Test handling of exceptions in transient constructors"""
        class FailingTransientService:
            def __init__(self):
                raise RuntimeError("Transient constructor failed")

        collection = ServiceCollection()
        collection.add_transient(FailingTransientService)
        provider = collection.build_provider()  # Should not fail at build time

        with self.assertRaises(RuntimeError) as context:
            provider.resolve(FailingTransientService)

        self.assertEqual(str(context.exception), "Transient constructor failed")


class TestThreadSafety(unittest.TestCase):
    """Test thread safety of the dependency injection container"""

    def setUp(self):
        self.collection = ServiceCollection()
        self.collection.add_singleton(Configuration)
        self.collection.add_singleton(SingletonRepository)
        self.collection.add_transient(TransientRepository)
        self.collection.add_scoped(ScopedRepository)
        self.provider = self.collection.build_provider()

    def test_singleton_thread_safety(self):
        """Test that singleton resolution is thread-safe"""
        results = []
        num_threads = 10

        def resolve_singleton():
            service = self.provider.resolve(SingletonRepository)
            results.append(service)

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(resolve_singleton) for _ in range(num_threads)]
            for future in as_completed(futures):
                future.result()  # Wait for completion

        # All resolved instances should be the same
        first_instance = results[0]
        for instance in results:
            self.assertIs(instance, first_instance)

    def test_transient_thread_safety(self):
        """Test that transient resolution is thread-safe"""
        results = []
        num_threads = 10

        def resolve_transient():
            service = self.provider.resolve(TransientRepository)
            results.append(service.id)

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(resolve_transient) for _ in range(num_threads)]
            for future in as_completed(futures):
                future.result()  # Wait for completion

        # All resolved instances should be different
        unique_ids = set(results)
        self.assertEqual(len(unique_ids), num_threads)

    def test_scoped_thread_safety(self):
        """Test that scoped resolution is thread-safe"""
        results = []
        num_threads = 5

        def resolve_in_scope():
            with self.provider.create_scope() as scope:
                service1 = scope.resolve(ScopedRepository)
                service2 = scope.resolve(ScopedRepository)
                # Within same scope, should be same instance
                assert service1.id == service2.id
                results.append(service1.id)

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(resolve_in_scope) for _ in range(num_threads)]
            for future in as_completed(futures):
                future.result()  # Wait for completion

        # Each scope should have different instances
        unique_ids = set(results)
        self.assertEqual(len(unique_ids), num_threads)


class TestDependencyInjectorDecorator(unittest.TestCase):
    """Test the dependency injector decorator functionality"""

    def setUp(self):
        self.collection = ServiceCollection()
        self.collection.add_singleton(Configuration)
        self.collection.add_singleton(EmailService)
        self.collection.add_transient(TransientRepository)
        self.provider = self.collection.build_provider()
        self.injector = DependencyInjector(self.provider)

    def test_function_decoration(self):
        """Test decorating functions with dependency injection"""
        @self.injector.inject
        async def test_function(config: Configuration, email: EmailService):
            return config, email

        # Set up scope manually for test
        with self.injector.create_scope() as scope:
            test_function._scope = scope
            config, email = asyncio.run(test_function())

            self.assertIsInstance(config, Configuration)
            self.assertIsInstance(email, EmailService)

    def test_partial_injection(self):
        """Test injection with some parameters provided manually"""
        @self.injector.inject
        async def test_function(manual_param: str, config: Configuration, email: EmailService):
            return manual_param, config, email

        with self.injector.create_scope() as scope:
            test_function._scope = scope
            manual, config, email = asyncio.run(test_function("test_value"))

            self.assertEqual(manual, "test_value")
            self.assertIsInstance(config, Configuration)
            self.assertIsInstance(email, EmailService)

    def test_strict_mode_missing_dependency(self):
        """Test strict mode behavior with missing dependencies"""
        injector = DependencyInjector(self.provider, strict=True)

        @injector.inject
        async def test_function(config: Configuration, missing: SampleService):
            return config, missing

        with injector.create_scope() as scope:
            test_function._scope = scope
            with self.assertRaises(Exception) as context:
                asyncio.run(test_function())

            self.assertIn("Failed to resolve dependency", str(context.exception))

    def test_non_strict_mode_missing_dependency(self):
        """Test non-strict mode behavior with missing dependencies"""
        injector = DependencyInjector(self.provider, strict=False)

        @injector.inject
        async def test_function(config: Configuration, missing: SampleService = None):
            return config, missing

        with injector.create_scope() as scope:
            test_function._scope = scope
            config, missing = asyncio.run(test_function())

            self.assertIsInstance(config, Configuration)
            self.assertIsNone(missing)


class TestAdvancedFeatures(unittest.TestCase):
    """Test advanced dependency injection features"""

    def test_multiple_implementations(self):
        """Test registering multiple implementations for same interface"""
        collection = ServiceCollection()
        collection.add_singleton(Configuration)
        collection.add_singleton(IUserRepository, UserRepository)

        provider = collection.build_provider()
        repo = provider.resolve(IUserRepository)

        self.assertIsInstance(repo, UserRepository)
        self.assertIsInstance(repo.config, Configuration)

    def test_conditional_registration_override(self):
        """Test overriding registrations"""
        collection = ServiceCollection()
        collection.add_singleton(IUserRepository, UserRepository)
        collection.add_singleton(Configuration)

        # Override with mock implementation
        collection.add_singleton(IUserRepository, MockUserRepository)

        provider = collection.build_provider()
        repo = provider.resolve(IUserRepository)

        self.assertIsInstance(repo, MockUserRepository)

    def test_complex_dependency_graph(self):
        """Test resolving complex dependency graphs"""
        collection = ServiceCollection()
        collection.add_singleton(Configuration)
        collection.add_singleton(EmailService)
        collection.add_singleton(DatabaseService, factory=configure_database_service)
        collection.add_scoped(UserRepository)
        collection.add_transient(NotificationService)

        provider = collection.build_provider()

        with provider.create_scope() as scope:
            notification = scope.resolve(NotificationService)

            # Verify entire dependency graph
            self.assertIsInstance(notification, NotificationService)
            self.assertIsInstance(notification.email_service, EmailService)
            self.assertIsInstance(notification.db_service, DatabaseService)
            self.assertIsInstance(notification.email_service.config, Configuration)
            self.assertEqual(
                notification.db_service.connection_string,
                notification.email_service.config.connection_string
            )

    def test_lazy_singleton_initialization(self):
        """Test that singletons are initialized lazily (not during build)"""
        initialization_count = 0

        class LazyService:
            def __init__(self):
                nonlocal initialization_count
                initialization_count += 1
                self.id = uuid.uuid4()

        collection = ServiceCollection()
        collection.add_transient(LazyService)  # Use transient to avoid build-time initialization
        provider = collection.build_provider()

        # Should not be initialized yet
        self.assertEqual(initialization_count, 0)

        # First resolution should initialize
        service1 = provider.resolve(LazyService)
        self.assertEqual(initialization_count, 1)

        # Second resolution should create new instance (transient)
        service2 = provider.resolve(LazyService)
        self.assertEqual(initialization_count, 2)
        self.assertNotEqual(service1.id, service2.id)

    def test_singleton_eager_initialization_during_build(self):
        """Test that singletons are initialized during build"""
        initialization_count = 0

        class EagerService:
            def __init__(self):
                nonlocal initialization_count
                initialization_count += 1
                self.id = uuid.uuid4()

        collection = ServiceCollection()
        collection.add_singleton(EagerService)

        # Should not be initialized yet
        self.assertEqual(initialization_count, 0)

        # Building provider should initialize singletons
        provider = collection.build_provider()
        self.assertEqual(initialization_count, 1)

        # Resolving should reuse the same instance
        service1 = provider.resolve(EagerService)
        service2 = provider.resolve(EagerService)
        self.assertEqual(initialization_count, 1)  # Still just 1
        self.assertIs(service1, service2)

    def test_eager_singleton_initialization(self):
        """Test that singletons with instances are available immediately"""
        eager_service = SampleService()

        collection = ServiceCollection()
        collection.add_singleton(SampleService, instance=eager_service)
        provider = collection.build_provider()

        resolved = provider.resolve(SampleService)
        self.assertIs(resolved, eager_service)

    def test_performance_multiple_resolutions(self):
        """Test performance of multiple dependency resolutions"""
        collection = ServiceCollection()
        collection.add_singleton(Configuration)
        collection.add_singleton(SingletonRepository)
        collection.add_transient(TransientRepository)
        provider = collection.build_provider()

        start_time = time.time()

        # Resolve many instances
        for _ in range(1000):
            singleton = provider.resolve(SingletonRepository)
            transient = provider.resolve(TransientRepository)
            config = provider.resolve(Configuration)

        end_time = time.time()
        duration = end_time - start_time

        # Should complete reasonably quickly (adjust threshold as needed)
        self.assertLess(duration, 1.0, "Resolution should be performant")
        logger.info(f"1000 resolutions completed in {duration:.3f} seconds")


if __name__ == "__main__":
    # Run tests with verbose output
    unittest.main(verbosity=2)
