from decimal import Decimal
import uuid

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase
from django.utils import timezone

from common.money import Currency

from ..models import (
    Account,
    AccountSystemRole,
    AccountType,
    Entry,
    EntrySide,
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
        self.assertEqual(account.system_role, "")

    def test_create_valid_system_account(self):
        account = Account.objects.create(
            user=self.user,
            name="Conta principal",
            account_type=AccountType.ASSET,
            currency=Currency.BRL,
            system_role=AccountSystemRole.PRIMARY,
        )

        self.assertEqual(account.system_role, AccountSystemRole.PRIMARY)
        account.full_clean()

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

    def test_system_role_is_unique_per_user(self):
        Account.objects.create(
            user=self.user,
            name="Principal",
            account_type=AccountType.ASSET,
            currency=Currency.BRL,
            system_role=AccountSystemRole.PRIMARY,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Account.objects.create(
                    user=self.user,
                    name="Outra principal",
                    account_type=AccountType.ASSET,
                    currency=Currency.BRL,
                    system_role=AccountSystemRole.PRIMARY,
                )

    def test_different_users_can_have_same_system_role(self):
        for user in (self.user, self.other_user):
            Account.objects.create(
                user=user,
                name="Principal",
                account_type=AccountType.ASSET,
                currency=Currency.BRL,
                system_role=AccountSystemRole.PRIMARY,
            )

        self.assertEqual(
            Account.objects.filter(system_role=AccountSystemRole.PRIMARY).count(),
            2,
        )

    def test_database_rejects_invalid_system_role(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Account.objects.create(
                    user=self.user,
                    name="Invalid",
                    account_type=AccountType.ASSET,
                    currency=Currency.BRL,
                    system_role="INVALID",
                )

    def test_database_rejects_system_role_with_wrong_account_type(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Account.objects.create(
                    user=self.user,
                    name="Wrong type",
                    account_type=AccountType.INCOME,
                    currency=Currency.BRL,
                    system_role=AccountSystemRole.PRIMARY,
                )


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
            source=TransactionSource.ASSISTANT,
            posted_at=posted_at,
        )

        self.assertEqual(tx.status, TransactionStatus.POSTED)
        self.assertEqual(tx.source, TransactionSource.ASSISTANT)
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


class EntryModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user_model = get_user_model()
        cls.user = cls.user_model.objects.create_user(
            email="user@example.com",
            password="StrongPassword!123",
        )
        cls.account = Account.objects.create(
            user=cls.user,
            name="Nubank Checking",
            account_type=AccountType.ASSET,
            currency=Currency.BRL,
        )
        cls.transaction = Transaction.objects.create(
            user=cls.user,
            description="Grocery shopping",
            currency=Currency.BRL,
            occurred_at=timezone.now(),
        )

    def test_create_valid_entry(self):
        entry = Entry.objects.create(
            transaction=self.transaction,
            account=self.account,
            side=EntrySide.CREDIT,
            amount=Decimal("150.50"),
            memo="Weekly groceries",
        )

        self.assertIsInstance(entry.id, uuid.UUID)
        self.assertEqual(entry.transaction, self.transaction)
        self.assertEqual(entry.account, self.account)
        self.assertEqual(entry.side, EntrySide.CREDIT)
        self.assertEqual(entry.amount, Decimal("150.50"))
        self.assertEqual(entry.memo, "Weekly groceries")
        self.assertIsNotNone(entry.created_at)
        self.assertIsNotNone(entry.updated_at)

    def test_entry_memo_defaults_to_empty_string(self):
        entry = Entry.objects.create(
            transaction=self.transaction,
            account=self.account,
            side=EntrySide.DEBIT,
            amount=Decimal("50.00"),
        )

        self.assertEqual(entry.memo, "")

    def test_reverse_relationships_on_transaction_and_account(self):
        entry = Entry.objects.create(
            transaction=self.transaction,
            account=self.account,
            side=EntrySide.DEBIT,
            amount=Decimal("100.00"),
        )

        self.assertIn(entry, self.transaction.entries.all())
        self.assertIn(entry, self.account.entries.all())

    def test_str_returns_useful_representation(self):
        entry = Entry.objects.create(
            transaction=self.transaction,
            account=self.account,
            side=EntrySide.DEBIT,
            amount=Decimal("100.00"),
        )

        self.assertEqual(str(entry), "DEBIT 100.00 (Nubank Checking)")

    def test_deleting_transaction_cascades_to_entries(self):
        tx = Transaction.objects.create(
            user=self.user,
            description="Temporary transaction",
            currency=Currency.BRL,
            occurred_at=timezone.now(),
        )
        entry = Entry.objects.create(
            transaction=tx,
            account=self.account,
            side=EntrySide.DEBIT,
            amount=Decimal("25.00"),
        )

        tx.delete()

        self.assertFalse(Entry.objects.filter(id=entry.id).exists())

    def test_deleting_account_with_entries_raises_protected_error(self):
        protected_account = Account.objects.create(
            user=self.user,
            name="Protected Account",
            account_type=AccountType.ASSET,
            currency=Currency.BRL,
        )
        Entry.objects.create(
            transaction=self.transaction,
            account=protected_account,
            side=EntrySide.DEBIT,
            amount=Decimal("25.00"),
        )

        with self.assertRaises(ProtectedError):
            protected_account.delete()

    def test_full_clean_rejects_invalid_side(self):
        entry = Entry(
            transaction=self.transaction,
            account=self.account,
            side="INVALID_SIDE",
            amount=Decimal("10.00"),
        )

        with self.assertRaises(ValidationError) as ctx:
            entry.full_clean()

        self.assertIn("side", ctx.exception.error_dict)

    def test_full_clean_rejects_zero_or_negative_amount(self):
        for invalid_amount in (Decimal("0.00"), Decimal("-10.00")):
            with self.subTest(amount=invalid_amount):
                entry = Entry(
                    transaction=self.transaction,
                    account=self.account,
                    side=EntrySide.DEBIT,
                    amount=invalid_amount,
                )
                with self.assertRaises(ValidationError) as ctx:
                    entry.full_clean()
                self.assertIn("amount", ctx.exception.error_dict)

    def test_database_rejects_invalid_side(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Entry.objects.create(
                    transaction=self.transaction,
                    account=self.account,
                    side="INVALID",
                    amount=Decimal("10.00"),
                )

    def test_database_rejects_zero_amount(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Entry.objects.create(
                    transaction=self.transaction,
                    account=self.account,
                    side=EntrySide.DEBIT,
                    amount=Decimal("0.00"),
                )

    def test_database_rejects_negative_amount(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Entry.objects.create(
                    transaction=self.transaction,
                    account=self.account,
                    side=EntrySide.DEBIT,
                    amount=Decimal("-10.00"),
                )
