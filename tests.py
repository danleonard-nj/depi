import uuid

from services import ServiceCollection


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


service_collection = ServiceCollection()

# Singleton
service_collection.add_singleton(Configuration)
service_collection.add_singleton(SingletonRepository)
service_collection.add_transient(TransientRepository)
service_collection.add_scoped(ScopedRepository)


# Fix: Use provider instead of service_collection in the factory function
def configure_database_service(provider):
    config = provider.resolve(Configuration)
    return DatabaseService(config)


service_collection.add_singleton(DatabaseService, factory=configure_database_service)

print("Service collection configured.")
print("Building service provider...")
provider = service_collection.build_provider()
print("Service provider built.")


print('Resolving singleton services')
singleton_one = provider.resolve(SingletonRepository)
singleton_two = provider.resolve(SingletonRepository)
print(f"Singleton One ID: {singleton_one.id}")
print(f"Singleton Two ID: {singleton_two.id}")


assert singleton_one.id == singleton_two.id, "Singleton instances should be the same."


print('Resolving transient services')
transient_one = provider.resolve(TransientRepository)
transient_two = provider.resolve(TransientRepository)

print(f"Transient One ID: {transient_one.id}")
print(f"Transient Two ID: {transient_two.id}")

assert transient_one.id != transient_two.id, "Transient instances should be different."

# Scoped
print('Resolving scoped services')
with provider.create_scope() as scope_provider_one:
    print("Inside first scope")
    scoped_one = scope_provider_one.resolve(ScopedRepository)
    scoped_two = scope_provider_one.resolve(ScopedRepository)

    print(f"Scoped One ID: {scoped_one.id}")
    print(f"Scoped Two ID: {scoped_two.id}")
    assert scoped_one.id == scoped_two.id, "Scoped instances should be the same within the same scope."
print("Outside first scope")

# Simulate a new scope
print("Creating second scope")
with provider.create_scope() as scope_provider_two:
    print("Inside second scope")
    scoped_three = scope_provider_two.resolve(ScopedRepository)
    print(f"Scoped Three ID: {scoped_three.id}")
    print(f"Scoped One ID (from first scope): {scoped_one.id}")
    assert scoped_one.id != scoped_three.id, "Scoped instances should be different across different scopes."


# Test singleton factory
print("Testing singleton factory")
singleton_factory_one = provider.resolve(DatabaseService)
singleton_factory_two = provider.resolve(DatabaseService)
print(f"Singleton Factory One ID: {singleton_factory_one.id}")
print(f"Singleton Factory Two ID: {singleton_factory_two.id}")
assert singleton_factory_one.id == singleton_factory_two.id, "Singleton factory instances should be the same."

# Now add and test scoped and transient factories


def configure_scoped_database_service(provider):
    config = provider.resolve(Configuration)
    return DatabaseService(config)


def configure_transient_database_service(provider):
    config = provider.resolve(Configuration)
    return DatabaseService(config)


# Add scoped and transient versions for testing
service_collection.add_scoped(DatabaseService, factory=configure_scoped_database_service)
service_collection.add_scoped(DatabaseService, factory=configure_transient_database_service)


scoped_one_id = ''
# Test scoped factory
print("Testing scoped factory")
with provider.create_scope() as scope:
    scoped_factory_one = scope.resolve(DatabaseService)
    scoped_factory_two = scope.resolve(DatabaseService)
    print(f"Scoped Factory One ID: {scoped_factory_one.id}")
    print(f"Scoped Factory Two ID: {scoped_factory_two.id}")
    assert scoped_factory_one.id == scoped_factory_two.id, "Scoped factory instances should be the same within a scope."
    scoped_one_id = scoped_factory_one.id

with provider.create_scope() as scope:
    scoped_factory_three = scope.resolve(DatabaseService)
    print(f"Scoped Factory Three ID: {scoped_factory_three.id}")
    assert scoped_factory_three.id != scoped_one_id, "Scoped factory instances should be different across different scopes."

# Transient factories
print("Testing transient factory")

collection = ServiceCollection()


def test_configure_transient_factory(provider):
    config = provider.resolve(Configuration)
    print('Resolved configuration in transient factory')
    assert isinstance(config, Configuration), "Configuration should be resolved correctly."
    return SampleService()


collection.add_singleton(Configuration)
collection.add_transient(SampleService, factory=test_configure_transient_factory)

provider = collection.build_provider()
print("Transient factory provider built.")

transient_one = provider.resolve(SampleService)
transient_two = provider.resolve(SampleService)

print(f"Transient Factory One ID: {transient_one.id}")
print(f"Transient Factory Two ID: {transient_two.id}")
assert transient_one.id != transient_two.id, "Transient factory instances should be different."

print("All tests passed.")

with provider.create_scope() as scope:
    transient_factory_one = scope.resolve(SampleService)
    transient_factory_two = scope.resolve(SampleService)
    print(f"Transient Factory One ID: {transient_factory_one.id}")
    print(f"Transient Factory Two ID: {transient_factory_two.id}")
    assert transient_factory_one.id != transient_factory_two.id, "Transient factory instances should be different within a scope."

print("All tests passed.")
