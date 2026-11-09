from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re
from typing import Protocol, runtime_checkable


class TextExtractionError(ValueError):
    pass


class TransactionKind:
    EXPENSE = "EXPENSE"
    INCOME = "INCOME"
    TRANSFER = "TRANSFER"


@dataclass(frozen=True, slots=True)
class ExtractedTransaction:
    kind: str
    amount: Decimal
    description: str
    account_name: str | None = None
    category_name: str | None = None
    source_account_name: str | None = None
    destination_account_name: str | None = None


@runtime_checkable
class TransactionExtractor(Protocol):
    """Contract shared by deterministic and model-backed extractors."""

    def extract(self, text: str) -> ExtractedTransaction:
        """Extract a transaction or raise ``TextExtractionError``."""
        ...


_TRANSACTION_PATTERN = re.compile(
    r"^(?P<kind>gasto|gastei|paguei|despesa|receita|ganho|ganhei|recebi)\s+"
    r"(?:de\s+)?(?:r\$\s*)?"
    r"(?P<amount>\d+(?:[.,]\d{1,2})?)"
    r"(?:\s+(?:reais?|brl))?"
    r"(?:\s+(?P<description>.+))?$",
    flags=re.IGNORECASE,
)

_TRANSFER_PATTERN = re.compile(
    r"^(?:transferi|transfer[eê]ncia)\s+(?:de\s+)?(?:r\$\s*)?"
    r"(?P<amount>\d+(?:[.,]\d{1,2})?)"
    r"(?:\s+(?:reais?|brl))?\s+d[oa]\s+(?P<source>.+?)\s+para\s+(?:[oa]\s+)?(?P<destination>.+)$",
    flags=re.IGNORECASE,
)


class DeterministicTransactionExtractor:
    """Extract the transaction grammar supported without external services."""

    def extract(self, text: str) -> ExtractedTransaction:
        if not isinstance(text, str):
            raise TextExtractionError("Transaction text must be a string.")

        transfer_match = _TRANSFER_PATTERN.fullmatch(text.strip())
        if transfer_match is not None:
            try:
                amount = Decimal(transfer_match.group("amount").replace(",", "."))
            except InvalidOperation as exc:
                raise TextExtractionError("Invalid transfer amount.") from exc
            if amount <= 0 or amount > Decimal("999999999999.99"):
                raise TextExtractionError("Transfer amount is outside valid bounds.")
            source = transfer_match.group("source").strip()
            destination = transfer_match.group("destination").strip()
            if source.casefold() == destination.casefold():
                raise TextExtractionError("Transfer accounts must be different.")
            return ExtractedTransaction(
                kind=TransactionKind.TRANSFER,
                amount=amount.quantize(Decimal("0.01")),
                description=f"Transferência de {source} para {destination}",
                source_account_name=source,
                destination_account_name=destination,
            )

        match = _TRANSACTION_PATTERN.fullmatch(text.strip())
        if match is None:
            raise TextExtractionError("Unsupported transaction text format.")

        try:
            amount = Decimal(match.group("amount").replace(",", "."))
        except InvalidOperation as exc:
            raise TextExtractionError("Invalid transaction amount.") from exc

        if amount <= 0 or amount > Decimal("999999999999.99"):
            raise TextExtractionError("Transaction amount is outside valid bounds.")

        raw_kind = match.group("kind").lower()
        kind = (
            TransactionKind.INCOME
            if raw_kind in {"receita", "ganho", "ganhei", "recebi"}
            else TransactionKind.EXPENSE
        )
        raw_description = match.group("description")
        description = (
            raw_description.strip()
            if raw_description
            else ("Receita" if kind == TransactionKind.INCOME else "Despesa")
        )
        if len(description) > 255:
            raise TextExtractionError("Invalid transaction description.")

        return ExtractedTransaction(
            kind=kind,
            amount=amount.quantize(Decimal("0.01")),
            description=description,
        )


class FallbackTransactionExtractor:
    def __init__(self, *, primary: TransactionExtractor, fallback: TransactionExtractor):
        self.primary = primary
        self.fallback = fallback

    def extract(self, text: str) -> ExtractedTransaction:
        try:
            return self.primary.extract(text)
        except TextExtractionError:
            return self.fallback.extract(text)


def get_transaction_extractor() -> TransactionExtractor:
    from django.conf import settings
    from django.core.exceptions import ImproperlyConfigured

    backend = settings.TRANSACTION_EXTRACTOR_BACKEND
    if backend == "deterministic":
        return DeterministicTransactionExtractor()
    if backend in {"openai", "hybrid"}:
        if not settings.OPENAI_API_KEY:
            if backend == "hybrid":
                return DeterministicTransactionExtractor()
            raise ImproperlyConfigured(
                "OPENAI_API_KEY is required for the OpenAI transaction extractor."
            )
        from .ai_extraction import AITransactionExtractor
        from .openai_extraction import OpenAIStructuredTransactionProvider

        ai_extractor = AITransactionExtractor(
            provider=OpenAIStructuredTransactionProvider(
                api_key=settings.OPENAI_API_KEY,
                model=settings.OPENAI_TRANSACTION_MODEL,
                timeout=settings.OPENAI_API_TIMEOUT_SECONDS,
            )
        )
        if backend == "hybrid":
            return FallbackTransactionExtractor(
                primary=DeterministicTransactionExtractor(),
                fallback=ai_extractor,
            )
        return ai_extractor
    raise ImproperlyConfigured(
        f"Unsupported TRANSACTION_EXTRACTOR_BACKEND: {backend!r}."
    )


def extract_transaction_from_text(text: str) -> ExtractedTransaction:
    """Compatibility entry point for callers that only have plain text."""
    return DeterministicTransactionExtractor().extract(text)
