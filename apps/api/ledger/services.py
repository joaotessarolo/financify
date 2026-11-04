from decimal import Decimal

from dataclasses import dataclass

from django.db import IntegrityError, transaction as db_transaction
from django.utils import timezone

from .models import (
    Account,
    AccountSystemRole,
    AccountType,
    EntrySide,
    Transaction,
    TransactionStatus,
)


@dataclass(frozen=True, slots=True)
class DefaultAccounts:
    primary: Account
    general_expense: Account
    general_income: Account


_DEFAULT_ACCOUNT_SPECS = (
    (AccountSystemRole.PRIMARY, "Conta principal", AccountType.ASSET),
    (
        AccountSystemRole.GENERAL_EXPENSE,
        "Despesas gerais",
        AccountType.EXPENSE,
    ),
    (
        AccountSystemRole.GENERAL_INCOME,
        "Receitas gerais",
        AccountType.INCOME,
    ),
)


def _get_or_create_default_account(
    *, user, system_role: str, name: str, account_type: str
) -> Account:
    account = Account.objects.filter(
        user=user,
        system_role=system_role,
    ).first()
    if account is not None:
        return account

    try:
        with db_transaction.atomic():
            return Account.objects.create(
                user=user,
                name=name,
                account_type=account_type,
                currency=user.currency,
                system_role=system_role,
            )
    except IntegrityError:
        return Account.objects.get(user=user, system_role=system_role)


def ensure_default_accounts(*, user) -> DefaultAccounts:
    accounts = {
        role: _get_or_create_default_account(
            user=user,
            system_role=role,
            name=name,
            account_type=account_type,
        )
        for role, name, account_type in _DEFAULT_ACCOUNT_SPECS
    }
    return DefaultAccounts(
        primary=accounts[AccountSystemRole.PRIMARY],
        general_expense=accounts[AccountSystemRole.GENERAL_EXPENSE],
        general_income=accounts[AccountSystemRole.GENERAL_INCOME],
    )


class TransactionPostingError(Exception):
    pass


@db_transaction.atomic
def post_transaction(*, transaction: Transaction) -> Transaction:
    locked_transaction = (
        Transaction.objects.select_for_update().get(pk=transaction.pk)
    )

    if locked_transaction.status != TransactionStatus.DRAFT:
        raise TransactionPostingError(
            "Only draft transactions can be posted."
        )

    entries = list(
        locked_transaction.entries.select_related("account").all()
    )

    if len(entries) < 2:
        raise TransactionPostingError(
            "A transaction must have at least two entries."
        )

    debit_total = Decimal("0.00")
    credit_total = Decimal("0.00")

    for entry in entries:
        account = entry.account

        if account.user_id != locked_transaction.user_id:
            raise TransactionPostingError(
                "All entry accounts must belong to the transaction owner."
            )

        if account.currency != locked_transaction.currency:
            raise TransactionPostingError(
                "All entry accounts must match the transaction currency."
            )

        if not account.is_active:
            raise TransactionPostingError(
                "All entry accounts must be active."
            )

        if entry.side == EntrySide.DEBIT:
            debit_total += entry.amount
        elif entry.side == EntrySide.CREDIT:
            credit_total += entry.amount

    if debit_total != credit_total:
        raise TransactionPostingError(
            "Transaction entries must balance (total debits must equal total credits)."
        )

    locked_transaction.status = TransactionStatus.POSTED
    locked_transaction.posted_at = timezone.now()
    locked_transaction.save(update_fields=["status", "posted_at", "updated_at"])

    return locked_transaction
