from django.urls import path

from .views import CashCorrectionView, OrderCashView

urlpatterns = [
    path(
        "admin/orders/<int:id>/cash",
        OrderCashView.as_view(),
        name="admin-order-cash",
    ),
    path(
        "admin/cash/corrections",
        CashCorrectionView.as_view(),
        name="admin-cash-correction",
    ),
]
