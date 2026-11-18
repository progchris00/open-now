from django.urls import path

from .views import AdminAuditView

urlpatterns = [
    path("admin/audit", AdminAuditView.as_view(), name="admin-audit"),
]
