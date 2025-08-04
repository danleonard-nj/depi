# test_django_di.py (works best with pytest-django)
from django.http import JsonResponse
from django.urls import path
from depi.services import ServiceCollection


class MyService:
    def get_value(self): return "django ok"


services = ServiceCollection()
services.add_singleton(MyService)
provider = services.build_provider()


def di_view(request):
    service = provider.resolve(MyService)
    return JsonResponse({"value": service.get_value()})


urlpatterns = [
    path("di/", di_view),
]


def test_django_di(client):
    response = client.get("/di/")
    assert response.status_code == 200
    assert response.json()["value"] == "django ok"
