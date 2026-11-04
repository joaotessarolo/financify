from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from ledger.models import AccountSystemRole
from ledger.services import calculate_account_balance, ensure_default_accounts

from ..models import TelegramIdentity, TelegramOnboardingStep
from ..onboarding import (
    OnboardingParseError,
    complete_account_onboarding,
    parse_account_setup,
    parse_balance,
    remember_primary_account_name,
)


class OnboardingParserTests(TestCase):
    def test_parses_supported_balance_forms(self):
        cases = (
            ("50 mil", Decimal("50000.00")),
            ("1.250,90", Decimal("1250.90")),
            ("-300", Decimal("-300.00")),
            ("R$ 2.500 reais", Decimal("2500.00")),
            ("0", Decimal("0.00")),
        )
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(parse_balance(text), expected)

    def test_parses_account_with_optional_balance(self):
        cases = (
            ("Nubank", "Nubank", None),
            ("Nubank, 50 mil reais", "Nubank", Decimal("50000.00")),
            ("Itaú com -300", "Itaú", Decimal("-300.00")),
            ("Inter, BRL, 1.250,90", "Inter", Decimal("1250.90")),
        )
        for text, name, balance in cases:
            with self.subTest(text=text):
                result = parse_account_setup(text)
                self.assertEqual(result.name, name)
                self.assertEqual(result.balance, balance)

    def test_rejects_invalid_values(self):
        for value in ("", "Nubank, muito", "123", "Nubank, 10 trilhões"):
            with self.subTest(value=value):
                with self.assertRaises(OnboardingParseError):
                    parse_account_setup(value)


class AccountOnboardingServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            email="onboarding@example.com",
            password="StrongPassword!123",
        )
        ensure_default_accounts(user=cls.user)

    def setUp(self):
        self.identity = TelegramIdentity.objects.create(
            user=self.user,
            telegram_user_id=123456,
            private_chat_id=123456,
        )

    def test_remembers_name_then_completes_with_balance(self):
        remember_primary_account_name(
            identity=self.identity,
            account_name="Nubank",
        )
        self.identity.refresh_from_db()
        self.assertEqual(
            self.identity.onboarding_step,
            TelegramOnboardingStep.AWAITING_BALANCE,
        )

        primary = complete_account_onboarding(
            identity=self.identity,
            account_name=self.identity.pending_account_name,
            balance=Decimal("1250.90"),
        )

        self.identity.refresh_from_db()
        self.assertEqual(self.identity.onboarding_step, TelegramOnboardingStep.COMPLETED)
        self.assertEqual(primary.name, "Nubank")
        self.assertEqual(
            calculate_account_balance(account=primary), Decimal("1250.90")
        )
        self.assertTrue(
            self.user.accounts.filter(
                system_role=AccountSystemRole.OPENING_BALANCE
            ).exists()
        )
