from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from common.money import Currency

from ..models import AccountSystemRole, Entry, EntrySide, Transaction, TransactionStatus
from ..services import (
    OpeningBalanceError,
    calculate_account_balance,
    ensure_default_accounts,
    post_transaction,
    record_opening_balance,
)


class OpeningBalanceServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            email="opening@example.com",
            password="StrongPassword!123",
            currency=Currency.BRL,
        )
        cls.accounts = ensure_default_accounts(user=cls.user)

    def test_positive_balance_creates_balanced_posted_transaction(self):
        transaction = record_opening_balance(
            account=self.accounts.primary,
            balance=Decimal("50000.00"),
        )

        self.assertEqual(transaction.status, TransactionStatus.POSTED)
        entries = {entry.side: entry for entry in transaction.entries.all()}
        self.assertEqual(entries[EntrySide.DEBIT].account, self.accounts.primary)
        self.assertEqual(
            entries[EntrySide.CREDIT].account.system_role,
            AccountSystemRole.OPENING_BALANCE,
        )
        self.assertEqual(
            calculate_account_balance(account=self.accounts.primary),
            Decimal("50000.00"),
        )

    def test_negative_balance_uses_credit_on_asset_account(self):
        record_opening_balance(
            account=self.accounts.primary,
            balance=Decimal("-300.00"),
        )

        self.assertEqual(
            calculate_account_balance(account=self.accounts.primary),
            Decimal("-300.00"),
        )

    def test_zero_balance_creates_idempotency_marker_without_entries(self):
        transaction = record_opening_balance(
            account=self.accounts.primary,
            balance=Decimal("0.00"),
        )

        self.assertEqual(transaction.status, TransactionStatus.POSTED)
        self.assertEqual(transaction.entries.count(), 0)
        self.accounts.primary.refresh_from_db()
        self.assertEqual(
            self.accounts.primary.opening_balance_transaction,
            transaction,
        )

    def test_opening_balance_cannot_be_recorded_twice(self):
        record_opening_balance(
            account=self.accounts.primary,
            balance=Decimal("100.00"),
        )

        with self.assertRaises(OpeningBalanceError):
            record_opening_balance(
                account=self.accounts.primary,
                balance=Decimal("200.00"),
            )

        self.assertEqual(
            calculate_account_balance(account=self.accounts.primary),
            Decimal("100.00"),
        )

    def test_existing_activity_is_considered_to_reach_current_balance(self):
        expense = Transaction.objects.create(
            user=self.user,
            description="Mercado",
            currency=Currency.BRL,
            occurred_at=self.user.date_joined,
        )
        Entry.objects.create(
            transaction=expense,
            account=self.accounts.general_expense,
            side=EntrySide.DEBIT,
            amount=Decimal("40.00"),
        )
        Entry.objects.create(
            transaction=expense,
            account=self.accounts.primary,
            side=EntrySide.CREDIT,
            amount=Decimal("40.00"),
        )
        post_transaction(transaction=expense)

        record_opening_balance(
            account=self.accounts.primary,
            balance=Decimal("1000.00"),
        )

        self.assertEqual(
            calculate_account_balance(account=self.accounts.primary),
            Decimal("1000.00"),
        )
