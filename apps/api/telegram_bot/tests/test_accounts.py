from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from conversations.extraction import ExtractedTransaction, TransactionKind
from ledger.models import AccountType

from ..accounts import (
    TelegramAccountError,
    create_asset_account,
    parse_create_account,
    select_transaction_account,
)


class TelegramAccountTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            email="telegram-accounts@example.com",
            password="StrongPassword!123",
        )

    def test_parses_natural_create_account_command(self):
        setup = parse_create_account("criar conta Inter com saldo 1.250,90")

        self.assertEqual(setup.name, "Inter")
        self.assertEqual(setup.balance, Decimal("1250.90"))

    def test_create_command_requires_opening_balance(self):
        with self.assertRaises(TelegramAccountError):
            parse_create_account("criar conta Inter")

    def test_creates_asset_account_and_rejects_duplicate_name(self):
        setup = parse_create_account("criar conta Inter com saldo 500")
        account = create_asset_account(user=self.user, setup=setup)

        self.assertEqual(account.account_type, AccountType.ASSET)
        with self.assertRaises(TelegramAccountError):
            create_asset_account(user=self.user, setup=setup)

    def test_selects_explicit_account_suffix(self):
        setup = parse_create_account("criar conta Inter com saldo 0")
        account = create_asset_account(user=self.user, setup=setup)
        extraction = ExtractedTransaction(
            kind=TransactionKind.EXPENSE,
            amount=Decimal("40.00"),
            description="no mercado pelo Inter",
        )

        selected, cleaned, result = select_transaction_account(
            user=self.user,
            text="gastei 40 no mercado pelo Inter",
            extraction=extraction,
        )

        self.assertEqual(selected, account)
        self.assertEqual(cleaned, "gastei 40 no mercado")
        self.assertEqual(result.account_name, "Inter")
