import uuid

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from common.money import Currency

from ..models import (
    Account,
    AccountType,
    Transaction,
    TransactionSource,
    TransactionStatus,
)


class AccountModelTests(TestCase):
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

    def test_create_valid_account(self):
        account = Account.objects.create(
            user=self.user,
            name="Nubank Checking",
            account_type=AccountType.ASSET,
            currency=Currency.BRL,
        )

        self.assertEqual(account.user, self.user)
        self.assertEqual(account.name, "Nubank Checking")
        self.assertEqual(account.account_type, AccountType.ASSET)
        self.assertEqual(account.currency, Currency.BRL)
        self.assertIsNotNone(account.created_at)
        self.assertIsNotNone(account.updated_at)

    def test_account_id_is_uuid(self):
        account = Account.objects.create(
            user=self.user,
            name="Cash",
            account_type=AccountType.ASSET,
            currency=Currency.BRL,
        )

        self.assertIsInstance(account.id, uuid.UUID)

    def test_account_is_active_by_default(self):
        account = Account.objects.create(
            user=self.user,
            name="Credit Card",
            account_type=AccountType.LIABILITY,
            currency=Currency.BRL,
        )

        self.assertTrue(account.is_active)

    def test_user_accounts_reverse_relationship(self):
        account = Account.objects.create(
            user=self.user,
            name="Salary",
            account_type=AccountType.INCOME,
            currency=Currency.BRL,
        )

        self.assertIn(account, self.user.accounts.all())

    def test_str_returns_useful_representation(self):
        account = Account.objects.create(
            user=self.user,
            name="Nubank Checking",
            account_type=AccountType.ASSET,
            currency=Currency.BRL,
        )

        self.assertEqual(str(account), "Nubank Checking (BRL)")

    def test_full_clean_rejects_invalid_account_type(self):
        account = Account(
            user=self.user,
            name="Invalid Account",
            account_type="INVALID_TYPE",
            currency=Currency.BRL,
        )

        with self.assertRaises(ValidationError) as ctx:
            account.full_clean()

        self.assertIn("account_type", ctx.exception.error_dict)

    def test_full_clean_rejects_invalid_currency(self):
        account = Account(
            user=self.user,
            name="Invalid Currency Account",
            account_type=AccountType.ASSET,
            currency="XYZ",
        )

        with self.assertRaises(ValidationError) as ctx:
            account.full_clean()

        self.assertIn("currency", ctx.exception.error_dict)

    def test_database_rejects_invalid_account_type(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Account.objects.create(
                    user=self.user,
                    name="Invalid Type DB",
                    account_type="INVALID_TYPE",
                    currency=Currency.BRL,
                )

    def test_database_rejects_invalid_currency(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Account.objects.create(
                    user=self.user,
                    name="Invalid Currency DB",
                    account_type=AccountType.ASSET,
                    currency="XYZ",
                )

    def test_different_users_can_have_accounts_with_same_name(self):
        account_one = Account.objects.create(
            user=self.user,
            name="Nubank",
            account_type=AccountType.ASSET,
            currency=Currency.BRL,
        )
        account_two = Account.objects.create(
            user=self.other_user,
            name="Nubank",
            account_type=AccountType.ASSET,
            currency=Currency.BRL,
        )

        self.assertEqual(account_one.name, account_two.name)
        self.assertNotEqual(account_one.id, account_two.id)

    def test_same_user_can_have_two_accounts_with_same_name(self):
        account_one = Account.objects.create(
            user=self.user,
            name="Nubank",
            account_type=AccountType.ASSET,
            currency=Currency.BRL,
        )
        account_two = Account.objects.create(
            user=self.user,
            name="Nubank",
            account_type=AccountType.LIABILITY,
            currency=Currency.BRL,
        )

        self.assertEqual(account_one.name, account_two.name)
        self.assertNotEqual(account_one.id, account_two.id)
        self.assertEqual(self.user.accounts.filter(name="Nubank").count(), 2)


class TransactionModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user_model = get_user_model()
        cls.user = cls.user_model.objects.create_user(
            email="user@example.com",
            password="StrongPassword!123",
        )
        cls.occurred_at = timezone.now()

    def test_create_valid_draft_transaction_with_defaults(self):
        tx = Transaction.objects.create(
            user=self.user,
            description="Grocery shopping",
            currency=Currency.BRL,
            occurred_at=self.occurred_at,
        )

        self.assertIsInstance(tx.id, uuid.UUID)
        self.assertEqual(tx.user, self.user)
        self.assertEqual(tx.description, "Grocery shopping")
        self.assertEqual(tx.currency, Currency.BRL)
        self.assertEqual(tx.occurred_at, self.occurred_at)
        self.assertEqual(tx.status, TransactionStatus.DRAFT)
        self.assertEqual(tx.source, TransactionSource.MANUAL)
        self.assertIsNone(tx.posted_at)
        self.assertIsNotNone(tx.created_at)
        self.assertIsNotNone(tx.updated_at)

    def test_create_valid_posted_transaction(self):
        posted_at = timezone.now()
        tx = Transaction.objects.create(
            user=self.user,
            description="Salary payment",
            currency=Currency.BRL,
            occurred_at=self.occurred_at,
            status=TransactionStatus.POSTED,
            source=TransactionSource.CHAT,
            posted_at=posted_at,
        )

        self.assertEqual(tx.status, TransactionStatus.POSTED)
        self.assertEqual(tx.source, TransactionSource.CHAT)
        self.assertEqual(tx.posted_at, posted_at)

    def test_create_valid_voided_transaction_with_posted_at(self):
        posted_at = timezone.now()
        tx = Transaction.objects.create(
            user=self.user,
            description="Voided payment",
            currency=Currency.BRL,
            occurred_at=self.occurred_at,
            status=TransactionStatus.VOIDED,
            posted_at=posted_at,
        )

        self.assertEqual(tx.status, TransactionStatus.VOIDED)
        self.assertEqual(tx.posted_at, posted_at)

    def test_user_transactions_reverse_relationship(self):
        tx = Transaction.objects.create(
            user=self.user,
            description="Rent",
            currency=Currency.BRL,
            occurred_at=self.occurred_at,
        )

        self.assertIn(tx, self.user.transactions.all())

    def test_str_returns_useful_representation(self):
        tx = Transaction.objects.create(
            user=self.user,
            description="Grocery shopping",
            currency=Currency.BRL,
            occurred_at=self.occurred_at,
        )

        self.assertEqual(str(tx), "Grocery shopping (DRAFT)")

    def test_full_clean_rejects_invalid_choices(self):
        for field, value in (
            ("currency", "XYZ"),
            ("status", "INVALID_STATUS"),
            ("source", "INVALID_SOURCE"),
        ):
            with self.subTest(field=field):
                kwargs = {
                    "user": self.user,
                    "description": "Invalid Transaction",
                    "currency": Currency.BRL,
                    "occurred_at": self.occurred_at,
                    field: value,
                }
                tx = Transaction(**kwargs)
                with self.assertRaises(ValidationError) as ctx:
                    tx.full_clean()
                self.assertIn(field, ctx.exception.error_dict)

    def test_database_rejects_invalid_currency(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Transaction.objects.create(
                    user=self.user,
                    description="Invalid Currency",
                    currency="XYZ",
                    occurred_at=self.occurred_at,
                )

    def test_database_rejects_invalid_status(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Transaction.objects.create(
                    user=self.user,
                    description="Invalid Status",
                    currency=Currency.BRL,
                    occurred_at=self.occurred_at,
                    status="INVALID_STATUS",
                )

    def test_database_rejects_invalid_source(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Transaction.objects.create(
                    user=self.user,
                    description="Invalid Source",
                    currency=Currency.BRL,
                    occurred_at=self.occurred_at,
                    source="INVALID_SOURCE",
                )

    def test_database_rejects_draft_transaction_with_posted_at(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Transaction.objects.create(
                    user=self.user,
                    description="Inconsistent Draft",
                    currency=Currency.BRL,
                    occurred_at=self.occurred_at,
                    status=TransactionStatus.DRAFT,
                    posted_at=timezone.now(),
                )

    def test_database_rejects_posted_transaction_without_posted_at(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Transaction.objects.create(
                    user=self.user,
                    description="Inconsistent Posted",
                    currency=Currency.BRL,
                    occurred_at=self.occurred_at,
                    status=TransactionStatus.POSTED,
                    posted_at=None,
                )

    def test_database_rejects_voided_transaction_without_posted_at(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Transaction.objects.create(
                    user=self.user,
                    description="Inconsistent Voided",
                    currency=Currency.BRL,
                    occurred_at=self.occurred_at,
                    status=TransactionStatus.VOIDED,
                    posted_at=None,
                )
