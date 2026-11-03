from datetime import timedelta
import hashlib
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase, override_settings
from django.utils import timezone

from ..models import TelegramLinkToken
from ..services import TelegramLink, create_telegram_link


@override_settings(
    TELEGRAM_BOT_USERNAME="financify_bot",
    TELEGRAM_LINK_TOKEN_TTL_SECONDS=600,
)
class CreateTelegramLinkServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user_model = get_user_model()
        cls.user = cls.user_model.objects.create_user(
            email="user@example.com",
            password="StrongPassword!123",
        )

    @patch(
        "telegram_bot.services.secrets.token_urlsafe",
        return_value="deterministic-token",
    )
    def test_creates_link_and_persists_only_hashed_token(
        self,
        mock_token_urlsafe,
    ):
        before = timezone.now()
        result = create_telegram_link(user=self.user)
        after = timezone.now()

        self.assertIsInstance(result, TelegramLink)
        self.assertEqual(
            result.url,
            "https://t.me/financify_bot?start=deterministic-token",
        )
        self.assertGreaterEqual(
            result.expires_at,
            before + timedelta(seconds=600),
        )
        self.assertLessEqual(
            result.expires_at,
            after + timedelta(seconds=600),
        )
        mock_token_urlsafe.assert_called_once_with(32)

        self.assertEqual(TelegramLinkToken.objects.count(), 1)
        token_record = TelegramLinkToken.objects.get()
        expected_digest = hashlib.sha256(
            b"deterministic-token"
        ).hexdigest()

        self.assertEqual(token_record.user, self.user)
        self.assertEqual(token_record.token_digest, expected_digest)
        self.assertEqual(token_record.expires_at, result.expires_at)
        self.assertNotIn("deterministic-token", token_record.token_digest)
        self.assertNotIn("deterministic-token", str(token_record))

    @override_settings(TELEGRAM_LINK_TOKEN_TTL_SECONDS=900)
    def test_respects_configured_ttl_seconds(self):
        before = timezone.now()
        result = create_telegram_link(user=self.user)
        after = timezone.now()

        self.assertGreaterEqual(
            result.expires_at,
            before + timedelta(seconds=900),
        )
        self.assertLessEqual(
            result.expires_at,
            after + timedelta(seconds=900),
        )

    def test_two_calls_generate_two_distinct_records(self):
        first_link = create_telegram_link(user=self.user)
        second_link = create_telegram_link(user=self.user)

        self.assertNotEqual(first_link.url, second_link.url)
        self.assertEqual(TelegramLinkToken.objects.count(), 2)

    @patch(
        "telegram_bot.services.secrets.token_urlsafe",
        return_value="secret-raw-token",
    )
    def test_repr_of_telegram_link_omits_url_and_raw_token(
        self,
        _mock_token_urlsafe,
    ):
        result = create_telegram_link(user=self.user)
        representation = repr(result)

        self.assertNotIn("secret-raw-token", representation)
        self.assertNotIn("https://t.me/", representation)
        self.assertIn("expires_at=", representation)

    @override_settings(TELEGRAM_BOT_USERNAME="")
    def test_empty_bot_username_raises_improperly_configured_without_creating_record(
        self,
    ):
        with self.assertRaisesMessage(
            ImproperlyConfigured,
            "TELEGRAM_BOT_USERNAME must be configured.",
        ):
            create_telegram_link(user=self.user)

        self.assertEqual(TelegramLinkToken.objects.count(), 0)

    @override_settings(TELEGRAM_BOT_USERNAME="@financify_bot")
    def test_bot_username_starting_with_at_sign_raises_improperly_configured(
        self,
    ):
        with self.assertRaisesMessage(
            ImproperlyConfigured,
            "TELEGRAM_BOT_USERNAME must not start with '@'.",
        ):
            create_telegram_link(user=self.user)

        self.assertEqual(TelegramLinkToken.objects.count(), 0)

    @override_settings(TELEGRAM_LINK_TOKEN_TTL_SECONDS=0)
    def test_zero_ttl_raises_improperly_configured(self):
        with self.assertRaisesMessage(
            ImproperlyConfigured,
            "TELEGRAM_LINK_TOKEN_TTL_SECONDS must be greater than zero.",
        ):
            create_telegram_link(user=self.user)

        self.assertEqual(TelegramLinkToken.objects.count(), 0)

    @override_settings(TELEGRAM_LINK_TOKEN_TTL_SECONDS=-60)
    def test_negative_ttl_raises_improperly_configured(self):
        with self.assertRaisesMessage(
            ImproperlyConfigured,
            "TELEGRAM_LINK_TOKEN_TTL_SECONDS must be greater than zero.",
        ):
            create_telegram_link(user=self.user)

        self.assertEqual(TelegramLinkToken.objects.count(), 0)
