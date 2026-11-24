"""The merchant's accept and reject endpoints (S2-15.1).

The views only parse the request and check who is calling; the rules live in
orders.transitions.
"""

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .permissions import IsOrderShopMember
from .serializers import (
    DecisionErrorSerializer,
    MerchantDecisionSerializer,
    RejectSerializer,
)
from .transitions import TransitionError, accept_deadline, latest_reason, transition

FORBIDDEN = OpenApiResponse(
    description="Not signed in, or the order is not this shop's (or does not exist)"
)
CONFLICT = OpenApiResponse(
    response=DecisionErrorSerializer,
    description="Already decided the other way, or the accept time has passed",
)


def decision_body(order) -> dict:
    return MerchantDecisionSerializer(
        {
            "id": order.pk,
            "status": order.status,
            "accept_deadline": accept_deadline(order),
            "reject_reason": latest_reason(order),
        }
    ).data


class _DecisionView(APIView):
    permission_classes = [IsOrderShopMember]
    target: str

    def decide(self, request, id: int, reason: str = "") -> Response:
        try:
            order, _ = transition(
                order_id=id, to=self.target, by=request.user, reason=reason
            )
        except TransitionError as error:
            return Response(
                {"code": error.code, "detail": str(error)},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(decision_body(order))


class AcceptOrderView(_DecisionView):
    target = "accepted"

    @extend_schema(
        request=None,
        responses={
            status.HTTP_200_OK: MerchantDecisionSerializer,
            status.HTTP_403_FORBIDDEN: FORBIDDEN,
            status.HTTP_409_CONFLICT: CONFLICT,
        },
    )
    def post(self, request, id: int) -> Response:
        return self.decide(request, id)


class RejectOrderView(_DecisionView):
    target = "rejected"

    @extend_schema(
        request=RejectSerializer,
        responses={
            status.HTTP_200_OK: MerchantDecisionSerializer,
            status.HTTP_400_BAD_REQUEST: OpenApiResponse(
                description="Missing, blank or too long reason"
            ),
            status.HTTP_403_FORBIDDEN: FORBIDDEN,
            status.HTTP_409_CONFLICT: CONFLICT,
        },
    )
    def post(self, request, id: int) -> Response:
        serializer = RejectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self.decide(request, id, serializer.validated_data["reason"])
