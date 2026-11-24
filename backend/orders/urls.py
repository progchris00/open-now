from django.urls import path

from .views import AcceptOrderView, RejectOrderView

urlpatterns = [
    path(
        "merchant/orders/<int:id>/accept",
        AcceptOrderView.as_view(),
        name="merchant-order-accept",
    ),
    path(
        "merchant/orders/<int:id>/reject",
        RejectOrderView.as_view(),
        name="merchant-order-reject",
    ),
]
