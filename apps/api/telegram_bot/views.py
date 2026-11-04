from django.core.exceptions import ImproperlyConfigured
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import TelegramLinkSerializer
from .services import create_telegram_link


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
