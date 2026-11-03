from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from common.money import Currency

from ..models import (
    Account,
    AccountType,
    Entry,
    EntrySide,
    Transaction,
    TransactionStatus,
)
from ..services import TransactionPostingError, post_transaction


class PostTransactionServiceTests(TestCase):
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

    def _create_draft_transaction(self, **kwargs) -> Transaction:
        defaults = {
            "user": self.user,
            "description": "Supermarket purchase",
            "currency": Currency.BRL,
            "occurred_at": timezone.now(),
        }
        defaults.update(kwargs)
        return Transaction.objects.create(**defaults)

    def test_post_balanced_transaction_updates_status_and_sets_posted_at(self):
        tx = self._create_draft_transaction()
        Entry.objects.create(
            transaction=tx,
            account=self.groceries_account,
            side=EntrySide.DEBIT,
            amount=Decimal("120.50"),
        )
        Entry.objects.create(
            transaction=tx,
            account=self.checking_account,
            side=EntrySide.CREDIT,
            amount=Decimal("120.50"),
        )

        posted_tx = post_transaction(transaction=tx)

        tx.refresh_from_db()
        self.assertEqual(posted_tx.id, tx.id)
        self.assertEqual(tx.status, TransactionStatus.POSTED)
        self.assertIsNotNone(tx.posted_at)
        self.assertEqual(posted_tx.status, TransactionStatus.POSTED)
        self.assertEqual(posted_tx.posted_at, tx.posted_at)

    def test_rejects_already_posted_transaction(self):
        tx = self._create_draft_transaction()
        Entry.objects.create(
            transaction=tx,
            account=self.groceries_account,
            side=EntrySide.DEBIT,
            amount=Decimal("50.00"),
        )
        Entry.objects.create(
            transaction=tx,
            account=self.checking_account,
            side=EntrySide.CREDIT,
            amount=Decimal("50.00"),
        )

        post_transaction(transaction=tx)
        tx.refresh_from_db()
        original_posted_at = tx.posted_at

        with self.assertRaises(TransactionPostingError):
            post_transaction(transaction=tx)

        tx.refresh_from_db()
        self.assertEqual(tx.status, TransactionStatus.POSTED)
        self.assertEqual(tx.posted_at, original_posted_at)

    def test_rejects_stale_draft_instance_when_already_posted_in_database(self):
        tx = self._create_draft_transaction()
        Entry.objects.create(
            transaction=tx,
            account=self.groceries_account,
            side=EntrySide.DEBIT,
            amount=Decimal("50.00"),
        )
        Entry.objects.create(
            transaction=tx,
            account=self.checking_account,
            side=EntrySide.CREDIT,
            amount=Decimal("50.00"),
        )

        posted_at = timezone.now()
        Transaction.objects.filter(pk=tx.pk).update(
            status=TransactionStatus.POSTED,
            posted_at=posted_at,
        )
        self.assertEqual(tx.status, TransactionStatus.DRAFT)

        with self.assertRaises(TransactionPostingError):
            post_transaction(transaction=tx)

        tx.refresh_from_db()
        self.assertEqual(tx.status, TransactionStatus.POSTED)
        self.assertEqual(tx.posted_at, posted_at)

    def test_rejects_transaction_with_fewer_than_two_entries(self):
        for entry_count in (0, 1):
            with self.subTest(entry_count=entry_count):
                tx = self._create_draft_transaction()
                if entry_count == 1:
                    Entry.objects.create(
                        transaction=tx,
                        account=self.groceries_account,
                        side=EntrySide.DEBIT,
                        amount=Decimal("50.00"),
                    )

                with self.assertRaises(TransactionPostingError):
                    post_transaction(transaction=tx)

                tx.refresh_from_db()
                self.assertEqual(tx.status, TransactionStatus.DRAFT)
                self.assertIsNone(tx.posted_at)

    def test_rejects_unbalanced_entries_and_preserves_draft_state(self):
        tx = self._create_draft_transaction()
        Entry.objects.create(
            transaction=tx,
            account=self.groceries_account,
            side=EntrySide.DEBIT,
            amount=Decimal("100.00"),
        )
        Entry.objects.create(
            transaction=tx,
            account=self.checking_account,
            side=EntrySide.CREDIT,
            amount=Decimal("80.00"),
        )

        with self.assertRaises(TransactionPostingError):
            post_transaction(transaction=tx)

        tx.refresh_from_db()
        self.assertEqual(tx.status, TransactionStatus.DRAFT)
        self.assertIsNone(tx.posted_at)

    def test_rejects_entry_with_account_belonging_to_another_user(self):
        other_user_account = Account.objects.create(
            user=self.other_user,
            name="Other User Checking",
            account_type=AccountType.ASSET,
            currency=Currency.BRL,
        )
        tx = self._create_draft_transaction()
        Entry.objects.create(
            transaction=tx,
            account=self.groceries_account,
            side=EntrySide.DEBIT,
            amount=Decimal("100.00"),
        )
        Entry.objects.create(
            transaction=tx,
            account=other_user_account,
            side=EntrySide.CREDIT,
            amount=Decimal("100.00"),
        )

        with self.assertRaises(TransactionPostingError):
            post_transaction(transaction=tx)

        tx.refresh_from_db()
        self.assertEqual(tx.status, TransactionStatus.DRAFT)
        self.assertIsNone(tx.posted_at)

    def test_rejects_entry_with_mismatched_account_currency(self):
        usd_account = Account.objects.create(
            user=self.user,
            name="USD Wallet",
            account_type=AccountType.ASSET,
            currency=Currency.USD,
        )
        tx = self._create_draft_transaction()
        Entry.objects.create(
            transaction=tx,
            account=self.groceries_account,
            side=EntrySide.DEBIT,
            amount=Decimal("100.00"),
        )
        Entry.objects.create(
            transaction=tx,
            account=usd_account,
            side=EntrySide.CREDIT,
            amount=Decimal("100.00"),
        )

        with self.assertRaises(TransactionPostingError):
            post_transaction(transaction=tx)

        tx.refresh_from_db()
        self.assertEqual(tx.status, TransactionStatus.DRAFT)
        self.assertIsNone(tx.posted_at)

    def test_rejects_entry_with_inactive_account(self):
        inactive_account = Account.objects.create(
            user=self.user,
            name="Closed Checking",
            account_type=AccountType.ASSET,
            currency=Currency.BRL,
            is_active=False,
        )
        tx = self._create_draft_transaction()
        Entry.objects.create(
            transaction=tx,
            account=self.groceries_account,
            side=EntrySide.DEBIT,
            amount=Decimal("100.00"),
        )
        Entry.objects.create(
            transaction=tx,
            account=inactive_account,
            side=EntrySide.CREDIT,
            amount=Decimal("100.00"),
        )

        with self.assertRaises(TransactionPostingError):
            post_transaction(transaction=tx)

        tx.refresh_from_db()
        self.assertEqual(tx.status, TransactionStatus.DRAFT)
        self.assertIsNone(tx.posted_at)
