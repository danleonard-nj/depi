# test_quart.py - Demonstrates both ServiceCollection and DependencyInjector patterns with Quart
import pytest
from quart import Quart, jsonify, g
from depi.services import ServiceCollection, DependencyInjector


class MyService:
    def get_value(self):
        return "quart ok"


class DatabaseService:
    def __init__(self, my_service: MyService):
        self.my_service = my_service

    def get_data(self):
        return f"db: {self.my_service.get_value()}"


class CacheService:
    def get_cached(self, key: str):
        return f"cached_{key}"


@pytest.mark.asyncio
async def test_quart_manual_resolution():
    """Test manual dependency resolution using ServiceCollection"""
    app = Quart(__name__)
    services = ServiceCollection()
    services.add_singleton(MyService)
    services.add_transient(DatabaseService)
    provider = services.build_provider()

    @app.route("/di/manual")
    async def di_view_manual():
        service = provider.resolve(MyService)
        db_service = provider.resolve(DatabaseService)
        return jsonify({
            "approach": "manual",
            "value": service.get_value(),
            "db_data": db_service.get_data()
        })

    test_client = app.test_client()
    response = await test_client.get("/di/manual")
    assert response.status_code == 200
    data = await response.get_json()
    assert data["approach"] == "manual"
    assert data["value"] == "quart ok"
    assert data["db_data"] == "db: quart ok"


@pytest.mark.asyncio
async def test_quart_injector_decorator():
    """Test automatic dependency injection using DependencyInjector with Quart"""
    app = Quart(__name__)
    services = ServiceCollection()
    services.add_singleton(MyService)
    services.add_transient(DatabaseService)
    provider = services.build_provider()

    injector = DependencyInjector(provider)

    @app.route("/di/injected")
    @injector.inject
    async def di_view_injected(my_service: MyService, db_service: DatabaseService):
        return jsonify({
            "approach": "injected",
            "value": my_service.get_value(),
            "db_data": db_service.get_data()
        })

    # Manual scope management for Quart
    @app.before_request
    async def before_request():
        g.scope = injector.create_scope()
        # Set scope on the injected view
        di_view_injected._scope = g.scope

    @app.teardown_request
    async def teardown_request(exception=None):
        if hasattr(g, 'scope'):
            g.scope.dispose()

    test_client = app.test_client()
    response = await test_client.get("/di/injected")
    assert response.status_code == 200
    data = await response.get_json()
    assert data["approach"] == "injected"
    assert data["value"] == "quart ok"
    assert data["db_data"] == "db: quart ok"


@pytest.mark.asyncio
async def test_quart_both_approaches():
    """Test that both DI approaches work in the same Quart app"""
    app = Quart(__name__)
    services = ServiceCollection()
    services.add_singleton(MyService)
    services.add_transient(DatabaseService)
    provider = services.build_provider()

    injector = DependencyInjector(provider)

    # Manual approach
    @app.route("/di/manual")
    async def di_view_manual():
        service = provider.resolve(MyService)
        return jsonify({"approach": "manual", "value": service.get_value()})

    # Injected approach
    @app.route("/di/injected")
    @injector.inject
    async def di_view_injected(my_service: MyService):
        return jsonify({"approach": "injected", "value": my_service.get_value()})

    # Setup scope management for injected views
    @app.before_request
    async def before_request():
        g.scope = injector.create_scope()
        di_view_injected._scope = g.scope

    @app.teardown_request
    async def teardown_request(exception=None):
        if hasattr(g, 'scope'):
            g.scope.dispose()

    test_client = app.test_client()

    # Test manual approach
    manual_response = await test_client.get("/di/manual")
    assert manual_response.status_code == 200
    manual_data = await manual_response.get_json()
    assert manual_data["approach"] == "manual"
    assert manual_data["value"] == "quart ok"

    # Test injected approach
    injected_response = await test_client.get("/di/injected")
    assert injected_response.status_code == 200
    injected_data = await injected_response.get_json()
    assert injected_data["approach"] == "injected"
    assert injected_data["value"] == "quart ok"

    # Verify they both work with the same service instance (singleton)
    assert manual_data["value"] == injected_data["value"]


@pytest.mark.asyncio
async def test_quart_strict_vs_non_strict_modes():
    """Test Quart with strict and non-strict DependencyInjector modes"""
    # Create services
    services = ServiceCollection()
    services.add_singleton(MyService)
    # Note: CacheService is NOT registered
    provider = services.build_provider()

    app = Quart(__name__)

    # Non-strict mode (default): graceful degradation for missing dependencies
    non_strict_injector = DependencyInjector(provider, strict=False)

    @app.route('/non-strict')
    @non_strict_injector.inject
    async def non_strict_endpoint(my_service: MyService, cache_service: CacheService = None):
        """In non-strict mode, only registered dependencies are injected.
        Unregistered dependencies remain as normal parameters."""
        if cache_service is None:
            return jsonify({"service": my_service.get_value(), "cache": "Not provided"})
        return jsonify({"service": my_service.get_value(), "cache": cache_service.get_cached('test')})

    # Strict mode: all annotated dependencies must be registered
    strict_injector = DependencyInjector(provider, strict=True)

    @app.route('/strict')
    @strict_injector.inject
    async def strict_endpoint(my_service: MyService):
        """In strict mode, all parameters are removed from signature.
        This creates clean endpoints for Quart."""
        return jsonify({"service": my_service.get_value()})

    test_client = app.test_client()

    # Non-strict mode works even with missing dependencies
    response = await test_client.get('/non-strict')
    assert response.status_code == 200
    data = await response.get_json()
    assert data["service"] == "quart ok"
    assert data["cache"] == "Not provided"

    # Strict mode works when all dependencies are registered
    response = await test_client.get('/strict')
    assert response.status_code == 200
    data = await response.get_json()
    assert data["service"] == "quart ok"


@pytest.mark.asyncio
async def test_quart_strict_mode_missing_dependency():
    """Test that strict mode fails with unregistered dependencies"""
    services = ServiceCollection()
    services.add_singleton(MyService)
    # CacheService is NOT registered
    provider = services.build_provider()

    strict_injector = DependencyInjector(provider, strict=True)

    app = Quart(__name__)

    with pytest.raises(ValueError, match="Failed to resolve dependency"):
        @app.route('/strict-missing')
        @strict_injector.inject
        async def strict_missing_endpoint(my_service: MyService, cache_service: CacheService):
            """This should fail because CacheService is not registered"""
            return jsonify({"service": my_service.get_value()})
