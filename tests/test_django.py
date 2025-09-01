# test_django_di.py - Demonstrates both ServiceCollection and DependencyInjector patterns
import django
import pytest
from django.http import JsonResponse
from django.urls import path
from django.test import Client
from django.conf import settings
from depi.services import ServiceCollection, DependencyInjector

# Simple Django middleware for DI scope management


class DIMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Create a new scope for each request and attach to request
        request.di_scope = di_injector.create_scope()

        # Set the scope on all decorated views
        for view_func in [di_view_injected]:
            if hasattr(view_func, '_scope'):
                view_func._scope = request.di_scope

        try:
            response = self.get_response(request)
        finally:
            # Clean up scope after request
            if hasattr(request, 'di_scope'):
                request.di_scope.dispose()

        return response


# Configure Django settings for testing
if not settings.configured:
    settings.configure(
        DEBUG=True,
        SECRET_KEY='test-secret-key',
        ROOT_URLCONF=__name__,
        INSTALLED_APPS=[
            'django.contrib.contenttypes',
            'django.contrib.auth',
        ],
        MIDDLEWARE=[
            __name__ + '.DIMiddleware',
        ],
        USE_TZ=True,
    )

django.setup()


# Services
class MyService:
    def get_value(self): return "django ok"


class DatabaseService:
    def get_data(self): return "db data"


# Setup DI container
services = ServiceCollection()
services.add_singleton(MyService)
services.add_singleton(DatabaseService)
provider = services.build_provider()

# Create DependencyInjector for automatic injection
di_injector = DependencyInjector(provider)


# Approach 1: Manual resolution using ServiceCollection
def di_view_manual(request):
    service = provider.resolve(MyService)
    return JsonResponse({"approach": "manual", "value": service.get_value()})


# Approach 2: Automatic injection using DependencyInjector
@di_injector.inject
def di_view_injected(request, my_service: MyService, db_service: DatabaseService):
    return JsonResponse({
        "approach": "injected",
        "value": my_service.get_value(),
        "db_data": db_service.get_data()
    })


urlpatterns = [
    path("di/manual/", di_view_manual),
    path("di/injected/", di_view_injected),
]


def test_django_di_manual():
    """Test manual dependency resolution using ServiceCollection"""
    client = Client()
    response = client.get("/di/manual/")
    assert response.status_code == 200
    data = response.json()
    assert data["approach"] == "manual"
    assert data["value"] == "django ok"


def test_django_di_injected():
    """Test automatic dependency injection using DependencyInjector"""
    client = Client()
    response = client.get("/di/injected/")
    assert response.status_code == 200
    data = response.json()
    assert data["approach"] == "injected"
    assert data["value"] == "django ok"
    assert data["db_data"] == "db data"


def test_both_approaches():
    """Test that both DI approaches work in the same Django app"""
    client = Client()

    # Test manual approach
    manual_response = client.get("/di/manual/")
    assert manual_response.status_code == 200

    # Test injected approach
    injected_response = client.get("/di/injected/")
    assert injected_response.status_code == 200

    # Verify they both work
    manual_data = manual_response.json()
    injected_data = injected_response.json()

    assert manual_data["approach"] == "manual"
    assert injected_data["approach"] == "injected"
    assert manual_data["value"] == injected_data["value"]  # Same service, same value
