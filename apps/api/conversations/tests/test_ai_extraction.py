from decimal import Decimal
from unittest.mock import Mock

from django.test import SimpleTestCase

from ..ai_extraction import (
    AITransactionExtractor,
    StructuredTransactionCandidate,
)
from ..extraction import TextExtractionError, TransactionKind


class AITransactionExtractorTests(SimpleTestCase):
    def _extractor(self, candidate: StructuredTransactionCandidate):
        provider = Mock()
        provider.extract.return_value = candidate
        return AITransactionExtractor(provider=provider), provider

    def test_extracts_valid_expense_from_structured_response(self):
        extractor, provider = self._extractor(
            StructuredTransactionCandidate(
                supported=True,
                kind=TransactionKind.EXPENSE,
                amount="35.9",
                description="Almoço",
            )
        )

        result = extractor.extract("paguei trinta e cinco e noventa no almoço")

        provider.extract.assert_called_once_with(
            "paguei trinta e cinco e noventa no almoço"
        )
        self.assertEqual(result.kind, TransactionKind.EXPENSE)
        self.assertEqual(result.amount, Decimal("35.90"))
        self.assertEqual(result.description, "Almoço")

    def test_extracts_valid_income_from_structured_response(self):
        extractor, _ = self._extractor(
            StructuredTransactionCandidate(
                supported=True,
                kind=TransactionKind.INCOME,
                amount="2500.00",
                description="Freelance",
            )
        )

        result = extractor.extract("entrou dois e quinhentos do freelance")

        self.assertEqual(result.kind, TransactionKind.INCOME)
        self.assertEqual(result.amount, Decimal("2500.00"))

    def test_rejects_unsupported_intent(self):
        extractor, _ = self._extractor(
            StructuredTransactionCandidate(supported=False)
        )

        with self.assertRaises(TextExtractionError):
            extractor.extract("como está o tempo?")

    def test_rejects_invalid_structured_fields(self):
        invalid_candidates = (
            StructuredTransactionCandidate(
                supported=True, kind="TRANSFER", amount="10", description="Pix"
            ),
            StructuredTransactionCandidate(
                supported=True,
                kind=TransactionKind.EXPENSE,
                amount="not-a-number",
                description="Almoço",
            ),
            StructuredTransactionCandidate(
                supported=True,
                kind=TransactionKind.EXPENSE,
                amount="0",
                description="Almoço",
            ),
            StructuredTransactionCandidate(
                supported=True,
                kind=TransactionKind.EXPENSE,
                amount="1000000000000",
                description="Almoço",
            ),
            StructuredTransactionCandidate(
                supported=True,
                kind=TransactionKind.EXPENSE,
                amount="10",
                description=" ",
            ),
            StructuredTransactionCandidate(
                supported=True,
                kind=TransactionKind.EXPENSE,
                amount="10",
                description="x" * 256,
            ),
        )

        for candidate in invalid_candidates:
            with self.subTest(candidate=candidate):
                extractor, _ = self._extractor(candidate)
                with self.assertRaises(TextExtractionError):
                    extractor.extract("uma mensagem")

    def test_rejects_empty_input_before_calling_provider(self):
        extractor, provider = self._extractor(
            StructuredTransactionCandidate(supported=False)
        )

        with self.assertRaises(TextExtractionError):
            extractor.extract("   ")

        provider.extract.assert_not_called()
