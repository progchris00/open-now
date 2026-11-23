"""Who may place an order.

TEMPORARY until S1-11 (role permissions): a customer is a user in the
"customer" group. When S1-11 lands, replace IsCustomer with its role check;
the views only import IsCustomer, so nothing else changes.
"""

from rest_framework.permissions import BasePermission

CUSTOMER_GROUP = "customer"


class IsCustomer(BasePermission):
    message = "Only customers can place orders."

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and user.groups.filter(name=CUSTOMER_GROUP).exists()
        )
