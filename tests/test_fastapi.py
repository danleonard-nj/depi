import pytest
from fastapi import FastAPI, Request, Depends
from fastapi.testclient import TestClient
from depi import (
    ServiceCollection,
    ServiceProvider,
    create_fastapi_injector,
    FastAPIDependencyInjector
)


class MyService:
    def get_value(self):
        return "fastapi ok"


class DatabaseService:
    def __init__(self, my_service: MyService):
        self.my_service = my_service

    def get_data(self):
        return f"db: {self.my_service.get_value()}"


class CacheService:
    def __init__(self):
        self.data = {}

    def get(self, key: str):
        return self.data.get(key, "cache miss")

    def set(self, key: str, value: str):
        self.data[key] = value


def test_fastapi_manual_resolution():
    """Test manual dependency resolution using ServiceCollection"""
    app = FastAPI()
    services = ServiceCollection()
    services.add_singleton(MyService)
    services.add_transient(DatabaseService)
    provider = services.build_provider()

    @app.get("/di/manual")
    async def di_view_manual():
        service = provider.resolve(MyService)
        db_service = provider.resolve(DatabaseService)
        return {
            "approach": "manual",
            "value": service.get_value(),
            "db_data": db_service.get_data()
        }

    client = TestClient(app)
    response = client.get("/di/manual")
    assert response.status_code == 200
    data = response.json()
    assert data["approach"] == "manual"
    assert data["value"] == "fastapi ok"
    assert data["db_data"] == "db: fastapi ok"


def test_fastapi_pure_wrapper_injection():
    """Test Strategy 1: Pure wrapper approach with new FastAPIDependencyInjector"""
    app = FastAPI()
    services = ServiceCollection()
    services.add_singleton(MyService)
    services.add_transient(DatabaseService)
    services.add_scoped(CacheService)
    provider = services.build_provider()

    # Create FastAPI-specific injector
    injector = create_fastapi_injector(provider, strict=True)
    injector.setup_fastapi(app)

    @app.get("/di/inject")
    @injector.inject
    async def di_view_injected(my_service: MyService, db_service: DatabaseService, cache: CacheService):
        cache.set("test", "cached_value")
        return {
            "approach": "pure_wrapper",
            "value": my_service.get_value(),
            "db_data": db_service.get_data(),
            "cache_data": cache.get("test")
        }

    @app.get("/di/mixed/{item_id}")
    @injector.inject
    async def mixed_params(item_id: int, name: str, my_service: MyService):
        return {
            "item_id": item_id,
            "name": name,
            "service_value": my_service.get_value()
        }

    client = TestClient(app)

    # Test pure injection
    response = client.get("/di/inject")
    assert response.status_code == 200
    data = response.json()
    assert data["approach"] == "pure_wrapper"
    assert data["value"] == "fastapi ok"
    assert data["db_data"] == "db: fastapi ok"
    assert data["cache_data"] == "cached_value"

    # Test mixed parameters (some injected, some from URL/query)
    response = client.get("/di/mixed/123?name=test")
    assert response.status_code == 200
    data = response.json()
    assert data["item_id"] == 123
    assert data["name"] == "test"
    assert data["service_value"] == "fastapi ok"


def test_fastapi_depends_injection():
    """Test Strategy 2: FastAPI Depends() integration"""
    app = FastAPI()
    services = ServiceCollection()
    services.add_singleton(MyService)
    services.add_transient(DatabaseService)
    provider = services.build_provider()

    injector = create_fastapi_injector(provider)
    injector.setup_fastapi(app)

    @app.get("/di/depends")
    @injector.depends_inject
    async def depends_view(my_service: MyService, db_service: DatabaseService):
        return {
            "approach": "depends",
            "value": my_service.get_value(),
            "db_data": db_service.get_data()
        }

    client = TestClient(app)
    response = client.get("/di/depends")
    assert response.status_code == 200
    data = response.json()
    assert data["approach"] == "depends"
    assert data["value"] == "fastapi ok"
    assert data["db_data"] == "db: fastapi ok"


def test_fastapi_manual_injection():
    """Test Strategy 3: Manual parameter specification"""
    app = FastAPI()
    services = ServiceCollection()
    services.add_singleton(MyService)
    services.add_transient(DatabaseService)
    provider = services.build_provider()

    injector = create_fastapi_injector(provider)
    injector.setup_fastapi(app)

    @app.get("/di/manual_inject/{user_id}")
    @injector.manual_inject(db=DatabaseService, service=MyService)
    async def manual_inject_view(user_id: int, db, service):
        return {
            "approach": "manual_inject",
            "user_id": user_id,
            "value": service.get_value(),
            "db_data": db.get_data()
        }

    client = TestClient(app)
    response = client.get("/di/manual_inject/42")
    assert response.status_code == 200
    data = response.json()
    assert data["approach"] == "manual_inject"
    assert data["user_id"] == 42
    assert data["value"] == "fastapi ok"
    assert data["db_data"] == "db: fastapi ok"


def test_fastapi_all_strategies_combined():
    """Test that all three strategies work in the same FastAPI app"""
    app = FastAPI()
    services = ServiceCollection()
    services.add_singleton(MyService)
    services.add_transient(DatabaseService)
    services.add_scoped(CacheService)
    provider = services.build_provider()

    injector = create_fastapi_injector(provider, strict=True)
    injector.setup_fastapi(app)

    # Strategy 1: Pure wrapper
    @app.get("/strategy1")
    @injector.inject
    async def strategy1(my_service: MyService):
        return {"strategy": 1, "value": my_service.get_value()}

    # Strategy 2: Depends
    @app.get("/strategy2")
    @injector.depends_inject
    async def strategy2(my_service: MyService):
        return {"strategy": 2, "value": my_service.get_value()}

    # Strategy 3: Manual
    @app.get("/strategy3")
    @injector.manual_inject(service=MyService)
    async def strategy3(service):
        return {"strategy": 3, "value": service.get_value()}

    # Manual resolution (no injection)
    @app.get("/manual")
    async def manual():
        service = provider.resolve(MyService)
        return {"strategy": "manual", "value": service.get_value()}

    client = TestClient(app)

    # Test all approaches
    for endpoint in ["/strategy1", "/strategy2", "/strategy3", "/manual"]:
        response = client.get(endpoint)
        assert response.status_code == 200
        data = response.json()
        assert data["value"] == "fastapi ok"


def test_fastapi_scoped_lifetimes():
    """Test that scoped services work correctly across requests"""
    app = FastAPI()
    services = ServiceCollection()
    services.add_singleton(MyService)
    services.add_scoped(CacheService)
    provider = services.build_provider()

    injector = create_fastapi_injector(provider)
    injector.setup_fastapi(app)

    @app.post("/cache/set")
    @injector.inject
    async def set_cache(key: str, value: str, cache: CacheService):
        cache.set(key, value)
        return {"status": "set", "key": key, "value": value}

    @app.get("/cache/get")
    @injector.inject
    async def get_cache(key: str, cache: CacheService):
        return {"key": key, "value": cache.get(key)}

    client = TestClient(app)

    # Set a value in one request
    response1 = client.post("/cache/set?key=test&value=hello")
    assert response1.status_code == 200

    # Try to get it in another request (should be cache miss due to scoped lifetime)
    response2 = client.get("/cache/get?key=test")
    assert response2.status_code == 200
    data = response2.json()
    assert data["value"] == "cache miss"  # Different scope, so cache is empty


# Core functionality tests
def test_fastapi_singleton_resolution():
    """Test that depi properly resolves singleton services"""
    services = ServiceCollection()
    services.add_singleton(MyService)
    provider = services.build_provider()

    # Test singleton behavior
    service1 = provider.resolve(MyService)
    service2 = provider.resolve(MyService)

    assert service1 is service2  # Same instance
    assert service1.get_value() == "fastapi ok"


def test_fastapi_dependency_injection():
    """Test that depi properly injects dependencies"""
    services = ServiceCollection()
    services.add_singleton(MyService)
    services.add_transient(DatabaseService)
    provider = services.build_provider()

    # Test dependency injection
    db_service = provider.resolve(DatabaseService)

    assert isinstance(db_service.my_service, MyService)
    assert db_service.get_data() == "db: fastapi ok"


def test_fastapi_error_handling():
    """Test error handling with strict mode"""
    app = FastAPI()
    services = ServiceCollection()
    services.add_singleton(MyService)
    # Intentionally don't register DatabaseService
    provider = services.build_provider()

    injector = create_fastapi_injector(provider, strict=True)
    injector.setup_fastapi(app)

    # This should fail because DatabaseService is not registered
    with pytest.raises(ValueError) as exc_info:
        @injector.inject
        async def failing_view(my_service: MyService, db_service: DatabaseService):
            return {"value": my_service.get_value()}

    assert "dependency is not registered" in str(exc_info.value)


def test_fastapi_non_strict_mode():
    """Test non-strict mode ignores unregistered dependencies"""
    app = FastAPI()
    services = ServiceCollection()
    services.add_singleton(MyService)
    # Don't register DatabaseService
    provider = services.build_provider()

    injector = create_fastapi_injector(provider, strict=False)
    injector.setup_fastapi(app)

    @app.get("/non-strict")
    @injector.inject
    async def non_strict_view(my_service: MyService, unregistered_param: str = "default"):
        return {
            "value": my_service.get_value(),
            "unregistered": unregistered_param
        }

    client = TestClient(app)
    response = client.get("/non-strict")
    assert response.status_code == 200
    data = response.json()
    assert data["value"] == "fastapi ok"
    assert data["unregistered"] == "default"


def test_fastapi_signature_modification():
    """Test that FastAPI sees the modified signatures correctly"""
    app = FastAPI()
    services = ServiceCollection()
    services.add_singleton(MyService)
    provider = services.build_provider()

    injector = create_fastapi_injector(provider)
    injector.setup_fastapi(app)

    @app.get("/signature-test/{item_id}")
    @injector.inject
    async def signature_test(item_id: int, name: str, my_service: MyService):
        return {
            "item_id": item_id,
            "name": name,
            "service_value": my_service.get_value()
        }

    # Check that the wrapped function has the correct signature for FastAPI
    import inspect
    sig = inspect.signature(signature_test)
    param_names = list(sig.parameters.keys())

    # Should only see non-injectable parameters
    assert "item_id" in param_names
    assert "name" in param_names
    assert "my_service" not in param_names  # This should be injected and hidden from FastAPI

    client = TestClient(app)
    response = client.get("/signature-test/123?name=test")
    assert response.status_code == 200
    data = response.json()
    assert data["item_id"] == 123
    assert data["name"] == "test"
    assert data["service_value"] == "fastapi ok"


def test_direct_injector_creation():
    """Test creating injector directly vs factory function"""
    services = ServiceCollection()
    services.add_singleton(MyService)
    provider = services.build_provider()

    # Test factory function
    injector1 = create_fastapi_injector(provider, strict=True)
    assert isinstance(injector1, FastAPIDependencyInjector)
    assert injector1._strict == True

    # Test direct instantiation
    injector2 = FastAPIDependencyInjector(provider, strict=False)
    assert isinstance(injector2, FastAPIDependencyInjector)
    assert injector2._strict == False

    # Both should work the same way
    assert injector1._provider is provider
    assert injector2._provider is provider
