import math

from django.contrib.admin.models import CHANGE, LogEntry
from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from .cache import get_cached_settings, invalidate_settings_cache
from .models import Setting
from .serializers import SettingSerializer, SettingUpdateSerializer

RULES = {
    "payment_method": {"type": str, "choices": ("cod",)},
    "service_fee_per_order": {"type": (int, float), "min": 0},
    "subscription_monthly": {"type": (int, float), "min": 0},
    "free_months": {"type": int, "min": 0},
    "bill_grace_days": {"type": int, "min": 0},
    "delivery_base_fee": {"type": (int, float), "min": 0},
    "delivery_per_km": {"type": (int, float), "min": 0},
    "senior_pwd_discount_percent": {
        "type": (int, float),
        "min": 0,
        "max": 100,
    },
    "return_fee": {"type": (int, float), "min": 0},
    "limit_new_customer": {"type": (int, float), "min": 0},
    "limit_regular": {"type": (int, float), "min": 0},
    "open_orders_new": {"type": int, "min": 0},
    "open_orders_regular": {"type": int, "min": 0},
    "otp_expiry_minutes": {"type": int, "min": 1},
    "session_days": {"type": int, "min": 1},
    "approval_target_days": {"type": int, "min": 1},
    "checkin_lead_minutes": {"type": int, "min": 0},
    "checkin_reminder_minutes": {"type": int, "min": 0},
    "first_order_autopause_minutes": {"type": int, "min": 0},
    "accept_minutes": {"type": int, "min": 0},
    "unusual_confirm_minutes": {"type": int, "min": 0},
    "offer_minutes": {"type": int, "min": 0},
    "offer_max_tries": {"type": int, "min": 1},
    "no_rider_cancel_minutes": {"type": int, "min": 0},
    "pickup_reassign_minutes": {"type": int, "min": 0},
    "failed_calls": {"type": int, "min": 1},
    "failed_wait_minutes": {"type": int, "min": 0},
}


@extend_schema(
    operation_id="getAdminSettings",
    summary="List admin settings",
    responses={
        status.HTTP_200_OK: SettingSerializer(many=True),
        status.HTTP_403_FORBIDDEN: OpenApiResponse(
            description="User is not an administrator"
        ),
    },
)
@api_view(["GET"])
@permission_classes([IsAdminUser])
def admin_settings(request) -> Response:
    del request
    return Response(get_cached_settings())


@extend_schema(
    operation_id="patchAdminSetting",
    summary="Update an admin setting",
    request=SettingUpdateSerializer,
    responses={
        status.HTTP_200_OK: SettingSerializer,
        status.HTTP_400_BAD_REQUEST: OpenApiResponse(
            description="Invalid value or locked setting"
        ),
        status.HTTP_403_FORBIDDEN: OpenApiResponse(
            description="User is not an administrator"
        ),
        status.HTTP_404_NOT_FOUND: OpenApiResponse(
            description="Setting does not exist"
        ),
    },
)
@api_view(["PATCH"])
@permission_classes([IsAdminUser])
def admin_setting(request, key: str) -> Response:
    setting = get_object_or_404(Setting, pk=key)
    serializer = SettingUpdateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    value = serializer.validated_data["value"]
    rule = RULES.get(key)
    if rule is None:
        return Response(
            {"value": ["This setting has no validation rule yet."]},
            status=status.HTTP_400_BAD_REQUEST,
        )

    expected_type = rule["type"]
    invalid_type = isinstance(value, bool) or not isinstance(value, expected_type)
    if isinstance(value, float) and not math.isfinite(value):
        invalid_type = True
    if invalid_type:
        return Response(
            {"value": ["Value has an invalid type."]},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if "choices" in rule and value not in rule["choices"]:
        return Response(
            {"value": ["Payment method is locked to cash on delivery."]},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if "min" in rule and value < rule["min"]:
        return Response(
            {"value": [f"Value must be at least {rule['min']}."]},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if "max" in rule and value > rule["max"]:
        return Response(
            {"value": [f"Value must be at most {rule['max']}."]},
            status=status.HTTP_400_BAD_REQUEST,
        )

    with transaction.atomic():
        setting.value = value
        setting.updated_by = request.user
        setting.save(update_fields=["value", "updated_by", "updated_at"])
        LogEntry.objects.log_actions(
            request.user.pk,
            [setting],
            CHANGE,
            change_message="Updated setting value.",
            single_object=True,
        )
        transaction.on_commit(invalidate_settings_cache)

    return Response(SettingSerializer(setting).data)
