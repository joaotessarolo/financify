from datetime import timedelta
from decimal import Decimal
import uuid

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import RestrictedError
from django.test import TestCase
from django.utils import timezone

from common.money import Currency
from ledger.models import Account, AccountType, EntrySide

from ..models import (
    Conversation,
    ConversationChannel,
    ConversationStatus,
    DraftEntry,
    Message,
    MessageDirection,
    MessageStatus,
    MessageType,
    TransactionDraft,
    TransactionDraftStatus,
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


class TransactionDraftModelTests(TestCase):
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
        cls.source_message = Message.objects.create(
            conversation=cls.conversation,
            direction=MessageDirection.INBOUND,
            message_type=MessageType.TEXT,
            content="Lunch 45 BRL",
        )
        cls.occurred_at = timezone.now()
        cls.expires_at = cls.occurred_at + timedelta(hours=24)

    def test_create_valid_pending_transaction_draft_with_defaults(self):
        draft = TransactionDraft.objects.create(
            user=self.user,
            source_message=self.source_message,
            description="Lunch at restaurant",
            currency=Currency.BRL,
            occurred_at=self.occurred_at,
            expires_at=self.expires_at,
        )

        self.assertIsInstance(draft.id, uuid.UUID)
        self.assertEqual(draft.user, self.user)
        self.assertEqual(draft.source_message, self.source_message)
        self.assertEqual(draft.description, "Lunch at restaurant")
        self.assertEqual(draft.currency, Currency.BRL)
        self.assertEqual(draft.occurred_at, self.occurred_at)
        self.assertEqual(draft.status, TransactionDraftStatus.PENDING)
        self.assertEqual(draft.expires_at, self.expires_at)
        self.assertIsNone(draft.resolved_at)
        self.assertIsNotNone(draft.created_at)
        self.assertIsNotNone(draft.updated_at)
        draft.full_clean()

    def test_reverse_relationships_on_user_and_source_message(self):
        draft = TransactionDraft.objects.create(
            user=self.user,
            source_message=self.source_message,
            description="Coffee",
            currency=Currency.BRL,
            occurred_at=self.occurred_at,
            expires_at=self.expires_at,
        )

        self.assertIn(draft, self.user.transaction_drafts.all())
        self.assertIn(draft, self.source_message.transaction_drafts.all())

    def test_deleting_source_message_with_draft_raises_restricted_error(self):
        restricted_message = Message.objects.create(
            conversation=self.conversation,
            direction=MessageDirection.INBOUND,
            message_type=MessageType.TEXT,
            content="Restricted message",
        )
        TransactionDraft.objects.create(
            user=self.user,
            source_message=restricted_message,
            description="Restricted draft",
            currency=Currency.BRL,
            occurred_at=self.occurred_at,
            expires_at=self.expires_at,
        )

        with self.assertRaises(RestrictedError):
            restricted_message.delete()

    def test_deleting_user_cascades_to_conversation_message_and_draft(self):
        cascade_user = self.user_model.objects.create_user(
            email="cascade@example.com",
            password="StrongPassword!123",
        )
        conversation = Conversation.objects.create(
            user=cascade_user,
            channel=ConversationChannel.TELEGRAM,
        )
        message = Message.objects.create(
            conversation=conversation,
            direction=MessageDirection.INBOUND,
            message_type=MessageType.TEXT,
            content="Dinner 80 BRL",
        )
        draft = TransactionDraft.objects.create(
            user=cascade_user,
            source_message=message,
            description="Dinner",
            currency=Currency.BRL,
            occurred_at=self.occurred_at,
            expires_at=self.expires_at,
        )

        cascade_user.delete()

        self.assertFalse(
            Conversation.objects.filter(id=conversation.id).exists()
        )
        self.assertFalse(Message.objects.filter(id=message.id).exists())
        self.assertFalse(TransactionDraft.objects.filter(id=draft.id).exists())

    def test_str_returns_useful_representation(self):
        draft = TransactionDraft.objects.create(
            user=self.user,
            source_message=self.source_message,
            description="Lunch at restaurant",
            currency=Currency.BRL,
            occurred_at=self.occurred_at,
            expires_at=self.expires_at,
        )

        self.assertEqual(str(draft), "Lunch at restaurant (Pending)")

    def test_terminal_statuses_with_resolved_at_are_valid(self):
        resolved_at = timezone.now()
        terminal_statuses = (
            TransactionDraftStatus.CONFIRMED,
            TransactionDraftStatus.REJECTED,
            TransactionDraftStatus.EXPIRED,
        )

        for status in terminal_statuses:
            with self.subTest(status=status):
                draft = TransactionDraft.objects.create(
                    user=self.user,
                    source_message=self.source_message,
                    description=f"Draft {status}",
                    currency=Currency.USD,
                    occurred_at=self.occurred_at,
                    status=status,
                    expires_at=self.expires_at,
                    resolved_at=resolved_at,
                )
                draft.full_clean()
                self.assertEqual(draft.status, status)
                self.assertEqual(draft.currency, Currency.USD)
                self.assertEqual(draft.resolved_at, resolved_at)

    def test_full_clean_rejects_invalid_currency_and_status(self):
        for field, value in (
            ("currency", "XYZ"),
            ("status", "INVALID"),
        ):
            with self.subTest(field=field):
                kwargs = {
                    "user": self.user,
                    "source_message": self.source_message,
                    "description": "Invalid draft",
                    "currency": Currency.BRL,
                    "occurred_at": self.occurred_at,
                    "expires_at": self.expires_at,
                    field: value,
                }
                draft = TransactionDraft(**kwargs)
                with self.assertRaises(ValidationError) as ctx:
                    draft.full_clean()
                self.assertIn(field, ctx.exception.error_dict)

    def test_database_rejects_invalid_currency(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                TransactionDraft.objects.create(
                    user=self.user,
                    source_message=self.source_message,
                    description="Invalid Currency",
                    currency="XYZ",
                    occurred_at=self.occurred_at,
                    expires_at=self.expires_at,
                )

    def test_database_rejects_invalid_status(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                TransactionDraft.objects.create(
                    user=self.user,
                    source_message=self.source_message,
                    description="Invalid Status",
                    currency=Currency.BRL,
                    occurred_at=self.occurred_at,
                    status="INVALID",
                    expires_at=self.expires_at,
                )

    def test_full_clean_rejects_inconsistent_status_and_resolved_at(self):
        now = timezone.now()
        inconsistent_cases = (
            (TransactionDraftStatus.PENDING, now),
            (TransactionDraftStatus.CONFIRMED, None),
            (TransactionDraftStatus.REJECTED, None),
            (TransactionDraftStatus.EXPIRED, None),
        )

        for status, resolved_at in inconsistent_cases:
            with self.subTest(status=status, resolved_at=resolved_at):
                draft = TransactionDraft(
                    user=self.user,
                    source_message=self.source_message,
                    description="Inconsistent Draft",
                    currency=Currency.BRL,
                    occurred_at=self.occurred_at,
                    status=status,
                    expires_at=self.expires_at,
                    resolved_at=resolved_at,
                )
                with self.assertRaises(ValidationError):
                    draft.full_clean()

    def test_database_rejects_pending_with_resolved_at(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                TransactionDraft.objects.create(
                    user=self.user,
                    source_message=self.source_message,
                    description="Inconsistent Pending",
                    currency=Currency.BRL,
                    occurred_at=self.occurred_at,
                    status=TransactionDraftStatus.PENDING,
                    expires_at=self.expires_at,
                    resolved_at=timezone.now(),
                )

    def test_database_rejects_terminal_status_without_resolved_at(self):
        for status in (
            TransactionDraftStatus.CONFIRMED,
            TransactionDraftStatus.REJECTED,
            TransactionDraftStatus.EXPIRED,
        ):
            with self.subTest(status=status):
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        TransactionDraft.objects.create(
                            user=self.user,
                            source_message=self.source_message,
                            description="Inconsistent Terminal",
                            currency=Currency.BRL,
                            occurred_at=self.occurred_at,
                            status=status,
                            expires_at=self.expires_at,
                            resolved_at=None,
                        )


class DraftEntryModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user_model = get_user_model()
        cls.user = cls.user_model.objects.create_user(
            email="user@example.com",
            password="StrongPassword!123",
        )
        cls.account = Account.objects.create(
            user=cls.user,
            name="Groceries",
            account_type=AccountType.EXPENSE,
            currency=Currency.BRL,
        )
        cls.conversation = Conversation.objects.create(
            user=cls.user,
            channel=ConversationChannel.TELEGRAM,
        )
        cls.source_message = Message.objects.create(
            conversation=cls.conversation,
            direction=MessageDirection.INBOUND,
            message_type=MessageType.TEXT,
            content="Groceries 45.00 BRL",
        )
        cls.occurred_at = timezone.now()
        cls.expires_at = cls.occurred_at + timedelta(hours=24)
        cls.draft = TransactionDraft.objects.create(
            user=cls.user,
            source_message=cls.source_message,
            description="Groceries purchase",
            currency=Currency.BRL,
            occurred_at=cls.occurred_at,
            expires_at=cls.expires_at,
        )

    def test_create_valid_draft_entry(self):
        draft_entry = DraftEntry.objects.create(
            draft=self.draft,
            account=self.account,
            side=EntrySide.DEBIT,
            amount=Decimal("45.75"),
            memo="Supermarket",
        )

        self.assertIsInstance(draft_entry.id, uuid.UUID)
        self.assertEqual(draft_entry.draft, self.draft)
        self.assertEqual(draft_entry.account, self.account)
        self.assertEqual(draft_entry.side, EntrySide.DEBIT)
        self.assertEqual(draft_entry.amount, Decimal("45.75"))
        self.assertEqual(draft_entry.memo, "Supermarket")
        self.assertIsNotNone(draft_entry.created_at)
        self.assertIsNotNone(draft_entry.updated_at)
        draft_entry.full_clean()

    def test_draft_entry_memo_defaults_to_empty_string(self):
        draft_entry = DraftEntry.objects.create(
            draft=self.draft,
            account=self.account,
            side=EntrySide.DEBIT,
            amount=Decimal("45.00"),
        )

        self.assertEqual(draft_entry.memo, "")

    def test_reverse_relationships_on_draft_and_account(self):
        draft_entry = DraftEntry.objects.create(
            draft=self.draft,
            account=self.account,
            side=EntrySide.DEBIT,
            amount=Decimal("45.00"),
        )

        self.assertIn(draft_entry, self.draft.entries.all())
        self.assertIn(draft_entry, self.account.draft_entries.all())

    def test_str_returns_useful_representation(self):
        draft_entry = DraftEntry.objects.create(
            draft=self.draft,
            account=self.account,
            side=EntrySide.DEBIT,
            amount=Decimal("45.00"),
        )

        self.assertEqual(str(draft_entry), "Debit 45.00 (Groceries)")

    def test_deleting_draft_cascades_to_draft_entries(self):
        draft = TransactionDraft.objects.create(
            user=self.user,
            source_message=self.source_message,
            description="Temporary draft",
            currency=Currency.BRL,
            occurred_at=self.occurred_at,
            expires_at=self.expires_at,
        )
        draft_entry = DraftEntry.objects.create(
            draft=draft,
            account=self.account,
            side=EntrySide.DEBIT,
            amount=Decimal("30.00"),
        )

        draft.delete()

        self.assertFalse(DraftEntry.objects.filter(id=draft_entry.id).exists())

    def test_deleting_account_with_draft_entry_raises_restricted_error(self):
        restricted_account = Account.objects.create(
            user=self.user,
            name="Restricted Account",
            account_type=AccountType.ASSET,
            currency=Currency.BRL,
        )
        DraftEntry.objects.create(
            draft=self.draft,
            account=restricted_account,
            side=EntrySide.CREDIT,
            amount=Decimal("45.00"),
        )

        with self.assertRaises(RestrictedError):
            restricted_account.delete()

    def test_deleting_user_cascades_to_drafts_and_draft_entries(self):
        cascade_user = self.user_model.objects.create_user(
            email="cascade-draft-entry@example.com",
            password="StrongPassword!123",
        )
        account = Account.objects.create(
            user=cascade_user,
            name="Checking",
            account_type=AccountType.ASSET,
            currency=Currency.BRL,
        )
        conversation = Conversation.objects.create(
            user=cascade_user,
            channel=ConversationChannel.TELEGRAM,
        )
        message = Message.objects.create(
            conversation=conversation,
            direction=MessageDirection.INBOUND,
            message_type=MessageType.TEXT,
            content="Lunch 35 BRL",
        )
        draft = TransactionDraft.objects.create(
            user=cascade_user,
            source_message=message,
            description="Lunch",
            currency=Currency.BRL,
            occurred_at=self.occurred_at,
            expires_at=self.expires_at,
        )
        draft_entry = DraftEntry.objects.create(
            draft=draft,
            account=account,
            side=EntrySide.CREDIT,
            amount=Decimal("35.00"),
        )

        cascade_user.delete()

        self.assertFalse(Account.objects.filter(id=account.id).exists())
        self.assertFalse(TransactionDraft.objects.filter(id=draft.id).exists())
        self.assertFalse(DraftEntry.objects.filter(id=draft_entry.id).exists())

    def test_full_clean_rejects_invalid_side(self):
        draft_entry = DraftEntry(
            draft=self.draft,
            account=self.account,
            side="INVALID",
            amount=Decimal("10.00"),
        )

        with self.assertRaises(ValidationError) as ctx:
            draft_entry.full_clean()

        self.assertIn("side", ctx.exception.error_dict)

    def test_full_clean_rejects_zero_or_negative_amount(self):
        for invalid_amount in (Decimal("0.00"), Decimal("-10.00")):
            with self.subTest(amount=invalid_amount):
                draft_entry = DraftEntry(
                    draft=self.draft,
                    account=self.account,
                    side=EntrySide.DEBIT,
                    amount=invalid_amount,
                )
                with self.assertRaises(ValidationError) as ctx:
                    draft_entry.full_clean()
                self.assertIn("amount", ctx.exception.error_dict)

    def test_database_rejects_invalid_side(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                DraftEntry.objects.create(
                    draft=self.draft,
                    account=self.account,
                    side="INVALID",
                    amount=Decimal("10.00"),
                )

    def test_database_rejects_zero_amount(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                DraftEntry.objects.create(
                    draft=self.draft,
                    account=self.account,
                    side=EntrySide.DEBIT,
                    amount=Decimal("0.00"),
                )

    def test_database_rejects_negative_amount(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                DraftEntry.objects.create(
                    draft=self.draft,
                    account=self.account,
                    side=EntrySide.DEBIT,
                    amount=Decimal("-10.00"),
                )
