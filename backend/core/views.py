from django.db import DatabaseError, connection
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


class HealthResponseSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["ok"])
    database = serializers.ChoiceField(choices=["ok"])
    postgis = serializers.ChoiceField(choices=["ok"])


class HealthErrorSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["error"])
    database = serializers.ChoiceField(choices=["unavailable"])
    postgis = serializers.ChoiceField(choices=["unknown"])


@extend_schema(
    operation_id="getHealth",
    responses={
        status.HTTP_200_OK: HealthResponseSerializer,
        status.HTTP_503_SERVICE_UNAVAILABLE: HealthErrorSerializer,
    },
    auth=[],
)
@api_view(["GET"])
@permission_classes([AllowAny])
def health(request) -> Response:
    del request

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT EXISTS("
                "SELECT 1 FROM pg_extension WHERE extname = 'postgis'"
                ")"
            )
            has_postgis = cursor.fetchone()[0]
    except DatabaseError:
        return Response(
            {
                "status": "error",
                "database": "unavailable",
                "postgis": "unknown",
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    if not has_postgis:
        return Response(
            {
                "status": "error",
                "database": "unavailable",
                "postgis": "unknown",
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return Response(
        {
            "status": "ok",
            "database": "ok",
            "postgis": "ok",
        }
    )
