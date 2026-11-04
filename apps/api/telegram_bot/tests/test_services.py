from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import hashlib
import threading
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.db import connections
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from ..models import TelegramIdentity, TelegramLinkToken
from ..services import (
    ExpiredTelegramLinkTokenError,
    InvalidTelegramChatError,
    InvalidTelegramLinkTokenError,
    TelegramAccountAlreadyLinkedError,
    TelegramLink,
    UsedTelegramLinkTokenError,
    UserAlreadyLinkedToTelegramError,
    consume_telegram_link,
    create_telegram_link,
)


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


class ConsumeTelegramLinkServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user_model = get_user_model()
        cls.user = cls.user_model.objects.create_user(
            email="user@example.com",
            password="StrongPassword!123",
        )
        cls.other_user = cls.user_model.objects.create_user(
            email="other@example.com",
            password="StrongPassword!123",
        )

    def _create_token(
        self,
        *,
        user=None,
        raw_token: str = "valid-raw-token",
        expires_in: timedelta = timedelta(minutes=10),
        used_at=None,
    ) -> tuple[str, TelegramLinkToken]:
        owner = user or self.user
        digest = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        token = TelegramLinkToken.objects.create(
            user=owner,
            token_digest=digest,
            expires_at=timezone.now() + expires_in,
            used_at=used_at,
        )
        return raw_token, token

    def test_consumes_valid_token_creates_identity_and_marks_token_used(self):
        raw_token, token = self._create_token()

        identity = consume_telegram_link(
            raw_token=raw_token,
            telegram_user_id=123456789,
            private_chat_id=123456789,
        )

        token.refresh_from_db()
        self.assertIsNotNone(token.used_at)
        self.assertTrue(token.is_used)
        self.assertGreaterEqual(token.used_at, token.created_at)
        self.assertLessEqual(token.used_at, token.expires_at)

        self.assertEqual(TelegramIdentity.objects.count(), 1)
        self.assertEqual(identity.user, self.user)
        self.assertEqual(identity.telegram_user_id, 123456789)
        self.assertEqual(identity.private_chat_id, 123456789)
        self.assertIsNone(identity.revoked_at)
        self.assertTrue(identity.is_active)

    def test_rejects_nonexistent_or_empty_token(self):
        for invalid_token in ("nonexistent-token", "", "   "):
            with self.subTest(raw_token=invalid_token):
                with self.assertRaises(InvalidTelegramLinkTokenError):
                    consume_telegram_link(
                        raw_token=invalid_token,
                        telegram_user_id=123456789,
                        private_chat_id=123456789,
                    )

        self.assertEqual(TelegramIdentity.objects.count(), 0)

    def test_rejects_expired_token_and_does_not_create_identity(self):
        raw_token, token = self._create_token(expires_in=timedelta(minutes=5))
        past_created_at = timezone.now() - timedelta(minutes=15)
        past_expires_at = timezone.now() - timedelta(seconds=1)
        TelegramLinkToken.objects.filter(pk=token.pk).update(
            created_at=past_created_at,
            expires_at=past_expires_at,
        )

        with self.assertRaises(ExpiredTelegramLinkTokenError):
            consume_telegram_link(
                raw_token=raw_token,
                telegram_user_id=123456789,
                private_chat_id=123456789,
            )

        token.refresh_from_db()
        self.assertIsNone(token.used_at)
        self.assertEqual(TelegramIdentity.objects.count(), 0)

    def test_rejects_already_used_token(self):
        raw_token, token = self._create_token()
        used_at = token.created_at + timedelta(seconds=10)
        TelegramLinkToken.objects.filter(pk=token.pk).update(used_at=used_at)

        with self.assertRaises(UsedTelegramLinkTokenError):
            consume_telegram_link(
                raw_token=raw_token,
                telegram_user_id=123456789,
                private_chat_id=123456789,
            )

        token.refresh_from_db()
        self.assertEqual(token.used_at, used_at)
        self.assertEqual(TelegramIdentity.objects.count(), 0)

    def test_rejects_non_private_chat_or_invalid_telegram_ids(self):
        raw_token, token = self._create_token()

        invalid_cases = (
            (123456789, 987654321),
            (123456789, -100123456789),
            (0, 0),
            (-10, -10),
            (True, True),
        )
        for telegram_user_id, private_chat_id in invalid_cases:
            with self.subTest(
                telegram_user_id=telegram_user_id,
                private_chat_id=private_chat_id,
            ):
                with self.assertRaises(InvalidTelegramChatError):
                    consume_telegram_link(
                        raw_token=raw_token,
                        telegram_user_id=telegram_user_id,
                        private_chat_id=private_chat_id,
                    )

        token.refresh_from_db()
        self.assertIsNone(token.used_at)
        self.assertEqual(TelegramIdentity.objects.count(), 0)

    def test_rejects_when_telegram_account_is_already_linked_to_another_user(
        self,
    ):
        TelegramIdentity.objects.create(
            user=self.other_user,
            telegram_user_id=111222333,
            private_chat_id=111222333,
        )
        raw_token, token = self._create_token(user=self.user)

        with self.assertRaises(TelegramAccountAlreadyLinkedError):
            consume_telegram_link(
                raw_token=raw_token,
                telegram_user_id=111222333,
                private_chat_id=111222333,
            )

        token.refresh_from_db()
        self.assertIsNone(token.used_at)
        self.assertFalse(
            TelegramIdentity.objects.filter(user=self.user).exists()
        )

    def test_rejects_when_user_is_already_linked_to_another_active_telegram(
        self,
    ):
        existing_identity = TelegramIdentity.objects.create(
            user=self.user,
            telegram_user_id=111111111,
            private_chat_id=111111111,
        )
        raw_token, token = self._create_token(user=self.user)

        with self.assertRaises(UserAlreadyLinkedToTelegramError):
            consume_telegram_link(
                raw_token=raw_token,
                telegram_user_id=222222222,
                private_chat_id=222222222,
            )

        token.refresh_from_db()
        existing_identity.refresh_from_db()
        self.assertIsNone(token.used_at)
        self.assertEqual(existing_identity.telegram_user_id, 111111111)
        self.assertEqual(existing_identity.private_chat_id, 111111111)

    def test_allows_relinking_to_different_telegram_when_previous_link_was_revoked(
        self,
    ):
        revoked_identity = TelegramIdentity.objects.create(
            user=self.user,
            telegram_user_id=111111111,
            private_chat_id=111111111,
            revoked_at=timezone.now() - timedelta(days=1),
        )
        raw_token, token = self._create_token(user=self.user)

        identity = consume_telegram_link(
            raw_token=raw_token,
            telegram_user_id=222222222,
            private_chat_id=222222222,
        )

        token.refresh_from_db()
        self.assertTrue(token.is_used)
        self.assertEqual(identity.id, revoked_identity.id)
        self.assertEqual(identity.telegram_user_id, 222222222)
        self.assertEqual(identity.private_chat_id, 222222222)
        self.assertIsNone(identity.revoked_at)
        self.assertTrue(identity.is_active)

    def test_same_user_and_same_telegram_is_idempotent_and_consumes_token(
        self,
    ):
        existing_identity = TelegramIdentity.objects.create(
            user=self.user,
            telegram_user_id=123456789,
            private_chat_id=123456789,
        )
        raw_token, token = self._create_token(
            user=self.user,
            raw_token="second-link-token",
        )

        identity = consume_telegram_link(
            raw_token=raw_token,
            telegram_user_id=123456789,
            private_chat_id=123456789,
        )

        token.refresh_from_db()
        self.assertEqual(identity.id, existing_identity.id)
        self.assertTrue(identity.is_active)
        self.assertTrue(token.is_used)
        self.assertEqual(TelegramIdentity.objects.count(), 1)

    def test_reactivates_revoked_identity_for_same_user_and_telegram(self):
        revoked_identity = TelegramIdentity.objects.create(
            user=self.user,
            telegram_user_id=123456789,
            private_chat_id=123456789,
            revoked_at=timezone.now() - timedelta(hours=1),
        )
        raw_token, token = self._create_token(user=self.user)

        identity = consume_telegram_link(
            raw_token=raw_token,
            telegram_user_id=123456789,
            private_chat_id=123456789,
        )

        token.refresh_from_db()
        revoked_identity.refresh_from_db()
        self.assertEqual(identity.id, revoked_identity.id)
        self.assertIsNone(revoked_identity.revoked_at)
        self.assertTrue(revoked_identity.is_active)
        self.assertTrue(token.is_used)

    def test_rolls_back_token_usage_when_identity_creation_fails(self):
        raw_token, token = self._create_token()

        with patch.object(
            TelegramIdentity.objects,
            "create",
            side_effect=RuntimeError("Database failure during identity creation"),
        ):
            with self.assertRaises(RuntimeError):
                consume_telegram_link(
                    raw_token=raw_token,
                    telegram_user_id=123456789,
                    private_chat_id=123456789,
                )

        token.refresh_from_db()
        self.assertIsNone(token.used_at)
        self.assertFalse(token.is_used)
        self.assertEqual(TelegramIdentity.objects.count(), 0)


class ConsumeTelegramLinkConcurrencyTests(TransactionTestCase):
    def setUp(self):
        super().setUp()
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            email="concurrent@example.com",
            password="StrongPassword!123",
        )
        self.raw_token = "concurrent-raw-token"
        digest = hashlib.sha256(self.raw_token.encode("utf-8")).hexdigest()
        self.token = TelegramLinkToken.objects.create(
            user=self.user,
            token_digest=digest,
            expires_at=timezone.now() + timedelta(minutes=10),
        )

    def test_two_concurrent_consumptions_allow_only_one_success(self):
        barrier = threading.Barrier(2)

        def worker(telegram_id: int):
            try:
                barrier.wait(timeout=5)
                return (
                    "ok",
                    consume_telegram_link(
                        raw_token=self.raw_token,
                        telegram_user_id=telegram_id,
                        private_chat_id=telegram_id,
                    ),
                )
            except Exception as exc:
                return ("error", exc)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(worker, 111111111),
                executor.submit(worker, 222222222),
            ]
            results = [future.result() for future in futures]

        successes = [payload for status, payload in results if status == "ok"]
        errors = [payload for status, payload in results if status == "error"]

        self.assertEqual(len(successes), 1)
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], UsedTelegramLinkTokenError)

        self.token.refresh_from_db()
        self.assertTrue(self.token.is_used)
        self.assertEqual(TelegramIdentity.objects.count(), 1)
        self.assertEqual(TelegramIdentity.objects.get().id, successes[0].id)
