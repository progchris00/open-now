from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from orders.models import Order

from .math import summarize_balances
from .serializers import (
    CashCorrectionSerializer,
    CashRecordSerializer,
    OrderCashSerializer,
)
from .services import correct_cash


class OrderCashView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        responses={
            status.HTTP_200_OK: OrderCashSerializer,
            status.HTTP_403_FORBIDDEN: OpenApiResponse(
                description="User is not an administrator"
            ),
            status.HTTP_404_NOT_FOUND: OpenApiResponse(
                description="Order does not exist"
            ),
        }
    )
    def get(self, request, id: int) -> Response:
        try:
            order = Order.objects.get(pk=id)
        except Order.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        records = list(order.cash_records.select_related("created_by"))
        balances = summarize_balances(
            (record.from_party, record.to_party, record.amount) for record in records
        )
        serializer = OrderCashSerializer(
            {"order": order.pk, "records": records, "balances": balances}
        )
        return Response(serializer.data)


class CashCorrectionView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        request=CashCorrectionSerializer,
        responses={
            status.HTTP_201_CREATED: CashRecordSerializer,
            status.HTTP_400_BAD_REQUEST: OpenApiResponse(
                description="Invalid correction"
            ),
            status.HTTP_403_FORBIDDEN: OpenApiResponse(
                description="User is not an administrator"
            ),
        },
    )
    def post(self, request) -> Response:
        serializer = CashCorrectionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        correction = correct_cash(
            created_by=request.user,
            **serializer.validated_data,
        )
        return Response(
            CashRecordSerializer(correction).data,
            status=status.HTTP_201_CREATED,
        )
