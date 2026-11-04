from unittest.mock import patch

from django.db import DatabaseError
from django.test import TestCase, override_settings
from django.urls import reverse


class HealthEndpointTests(TestCase):
    def test_health_is_public_and_does_not_query_dependencies(self):
        response = self.client.get(reverse("health"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})


@override_settings(
    TELEGRAM_BOT_TOKEN="bot-token",
    TELEGRAM_BOT_USERNAME="financify_bot",
    TELEGRAM_WEBHOOK_SECRET="webhook-secret",
)
class ReadinessEndpointTests(TestCase):
    def test_ready_when_database_and_configuration_are_available(self):
        response = self.client.get(reverse("readiness"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "status": "ready",
                "database": "ok",
                "configuration": "ok",
            },
        )

    @override_settings(TELEGRAM_BOT_TOKEN="")
    def test_not_ready_when_configuration_is_missing(self):
        response = self.client.get(reverse("readiness"))

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["configuration"], "missing")
        self.assertNotIn("TELEGRAM_BOT_TOKEN", response.content.decode())

    def test_not_ready_when_database_is_unavailable(self):
        with patch(
            "config.views.connection.cursor",
            side_effect=DatabaseError("database unavailable"),
        ):
            response = self.client.get(reverse("readiness"))

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["database"], "unavailable")
