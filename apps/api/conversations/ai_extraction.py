from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Protocol

from .extraction import (
    ExtractedTransaction,
    TextExtractionError,
    TransactionKind,
)


@dataclass(frozen=True, slots=True)
class StructuredTransactionCandidate:
    supported: bool
    kind: str | None = None
    amount: str | None = None
    description: str | None = None
    account_name: str | None = None
    category_name: str | None = None


class StructuredTransactionProvider(Protocol):
    """Provider boundary for schema-constrained model responses."""

    def extract(self, text: str) -> StructuredTransactionCandidate:
        ...


class TransactionExtractionProviderError(RuntimeError):
    """The configured model provider could not produce a usable response."""


class AITransactionExtractor:
    """Validate a model-produced candidate before it reaches the ledger."""

    def __init__(self, *, provider: StructuredTransactionProvider):
        self.provider = provider

    def extract(self, text: str) -> ExtractedTransaction:
        if not isinstance(text, str) or not text.strip():
            raise TextExtractionError("Transaction text must be a non-empty string.")

        candidate = self.provider.extract(text.strip())
        if not candidate.supported:
            raise TextExtractionError("The message does not describe a transaction.")
        if candidate.kind not in {TransactionKind.EXPENSE, TransactionKind.INCOME}:
            raise TextExtractionError("Invalid transaction kind returned by provider.")
        if not isinstance(candidate.amount, str):
            raise TextExtractionError("Missing transaction amount.")

        try:
            amount = Decimal(candidate.amount)
        except InvalidOperation as exc:
            raise TextExtractionError("Invalid transaction amount.") from exc
        if not amount.is_finite() or amount <= 0 or amount > Decimal("999999999999.99"):
            raise TextExtractionError("Transaction amount is outside valid bounds.")

        if not isinstance(candidate.description, str):
            raise TextExtractionError("Missing transaction description.")
        description = candidate.description.strip()
        if not description or len(description) > 255:
            raise TextExtractionError("Invalid transaction description.")

        return ExtractedTransaction(
            kind=candidate.kind,
            amount=amount.quantize(Decimal("0.01")),
            description=description,
            account_name=(
                candidate.account_name.strip()
                if isinstance(candidate.account_name, str)
                and candidate.account_name.strip()
                else None
            ),
            category_name=(
                candidate.category_name.strip()
                if isinstance(candidate.category_name, str)
                and candidate.category_name.strip()
                else None
            ),
        )
