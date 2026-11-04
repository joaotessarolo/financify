from rest_framework import serializers


class TelegramLinkSerializer(serializers.Serializer):
    url = serializers.URLField(read_only=True)
    expires_at = serializers.DateTimeField(read_only=True)
