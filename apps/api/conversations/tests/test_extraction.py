from decimal import Decimal

from django.test import SimpleTestCase

from ..extraction import (
    ExtractedTransaction,
    TextExtractionError,
    TransactionExtractor,
    TransactionKind,
    extract_transaction_from_text,
)


class StubTransactionExtractor:
    def extract(self, text: str) -> ExtractedTransaction:
        return ExtractedTransaction(
            kind=TransactionKind.EXPENSE,
            amount=Decimal("1.00"),
            description=text,
        )


class ExtractTransactionFromTextTests(SimpleTestCase):
    def test_extractor_contract_supports_structural_implementations(self):
        self.assertIsInstance(StubTransactionExtractor(), TransactionExtractor)

    def test_accepts_natural_expense_forms(self):
        cases = (
            ("gasto de 2500", Decimal("2500.00"), "Despesa"),
            ("gastei 2500", Decimal("2500.00"), "Despesa"),
            ("despesa R$ 35,90 almoço", Decimal("35.90"), "almoço"),
            ("gastei 35 reais no almoço", Decimal("35.00"), "no almoço"),
        )
        for text, amount, description in cases:
            with self.subTest(text=text):
                result = extract_transaction_from_text(text)
                self.assertEqual(result.kind, TransactionKind.EXPENSE)
                self.assertEqual(result.amount, amount)
                self.assertEqual(result.description, description)

    def test_accepts_natural_income_forms(self):
        cases = (
            ("receita de 2500", Decimal("2500.00"), "Receita"),
            ("ganho de 2500", Decimal("2500.00"), "Receita"),
            ("ganhei 2500 salário", Decimal("2500.00"), "salário"),
            ("receita 99.50 BRL freelance", Decimal("99.50"), "freelance"),
        )
        for text, amount, description in cases:
            with self.subTest(text=text):
                result = extract_transaction_from_text(text)
                self.assertEqual(result.kind, TransactionKind.INCOME)
                self.assertEqual(result.amount, amount)
                self.assertEqual(result.description, description)

    def test_is_case_insensitive_and_ignores_outer_whitespace(self):
        result = extract_transaction_from_text("  GASTEI 10 Café  ")

        self.assertEqual(result.kind, TransactionKind.EXPENSE)
        self.assertEqual(result.amount, Decimal("10.00"))
        self.assertEqual(result.description, "Café")

    def test_rejects_unsupported_or_invalid_values(self):
        invalid_values = (
            "",
            "paguei 10 almoço",
            "gastei almoço",
            "gasto 0 almoço",
            "receita -10",
            "gasto 10,999 almoço",
            "gasto 1000000000000 almoço",
            123,
        )
        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaises(TextExtractionError):
                    extract_transaction_from_text(value)

    def test_rejects_description_longer_than_model_limit(self):
        with self.assertRaises(TextExtractionError):
            extract_transaction_from_text("gasto 10 " + "x" * 256)
