from django.urls import path

from .views import health, openapi_schema

urlpatterns = [
    path("health", health, name="health"),
    path("schema/", openapi_schema, name="openapi-schema"),
]
