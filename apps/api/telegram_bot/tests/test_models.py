import uuid

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from ..models import TelegramIdentity


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
