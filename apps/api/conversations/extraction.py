from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re


class TextExtractionError(ValueError):
    pass


class TransactionKind:
    EXPENSE = "EXPENSE"
    INCOME = "INCOME"


@dataclass(frozen=True, slots=True)
class ExtractedTransaction:
    kind: str
    amount: Decimal
    description: str


_TRANSACTION_PATTERN = re.compile(
    r"^(?P<kind>gasto|gastei|despesa|receita|ganho|ganhei)\s+"
    r"(?:de\s+)?(?:r\$\s*)?"
    r"(?P<amount>\d+(?:[.,]\d{1,2})?)"
    r"(?:\s+(?:reais?|brl))?"
    r"(?:\s+(?P<description>.+))?$",
    flags=re.IGNORECASE,
)


def extract_transaction_from_text(text: str) -> ExtractedTransaction:
    if not isinstance(text, str):
        raise TextExtractionError("Transaction text must be a string.")

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
        if raw_kind in {"receita", "ganho", "ganhei"}
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
