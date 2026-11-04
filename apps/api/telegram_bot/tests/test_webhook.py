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

from conversations.models import (
    Conversation,
    ConversationChannel,
    Message,
    MessageDirection,
    MessageStatus,
    MessageType,
    TransactionDraft,
    TransactionDraftStatus,
)
from ledger.models import AccountSystemRole, Transaction, TransactionSource, TransactionStatus
from ledger.services import calculate_account_balance

from ..client import (
    TelegramAPIError,
    TelegramUnavailableError,
)
from ..models import (
    TelegramIdentity,
    TelegramLinkToken,
    TelegramOnboardingStep,
    TelegramUpdate,
    TelegramUpdateStatus,
    TelegramUpdateType,
)
from ..messages import ACCOUNT_ONBOARDING_PROMPT
from ..webhook import ERROR_REPLIES, TEXT_FORMAT_REPLY
from .fakes import FakeTelegramClient

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
        self.telegram = FakeTelegramClient()
        patcher = patch(
            "telegram_bot.webhook.get_telegram_client",
            return_value=self.telegram,
        )
        self.mock_get_client = patcher.start()
        self.addCleanup(patcher.stop)

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

    def _callback_update(
        self,
        *,
        draft,
        action="confirm",
        update_id=7001,
        callback_id="callback-1",
        chat_id=TELEGRAM_ID,
        from_id=TELEGRAM_ID,
    ):
        return {
            "update_id": update_id,
            "callback_query": {
                "id": callback_id,
                "from": {"id": from_id, "is_bot": False},
                "message": {
                    "message_id": 10,
                    "chat": {"id": chat_id, "type": "private"},
                },
                "data": f"draft:{action}:{draft.id}",
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

    def test_plain_text_from_unlinked_telegram_is_rejected(self):
        self._post(self._message_update(text="gastei 35 no almoço"))

        update = TelegramUpdate.objects.get()
        self.assertEqual(update.status, TelegramUpdateStatus.FAILED)
        self.assertEqual(update.error_code, "telegram_not_linked")

    def test_unknown_command_is_recorded_as_unsupported(self):
        self._post(self._message_update(text="/help"))

        update = TelegramUpdate.objects.get()
        self.assertEqual(update.error_code, "unsupported_command")

    def test_malformed_callback_query_is_recorded_as_failed(self):
        response = self._post(
            {"update_id": 3000, "callback_query": {"id": "abc", "data": "x"}}
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        update = TelegramUpdate.objects.get()
        self.assertEqual(update.update_type, TelegramUpdateType.CALLBACK_QUERY)
        self.assertEqual(update.status, TelegramUpdateStatus.FAILED)
        self.assertEqual(update.error_code, "malformed_callback_query")

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
        ), self.assertLogs("telegram_bot.webhook", level="ERROR") as logs:
            response = self._post(self._message_update())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        update = TelegramUpdate.objects.get()
        self.assertEqual(update.status, TelegramUpdateStatus.FAILED)
        self.assertEqual(update.error_code, "internal_error")
        self.assertEqual(logs.records[0].telegram_update_id, 1000)

    # --- Outbound replies ---------------------------------------------------

    def test_valid_start_replies_with_onboarding_prompt(self):
        self._create_token()

        self._post(self._message_update())

        self.assertEqual(
            self.telegram.sent_messages,
            [{"chat_id": TELEGRAM_ID, "text": ACCOUNT_ONBOARDING_PROMPT}],
        )

    def test_known_failures_reply_with_friendly_message(self):
        token = self._create_token()
        TelegramLinkToken.objects.filter(pk=token.pk).update(
            created_at=timezone.now() - timedelta(minutes=20),
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        cases = (
            (4001, "/start raw-link-token", "expired_link_token"),
            (4002, "/start unknown", "invalid_link_token"),
            (4003, "/start", "start_without_token"),
            (4004, "gastei 35", "telegram_not_linked"),
        )
        for update_id, text, error_code in cases:
            with self.subTest(error_code=error_code):
                self.telegram.sent_messages.clear()
                self._post(self._message_update(update_id=update_id, text=text))
                self.assertEqual(
                    self.telegram.sent_messages,
                    [{"chat_id": TELEGRAM_ID, "text": ERROR_REPLIES[error_code]}],
                )

    def test_failure_replies_never_echo_the_token(self):
        self._post(self._message_update(text="/start secret-raw-token"))

        for sent in self.telegram.sent_messages:
            self.assertNotIn("secret-raw-token", sent["text"])

    def test_non_private_chat_gets_no_reply(self):
        self._post(
            self._message_update(chat_type="group", chat_id=-100123456789)
        )

        self.assertEqual(self.telegram.sent_messages, [])

    def test_callback_and_unknown_updates_get_no_reply(self):
        self._post({"update_id": 5001, "callback_query": {"id": "x"}})
        self._post({"update_id": 5002, "edited_message": {}})

        self.assertEqual(self.telegram.sent_messages, [])

    def test_duplicate_update_does_not_reply_twice(self):
        self._create_token()

        self._post(self._message_update())
        self._post(self._message_update())

        self.assertEqual(len(self.telegram.sent_messages), 1)

    def test_send_failure_does_not_undo_completed_link(self):
        token = self._create_token()
        for error in (
            TelegramUnavailableError("Telegram sendMessage timed out."),
            TelegramAPIError("rejected", status_code=403),
        ):
            with self.subTest(error=type(error).__name__):
                TelegramIdentity.objects.all().delete()
                TelegramUpdate.objects.all().delete()
                TelegramLinkToken.objects.filter(pk=token.pk).update(used_at=None)
                self.mock_get_client.return_value = FakeTelegramClient(
                    error=error
                )

                with self.assertLogs("telegram_bot.webhook", level="WARNING"):
                    response = self._post(self._message_update())

                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertEqual(TelegramIdentity.objects.count(), 1)
                token.refresh_from_db()
                self.assertTrue(token.is_used)
                update = TelegramUpdate.objects.get()
                self.assertEqual(update.status, TelegramUpdateStatus.COMPLETED)

    def test_unconfigured_client_skips_reply_but_keeps_link(self):
        from django.core.exceptions import ImproperlyConfigured

        self._create_token()
        self.mock_get_client.side_effect = ImproperlyConfigured("missing")

        with self.assertLogs("telegram_bot.webhook", level="WARNING"):
            response = self._post(self._message_update())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(TelegramIdentity.objects.count(), 1)
        self.assertEqual(
            TelegramUpdate.objects.get().status, TelegramUpdateStatus.COMPLETED
        )

    def test_token_never_appears_in_logs(self):
        self._create_token(raw_token="log-sensitive-token")
        self.mock_get_client.return_value = FakeTelegramClient(
            error=TelegramUnavailableError("Telegram sendMessage timed out.")
        )

        with self.assertLogs("telegram_bot", level="DEBUG") as logs:
            self._post(self._message_update(text="/start log-sensitive-token"))

        for line in logs.output:
            self.assertNotIn("log-sensitive-token", line)

    # --- Persisted text conversations --------------------------------------

    def _link_identity(
        self,
        *,
        user=None,
        telegram_id=TELEGRAM_ID,
        onboarding_step=TelegramOnboardingStep.COMPLETED,
    ):
        return TelegramIdentity.objects.create(
            user=user or self.user,
            telegram_user_id=telegram_id,
            private_chat_id=telegram_id,
            onboarding_step=onboarding_step,
        )

    def test_onboarding_collects_account_then_balance(self):
        identity = self._link_identity(
            onboarding_step=TelegramOnboardingStep.AWAITING_ACCOUNT
        )

        self._post(self._message_update(update_id=5901, text="Nubank"))
        identity.refresh_from_db()
        self.assertEqual(
            identity.onboarding_step,
            TelegramOnboardingStep.AWAITING_BALANCE,
        )
        self.assertIn("saldo", self.telegram.sent_messages[-1]["text"].lower())

        self._post(self._message_update(update_id=5902, text="50 mil"))
        identity.refresh_from_db()
        self.assertEqual(
            identity.onboarding_step,
            TelegramOnboardingStep.COMPLETED,
        )
        primary = self.user.accounts.get(system_role=AccountSystemRole.PRIMARY)
        self.assertEqual(primary.name, "Nubank")
        self.assertEqual(calculate_account_balance(account=primary), 50000)
        self.assertIn("Conta pronta", self.telegram.sent_messages[-1]["text"])

    def test_linked_text_creates_conversation_and_inbound_outbound_messages(self):
        self._link_identity()

        response = self._post(
            self._message_update(text="gastei 35 reais no almoço")
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        update = TelegramUpdate.objects.get()
        self.assertEqual(update.status, TelegramUpdateStatus.COMPLETED)

        conversation = Conversation.objects.get()
        self.assertEqual(conversation.user, self.user)
        self.assertEqual(conversation.channel, ConversationChannel.TELEGRAM)

        messages = list(conversation.messages.order_by("created_at"))
        self.assertEqual(len(messages), 2)
        inbound, outbound = messages
        self.assertEqual(inbound.direction, MessageDirection.INBOUND)
        self.assertEqual(inbound.message_type, MessageType.TEXT)
        self.assertEqual(inbound.status, MessageStatus.COMPLETED)
        self.assertEqual(inbound.content, "gastei 35 reais no almoço")
        self.assertIsNotNone(inbound.processed_at)
        self.assertEqual(outbound.direction, MessageDirection.OUTBOUND)
        self.assertEqual(outbound.message_type, MessageType.TEXT)
        self.assertEqual(outbound.status, MessageStatus.COMPLETED)
        self.assertIn("Rascunho criado:", outbound.content)
        self.assertIsNotNone(outbound.processed_at)

        draft = TransactionDraft.objects.get()
        self.assertEqual(draft.source_message, inbound)
        self.assertEqual(draft.description, "no almoço")
        self.assertEqual(str(draft.currency), "BRL")
        self.assertEqual(draft.entries.count(), 2)
        self.assertIsNone(draft.transaction)
        preview = self.telegram.sent_messages[-1]
        buttons = preview["reply_markup"]["inline_keyboard"][0]
        self.assertEqual([button["text"] for button in buttons], ["Confirmar", "Cancelar"])
        self.assertEqual(
            buttons[0]["callback_data"], f"draft:confirm:{draft.id}"
        )
        self.assertEqual(
            buttons[1]["callback_data"], f"draft:cancel:{draft.id}"
        )

    def test_natural_income_form_creates_draft(self):
        self._link_identity()

        self._post(self._message_update(update_id=6000, text="ganho de 2500"))

        draft = TransactionDraft.objects.get()
        self.assertEqual(draft.description, "Receita")
        self.assertEqual(draft.entries.count(), 2)

    def test_subsequent_text_reuses_active_conversation(self):
        self._link_identity()

        self._post(self._message_update(update_id=6001, text="primeira"))
        self._post(self._message_update(update_id=6002, text="segunda"))

        self.assertEqual(Conversation.objects.count(), 1)
        self.assertEqual(Message.objects.count(), 4)
        self.assertEqual(TransactionDraft.objects.count(), 0)
        self.assertEqual(
            set(
                Message.objects.filter(
                    direction=MessageDirection.OUTBOUND
                ).values_list("content", flat=True)
            ),
            {TEXT_FORMAT_REPLY},
        )

    def test_duplicate_update_does_not_duplicate_conversation_messages(self):
        self._link_identity()
        payload = self._message_update(update_id=6003, text="mensagem única")

        self._post(payload)
        self._post(payload)

        self.assertEqual(Conversation.objects.count(), 1)
        self.assertEqual(Message.objects.count(), 2)

    def test_revoked_identity_cannot_create_conversation(self):
        identity = self._link_identity()
        identity.revoked_at = timezone.now()
        identity.save(update_fields=["revoked_at", "updated_at"])

        self._post(self._message_update(update_id=6004, text="olá"))

        update = TelegramUpdate.objects.get(update_id=6004)
        self.assertEqual(update.status, TelegramUpdateStatus.FAILED)
        self.assertEqual(update.error_code, "telegram_not_linked")
        self.assertEqual(Conversation.objects.count(), 0)
        self.assertEqual(Message.objects.count(), 0)

    def test_telegram_identity_isolates_conversations_by_user(self):
        self._link_identity(user=self.user, telegram_id=111111111)
        self._link_identity(user=self.other_user, telegram_id=222222222)

        self._post(
            self._message_update(
                update_id=6005,
                text="mensagem do primeiro",
                chat_id=111111111,
                from_id=111111111,
            )
        )
        self._post(
            self._message_update(
                update_id=6006,
                text="mensagem do segundo",
                chat_id=222222222,
                from_id=222222222,
            )
        )

        self.assertEqual(Conversation.objects.count(), 2)
        self.assertEqual(
            Conversation.objects.get(user=self.user)
            .messages.get(direction=MessageDirection.INBOUND)
            .content,
            "mensagem do primeiro",
        )
        self.assertEqual(
            Conversation.objects.get(user=self.other_user)
            .messages.get(direction=MessageDirection.INBOUND)
            .content,
            "mensagem do segundo",
        )

    def test_send_failure_keeps_inbound_but_does_not_record_outbound(self):
        self._link_identity()
        self.mock_get_client.return_value = FakeTelegramClient(
            error=TelegramUnavailableError("Telegram sendMessage timed out.")
        )

        with self.assertLogs("telegram_bot.webhook", level="WARNING"):
            self._post(self._message_update(update_id=6007, text="olá"))

        message = Message.objects.get()
        self.assertEqual(message.direction, MessageDirection.INBOUND)
        self.assertEqual(message.content, "olá")

    def test_start_token_is_never_persisted_as_conversation_message(self):
        self._create_token(raw_token="never-store-this-token")

        self._post(
            self._message_update(text="  /start never-store-this-token  ")
        )

        self.assertEqual(Conversation.objects.count(), 0)
        self.assertEqual(Message.objects.count(), 0)

    # --- Draft callbacks ----------------------------------------------------

    def test_confirm_callback_posts_draft_and_answers_callback(self):
        self._link_identity()
        self._post(
            self._message_update(
                update_id=7000,
                text="gastei 35,90 no almoço",
            )
        )
        draft = TransactionDraft.objects.get()

        response = self._post(self._callback_update(draft=draft))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        draft.refresh_from_db()
        self.assertEqual(draft.status, TransactionDraftStatus.CONFIRMED)
        self.assertIsNotNone(draft.resolved_at)
        transaction = Transaction.objects.get()
        self.assertEqual(transaction, draft.transaction)
        self.assertEqual(transaction.status, TransactionStatus.POSTED)
        self.assertEqual(transaction.source, TransactionSource.ASSISTANT)
        self.assertEqual(transaction.entries.count(), 2)
        self.assertEqual(
            self.telegram.answered_callbacks[-1],
            {
                "callback_query_id": "callback-1",
                "text": "Registro confirmado.",
            },
        )
        self.assertEqual(
            self.telegram.edited_messages[-1],
            {
                "chat_id": TELEGRAM_ID,
                "message_id": 10,
                "text": "Registro confirmado: no almoço.",
            },
        )
        callback_update = TelegramUpdate.objects.get(update_id=7001)
        self.assertEqual(callback_update.status, TelegramUpdateStatus.COMPLETED)

    def test_cancel_callback_rejects_draft_without_ledger_transaction(self):
        self._link_identity()
        self._post(
            self._message_update(update_id=7010, text="receita de 2500 salário")
        )
        draft = TransactionDraft.objects.get()

        self._post(
            self._callback_update(
                draft=draft,
                action="cancel",
                update_id=7011,
                callback_id="callback-cancel",
            )
        )

        draft.refresh_from_db()
        self.assertEqual(draft.status, TransactionDraftStatus.REJECTED)
        self.assertIsNotNone(draft.resolved_at)
        self.assertEqual(Transaction.objects.count(), 0)
        self.assertEqual(
            self.telegram.answered_callbacks[-1]["text"],
            "Rascunho cancelado.",
        )
        self.assertEqual(
            self.telegram.edited_messages[-1]["text"],
            "Rascunho cancelado: salário.",
        )

    def test_other_linked_user_cannot_confirm_draft(self):
        self._link_identity(user=self.user, telegram_id=111111111)
        self._link_identity(user=self.other_user, telegram_id=222222222)
        self._post(
            self._message_update(
                update_id=7020,
                text="gasto 10 café",
                chat_id=111111111,
                from_id=111111111,
            )
        )
        draft = TransactionDraft.objects.get()

        self._post(
            self._callback_update(
                draft=draft,
                update_id=7021,
                callback_id="callback-other",
                chat_id=222222222,
                from_id=222222222,
            )
        )

        draft.refresh_from_db()
        self.assertEqual(draft.status, TransactionDraftStatus.PENDING)
        self.assertEqual(Transaction.objects.count(), 0)
        self.assertEqual(
            self.telegram.answered_callbacks[-1]["text"],
            "Rascunho não encontrado.",
        )

    def test_duplicate_callback_update_does_not_post_twice(self):
        self._link_identity()
        self._post(self._message_update(update_id=7030, text="gasto 10 café"))
        draft = TransactionDraft.objects.get()
        callback = self._callback_update(draft=draft, update_id=7031)

        self._post(callback)
        self._post(callback)

        self.assertEqual(Transaction.objects.count(), 1)
        self.assertEqual(len(self.telegram.answered_callbacks), 1)

    def test_second_confirm_callback_only_answers_already_confirmed(self):
        self._link_identity()
        self._post(self._message_update(update_id=7040, text="gasto 10 café"))
        draft = TransactionDraft.objects.get()

        self._post(self._callback_update(draft=draft, update_id=7041))
        self._post(
            self._callback_update(
                draft=draft,
                update_id=7042,
                callback_id="callback-second",
            )
        )

        self.assertEqual(Transaction.objects.count(), 1)
        self.assertEqual(len(self.telegram.edited_messages), 1)
        self.assertEqual(len(self.telegram.sent_messages), 1)
        self.assertEqual(
            self.telegram.answered_callbacks[-1],
            {
                "callback_query_id": "callback-second",
                "text": "Registro já confirmado.",
            },
        )
