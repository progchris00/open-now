from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .models import Order, OrderItem

PESOS = {"max_digits": 10, "decimal_places": 2}
IDEMPOTENCY_KEY_MAX_LENGTH = 100


@extend_schema_field(
    {"type": "string", "format": "decimal", "pattern": r"^\d{1,8}(\.\d{1,2})?$"}
)
class PesoField(serializers.DecimalField):
    """A non-negative peso amount, sent as a string such as "1000.00"."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**PESOS, min_value=0, **kwargs)


@extend_schema_field(
    {"type": "string", "format": "decimal", "pattern": r"^\d{1,4}(\.\d{1,3})?$"}
)
class KilometreField(serializers.DecimalField):
    def __init__(self, **kwargs) -> None:
        super().__init__(max_digits=7, decimal_places=3, min_value=0, **kwargs)


class PlaceOrderLineSerializer(serializers.Serializer):
    product_id = serializers.IntegerField(min_value=1)
    quantity = serializers.IntegerField(min_value=1)


class PlaceOrderSerializer(serializers.Serializer):
    """What the customer sends. Prices, fees and totals are never read from it."""

    items = serializers.ListField(
        child=PlaceOrderLineSerializer(), allow_empty=False, min_length=1
    )
    distance_km = KilometreField(
        help_text=(
            "TEMPORARY until S2-11 (delivery details): distance from the shop "
            "to the customer in km. S2-11 will work it out from the address."
        ),
    )
    bill = PesoField(help_text="The peso bill the customer will pay with.")
    payment_method = serializers.ChoiceField(
        choices=Order.PaymentMethod.choices,
        help_text="Cash on delivery only, and it must match the admin setting.",
    )


class IdempotencyKeySerializer(serializers.Serializer):
    idempotency_key = serializers.CharField(
        min_length=1, max_length=IDEMPOTENCY_KEY_MAX_LENGTH
    )


class OrderItemSerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = OrderItem
        fields = ["product_id", "name", "unit_price", "quantity", "line_total"]
        read_only_fields = fields


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "status",
            "shop_id",
            "payment_method",
            "items",
            "items_total",
            "delivery_fee",
            "service_fee",
            "discount",
            "total",
            "bill",
            "change",
            "created_at",
        ]
        read_only_fields = fields
