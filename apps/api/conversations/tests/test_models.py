import uuid

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from ..models import (
    Conversation,
    ConversationChannel,
    ConversationStatus,
    Message,
    MessageDirection,
    MessageStatus,
    MessageType,
)


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


class MessageModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user_model = get_user_model()
        cls.user = cls.user_model.objects.create_user(
            email="user@example.com",
            password="StrongPassword!123",
        )
        cls.conversation = Conversation.objects.create(
            user=cls.user,
            channel=ConversationChannel.TELEGRAM,
        )

    def test_create_valid_message_with_defaults(self):
        message = Message.objects.create(
            conversation=self.conversation,
            direction=MessageDirection.INBOUND,
            message_type=MessageType.TEXT,
            content="Spent 45 BRL on lunch",
        )

        self.assertIsInstance(message.id, uuid.UUID)
        self.assertEqual(message.conversation, self.conversation)
        self.assertEqual(message.direction, MessageDirection.INBOUND)
        self.assertEqual(message.message_type, MessageType.TEXT)
        self.assertEqual(message.status, MessageStatus.RECEIVED)
        self.assertEqual(message.content, "Spent 45 BRL on lunch")
        self.assertIsNone(message.processed_at)
        self.assertIsNotNone(message.created_at)
        self.assertIsNotNone(message.updated_at)

    def test_voice_message_allows_empty_content(self):
        message = Message.objects.create(
            conversation=self.conversation,
            direction=MessageDirection.INBOUND,
            message_type=MessageType.VOICE,
        )

        self.assertEqual(message.content, "")
        self.assertIsNone(message.processed_at)
        message.full_clean()

    def test_create_completed_message_with_processed_at(self):
        processed_at = timezone.now()
        message = Message.objects.create(
            conversation=self.conversation,
            direction=MessageDirection.OUTBOUND,
            message_type=MessageType.SYSTEM,
            status=MessageStatus.COMPLETED,
            content="Draft created.",
            processed_at=processed_at,
        )

        self.assertEqual(message.status, MessageStatus.COMPLETED)
        self.assertEqual(message.processed_at, processed_at)
        message.full_clean()

    def test_create_failed_message_with_processed_at(self):
        processed_at = timezone.now()
        message = Message.objects.create(
            conversation=self.conversation,
            direction=MessageDirection.INBOUND,
            message_type=MessageType.VOICE,
            status=MessageStatus.FAILED,
            processed_at=processed_at,
        )

        self.assertEqual(message.status, MessageStatus.FAILED)
        self.assertEqual(message.processed_at, processed_at)
        message.full_clean()

    def test_conversation_messages_reverse_relationship(self):
        message = Message.objects.create(
            conversation=self.conversation,
            direction=MessageDirection.INBOUND,
            message_type=MessageType.TEXT,
            content="Coffee 12 BRL",
        )

        self.assertIn(message, self.conversation.messages.all())

    def test_deleting_conversation_cascades_to_messages(self):
        conversation = Conversation.objects.create(
            user=self.user,
            channel=ConversationChannel.TELEGRAM,
        )
        message = Message.objects.create(
            conversation=conversation,
            direction=MessageDirection.INBOUND,
            message_type=MessageType.TEXT,
            content="Temporary message",
        )

        conversation.delete()

        self.assertFalse(Message.objects.filter(id=message.id).exists())

    def test_str_returns_useful_representation(self):
        message = Message.objects.create(
            conversation=self.conversation,
            direction=MessageDirection.INBOUND,
            message_type=MessageType.VOICE,
        )

        self.assertEqual(str(message), "Inbound Voice (Received)")

    def test_full_clean_rejects_invalid_choices(self):
        for field, value in (
            ("direction", "INVALID"),
            ("message_type", "INVALID"),
            ("status", "INVALID"),
        ):
            with self.subTest(field=field):
                kwargs = {
                    "conversation": self.conversation,
                    "direction": MessageDirection.INBOUND,
                    "message_type": MessageType.TEXT,
                    "content": "Test",
                    field: value,
                }
                message = Message(**kwargs)
                with self.assertRaises(ValidationError) as ctx:
                    message.full_clean()
                self.assertIn(field, ctx.exception.error_dict)

    def test_database_rejects_invalid_direction(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Message.objects.create(
                    conversation=self.conversation,
                    direction="INVALID",
                    message_type=MessageType.TEXT,
                )

    def test_database_rejects_invalid_message_type(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Message.objects.create(
                    conversation=self.conversation,
                    direction=MessageDirection.INBOUND,
                    message_type="INVALID",
                )

    def test_database_rejects_invalid_status(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Message.objects.create(
                    conversation=self.conversation,
                    direction=MessageDirection.INBOUND,
                    message_type=MessageType.TEXT,
                    status="INVALID",
                )

    def test_full_clean_rejects_inconsistent_status_and_processed_at(self):
        now = timezone.now()
        inconsistent_cases = (
            (MessageStatus.RECEIVED, now),
            (MessageStatus.PROCESSING, now),
            (MessageStatus.COMPLETED, None),
            (MessageStatus.FAILED, None),
        )

        for status, processed_at in inconsistent_cases:
            with self.subTest(status=status, processed_at=processed_at):
                message = Message(
                    conversation=self.conversation,
                    direction=MessageDirection.INBOUND,
                    message_type=MessageType.TEXT,
                    status=status,
                    processed_at=processed_at,
                )
                with self.assertRaises(ValidationError):
                    message.full_clean()

    def test_database_rejects_received_or_processing_with_processed_at(self):
        for status in (MessageStatus.RECEIVED, MessageStatus.PROCESSING):
            with self.subTest(status=status):
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        Message.objects.create(
                            conversation=self.conversation,
                            direction=MessageDirection.INBOUND,
                            message_type=MessageType.TEXT,
                            status=status,
                            processed_at=timezone.now(),
                        )

    def test_database_rejects_completed_or_failed_without_processed_at(self):
        for status in (MessageStatus.COMPLETED, MessageStatus.FAILED):
            with self.subTest(status=status):
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        Message.objects.create(
                            conversation=self.conversation,
                            direction=MessageDirection.INBOUND,
                            message_type=MessageType.TEXT,
                            status=status,
                            processed_at=None,
                        )
