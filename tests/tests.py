import uuid
import logging
import unittest

from depi.services import ServiceCollection

# configure root logger once
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


class SampleService:
    def __init__(self):
        self.id = uuid.uuid4()


class SingletonRepository(SampleService):
    pass


class ScopedRepository(SampleService):
    pass


class TransientRepository(SampleService):
    pass


class Configuration:
    def __init__(self):
        self.connection_string = "test_connection_string"


class DatabaseService(SampleService):
    def __init__(self, config: Configuration):
        super().__init__()
        self.connection_string = config.connection_string


def configure_database_service(provider):
    config = provider.resolve(Configuration)
    return DatabaseService(config)


def configure_scoped_database_service(provider):
    config = provider.resolve(Configuration)
    return DatabaseService(config)


def configure_transient_database_service(provider):
    config = provider.resolve(Configuration)
    return DatabaseService(config)


class TestDependencyInjection(unittest.TestCase):
    def setUp(self):
        # common setup for most tests
        self.collection = ServiceCollection()
        self.collection.add_singleton(Configuration)
        self.collection.add_singleton(SingletonRepository)
        self.collection.add_transient(TransientRepository)
        self.collection.add_scoped(ScopedRepository)
        self.collection.add_singleton(DatabaseService, factory=configure_database_service)
        self.provider = self.collection.build_provider()
        logger.info("Built ServiceProvider for test %s", self._testMethodName)

    def test_singleton_behavior(self):
        logger.info("Testing singleton resolution")
        one = self.provider.resolve(SingletonRepository)
        two = self.provider.resolve(SingletonRepository)
        logger.info("IDs: %s, %s", one.id, two.id)
        self.assertEqual(one.id, two.id, "Singleton instances should match")

    def test_transient_behavior(self):
        logger.info("Testing transient resolution")
        one = self.provider.resolve(TransientRepository)
        two = self.provider.resolve(TransientRepository)
        logger.info("IDs: %s, %s", one.id, two.id)
        self.assertNotEqual(one.id, two.id, "Transient instances should differ")

    def test_scoped_behavior(self):
        logger.info("Testing scoped resolution per-scope")
        with self.provider.create_scope() as scope1:
            a = scope1.resolve(ScopedRepository)
            b = scope1.resolve(ScopedRepository)
            logger.info("Scope1 IDs: %s, %s", a.id, b.id)
            self.assertEqual(a.id, b.id, "Scoped within same scope should match")
        with self.provider.create_scope() as scope2:
            c = scope2.resolve(ScopedRepository)
            logger.info("Scope2 ID: %s", c.id)
            self.assertNotEqual(a.id, c.id, "Scoped across scopes should differ")

    def test_singleton_factory(self):
        logger.info("Testing singleton factory for DatabaseService")
        one = self.provider.resolve(DatabaseService)
        two = self.provider.resolve(DatabaseService)
        logger.info("Factory singleton IDs: %s, %s", one.id, two.id)
        self.assertEqual(one.id, two.id, "Factory singleton should match")

    def test_scoped_factory(self):
        logger.info("Adding scoped factory registration for DatabaseService")
        self.collection.add_scoped(DatabaseService, factory=configure_scoped_database_service)
        provider2 = self.collection.build_provider()
        with provider2.create_scope() as scope1:
            a = scope1.resolve(DatabaseService)
            b = scope1.resolve(DatabaseService)
            logger.info("Scoped-factory Scope1 IDs: %s, %s", a.id, b.id)
            self.assertEqual(a.id, b.id)
        with provider2.create_scope() as scope2:
            c = scope2.resolve(DatabaseService)
            logger.info("Scoped-factory Scope2 ID: %s", c.id)
            self.assertNotEqual(a.id, c.id)

    def test_transient_factory(self):
        logger.info("Creating fresh collection for transient factory test")
        coll = ServiceCollection()
        coll.add_singleton(Configuration)
        coll.add_transient(SampleService, factory=configure_transient_database_service)
        provider3 = coll.build_provider()
        one = provider3.resolve(SampleService)
        two = provider3.resolve(SampleService)
        logger.info("Transient-factory IDs: %s, %s", one.id, two.id)
        self.assertNotEqual(one.id, two.id)

    def test_complex_service_singleton(self):
        logger.info("Testing ComplexService with singleton lifetimes")

        class ComplexService:
            def __init__(self, config: Configuration, db: DatabaseService):
                self.id = uuid.uuid4()

        coll = ServiceCollection()
        coll.add_singleton(Configuration)
        coll.add_singleton(DatabaseService, factory=configure_database_service)
        coll.add_singleton(ComplexService)
        prov = coll.build_provider()
        first = prov.resolve(ComplexService)
        second = prov.resolve(ComplexService)
        logger.info("ComplexService IDs: %s, %s", first.id, second.id)
        self.assertEqual(first.id, second.id)

    def test_complex_service_transient(self):
        logger.info("Testing ComplexService with transient lifetimes")

        class ComplexService:
            def __init__(self, config: Configuration, db: DatabaseService):
                self.id = uuid.uuid4()

        coll = ServiceCollection()
        coll.add_singleton(Configuration)
        coll.add_singleton(DatabaseService, factory=configure_database_service)
        coll.add_transient(ComplexService)
        prov = coll.build_provider()
        first = prov.resolve(ComplexService)
        second = prov.resolve(ComplexService)
        logger.info("ComplexService (transient) IDs: %s, %s", first.id, second.id)
        self.assertNotEqual(first.id, second.id)


if __name__ == "__main__":
    unittest.main()
