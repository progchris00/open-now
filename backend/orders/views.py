from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .permissions import IsCustomer
from .serializers import (
    IDEMPOTENCY_KEY_MAX_LENGTH,
    IdempotencyKeySerializer,
    OrderSerializer,
    PlaceOrderSerializer,
)
from .services import CartLine, KeyReused, PlacementError, place_order


class PlaceOrderView(APIView):
    permission_classes = [IsCustomer]

    @extend_schema(
        operation_id="placeOrder",
        summary="Place a cash-on-delivery order",
        parameters=[
            OpenApiParameter(
                name="Idempotency-Key",
                type={
                    "type": "string",
                    "minLength": 1,
                    "maxLength": IDEMPOTENCY_KEY_MAX_LENGTH,
                },
                location=OpenApiParameter.HEADER,
                required=True,
                description=(
                    "A new random value for each order. "
                    "Retrying with the same key returns the first order."
                ),
            )
        ],
        request=PlaceOrderSerializer,
        responses={
            status.HTTP_201_CREATED: OrderSerializer,
            status.HTTP_200_OK: OpenApiResponse(
                response=OrderSerializer,
                description="Already placed with this Idempotency-Key",
            ),
            status.HTTP_400_BAD_REQUEST: OpenApiResponse(
                description="Invalid cart, bill below the total, or not cash"
            ),
            status.HTTP_403_FORBIDDEN: OpenApiResponse(
                description="Not signed in as a customer"
            ),
            status.HTTP_409_CONFLICT: OpenApiResponse(
                description="Idempotency-Key already used for a different order"
            ),
        },
    )
    def post(self, request) -> Response:
        key = IdempotencyKeySerializer(
            data={"idempotency_key": request.headers.get("Idempotency-Key")}
        )
        key.is_valid(raise_exception=True)
        body = PlaceOrderSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data

        try:
            order, created = place_order(
                customer=request.user,
                lines=[CartLine(**line) for line in data["items"]],
                distance_km=data["distance_km"],
                bill=data["bill"],
                payment_method=data["payment_method"],
                idempotency_key=key.validated_data["idempotency_key"],
            )
        except PlacementError as error:
            return Response(
                {error.field: [str(error)]}, status=status.HTTP_400_BAD_REQUEST
            )
        except KeyReused as error:
            return Response({"detail": str(error)}, status=status.HTTP_409_CONFLICT)

        return Response(
            OrderSerializer(order).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )
