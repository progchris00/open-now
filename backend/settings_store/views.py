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
    if key == "payment_method" and value != "cod":
        return Response(
            {"value": ["Payment method is locked to cash on delivery."]},
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
