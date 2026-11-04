from dataclasses import dataclass
from decimal import Decimal

from django.db import IntegrityError, transaction as db_transaction
from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import (
    Account,
    AccountSystemRole,
    AccountType,
    Entry,
    EntrySide,
    Transaction,
    TransactionSource,
    TransactionStatus,
)


@dataclass(frozen=True, slots=True)
class DefaultAccounts:
    primary: Account
    general_expense: Account
    general_income: Account
    opening_balance: Account


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
    (
        AccountSystemRole.OPENING_BALANCE,
        "Patrimônio inicial",
        AccountType.EQUITY,
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
        opening_balance=accounts[AccountSystemRole.OPENING_BALANCE],
    )


class OpeningBalanceError(Exception):
    pass


@db_transaction.atomic
def record_opening_balance(
    *, account: Account, balance: Decimal, occurred_at=None
) -> Transaction:
    locked_account = Account.objects.select_for_update().select_related("user").get(
        pk=account.pk
    )
    if locked_account.opening_balance_transaction_id is not None:
        raise OpeningBalanceError("Opening balance has already been recorded.")
    if locked_account.account_type != AccountType.ASSET:
        raise OpeningBalanceError("Opening balances currently require an asset account.")

    defaults = ensure_default_accounts(user=locked_account.user)
    equity_account = defaults.opening_balance
    if locked_account.currency != equity_account.currency:
        raise OpeningBalanceError("Opening balance accounts must use the same currency.")

    transaction = Transaction.objects.create(
        user=locked_account.user,
        description=f"Saldo inicial — {locked_account.name}",
        currency=locked_account.currency,
        occurred_at=occurred_at or timezone.now(),
        source=TransactionSource.MANUAL,
    )
    current_balance = calculate_account_balance(account=locked_account)
    adjustment = balance - current_balance
    amount = abs(adjustment)
    if amount > 0:
        if adjustment > 0:
            account_side, equity_side = EntrySide.DEBIT, EntrySide.CREDIT
        else:
            account_side, equity_side = EntrySide.CREDIT, EntrySide.DEBIT
        Entry.objects.bulk_create(
            [
                Entry(
                    transaction=transaction,
                    account=locked_account,
                    side=account_side,
                    amount=amount,
                ),
                Entry(
                    transaction=transaction,
                    account=equity_account,
                    side=equity_side,
                    amount=amount,
                ),
            ]
        )
    else:
        # A zero balance still needs an auditable, idempotent opening marker.
        transaction.status = TransactionStatus.POSTED
        transaction.posted_at = timezone.now()
        transaction.save(update_fields=["status", "posted_at", "updated_at"])

    if amount > 0:
        transaction = post_transaction(transaction=transaction)
    locked_account.opening_balance_transaction = transaction
    locked_account.save(
        update_fields=["opening_balance_transaction", "updated_at"]
    )
    return transaction


def calculate_account_balance(*, account: Account) -> Decimal:
    totals = account.entries.aggregate(
        debits=Coalesce(
            Sum("amount", filter=Q(side=EntrySide.DEBIT)),
            Decimal("0.00"),
        ),
        credits=Coalesce(
            Sum("amount", filter=Q(side=EntrySide.CREDIT)),
            Decimal("0.00"),
        ),
    )
    if account.account_type in {AccountType.ASSET, AccountType.EXPENSE}:
        return totals["debits"] - totals["credits"]
    return totals["credits"] - totals["debits"]


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
