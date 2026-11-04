from datetime import datetime
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from ..models import TelegramLinkToken
from ..services import create_telegram_link


@override_settings(
    TELEGRAM_BOT_USERNAME="financify_bot",
    TELEGRAM_LINK_TOKEN_TTL_SECONDS=600,
)
class TelegramLinkViewTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user_model = get_user_model()
        cls.user = cls.user_model.objects.create_user(
            email="user@example.com",
            password="StrongPassword!123",
        )
        cls.url = reverse("telegram_bot:link")

    def test_url_resolves_to_expected_path(self):
        self.assertEqual(self.url, "/api/v1/telegram/link/")

    def test_unauthenticated_post_returns_403_and_does_not_create_token(self):
        response = self.client.post(self.url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(TelegramLinkToken.objects.count(), 0)

    def test_get_method_is_not_allowed(self):
        self.client.force_login(self.user)

        response = self.client.get(self.url)

        self.assertEqual(
            response.status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    @patch(
        "telegram_bot.services.secrets.token_urlsafe",
        return_value="api-generated-token",
    )
    def test_authenticated_post_creates_link_and_returns_only_url_and_expires_at(
        self,
        _mock_token_urlsafe,
    ):
        self.client.force_login(self.user)

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(set(response.data.keys()), {"url", "expires_at"})
        self.assertEqual(
            response.data["url"],
            "https://t.me/financify_bot?start=api-generated-token",
        )

        token_record = TelegramLinkToken.objects.get()
        self.assertEqual(token_record.user, self.user)
        parsed_expires_at = datetime.fromisoformat(response.data["expires_at"])
        self.assertEqual(parsed_expires_at, token_record.expires_at)

        for forbidden_key in (
            "id",
            "token",
            "raw_token",
            "token_digest",
            "digest",
            "user",
            "user_id",
            "used_at",
            "created_at",
        ):
            self.assertNotIn(forbidden_key, response.data)

        serialized_payload = response.content.decode("utf-8")
        self.assertNotIn(token_record.token_digest, serialized_payload)
        self.assertNotIn(str(token_record.id), serialized_payload)

    def test_authenticated_post_calls_create_telegram_link_with_request_user(
        self,
    ):
        self.client.force_login(self.user)

        with patch(
            "telegram_bot.views.create_telegram_link",
            wraps=create_telegram_link,
        ) as mock_create_link:
            response = self.client.post(self.url)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        mock_create_link.assert_called_once_with(user=self.user)

    @override_settings(TELEGRAM_BOT_USERNAME="")
    def test_invalid_bot_username_configuration_returns_503_and_creates_no_token(
        self,
    ):
        self.client.force_login(self.user)

        response = self.client.post(self.url)

        self.assertEqual(
            response.status_code,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
        self.assertEqual(
            response.data,
            {"detail": "Telegram integration is not available."},
        )
        self.assertEqual(TelegramLinkToken.objects.count(), 0)

    @override_settings(TELEGRAM_LINK_TOKEN_TTL_SECONDS=0)
    def test_invalid_ttl_configuration_returns_503_and_creates_no_token(self):
        self.client.force_login(self.user)

        response = self.client.post(self.url)

        self.assertEqual(
            response.status_code,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
        self.assertEqual(
            response.data,
            {"detail": "Telegram integration is not available."},
        )
        self.assertEqual(TelegramLinkToken.objects.count(), 0)
