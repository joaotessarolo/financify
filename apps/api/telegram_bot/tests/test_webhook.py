from datetime import timedelta
import hashlib
import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from ..models import (
    TelegramIdentity,
    TelegramLinkToken,
    TelegramUpdate,
    TelegramUpdateStatus,
    TelegramUpdateType,
)

WEBHOOK_SECRET = "test-webhook-secret"
TELEGRAM_ID = 123456789


@override_settings(TELEGRAM_WEBHOOK_SECRET=WEBHOOK_SECRET)
class TelegramWebhookViewTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.user = user_model.objects.create_user(
            email="user@example.com",
            password="StrongPassword!123",
        )
        cls.other_user = user_model.objects.create_user(
            email="other@example.com",
            password="StrongPassword!123",
        )
        cls.url = reverse("telegram_bot:webhook")

    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)

    def _create_token(self, raw_token="raw-link-token", user=None):
        return TelegramLinkToken.objects.create(
            user=user or self.user,
            token_digest=hashlib.sha256(raw_token.encode()).hexdigest(),
            expires_at=timezone.now() + timedelta(minutes=10),
        )

    def _message_update(
        self,
        *,
        update_id=1000,
        text="/start raw-link-token",
        chat_type="private",
        chat_id=TELEGRAM_ID,
        from_id=TELEGRAM_ID,
    ):
        return {
            "update_id": update_id,
            "message": {
                "message_id": 1,
                "date": 1700000000,
                "chat": {"id": chat_id, "type": chat_type},
                "from": {"id": from_id, "is_bot": False, "first_name": "Ana"},
                "text": text,
            },
        }

    def _post(self, payload, secret=WEBHOOK_SECRET):
        headers = {}
        if secret is not None:
            headers["X-Telegram-Bot-Api-Secret-Token"] = secret
        return self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
            headers=headers,
        )

    def test_url_resolves_to_expected_path(self):
        self.assertEqual(self.url, "/api/v1/telegram/webhook/")

    # --- Secret validation -------------------------------------------------

    def test_missing_secret_returns_403_and_records_nothing(self):
        response = self._post(self._message_update(), secret=None)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(TelegramUpdate.objects.count(), 0)

    def test_invalid_secret_returns_403_and_records_nothing(self):
        self._create_token()

        response = self._post(self._message_update(), secret="wrong-secret")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(TelegramUpdate.objects.count(), 0)
        self.assertEqual(TelegramIdentity.objects.count(), 0)

    @override_settings(TELEGRAM_WEBHOOK_SECRET="")
    def test_unconfigured_secret_returns_503_even_with_empty_header(self):
        response = self._post(self._message_update(), secret="")

        self.assertEqual(
            response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE
        )
        self.assertEqual(TelegramUpdate.objects.count(), 0)

    def test_endpoint_does_not_require_session_or_csrf(self):
        self._create_token()

        response = self._post(self._message_update())

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_get_method_is_not_allowed(self):
        response = self.client.get(
            self.url,
            headers={"X-Telegram-Bot-Api-Secret-Token": WEBHOOK_SECRET},
        )

        self.assertEqual(
            response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED
        )

    # --- Payload validation ------------------------------------------------

    def test_invalid_payloads_return_400_and_record_nothing(self):
        invalid_payloads = (
            [],
            "string",
            {},
            {"update_id": None},
            {"update_id": "1000"},
            {"update_id": 0},
            {"update_id": -5},
            {"update_id": True},
            {"update_id": 1000, "message": "not-an-object"},
            {"update_id": 1000, "callback_query": []},
        )
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                response = self._post(payload)
                self.assertEqual(
                    response.status_code, status.HTTP_400_BAD_REQUEST
                )

        self.assertEqual(TelegramUpdate.objects.count(), 0)

    def test_malformed_json_returns_400(self):
        response = self.client.post(
            self.url,
            data="{not json",
            content_type="application/json",
            headers={"X-Telegram-Bot-Api-Secret-Token": WEBHOOK_SECRET},
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(TelegramUpdate.objects.count(), 0)

    # --- /start flow -------------------------------------------------------

    def test_valid_start_links_account_and_completes_update(self):
        token = self._create_token()

        response = self._post(self._message_update())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        identity = TelegramIdentity.objects.get()
        self.assertEqual(identity.user, self.user)
        self.assertEqual(identity.telegram_user_id, TELEGRAM_ID)
        self.assertEqual(identity.private_chat_id, TELEGRAM_ID)

        token.refresh_from_db()
        self.assertTrue(token.is_used)

        update = TelegramUpdate.objects.get(update_id=1000)
        self.assertEqual(update.update_type, TelegramUpdateType.MESSAGE)
        self.assertEqual(update.status, TelegramUpdateStatus.COMPLETED)
        self.assertEqual(update.error_code, "")
        self.assertIsNotNone(update.processed_at)

    def test_start_with_bot_mention_is_recognized(self):
        self._create_token()

        self._post(
            self._message_update(text="/start@financify_bot raw-link-token")
        )

        self.assertEqual(TelegramIdentity.objects.count(), 1)
        self.assertEqual(
            TelegramUpdate.objects.get().status, TelegramUpdateStatus.COMPLETED
        )

    def test_update_record_does_not_store_token_or_payload(self):
        self._create_token()

        self._post(self._message_update())

        update = TelegramUpdate.objects.get()
        stored_values = " ".join(
            str(getattr(update, field.attname))
            for field in TelegramUpdate._meta.concrete_fields
        )
        self.assertNotIn("raw-link-token", stored_values)
        self.assertNotIn("Ana", stored_values)

    def test_duplicate_update_returns_200_without_reprocessing(self):
        self._create_token()
        first = self._post(self._message_update())
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        update = TelegramUpdate.objects.get()

        with patch("telegram_bot.webhook.consume_telegram_link") as mock_consume:
            second = self._post(self._message_update())

        self.assertEqual(second.status_code, status.HTTP_200_OK)
        mock_consume.assert_not_called()
        self.assertEqual(TelegramUpdate.objects.count(), 1)
        update_after = TelegramUpdate.objects.get()
        self.assertEqual(update_after.processed_at, update.processed_at)
        self.assertEqual(update_after.status, TelegramUpdateStatus.COMPLETED)

    def test_expired_token_marks_update_failed(self):
        token = self._create_token()
        TelegramLinkToken.objects.filter(pk=token.pk).update(
            created_at=timezone.now() - timedelta(minutes=20),
            expires_at=timezone.now() - timedelta(minutes=1),
        )

        response = self._post(self._message_update())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        update = TelegramUpdate.objects.get()
        self.assertEqual(update.status, TelegramUpdateStatus.FAILED)
        self.assertEqual(update.error_code, "expired_link_token")
        self.assertIsNotNone(update.processed_at)
        self.assertEqual(TelegramIdentity.objects.count(), 0)

    def test_unknown_token_marks_update_failed(self):
        response = self._post(self._message_update(text="/start unknown"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        update = TelegramUpdate.objects.get()
        self.assertEqual(update.status, TelegramUpdateStatus.FAILED)
        self.assertEqual(update.error_code, "invalid_link_token")

    def test_start_without_token_marks_update_failed(self):
        response = self._post(self._message_update(text="/start"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        update = TelegramUpdate.objects.get()
        self.assertEqual(update.status, TelegramUpdateStatus.FAILED)
        self.assertEqual(update.error_code, "start_without_token")

    def test_telegram_already_linked_to_other_user_marks_update_failed(self):
        TelegramIdentity.objects.create(
            user=self.other_user,
            telegram_user_id=TELEGRAM_ID,
            private_chat_id=TELEGRAM_ID,
        )
        token = self._create_token(user=self.user)

        response = self._post(self._message_update())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        update = TelegramUpdate.objects.get()
        self.assertEqual(update.status, TelegramUpdateStatus.FAILED)
        self.assertEqual(update.error_code, "telegram_account_already_linked")
        token.refresh_from_db()
        self.assertFalse(token.is_used)
        self.assertFalse(TelegramIdentity.objects.filter(user=self.user).exists())

    def test_user_already_linked_to_other_telegram_marks_update_failed(self):
        TelegramIdentity.objects.create(
            user=self.user,
            telegram_user_id=999999999,
            private_chat_id=999999999,
        )
        self._create_token(user=self.user)

        self._post(self._message_update())

        update = TelegramUpdate.objects.get()
        self.assertEqual(update.status, TelegramUpdateStatus.FAILED)
        self.assertEqual(update.error_code, "user_already_linked")

    def test_non_private_chat_marks_update_failed_without_linking(self):
        token = self._create_token()

        for idx, chat_type in enumerate(("group", "supergroup", "channel")):
            with self.subTest(chat_type=chat_type):
                response = self._post(
                    self._message_update(
                        update_id=2000 + idx,
                        chat_type=chat_type,
                        chat_id=-100123456789,
                    )
                )
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                update = TelegramUpdate.objects.get(update_id=2000 + idx)
                self.assertEqual(update.status, TelegramUpdateStatus.FAILED)
                self.assertEqual(update.error_code, "non_private_chat")

        token.refresh_from_db()
        self.assertFalse(token.is_used)
        self.assertEqual(TelegramIdentity.objects.count(), 0)

    # --- Other update kinds -------------------------------------------------

    def test_plain_text_message_is_recorded_as_unsupported_for_now(self):
        self._post(self._message_update(text="gastei 35 no almoço"))

        update = TelegramUpdate.objects.get()
        self.assertEqual(update.status, TelegramUpdateStatus.FAILED)
        self.assertEqual(update.error_code, "unsupported_message")

    def test_unknown_command_is_recorded_as_unsupported(self):
        self._post(self._message_update(text="/help"))

        update = TelegramUpdate.objects.get()
        self.assertEqual(update.error_code, "unsupported_command")

    def test_callback_query_is_recorded_as_unsupported_for_now(self):
        response = self._post(
            {"update_id": 3000, "callback_query": {"id": "abc", "data": "x"}}
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        update = TelegramUpdate.objects.get()
        self.assertEqual(update.update_type, TelegramUpdateType.CALLBACK_QUERY)
        self.assertEqual(update.status, TelegramUpdateStatus.FAILED)
        self.assertEqual(update.error_code, "unsupported_update_type")

    def test_unknown_update_kind_is_recorded_as_unsupported(self):
        response = self._post({"update_id": 3001, "edited_message": {}})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        update = TelegramUpdate.objects.get()
        self.assertEqual(update.update_type, TelegramUpdateType.UNSUPPORTED)
        self.assertEqual(update.error_code, "unsupported_update_type")

    def test_unexpected_error_marks_update_failed_with_generic_code(self):
        self._create_token()

        with patch(
            "telegram_bot.webhook.consume_telegram_link",
            side_effect=RuntimeError("boom"),
        ), self.assertLogs("telegram_bot.webhook", level="ERROR"):
            response = self._post(self._message_update())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        update = TelegramUpdate.objects.get()
        self.assertEqual(update.status, TelegramUpdateStatus.FAILED)
        self.assertEqual(update.error_code, "internal_error")
