from rest_framework.permissions import BasePermission

from .models import Order, ShopMember


def works_at_order_shop(user, order_id: int) -> bool:
    """True if user is a member of the shop the order belongs to.

    A missing order answers False, the same as another shop's order, so the
    API can't be used to find out which order numbers exist.
    """
    shop_id = (
        Order.objects.filter(pk=order_id).values_list("shop_id", flat=True).first()
    )
    return (
        shop_id is not None
        and ShopMember.objects.filter(user=user, shop_id=shop_id).exists()
    )


class IsOrderShopMember(BasePermission):
    message = "You can only decide on your own shop's orders."

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and works_at_order_shop(user, view.kwargs["id"])
        )
