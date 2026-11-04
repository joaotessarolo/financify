from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings

from .fakes import FakeTelegramClient


class ConfigureTelegramWebhookCommandTests(SimpleTestCase):
    @override_settings(TELEGRAM_WEBHOOK_SECRET="webhook-secret")
    def test_configures_webhook_without_printing_secret(self):
        client = FakeTelegramClient()
        stdout = StringIO()

        with patch(
            "telegram_bot.management.commands.configure_telegram_webhook.get_telegram_client",
            return_value=client,
        ):
            call_command(
                "configure_telegram_webhook",
                url="https://example.com/api/v1/telegram/webhook/",
                stdout=stdout,
            )

        self.assertEqual(
            client.webhook_configurations,
            [
                {
                    "url": "https://example.com/api/v1/telegram/webhook/",
                    "secret_token": "webhook-secret",
                }
            ],
        )
        self.assertIn("Telegram webhook configured", stdout.getvalue())
        self.assertNotIn("webhook-secret", stdout.getvalue())

    @override_settings(TELEGRAM_WEBHOOK_SECRET="")
    def test_requires_configured_webhook_secret(self):
        with self.assertRaisesMessage(
            CommandError,
            "TELEGRAM_WEBHOOK_SECRET must be configured.",
        ):
            call_command(
                "configure_telegram_webhook",
                url="https://example.com/api/v1/telegram/webhook/",
            )

    @override_settings(TELEGRAM_WEBHOOK_SECRET="webhook-secret")
    def test_rejects_non_https_url(self):
        with self.assertRaisesMessage(CommandError, "must use HTTPS"):
            call_command(
                "configure_telegram_webhook",
                url="http://example.com/webhook/",
            )
