from django.urls import path

from .views import admin_setting, admin_settings

urlpatterns = [
    path("admin/settings", admin_settings, name="admin-settings"),
    path("admin/settings/<str:key>", admin_setting, name="admin-setting"),
]
