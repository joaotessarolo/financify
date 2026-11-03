from decimal import Decimal

from django.db import transaction as db_transaction
from django.utils import timezone

from .models import EntrySide, Transaction, TransactionStatus


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
