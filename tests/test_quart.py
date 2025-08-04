# test_quart.py
import pytest
from quart import Quart, jsonify, request
from depi.services import ServiceCollection, DependencyInjector


class MyService:
    def get_value(self):
        return "quart ok"


class DatabaseService:
    def __init__(self, my_service: MyService):
        self.my_service = my_service

    def get_data(self):
        return f"db: {self.my_service.get_value()}"


@pytest.mark.asyncio
async def test_quart_direct_resolution():
    """Test direct resolution without decorators"""
    app = Quart(__name__)
    services = ServiceCollection()
    services.add_singleton(MyService)
    provider = services.build_provider()

    @app.route("/di")
    async def di_view():
        service = provider.resolve(MyService)
        return jsonify({"value": service.get_value()})

    test_client = app.test_client()
    response = await test_client.get("/di")
    assert response.status_code == 200
    data = await response.get_json()
    assert data["value"] == "quart ok"


@pytest.mark.asyncio
async def test_quart_injector_decorator():
    """Test @inject decorator with Quart"""
    app = Quart(__name__)
    services = ServiceCollection()
    services.add_singleton(MyService)
    services.add_transient(DatabaseService)
    provider = services.build_provider()

    injector = DependencyInjector(provider)

    # Test basic injection
    @app.route("/basic")
    @injector.inject
    async def basic_view(my_service: MyService):
        return jsonify({"value": my_service.get_value()})

    # Test injection with dependencies
    @app.route("/complex")
    @injector.inject
    async def complex_view(my_service: MyService, db_service: DatabaseService):
        return jsonify({
            "service": my_service.get_value(),
            "database": db_service.get_data()
        })

    # Test mixed parameters (injected + Quart parameters)
    @app.route("/mixed/<item_id>")
    @injector.inject
    async def mixed_view(item_id: str, my_service: MyService):
        return jsonify({
            "item_id": item_id,
            "service": my_service.get_value()
        })

    # Manual scope setup for testing (since setup_quart doesn't exist yet)
    @app.before_request
    async def before_request():
        from quart import g
        g.scope = injector.create_scope()
        # Set scope on all injected functions
        for rule in app.url_map.iter_rules():
            endpoint = app.view_functions[rule.endpoint]
            if hasattr(endpoint, '_scope'):
                endpoint._scope = g.scope

    @app.after_request
    async def after_request(response):
        from quart import g
        if hasattr(g, 'scope'):
            g.scope.dispose()
        return response

    test_client = app.test_client()

    # Test basic injection
    response = await test_client.get("/basic")
    assert response.status_code == 200
    data = await response.get_json()
    assert data["value"] == "quart ok"

    # Test complex injection
    response = await test_client.get("/complex")
    assert response.status_code == 200
    data = await response.get_json()
    assert data["service"] == "quart ok"
    assert data["database"] == "db: quart ok"

    # Test mixed parameters
    response = await test_client.get("/mixed/456")
    assert response.status_code == 200
    data = await response.get_json()
    assert data["item_id"] == "456"
    assert data["service"] == "quart ok"


@pytest.mark.asyncio
async def test_quart_manual_scope_management():
    """Test manual scope management with Quart"""
    services = ServiceCollection()
    services.add_singleton(MyService)
    services.add_transient(DatabaseService)
    provider = services.build_provider()

    injector = DependencyInjector(provider)

    @injector.inject
    async def process_request(my_service: MyService, db_service: DatabaseService):
        return {
            "service": my_service.get_value(),
            "database": db_service.get_data()
        }

    # Manual scope management
    scope = injector.create_scope()
    process_request._scope = scope

    try:
        result = await process_request()
        assert result["service"] == "quart ok"
        assert result["database"] == "db: quart ok"
    finally:
        scope.dispose()


@pytest.mark.asyncio
async def test_quart_scoped_services():
    """Test scoped services with Quart"""
    app = Quart(__name__)
    services = ServiceCollection()
    services.add_singleton(MyService)
    services.add_scoped(DatabaseService)
    provider = services.build_provider()

    injector = DependencyInjector(provider)

    @app.route("/scoped")
    @injector.inject
    async def scoped_view(my_service: MyService, db_service: DatabaseService):
        return jsonify({
            "service": my_service.get_value(),
            "database": db_service.get_data(),
            "db_id": str(id(db_service))
        })

    # Manual scope setup
    @app.before_request
    async def before_request():
        from quart import g
        g.scope = injector.create_scope()
        for rule in app.url_map.iter_rules():
            endpoint = app.view_functions[rule.endpoint]
            if hasattr(endpoint, '_scope'):
                endpoint._scope = g.scope

    @app.after_request
    async def after_request(response):
        from quart import g
        if hasattr(g, 'scope'):
            g.scope.dispose()
        return response

    test_client = app.test_client()

    # Multiple requests should get different scoped instances
    response1 = await test_client.get("/scoped")
    response2 = await test_client.get("/scoped")

    assert response1.status_code == 200
    assert response2.status_code == 200

    data1 = await response1.get_json()
    data2 = await response2.get_json()

    # Different requests should have different scoped instances
    assert data1["db_id"] != data2["db_id"]
