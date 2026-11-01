import uuid

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from common.money import Currency

from ..models import Account, AccountType


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
