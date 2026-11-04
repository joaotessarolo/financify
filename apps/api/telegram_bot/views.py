import hmac

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from rest_framework import status
from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import TelegramLinkSerializer
from .services import create_telegram_link
from .webhook import InvalidTelegramUpdateError, process_update

WEBHOOK_SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"


class TelegramLinkView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            link = create_telegram_link(user=request.user)
        except ImproperlyConfigured:
            return Response(
                {"detail": "Telegram integration is not available."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        serializer = TelegramLinkSerializer(link)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class TelegramWebhookView(APIView):
    # Telegram authenticates via the shared secret header, not sessions.
    # No session authentication also means no CSRF enforcement here.
    authentication_classes = []
    permission_classes = [AllowAny]
    parser_classes = [JSONParser]

    def post(self, request):
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
