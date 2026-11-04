from datetime import timedelta
import uuid

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from ..models import (
    TelegramIdentity,
    TelegramLinkToken,
    TelegramUpdate,
    TelegramUpdateStatus,
    TelegramUpdateType,
)


class TelegramIdentityModelTests(TestCase):
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

    def test_create_valid_telegram_identity(self):
        identity = TelegramIdentity.objects.create(
            user=self.user,
            telegram_user_id=9876543210,
            private_chat_id=9876543210,
        )

        self.assertIsInstance(identity.id, uuid.UUID)
        self.assertEqual(identity.user, self.user)
        self.assertEqual(self.user.telegram_identity, identity)
        self.assertEqual(identity.telegram_user_id, 9876543210)
        self.assertEqual(identity.private_chat_id, 9876543210)
        self.assertIsNotNone(identity.linked_at)
        self.assertIsNotNone(identity.updated_at)
        self.assertIsNone(identity.revoked_at)
        self.assertTrue(identity.is_active)
        identity.full_clean()

    def test_is_active_is_false_when_revoked_at_is_set(self):
        identity = TelegramIdentity.objects.create(
            user=self.user,
            telegram_user_id=123456789,
            private_chat_id=123456789,
            revoked_at=timezone.now(),
        )

        self.assertFalse(identity.is_active)

    def test_str_returns_telegram_user_id_without_personal_data(self):
        identity = TelegramIdentity.objects.create(
            user=self.user,
            telegram_user_id=123456789,
            private_chat_id=123456789,
        )

        self.assertEqual(str(identity), "Telegram 123456789")
        self.assertNotIn(self.user.email, str(identity))

    def test_deleting_user_cascades_to_telegram_identity(self):
        cascade_user = self.user_model.objects.create_user(
            email="cascade@example.com",
            password="StrongPassword!123",
        )
        identity = TelegramIdentity.objects.create(
            user=cascade_user,
            telegram_user_id=555555555,
            private_chat_id=555555555,
        )

        cascade_user.delete()

        self.assertFalse(
            TelegramIdentity.objects.filter(id=identity.id).exists()
        )

    def test_user_cannot_have_two_telegram_identities(self):
        TelegramIdentity.objects.create(
            user=self.user,
            telegram_user_id=111111111,
            private_chat_id=111111111,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                TelegramIdentity.objects.create(
                    user=self.user,
                    telegram_user_id=222222222,
                    private_chat_id=222222222,
                )

    def test_telegram_user_id_cannot_belong_to_two_users(self):
        TelegramIdentity.objects.create(
            user=self.user,
            telegram_user_id=111111111,
            private_chat_id=111111111,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                TelegramIdentity.objects.create(
                    user=self.other_user,
                    telegram_user_id=111111111,
                    private_chat_id=222222222,
                )

    def test_private_chat_id_cannot_belong_to_two_identities(self):
        TelegramIdentity.objects.create(
            user=self.user,
            telegram_user_id=111111111,
            private_chat_id=999999999,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                TelegramIdentity.objects.create(
                    user=self.other_user,
                    telegram_user_id=222222222,
                    private_chat_id=999999999,
                )

    def test_full_clean_rejects_zero_or_negative_telegram_ids(self):
        for field in ("telegram_user_id", "private_chat_id"):
            for invalid_value in (0, -1, -100123456789):
                with self.subTest(field=field, value=invalid_value):
                    kwargs = {
                        "user": self.user,
                        "telegram_user_id": 123456789,
                        "private_chat_id": 123456789,
                        field: invalid_value,
                    }
                    identity = TelegramIdentity(**kwargs)
                    with self.assertRaises(ValidationError) as ctx:
                        identity.full_clean()
                    self.assertIn(field, ctx.exception.error_dict)

    def test_database_rejects_zero_or_negative_telegram_user_id(self):
        for invalid_value in (0, -1, -100123456789):
            with self.subTest(telegram_user_id=invalid_value):
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        TelegramIdentity.objects.create(
                            user=self.user,
                            telegram_user_id=invalid_value,
                            private_chat_id=123456789,
                        )

    def test_database_rejects_zero_or_negative_private_chat_id(self):
        for invalid_value in (0, -1, -100123456789):
            with self.subTest(private_chat_id=invalid_value):
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        TelegramIdentity.objects.create(
                            user=self.user,
                            telegram_user_id=123456789,
                            private_chat_id=invalid_value,
                        )


class TelegramLinkTokenModelTests(TestCase):
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
        cls.digest = "a" * 64

    def test_create_valid_telegram_link_token(self):
        expires_at = timezone.now() + timedelta(minutes=10)
        token = TelegramLinkToken.objects.create(
            user=self.user,
            token_digest=self.digest,
            expires_at=expires_at,
        )

        self.assertIsInstance(token.id, uuid.UUID)
        self.assertEqual(token.user, self.user)
        self.assertIn(token, self.user.telegram_link_tokens.all())
        self.assertEqual(token.token_digest, self.digest)
        self.assertEqual(token.expires_at, expires_at)
        self.assertIsNone(token.used_at)
        self.assertFalse(token.is_used)
        self.assertIsNotNone(token.created_at)
        token.full_clean()

    def test_is_used_is_true_when_used_at_is_set(self):
        expires_at = timezone.now() + timedelta(minutes=10)
        token = TelegramLinkToken.objects.create(
            user=self.user,
            token_digest=self.digest,
            expires_at=expires_at,
        )

        used_at = token.created_at + timedelta(minutes=1)
        token.used_at = used_at
        token.save(update_fields=["used_at"])
        token.refresh_from_db()

        self.assertTrue(token.is_used)
        self.assertEqual(token.used_at, used_at)

    def test_str_does_not_expose_digest_or_email(self):
        token = TelegramLinkToken.objects.create(
            user=self.user,
            token_digest=self.digest,
            expires_at=timezone.now() + timedelta(minutes=10),
        )

        representation = str(token)
        self.assertEqual(representation, f"Telegram link token {token.id}")
        self.assertNotIn(self.digest, representation)
        self.assertNotIn(self.user.email, representation)

    def test_deleting_user_cascades_to_link_tokens(self):
        cascade_user = self.user_model.objects.create_user(
            email="cascade-token@example.com",
            password="StrongPassword!123",
        )
        token = TelegramLinkToken.objects.create(
            user=cascade_user,
            token_digest="b" * 64,
            expires_at=timezone.now() + timedelta(minutes=10),
        )

        cascade_user.delete()

        self.assertFalse(TelegramLinkToken.objects.filter(id=token.id).exists())

    def test_token_digest_must_be_unique(self):
        expires_at = timezone.now() + timedelta(minutes=10)
        TelegramLinkToken.objects.create(
            user=self.user,
            token_digest=self.digest,
            expires_at=expires_at,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                TelegramLinkToken.objects.create(
                    user=self.other_user,
                    token_digest=self.digest,
                    expires_at=expires_at,
                )

    def test_same_user_can_have_multiple_link_tokens(self):
        expires_at = timezone.now() + timedelta(minutes=10)
        first_token = TelegramLinkToken.objects.create(
            user=self.user,
            token_digest="a" * 64,
            expires_at=expires_at,
        )
        second_token = TelegramLinkToken.objects.create(
            user=self.user,
            token_digest="b" * 64,
            expires_at=expires_at,
        )

        self.assertNotEqual(first_token.id, second_token.id)
        self.assertEqual(self.user.telegram_link_tokens.count(), 2)

    def test_database_rejects_expires_at_less_than_or_equal_to_created_at(self):
        token = TelegramLinkToken.objects.create(
            user=self.user,
            token_digest=self.digest,
            expires_at=timezone.now() + timedelta(minutes=10),
        )

        for invalid_expires_at in (
            token.created_at,
            token.created_at - timedelta(seconds=1),
        ):
            with self.subTest(expires_at=invalid_expires_at):
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        TelegramLinkToken.objects.filter(pk=token.pk).update(
                            expires_at=invalid_expires_at,
                        )

    def test_database_rejects_used_at_before_created_at(self):
        token = TelegramLinkToken.objects.create(
            user=self.user,
            token_digest=self.digest,
            expires_at=timezone.now() + timedelta(minutes=10),
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                TelegramLinkToken.objects.filter(pk=token.pk).update(
                    used_at=token.created_at - timedelta(seconds=1),
                )

    def test_database_rejects_used_at_after_expires_at(self):
        token = TelegramLinkToken.objects.create(
            user=self.user,
            token_digest=self.digest,
            expires_at=timezone.now() + timedelta(minutes=10),
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                TelegramLinkToken.objects.filter(pk=token.pk).update(
                    used_at=token.expires_at + timedelta(seconds=1),
                )

    def test_database_accepts_used_at_within_created_at_and_expires_at_bounds(self):
        token = TelegramLinkToken.objects.create(
            user=self.user,
            token_digest=self.digest,
            expires_at=timezone.now() + timedelta(minutes=10),
        )

        for valid_used_at in (
            token.created_at,
            token.created_at + timedelta(minutes=5),
            token.expires_at,
        ):
            with self.subTest(used_at=valid_used_at):
                TelegramLinkToken.objects.filter(pk=token.pk).update(
                    used_at=valid_used_at,
                )
                token.refresh_from_db()
                self.assertEqual(token.used_at, valid_used_at)
                self.assertTrue(token.is_used)


class TelegramUpdateModelTests(TestCase):
    def test_create_valid_telegram_update_with_defaults(self):
        update = TelegramUpdate.objects.create(
            update_id=100001,
            update_type=TelegramUpdateType.MESSAGE,
        )

        self.assertIsInstance(update.id, uuid.UUID)
        self.assertEqual(update.update_id, 100001)
        self.assertEqual(update.update_type, TelegramUpdateType.MESSAGE)
        self.assertEqual(update.status, TelegramUpdateStatus.RECEIVED)
        self.assertEqual(update.error_code, "")
        self.assertIsNotNone(update.received_at)
        self.assertIsNone(update.processed_at)
        update.full_clean()

    def test_create_completed_and_failed_updates_with_processed_at(self):
        processed_at = timezone.now()
        completed_update = TelegramUpdate.objects.create(
            update_id=100002,
            update_type=TelegramUpdateType.CALLBACK_QUERY,
            status=TelegramUpdateStatus.COMPLETED,
            processed_at=processed_at,
        )
        failed_update = TelegramUpdate.objects.create(
            update_id=100003,
            update_type=TelegramUpdateType.UNSUPPORTED,
            status=TelegramUpdateStatus.FAILED,
            error_code="unsupported_update_type",
            processed_at=processed_at,
        )

        completed_update.full_clean()
        failed_update.full_clean()
        self.assertEqual(completed_update.processed_at, processed_at)
        self.assertEqual(failed_update.error_code, "unsupported_update_type")

    def test_str_returns_update_id_and_status_display(self):
        update = TelegramUpdate.objects.create(
            update_id=555555,
            update_type=TelegramUpdateType.MESSAGE,
        )

        self.assertEqual(
            str(update),
            "Telegram update 555555 (Received)",
        )

    def test_update_id_must_be_unique(self):
        TelegramUpdate.objects.create(
            update_id=777777,
            update_type=TelegramUpdateType.MESSAGE,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                TelegramUpdate.objects.create(
                    update_id=777777,
                    update_type=TelegramUpdateType.CALLBACK_QUERY,
                )

    def test_full_clean_and_database_reject_non_positive_update_id(self):
        for invalid_update_id in (0, -1, -999999):
            with self.subTest(update_id=invalid_update_id):
                update = TelegramUpdate(
                    update_id=invalid_update_id,
                    update_type=TelegramUpdateType.MESSAGE,
                )
                with self.assertRaises(ValidationError) as ctx:
                    update.full_clean()
                self.assertIn("update_id", ctx.exception.error_dict)

                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        TelegramUpdate.objects.create(
                            update_id=invalid_update_id,
                            update_type=TelegramUpdateType.MESSAGE,
                        )

    def test_full_clean_and_database_reject_invalid_update_type_and_status(
        self,
    ):
        for field, invalid_value in (
            ("update_type", "INVALID_TYPE"),
            ("status", "INVALID_STATUS"),
        ):
            with self.subTest(field=field):
                kwargs = {
                    "update_id": 888888,
                    "update_type": TelegramUpdateType.MESSAGE,
                    "status": TelegramUpdateStatus.RECEIVED,
                    field: invalid_value,
                }
                update = TelegramUpdate(**kwargs)
                with self.assertRaises(ValidationError) as ctx:
                    update.full_clean()
                self.assertIn(field, ctx.exception.error_dict)

                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        TelegramUpdate.objects.create(**kwargs)

    def test_full_clean_rejects_inconsistent_status_and_processed_at(self):
        now = timezone.now()
        inconsistent_cases = (
            (TelegramUpdateStatus.RECEIVED, now),
            (TelegramUpdateStatus.PROCESSING, now),
            (TelegramUpdateStatus.COMPLETED, None),
            (TelegramUpdateStatus.FAILED, None),
        )

        for status, processed_at in inconsistent_cases:
            with self.subTest(status=status, processed_at=processed_at):
                update = TelegramUpdate(
                    update_id=900001,
                    update_type=TelegramUpdateType.MESSAGE,
                    status=status,
                    processed_at=processed_at,
                )
                with self.assertRaises(ValidationError):
                    update.full_clean()

    def test_database_rejects_received_or_processing_with_processed_at(self):
        for idx, status in enumerate(
            (TelegramUpdateStatus.RECEIVED, TelegramUpdateStatus.PROCESSING),
            start=1,
        ):
            with self.subTest(status=status):
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        TelegramUpdate.objects.create(
                            update_id=910000 + idx,
                            update_type=TelegramUpdateType.MESSAGE,
                            status=status,
                            processed_at=timezone.now(),
                        )

    def test_database_rejects_completed_or_failed_without_processed_at(self):
        for idx, status in enumerate(
            (TelegramUpdateStatus.COMPLETED, TelegramUpdateStatus.FAILED),
            start=1,
        ):
            with self.subTest(status=status):
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        TelegramUpdate.objects.create(
                            update_id=920000 + idx,
                            update_type=TelegramUpdateType.MESSAGE,
                            status=status,
                            processed_at=None,
                        )

    def test_database_rejects_error_code_on_non_failed_status(self):
        now = timezone.now()
        non_failed_cases = (
            (TelegramUpdateStatus.RECEIVED, None),
            (TelegramUpdateStatus.PROCESSING, None),
            (TelegramUpdateStatus.COMPLETED, now),
        )

        for idx, (status, processed_at) in enumerate(
            non_failed_cases,
            start=1,
        ):
            with self.subTest(status=status):
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        TelegramUpdate.objects.create(
                            update_id=930000 + idx,
                            update_type=TelegramUpdateType.MESSAGE,
                            status=status,
                            error_code="unexpected_error_code",
                            processed_at=processed_at,
                        )
