from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AuditLog, CashRecord, Order
from .serializers import (
    AuditLogSerializer,
    CashRecordSerializer,
    OrderStatusSerializer,
)


class AdminAuditView(ListAPIView):
    queryset = AuditLog.objects.select_related("who").all()
    serializer_class = AuditLogSerializer
    permission_classes = [IsAdminUser]

    @extend_schema(
        operation_id="getAdminAudit",
        summary="List audit entries",
        responses={
            status.HTTP_200_OK: AuditLogSerializer(many=True),
            status.HTTP_403_FORBIDDEN: OpenApiResponse(
                description="User is not an administrator"
            ),
        },
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class AdminOrderStatusView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        operation_id="patchAdminOrderStatus",
        summary="Change an order status",
        request=OrderStatusSerializer,
        responses={
            status.HTTP_200_OK: OrderStatusSerializer,
            status.HTTP_400_BAD_REQUEST: OpenApiResponse(
                description="Invalid order status"
            ),
            status.HTTP_403_FORBIDDEN: OpenApiResponse(
                description="User is not an administrator"
            ),
            status.HTTP_404_NOT_FOUND: OpenApiResponse(
                description="Order does not exist"
            ),
        },
    )
    def patch(self, request, pk: int) -> Response:
        order = get_object_or_404(Order, pk=pk)
        serializer = OrderStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order.status = serializer.validated_data["status"]
        order.save(actor=request.user)
        return Response({"status": order.status})


class AdminCashRecordView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        operation_id="createAdminCashRecord",
        summary="Create an append-only cash record",
        request=CashRecordSerializer,
        responses={
            status.HTTP_201_CREATED: CashRecordSerializer,
            status.HTTP_400_BAD_REQUEST: OpenApiResponse(
                description="Invalid cash record"
            ),
            status.HTTP_403_FORBIDDEN: OpenApiResponse(
                description="User is not an administrator"
            ),
        },
    )
    def post(self, request) -> Response:
        serializer = CashRecordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        record = CashRecord.objects.create(
            actor=request.user,
            label=serializer.validated_data["label"],
        )
        return Response(
            CashRecordSerializer(record).data,
            status=status.HTTP_201_CREATED,
        )
