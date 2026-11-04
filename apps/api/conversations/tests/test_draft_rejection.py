from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from common.money import Currency

from ..models import (
    Conversation,
    ConversationChannel,
    Message,
    MessageDirection,
    MessageType,
    TransactionDraft,
    TransactionDraftStatus,
)
from ..services import DraftRejectionError, reject_transaction_draft


class RejectTransactionDraftTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            email="reject@example.com",
            password="StrongPassword!123",
        )
        cls.conversation = Conversation.objects.create(
            user=cls.user,
            channel=ConversationChannel.TELEGRAM,
        )
        cls.message = Message.objects.create(
            conversation=cls.conversation,
            direction=MessageDirection.INBOUND,
            message_type=MessageType.TEXT,
            content="gasto 10 café",
        )

    def _draft(self, *, expires_at=None):
        return TransactionDraft.objects.create(
            user=self.user,
            source_message=self.message,
            description="café",
            currency=Currency.BRL,
            occurred_at=timezone.now(),
            expires_at=expires_at or timezone.now() + timedelta(hours=1),
        )

    def test_rejects_pending_draft(self):
        draft = self._draft()

        rejected = reject_transaction_draft(draft=draft)

        self.assertEqual(rejected.status, TransactionDraftStatus.REJECTED)
        self.assertIsNotNone(rejected.resolved_at)
        self.assertIsNone(rejected.transaction)

    def test_second_rejection_is_idempotent(self):
        draft = self._draft()
        first = reject_transaction_draft(draft=draft)

        second = reject_transaction_draft(draft=draft)

        self.assertEqual(second.id, first.id)
        self.assertEqual(second.resolved_at, first.resolved_at)

    def test_expired_draft_is_marked_expired_and_rejected(self):
        draft = self._draft(expires_at=timezone.now() - timedelta(seconds=1))

        with self.assertRaises(DraftRejectionError):
            reject_transaction_draft(draft=draft)

        draft.refresh_from_db()
        self.assertEqual(draft.status, TransactionDraftStatus.EXPIRED)
        self.assertIsNotNone(draft.resolved_at)

    def test_non_pending_draft_cannot_be_rejected(self):
        draft = self._draft()
        TransactionDraft.objects.filter(pk=draft.pk).update(
            status=TransactionDraftStatus.EXPIRED,
            resolved_at=timezone.now(),
        )

        with self.assertRaises(DraftRejectionError):
            reject_transaction_draft(draft=draft)
