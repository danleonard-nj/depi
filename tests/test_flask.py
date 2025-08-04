# test_flask.py
import pytest
from flask import Flask, jsonify, request
from depi.services import ServiceCollection, DependencyInjector


class MyService:
    def get_value(self):
        return "flask ok"


class DatabaseService:
    def __init__(self, my_service: MyService):
        self.my_service = my_service

    def get_data(self):
        return f"db: {self.my_service.get_value()}"


def test_flask_direct_resolution():
    """Test direct resolution without decorators"""
    app = Flask(__name__)
    services = ServiceCollection()
    services.add_singleton(MyService)
    provider = services.build_provider()

    @app.route("/di")
    def di_view():
        service = provider.resolve(MyService)
        return jsonify({"value": service.get_value()})

    with app.test_client() as client:
        response = client.get("/di")
        assert response.status_code == 200
        assert response.json["value"] == "flask ok"


def test_flask_injector_decorator():
    """Test @inject decorator with Flask using manual scope management"""
    app = Flask(__name__)
    services = ServiceCollection()
    services.add_singleton(MyService)
    services.add_transient(DatabaseService)
    provider = services.build_provider()

    injector = DependencyInjector(provider)

    # Test basic injection
    @injector.inject
    def basic_view(my_service: MyService):
        return jsonify({"value": my_service.get_value()})

    app.add_url_rule("/basic", "basic", basic_view, methods=["GET"])

    # Test injection with dependencies
    @injector.inject
    def complex_view(my_service: MyService, db_service: DatabaseService):
        return jsonify({
            "service": my_service.get_value(),
            "database": db_service.get_data()
        })

    app.add_url_rule("/complex", "complex", complex_view, methods=["GET"])

    # Test mixed parameters (injected + Flask parameters)
    @injector.inject
    def mixed_view(item_id: str, my_service: MyService):
        return jsonify({
            "item_id": item_id,
            "service": my_service.get_value()
        })

    app.add_url_rule("/mixed/<item_id>", "mixed", mixed_view, methods=["GET"])

    # Manual scope management for testing
    @app.before_request
    def before_request():
        from flask import g
        g.scope = injector.create_scope()
        # Set scope on all injected views
        basic_view._scope = g.scope
        complex_view._scope = g.scope
        mixed_view._scope = g.scope

    @app.teardown_request
    def teardown_request(exception=None):
        from flask import g
        if hasattr(g, 'scope'):
            g.scope.dispose()

    with app.test_client() as client:
        # Test basic injection
        response = client.get("/basic")
        assert response.status_code == 200
        assert response.json["value"] == "flask ok"

        # Test complex injection
        response = client.get("/complex")
        assert response.status_code == 200
        assert response.json["service"] == "flask ok"
        assert response.json["database"] == "db: flask ok"

        # Test mixed parameters
        response = client.get("/mixed/123")
        assert response.status_code == 200
        assert response.json["item_id"] == "123"
        assert response.json["service"] == "flask ok"


def test_flask_manual_scope_management():
    """Test manual scope management with Flask"""
    services = ServiceCollection()
    services.add_singleton(MyService)
    services.add_transient(DatabaseService)
    provider = services.build_provider()

    injector = DependencyInjector(provider)

    @injector.inject
    def process_request(my_service: MyService, db_service: DatabaseService):
        return {
            "service": my_service.get_value(),
            "database": db_service.get_data()
        }

    # Manual scope management
    scope = injector.create_scope()
    process_request._scope = scope

    try:
        result = process_request()
        assert result["service"] == "flask ok"
        assert result["database"] == "db: flask ok"
    finally:
        scope.dispose()


def test_flask_scoped_services():
    """Test scoped services with Flask"""
    app = Flask(__name__)
    services = ServiceCollection()
    services.add_singleton(MyService)
    services.add_scoped(DatabaseService)
    provider = services.build_provider()

    injector = DependencyInjector(provider)

    @app.route("/scoped")
    @injector.inject
    def scoped_view(my_service: MyService, db_service: DatabaseService):
        return jsonify({
            "service": my_service.get_value(),
            "database": db_service.get_data(),
            "db_id": str(id(db_service))
        })

    injector.setup_flask(app)

    with app.test_client() as client:
        # Multiple requests should get same scoped instance within request
        response1 = client.get("/scoped")
        response2 = client.get("/scoped")

        assert response1.status_code == 200
        assert response2.status_code == 200

        # Different requests should have different scoped instances
        assert response1.json["db_id"] != response2.json["db_id"]
