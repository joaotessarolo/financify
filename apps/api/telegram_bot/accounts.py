from dataclasses import dataclass, replace
from decimal import Decimal
import re
import unicodedata

from django.db import transaction as db_transaction

from conversations.extraction import ExtractedTransaction
from ledger.models import Account, AccountType
from ledger.services import record_opening_balance

from .onboarding import OnboardingParseError, parse_account_setup, parse_balance


class TelegramAccountError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CreateAccountInput:
    name: str
    balance: Decimal


def normalize_account_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.strip().casefold())
    return "".join(char for char in normalized if not unicodedata.combining(char))


def parse_create_account(text: str) -> CreateAccountInput | None:
    match = re.fullmatch(r"criar\s+conta\s+(.+)", text.strip(), flags=re.I)
    if match is None:
        return None
    body = match.group(1)
    natural_match = re.fullmatch(
        r"(?P<name>.+?)\s+com\s+saldo(?:\s+de)?\s+(?P<balance>.+)",
        body,
        flags=re.I,
    )
    try:
        if natural_match is not None:
            setup = parse_account_setup(natural_match.group("name"))
            setup = replace(
                setup,
                balance=parse_balance(natural_match.group("balance")),
            )
        else:
            setup = parse_account_setup(body)
    except OnboardingParseError as exc:
        raise TelegramAccountError("Invalid account setup.") from exc
    if setup.balance is None:
        raise TelegramAccountError("Opening balance is required.")
    return CreateAccountInput(name=setup.name, balance=setup.balance)


@db_transaction.atomic
def create_asset_account(*, user, setup: CreateAccountInput) -> Account:
    if user.accounts.filter(name__iexact=setup.name, is_active=True).exists():
        raise TelegramAccountError("An active account with this name already exists.")
    account = Account.objects.create(
        user=user,
        name=setup.name,
        account_type=AccountType.ASSET,
        currency=user.currency,
    )
    record_opening_balance(account=account, balance=setup.balance)
    return account


def find_asset_account(*, user, name: str) -> Account | None:
    wanted = normalize_account_name(name)
    return next(
        (
            account
            for account in user.accounts.filter(
                account_type=AccountType.ASSET,
                is_active=True,
            )
            if normalize_account_name(account.name) == wanted
        ),
        None,
    )


def select_transaction_account(*, user, text: str, extraction: ExtractedTransaction):
    accounts = list(
        user.accounts.filter(account_type=AccountType.ASSET, is_active=True)
    )
    if extraction.account_name:
        account = find_asset_account(user=user, name=extraction.account_name)
        if account is None:
            raise TelegramAccountError("Mentioned account was not found.")
        return account, text, extraction

    normalized_text = normalize_account_name(text)
    for account in sorted(accounts, key=lambda item: len(item.name), reverse=True):
        normalized_name = normalize_account_name(account.name)
        for connector in ("pelo", "pela", "no", "na"):
            suffix = f" {connector} {normalized_name}"
            if normalized_text.endswith(suffix):
                cleaned = text[: len(text) - len(suffix)].rstrip(" ,")
                return account, cleaned, replace(extraction, account_name=account.name)
    return None, text, extraction
