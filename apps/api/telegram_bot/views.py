import hmac

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from rest_framework import status
from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import TelegramLinkSerializer
from .services import create_telegram_link
from .services import revoke_telegram_identity
from .rate_limits import allow_request, client_ip
from .observability import metrics_snapshot
from .webhook import InvalidTelegramUpdateError, process_update

WEBHOOK_SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"


class TelegramLinkView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        identity = getattr(request.user, "telegram_identity", None)
        return Response(
            {
                "connected": bool(identity and identity.revoked_at is None),
                "linked_at": identity.linked_at if identity and identity.revoked_at is None else None,
            }
        )

    def post(self, request):
        if not allow_request(
            scope="telegram-link",
            identifier=str(request.user.pk),
            limit=settings.TELEGRAM_LINK_RATE_LIMIT,
            window=3600,
        ):
            return Response(
                {"detail": "Too many link requests."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        try:
            link = create_telegram_link(user=request.user)
        except ImproperlyConfigured:
            return Response(
                {"detail": "Telegram integration is not available."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        serializer = TelegramLinkSerializer(link)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def delete(self, request):
        revoked = revoke_telegram_identity(user=request.user)
        return Response(
            {"revoked": revoked},
            status=status.HTTP_200_OK,
        )


class TelegramWebhookView(APIView):
    # Telegram authenticates via the shared secret header, not sessions.
    # No session authentication also means no CSRF enforcement here.
    authentication_classes = []
    permission_classes = [AllowAny]
    parser_classes = [JSONParser]

    def post(self, request):
        content_length = request.META.get("CONTENT_LENGTH")
        try:
            content_length = int(content_length or 0)
        except ValueError:
            return Response(status=status.HTTP_400_BAD_REQUEST)
        if content_length > settings.TELEGRAM_WEBHOOK_MAX_BYTES:
            return Response(status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
        if not allow_request(
            scope="telegram-webhook",
            identifier=client_ip(request),
            limit=settings.TELEGRAM_WEBHOOK_RATE_LIMIT,
            window=60,
        ):
            return Response(status=status.HTTP_429_TOO_MANY_REQUESTS)
        expected_secret = settings.TELEGRAM_WEBHOOK_SECRET
        if not expected_secret:
            return Response(status=status.HTTP_503_SERVICE_UNAVAILABLE)

        received_secret = request.headers.get(WEBHOOK_SECRET_HEADER, "")
        if not hmac.compare_digest(
            received_secret.encode("utf-8"),
            expected_secret.encode("utf-8"),
        ):
            return Response(status=status.HTTP_403_FORBIDDEN)

        try:
            process_update(request.data)
        except InvalidTelegramUpdateError:
            return Response(
                {"detail": "Invalid Telegram update."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({"ok": True}, status=status.HTTP_200_OK)


class TelegramMetricsView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        return Response(metrics_snapshot())
