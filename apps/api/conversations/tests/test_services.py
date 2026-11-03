from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from common.money import Currency
from ledger.models import (
    Account,
    AccountType,
    Entry,
    EntrySide,
    Transaction,
    TransactionSource,
    TransactionStatus,
)

from ..models import (
    Conversation,
    ConversationChannel,
    DraftEntry,
    Message,
    MessageDirection,
    MessageType,
    TransactionDraft,
    TransactionDraftStatus,
)
from ..services import (
    DraftConfirmationError,
    DraftExpiredError,
    confirm_transaction_draft,
)


class ConfirmTransactionDraftServiceTests(TestCase):
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
        cls.checking_account = Account.objects.create(
            user=cls.user,
            name="Nubank Checking",
            account_type=AccountType.ASSET,
            currency=Currency.BRL,
        )
        cls.groceries_account = Account.objects.create(
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
            content="Groceries 120.50 BRL",
        )

    def _create_draft(self, **kwargs) -> TransactionDraft:
        now = timezone.now()
        defaults = {
            "user": self.user,
            "source_message": self.source_message,
            "description": "Supermarket purchase",
            "currency": Currency.BRL,
            "occurred_at": now - timedelta(minutes=10),
            "expires_at": now + timedelta(hours=24),
        }
        defaults.update(kwargs)
        return TransactionDraft.objects.create(**defaults)

    def _add_balanced_draft_entries(
        self,
        draft: TransactionDraft,
        amount: Decimal = Decimal("120.50"),
    ) -> tuple[DraftEntry, DraftEntry]:
        debit_entry = DraftEntry.objects.create(
            draft=draft,
            account=self.groceries_account,
            side=EntrySide.DEBIT,
            amount=amount,
            memo="Food items",
        )
        credit_entry = DraftEntry.objects.create(
            draft=draft,
            account=self.checking_account,
            side=EntrySide.CREDIT,
            amount=amount,
            memo="Debit card payment",
        )
        return debit_entry, credit_entry

    def test_confirms_balanced_draft_and_creates_posted_transaction(self):
        draft = self._create_draft()
        self._add_balanced_draft_entries(draft)

        posted_tx = confirm_transaction_draft(draft=draft)

        draft.refresh_from_db()
        self.assertEqual(draft.status, TransactionDraftStatus.CONFIRMED)
        self.assertIsNotNone(draft.resolved_at)
        self.assertEqual(draft.transaction, posted_tx)

        self.assertEqual(posted_tx.user, self.user)
        self.assertEqual(posted_tx.description, draft.description)
        self.assertEqual(posted_tx.currency, draft.currency)
        self.assertEqual(posted_tx.occurred_at, draft.occurred_at)
        self.assertEqual(posted_tx.source, TransactionSource.ASSISTANT)
        self.assertEqual(posted_tx.status, TransactionStatus.POSTED)
        self.assertIsNotNone(posted_tx.posted_at)

        entries = list(posted_tx.entries.order_by("side"))
        self.assertEqual(len(entries), 2)

        credit_entry, debit_entry = entries
        self.assertEqual(credit_entry.account, self.checking_account)
        self.assertEqual(credit_entry.side, EntrySide.CREDIT)
        self.assertEqual(credit_entry.amount, Decimal("120.50"))
        self.assertEqual(credit_entry.memo, "Debit card payment")

        self.assertEqual(debit_entry.account, self.groceries_account)
        self.assertEqual(debit_entry.side, EntrySide.DEBIT)
        self.assertEqual(debit_entry.amount, Decimal("120.50"))
        self.assertEqual(debit_entry.memo, "Food items")

    def test_second_confirmation_is_idempotent(self):
        draft = self._create_draft()
        self._add_balanced_draft_entries(draft)

        first_tx = confirm_transaction_draft(draft=draft)
        draft.refresh_from_db()
        original_resolved_at = draft.resolved_at

        second_tx = confirm_transaction_draft(draft=draft)

        draft.refresh_from_db()
        self.assertEqual(second_tx.id, first_tx.id)
        self.assertEqual(draft.resolved_at, original_resolved_at)
        self.assertEqual(Transaction.objects.count(), 1)
        self.assertEqual(Entry.objects.count(), 2)

    def test_rejects_already_rejected_draft(self):
        draft = self._create_draft(
            status=TransactionDraftStatus.REJECTED,
            resolved_at=timezone.now(),
        )
        self._add_balanced_draft_entries(draft)

        with self.assertRaises(DraftConfirmationError):
            confirm_transaction_draft(draft=draft)

        self.assertEqual(Transaction.objects.count(), 0)
        self.assertEqual(Entry.objects.count(), 0)

    def test_rejects_already_expired_draft(self):
        draft = self._create_draft(
            status=TransactionDraftStatus.EXPIRED,
            resolved_at=timezone.now(),
        )
        self._add_balanced_draft_entries(draft)

        with self.assertRaises(DraftConfirmationError):
            confirm_transaction_draft(draft=draft)

        self.assertEqual(Transaction.objects.count(), 0)
        self.assertEqual(Entry.objects.count(), 0)

    def test_marks_past_due_draft_as_expired_and_raises_draft_expired_error(self):
        draft = self._create_draft(
            expires_at=timezone.now() - timedelta(seconds=1),
        )
        self._add_balanced_draft_entries(draft)

        with self.assertRaises(DraftExpiredError):
            confirm_transaction_draft(draft=draft)

        draft.refresh_from_db()
        self.assertEqual(draft.status, TransactionDraftStatus.EXPIRED)
        self.assertIsNotNone(draft.resolved_at)
        self.assertIsNone(draft.transaction)
        self.assertEqual(Transaction.objects.count(), 0)
        self.assertEqual(Entry.objects.count(), 0)

    def test_rejects_draft_with_fewer_than_two_entries_and_rolls_back(self):
        for entry_count in (0, 1):
            with self.subTest(entry_count=entry_count):
                draft = self._create_draft()
                if entry_count == 1:
                    DraftEntry.objects.create(
                        draft=draft,
                        account=self.groceries_account,
                        side=EntrySide.DEBIT,
                        amount=Decimal("50.00"),
                    )

                with self.assertRaises(DraftConfirmationError):
                    confirm_transaction_draft(draft=draft)

                draft.refresh_from_db()
                self.assertEqual(draft.status, TransactionDraftStatus.PENDING)
                self.assertIsNone(draft.resolved_at)
                self.assertIsNone(draft.transaction)
                self.assertEqual(Transaction.objects.count(), 0)
                self.assertEqual(Entry.objects.count(), 0)

    def test_rejects_unbalanced_draft_entries_and_rolls_back(self):
        draft = self._create_draft()
        DraftEntry.objects.create(
            draft=draft,
            account=self.groceries_account,
            side=EntrySide.DEBIT,
            amount=Decimal("100.00"),
        )
        DraftEntry.objects.create(
            draft=draft,
            account=self.checking_account,
            side=EntrySide.CREDIT,
            amount=Decimal("80.00"),
        )

        with self.assertRaises(DraftConfirmationError):
            confirm_transaction_draft(draft=draft)

        draft.refresh_from_db()
        self.assertEqual(draft.status, TransactionDraftStatus.PENDING)
        self.assertIsNone(draft.resolved_at)
        self.assertIsNone(draft.transaction)
        self.assertEqual(Transaction.objects.count(), 0)
        self.assertEqual(Entry.objects.count(), 0)

    def test_rejects_draft_entry_with_account_of_another_user_and_rolls_back(self):
        other_user_account = Account.objects.create(
            user=self.other_user,
            name="Other Checking",
            account_type=AccountType.ASSET,
            currency=Currency.BRL,
        )
        draft = self._create_draft()
        DraftEntry.objects.create(
            draft=draft,
            account=self.groceries_account,
            side=EntrySide.DEBIT,
            amount=Decimal("100.00"),
        )
        DraftEntry.objects.create(
            draft=draft,
            account=other_user_account,
            side=EntrySide.CREDIT,
            amount=Decimal("100.00"),
        )

        with self.assertRaises(DraftConfirmationError):
            confirm_transaction_draft(draft=draft)

        draft.refresh_from_db()
        self.assertEqual(draft.status, TransactionDraftStatus.PENDING)
        self.assertIsNone(draft.resolved_at)
        self.assertIsNone(draft.transaction)
        self.assertEqual(Transaction.objects.count(), 0)
        self.assertEqual(Entry.objects.count(), 0)

    def test_rejects_draft_entry_with_different_currency_and_rolls_back(self):
        usd_account = Account.objects.create(
            user=self.user,
            name="USD Wallet",
            account_type=AccountType.ASSET,
            currency=Currency.USD,
        )
        draft = self._create_draft()
        DraftEntry.objects.create(
            draft=draft,
            account=self.groceries_account,
            side=EntrySide.DEBIT,
            amount=Decimal("100.00"),
        )
        DraftEntry.objects.create(
            draft=draft,
            account=usd_account,
            side=EntrySide.CREDIT,
            amount=Decimal("100.00"),
        )

        with self.assertRaises(DraftConfirmationError):
            confirm_transaction_draft(draft=draft)

        draft.refresh_from_db()
        self.assertEqual(draft.status, TransactionDraftStatus.PENDING)
        self.assertIsNone(draft.resolved_at)
        self.assertIsNone(draft.transaction)
        self.assertEqual(Transaction.objects.count(), 0)
        self.assertEqual(Entry.objects.count(), 0)

    def test_rejects_draft_entry_with_inactive_account_and_rolls_back(self):
        inactive_account = Account.objects.create(
            user=self.user,
            name="Closed Checking",
            account_type=AccountType.ASSET,
            currency=Currency.BRL,
            is_active=False,
        )
        draft = self._create_draft()
        DraftEntry.objects.create(
            draft=draft,
            account=self.groceries_account,
            side=EntrySide.DEBIT,
            amount=Decimal("100.00"),
        )
        DraftEntry.objects.create(
            draft=draft,
            account=inactive_account,
            side=EntrySide.CREDIT,
            amount=Decimal("100.00"),
        )

        with self.assertRaises(DraftConfirmationError):
            confirm_transaction_draft(draft=draft)

        draft.refresh_from_db()
        self.assertEqual(draft.status, TransactionDraftStatus.PENDING)
        self.assertIsNone(draft.resolved_at)
        self.assertIsNone(draft.transaction)
        self.assertEqual(Transaction.objects.count(), 0)
        self.assertEqual(Entry.objects.count(), 0)

    def test_stale_pending_instance_is_reloaded_from_database(self):
        draft = self._create_draft()
        self._add_balanced_draft_entries(draft)

        TransactionDraft.objects.filter(pk=draft.pk).update(
            status=TransactionDraftStatus.REJECTED,
            resolved_at=timezone.now(),
        )
        self.assertEqual(draft.status, TransactionDraftStatus.PENDING)

        with self.assertRaises(DraftConfirmationError):
            confirm_transaction_draft(draft=draft)

        self.assertEqual(Transaction.objects.count(), 0)
        self.assertEqual(Entry.objects.count(), 0)
