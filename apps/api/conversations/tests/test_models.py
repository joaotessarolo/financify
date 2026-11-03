import uuid

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from ..models import Conversation, ConversationChannel, ConversationStatus


class ConversationModelTests(TestCase):
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

    def test_create_valid_conversation(self):
        conversation = Conversation.objects.create(
            user=self.user,
            channel=ConversationChannel.TELEGRAM,
        )

        self.assertEqual(conversation.user, self.user)
        self.assertEqual(conversation.channel, ConversationChannel.TELEGRAM)
        self.assertIsNotNone(conversation.created_at)
        self.assertIsNotNone(conversation.updated_at)

    def test_conversation_id_is_uuid(self):
        conversation = Conversation.objects.create(
            user=self.user,
            channel=ConversationChannel.TELEGRAM,
        )

        self.assertIsInstance(conversation.id, uuid.UUID)

    def test_conversation_status_defaults_to_active(self):
        conversation = Conversation.objects.create(
            user=self.user,
            channel=ConversationChannel.TELEGRAM,
        )

        self.assertEqual(conversation.status, ConversationStatus.ACTIVE)

    def test_user_conversations_reverse_relationship(self):
        conversation = Conversation.objects.create(
            user=self.user,
            channel=ConversationChannel.TELEGRAM,
        )

        self.assertIn(conversation, self.user.conversations.all())

    def test_str_returns_useful_representation(self):
        conversation = Conversation.objects.create(
            user=self.user,
            channel=ConversationChannel.TELEGRAM,
        )

        self.assertEqual(
            str(conversation),
            "user@example.com - Telegram (Active)",
        )

    def test_full_clean_rejects_invalid_channel(self):
        conversation = Conversation(
            user=self.user,
            channel="INVALID_CHANNEL",
        )

        with self.assertRaises(ValidationError) as ctx:
            conversation.full_clean()

        self.assertIn("channel", ctx.exception.error_dict)

    def test_full_clean_rejects_invalid_status(self):
        conversation = Conversation(
            user=self.user,
            channel=ConversationChannel.TELEGRAM,
            status="INVALID_STATUS",
        )

        with self.assertRaises(ValidationError) as ctx:
            conversation.full_clean()

        self.assertIn("status", ctx.exception.error_dict)

    def test_database_rejects_invalid_channel(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Conversation.objects.create(
                    user=self.user,
                    channel="INVALID",
                )

    def test_database_rejects_invalid_status(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Conversation.objects.create(
                    user=self.user,
                    channel=ConversationChannel.TELEGRAM,
                    status="INVALID",
                )

    def test_different_users_have_independent_conversations(self):
        user_conversation = Conversation.objects.create(
            user=self.user,
            channel=ConversationChannel.TELEGRAM,
        )
        other_user_conversation = Conversation.objects.create(
            user=self.other_user,
            channel=ConversationChannel.TELEGRAM,
            status=ConversationStatus.ARCHIVED,
        )

        self.assertNotEqual(user_conversation.id, other_user_conversation.id)
        self.assertEqual(
            list(self.user.conversations.all()),
            [user_conversation],
        )
        self.assertEqual(
            list(self.other_user.conversations.all()),
            [other_user_conversation],
        )
