from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re

from django.db import transaction as db_transaction

from ledger.models import AccountSystemRole
from ledger.services import ensure_default_accounts, record_opening_balance

from .models import TelegramIdentity, TelegramOnboardingStep


class OnboardingParseError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AccountSetupInput:
    name: str
    balance: Decimal | None


_BALANCE_PATTERN = re.compile(
    r"(?P<amount>[+-]?[\d.]+(?:,\d{1,2})?|[+-]?\d+(?:\.\d{1,2})?)"
    r"\s*(?P<thousand>mil)?",
    re.IGNORECASE,
)


def parse_balance(text: str) -> Decimal:
    normalized = text.strip().lower()
    normalized = re.sub(r"\b(reais?|brl)\b", "", normalized)
    normalized = normalized.replace("r$", "").strip()
    match = _BALANCE_PATTERN.fullmatch(normalized)
    if match is None:
        raise OnboardingParseError("Invalid balance.")

    raw = match.group("amount")
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"[+-]?\d{1,3}(?:\.\d{3})+", raw):
        raw = raw.replace(".", "")
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise OnboardingParseError("Invalid balance.") from exc
    if match.group("thousand"):
        value *= 1000
    if abs(value) > Decimal("999999999999.99"):
        raise OnboardingParseError("Balance is outside valid bounds.")
    return value.quantize(Decimal("0.01"))


def parse_account_setup(text: str) -> AccountSetupInput:
    normalized = text.strip()
    if not normalized:
        raise OnboardingParseError("Account name is required.")

    separator = re.search(r"\s*(?:,|\bcom\b|\bsaldo(?:\s+de)?\b)\s*", normalized, re.I)
    if separator is None:
        name, balance = normalized, None
    else:
        name = normalized[: separator.start()].strip(" ,")
        remainder = normalized[separator.end() :].strip(" ,")
        remainder = re.sub(r"^(?:BRL|R\$)\s*", "", remainder, flags=re.I)
        remainder = remainder.strip(" ,")
        balance = parse_balance(remainder)
    if not name or len(name) > 120 or any(char.isdigit() for char in name):
        raise OnboardingParseError("Invalid account name.")
    return AccountSetupInput(name=name, balance=balance)


@db_transaction.atomic
def remember_primary_account_name(
    *, identity: TelegramIdentity, account_name: str
) -> TelegramIdentity:
    locked = TelegramIdentity.objects.select_for_update().get(pk=identity.pk)
    locked.pending_account_name = account_name
    locked.onboarding_step = TelegramOnboardingStep.AWAITING_BALANCE
    locked.save(
        update_fields=["pending_account_name", "onboarding_step", "updated_at"]
    )
    return locked


@db_transaction.atomic
def complete_account_onboarding(
    *, identity: TelegramIdentity, account_name: str, balance: Decimal
):
    locked = (
        TelegramIdentity.objects.select_for_update()
        .select_related("user")
        .get(pk=identity.pk)
    )
    if locked.onboarding_step == TelegramOnboardingStep.COMPLETED:
        return ensure_default_accounts(user=locked.user).primary

    defaults = ensure_default_accounts(user=locked.user)
    primary = defaults.primary
    primary.name = account_name
    primary.save(update_fields=["name", "updated_at"])
    record_opening_balance(account=primary, balance=balance)

    locked.onboarding_step = TelegramOnboardingStep.COMPLETED
    locked.pending_account_name = ""
    locked.save(
        update_fields=["onboarding_step", "pending_account_name", "updated_at"]
    )
    return primary
