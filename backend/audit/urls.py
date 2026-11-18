from django.urls import path

from .views import AdminAuditView, AdminCashRecordView, AdminOrderStatusView

urlpatterns = [
    path("admin/audit", AdminAuditView.as_view(), name="admin-audit"),
    path(
        "admin/orders/<int:pk>/status",
        AdminOrderStatusView.as_view(),
        name="admin-order-status",
    ),
    path(
        "admin/cash-records",
        AdminCashRecordView.as_view(),
        name="admin-cash-record",
    ),
]
