# test_fastapi.py
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from depi.services import ServiceCollection, DependencyInjector


# Pending injector support for FastAPI, currently passes the unchanged method signature and dependencies to FastAPI and it gets confused
# The tests below are written to test the functionality of depi with FastAPI

class MyService:
    def get_value(self):
        return "fastapi ok"


class DatabaseService:
    def __init__(self, my_service: MyService):
        self.my_service = my_service

    def get_data(self):
        return f"db: {self.my_service.get_value()}"


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


def test_fastapi_transient_behavior():
    """Test that depi creates new instances for transient services"""
    services = ServiceCollection()
    services.add_singleton(MyService)
    services.add_transient(DatabaseService)
    provider = services.build_provider()

    # Test transient behavior
    db1 = provider.resolve(DatabaseService)
    db2 = provider.resolve(DatabaseService)

    assert db1 is not db2  # Different instances
    assert db1.my_service is db2.my_service  # But same singleton dependency
    assert db1.get_data() == db2.get_data()


def test_fastapi_with_actual_app():
    """Test depi integration with a real FastAPI app (without using Depends)"""
    # Setup depi container
    services = ServiceCollection()
    services.add_singleton(MyService)
    services.add_transient(DatabaseService)
    provider = services.build_provider()

    # Create FastAPI app that uses depi directly
    app = FastAPI()

    @app.get("/service")
    def get_service_value():
        service = provider.resolve(MyService)
        return {"value": service.get_value()}

    @app.get("/database")
    def get_database_data():
        db_service = provider.resolve(DatabaseService)
        return {"data": db_service.get_data()}

    # Test the app
    client = TestClient(app)

    response = client.get("/service")
    assert response.status_code == 200
    assert response.json()["value"] == "fastapi ok"

    response = client.get("/database")
    assert response.status_code == 200
    assert response.json()["data"] == "db: fastapi ok"


def test_dependency_injector_decorator():
    """Test the @injector.inject decorator with manual scope management"""
    # Setup depi container
    services = ServiceCollection()
    services.add_singleton(MyService)
    services.add_transient(DatabaseService)
    provider = services.build_provider()

    # Create dependency injector
    injector = DependencyInjector(provider)

    # Function using @inject decorator
    @injector.inject
    def process_data(my_service: MyService, db_service: DatabaseService):
        return {
            "service_value": my_service.get_value(),
            "db_data": db_service.get_data()
        }

    # Manually set scope (normally done by middleware)
    scope = injector.create_scope()
    process_data._scope = scope

    try:
        result = process_data()
        assert result["service_value"] == "fastapi ok"
        assert result["db_data"] == "db: fastapi ok"
    finally:
        scope.dispose()


def test_dependency_injector_async_decorator():
    """Test the @injector.inject decorator with async functions"""
    # Setup depi container
    services = ServiceCollection()
    services.add_singleton(MyService)
    services.add_transient(DatabaseService)
    provider = services.build_provider()

    # Create dependency injector
    injector = DependencyInjector(provider)

    # Async function using @inject decorator
    @injector.inject
    async def async_process_data(my_service: MyService, db_service: DatabaseService):
        return {
            "service_value": my_service.get_value(),
            "db_data": db_service.get_data()
        }

    # Test async function
    import asyncio

    async def run_test():
        scope = injector.create_scope()
        async_process_data._scope = scope

        try:
            result = await async_process_data()
            assert result["service_value"] == "fastapi ok"
            assert result["db_data"] == "db: fastapi ok"
        finally:
            scope.dispose()

    asyncio.run(run_test())


def test_dependency_injector_with_fastapi_middleware():
    """Test the @injector.inject decorator basic functionality (without full FastAPI integration)"""
    # Setup depi container
    services = ServiceCollection()
    services.add_singleton(MyService)
    services.add_transient(DatabaseService)
    provider = services.build_provider()

    # Create dependency injector
    injector = DependencyInjector(provider)

    # Test the inject decorator directly without FastAPI route registration
    @injector.inject
    async def get_injected_data(my_service: MyService, db_service: DatabaseService):
        return {
            "service_value": my_service.get_value(),
            "db_data": db_service.get_data()
        }

    # Test async function with manual scope management
    import asyncio

    async def run_test():
        scope = injector.create_scope()
        get_injected_data._scope = scope

        try:
            result = await get_injected_data()
            assert result["service_value"] == "fastapi ok"
            assert result["db_data"] == "db: fastapi ok"
        finally:
            scope.dispose()

    asyncio.run(run_test())


def test_dependency_injector_partial_injection():
    """Test @inject decorator with mixed injected and manual parameters"""
    # Setup depi container
    services = ServiceCollection()
    services.add_singleton(MyService)
    provider = services.build_provider()

    # Create dependency injector
    injector = DependencyInjector(provider)

    # Function with mixed parameters
    @injector.inject
    def mixed_parameters(manual_param: str, my_service: MyService, another_manual: int = 42):
        return {
            "manual": manual_param,
            "injected": my_service.get_value(),
            "default": another_manual
        }

    # Manually set scope
    scope = injector.create_scope()
    mixed_parameters._scope = scope

    try:
        result = mixed_parameters("test_value")
        assert result["manual"] == "test_value"
        assert result["injected"] == "fastapi ok"
        assert result["default"] == 42

        # Test with override
        result2 = mixed_parameters("test_value", another_manual=100)
        assert result2["default"] == 100
    finally:
        scope.dispose()


def test_dependency_injector_no_scope_error():
    """Test that @inject decorator raises error when no scope is set"""
    # Setup depi container
    services = ServiceCollection()
    services.add_singleton(MyService)
    provider = services.build_provider()

    # Create dependency injector
    injector = DependencyInjector(provider)

    # Function using @inject decorator
    @injector.inject
    def requires_scope(my_service: MyService):
        return my_service.get_value()

    # Should raise error when no scope is set
    with pytest.raises(Exception) as exc_info:
        requires_scope()

    assert "No active ServiceScope" in str(exc_info.value)
