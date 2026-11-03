from django.db import transaction as db_transaction
from django.utils import timezone

from ledger.models import Entry, Transaction, TransactionSource, TransactionStatus
from ledger.services import TransactionPostingError, post_transaction

from .models import TransactionDraft, TransactionDraftStatus


class DraftConfirmationError(Exception):
    pass


class DraftExpiredError(DraftConfirmationError):
    pass


def confirm_transaction_draft(
    *,
    draft: TransactionDraft,
) -> Transaction:
    expired = False

    with db_transaction.atomic():
        locked_draft = (
            TransactionDraft.objects.select_for_update(of=("self",))
            .select_related("transaction")
            .get(pk=draft.pk)
        )

        if locked_draft.status == TransactionDraftStatus.CONFIRMED:
            return locked_draft.transaction

        if locked_draft.status != TransactionDraftStatus.PENDING:
            raise DraftConfirmationError(
                "Only pending transaction drafts can be confirmed."
            )

        now = timezone.now()
        if locked_draft.expires_at <= now:
            locked_draft.status = TransactionDraftStatus.EXPIRED
            locked_draft.resolved_at = now
            locked_draft.save(
                update_fields=["status", "resolved_at", "updated_at"]
            )
            expired = True
        else:
            ledger_transaction = Transaction.objects.create(
                user_id=locked_draft.user_id,
                description=locked_draft.description,
                currency=locked_draft.currency,
                occurred_at=locked_draft.occurred_at,
                status=TransactionStatus.DRAFT,
                source=TransactionSource.ASSISTANT,
            )

            draft_entries = list(locked_draft.entries.all())
            for draft_entry in draft_entries:
                Entry.objects.create(
                    transaction=ledger_transaction,
                    account_id=draft_entry.account_id,
                    side=draft_entry.side,
                    amount=draft_entry.amount,
                    memo=draft_entry.memo,
                )

            try:
                posted_transaction = post_transaction(
                    transaction=ledger_transaction
                )
            except TransactionPostingError as exc:
                raise DraftConfirmationError(str(exc)) from exc

            locked_draft.transaction = posted_transaction
            locked_draft.status = TransactionDraftStatus.CONFIRMED
            locked_draft.resolved_at = timezone.now()
            locked_draft.save(
                update_fields=[
                    "transaction",
                    "status",
                    "resolved_at",
                    "updated_at",
                ]
            )
            return posted_transaction

    if expired:
        raise DraftExpiredError("Transaction draft has expired.")
