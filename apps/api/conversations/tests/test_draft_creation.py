from datetime import UTC, datetime, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase, override_settings
from django.utils import timezone

from common.money import Currency
from ledger.models import AccountSystemRole, EntrySide, Transaction
from ledger.services import ensure_default_accounts

from ..extraction import TransactionKind, extract_transaction_from_text
from ..models import (
    Conversation,
    ConversationChannel,
    Message,
    MessageDirection,
    MessageStatus,
    MessageType,
    TransactionDraft,
    TransactionDraftStatus,
)
from ..services import (
    DefaultAccountConfigurationError,
    create_transaction_draft_from_extraction,
)


@override_settings(TRANSACTION_DRAFT_TTL_SECONDS=3600)
class CreateTransactionDraftFromExtractionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            email="draft@example.com",
            password="StrongPassword!123",
            currency=Currency.BRL,
        )
        ensure_default_accounts(user=cls.user)
        cls.conversation = Conversation.objects.create(
            user=cls.user,
            channel=ConversationChannel.TELEGRAM,
        )

    def _message(self, content: str) -> Message:
        return Message.objects.create(
            conversation=self.conversation,
            direction=MessageDirection.INBOUND,
            message_type=MessageType.TEXT,
            status=MessageStatus.COMPLETED,
            content=content,
            processed_at=timezone.now(),
        )

    def test_expense_creates_balanced_pending_draft(self):
        source = self._message("gastei 35,90 no almoço")
        extraction = extract_transaction_from_text(source.content)
        occurred_at = datetime(2026, 11, 4, 12, 30, tzinfo=UTC)
        before = timezone.now()

        draft = create_transaction_draft_from_extraction(
            source_message=source,
            extraction=extraction,
            occurred_at=occurred_at,
        )

        self.assertEqual(draft.user, self.user)
        self.assertEqual(draft.source_message, source)
        self.assertEqual(draft.description, "no almoço")
        self.assertEqual(draft.currency, Currency.BRL)
        self.assertEqual(draft.occurred_at, occurred_at)
        self.assertEqual(draft.status, TransactionDraftStatus.PENDING)
        self.assertGreaterEqual(draft.expires_at, before + timedelta(hours=1))
        self.assertLessEqual(draft.expires_at, timezone.now() + timedelta(hours=1))
        self.assertIsNone(draft.transaction)

        entries = {entry.side: entry for entry in draft.entries.all()}
        self.assertEqual(entries[EntrySide.DEBIT].amount, Decimal("35.90"))
        self.assertEqual(
            entries[EntrySide.DEBIT].account.system_role,
            AccountSystemRole.GENERAL_EXPENSE,
        )
        self.assertEqual(entries[EntrySide.CREDIT].amount, Decimal("35.90"))
        self.assertEqual(
            entries[EntrySide.CREDIT].account.system_role,
            AccountSystemRole.PRIMARY,
        )
        self.assertEqual(Transaction.objects.count(), 0)

    def test_income_uses_primary_and_general_income_accounts(self):
        source = self._message("ganho de 2500")
        extraction = extract_transaction_from_text(source.content)

        draft = create_transaction_draft_from_extraction(
            source_message=source,
            extraction=extraction,
            occurred_at=timezone.now(),
        )

        self.assertEqual(extraction.kind, TransactionKind.INCOME)
        entries = {entry.side: entry for entry in draft.entries.all()}
        self.assertEqual(
            entries[EntrySide.DEBIT].account.system_role,
            AccountSystemRole.PRIMARY,
        )
        self.assertEqual(
            entries[EntrySide.CREDIT].account.system_role,
            AccountSystemRole.GENERAL_INCOME,
        )

    def test_missing_or_inactive_default_account_rolls_back_draft(self):
        self.user.accounts.filter(
            system_role=AccountSystemRole.GENERAL_EXPENSE
        ).update(is_active=False)
        source = self._message("gasto 10 café")

        with self.assertRaises(DefaultAccountConfigurationError):
            create_transaction_draft_from_extraction(
                source_message=source,
                extraction=extract_transaction_from_text(source.content),
                occurred_at=timezone.now(),
            )

        self.assertEqual(TransactionDraft.objects.count(), 0)

    @override_settings(TRANSACTION_DRAFT_TTL_SECONDS=0)
    def test_invalid_ttl_does_not_create_draft(self):
        source = self._message("receita 100 bônus")

        with self.assertRaisesMessage(
            ImproperlyConfigured,
            "TRANSACTION_DRAFT_TTL_SECONDS must be greater than zero.",
        ):
            create_transaction_draft_from_extraction(
                source_message=source,
                extraction=extract_transaction_from_text(source.content),
                occurred_at=timezone.now(),
            )

        self.assertEqual(TransactionDraft.objects.count(), 0)
