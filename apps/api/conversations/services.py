from datetime import datetime, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import IntegrityError, transaction as db_transaction
from django.utils import timezone

from ledger.models import (
    AccountSystemRole,
    AccountType,
    Entry,
    EntrySide,
    Transaction,
    TransactionSource,
    TransactionStatus,
)
from ledger.services import (
    TransactionPostingError,
    ensure_default_accounts,
    post_transaction,
)

from .extraction import ExtractedTransaction, TransactionKind
from .models import (
    Conversation,
    ConversationStatus,
    DraftEntry,
    Message,
    MessageDirection,
    MessageStatus,
    MessageType,
    TransactionDraft,
    TransactionDraftStatus,
)


def get_or_create_active_conversation(*, user, channel: str) -> Conversation:
    conversation = Conversation.objects.filter(
        user=user,
        channel=channel,
        status=ConversationStatus.ACTIVE,
    ).first()
    if conversation is not None:
        return conversation

    try:
        with db_transaction.atomic():
            return Conversation.objects.create(user=user, channel=channel)
    except IntegrityError:
        return Conversation.objects.get(
            user=user,
            channel=channel,
            status=ConversationStatus.ACTIVE,
        )


@db_transaction.atomic
def record_completed_text_message(
    *,
    conversation: Conversation,
    direction: str,
    content: str,
) -> Message:
    message = Message.objects.create(
        conversation=conversation,
        direction=direction,
        message_type=MessageType.TEXT,
        status=MessageStatus.RECEIVED,
        content=content,
    )
    message.status = MessageStatus.PROCESSING
    message.save(update_fields=["status", "updated_at"])
    message.status = MessageStatus.COMPLETED
    message.processed_at = timezone.now()
    message.save(update_fields=["status", "processed_at", "updated_at"])
    return message


def record_completed_inbound_text_message(
    *, conversation: Conversation, content: str
) -> Message:
    return record_completed_text_message(
        conversation=conversation,
        direction=MessageDirection.INBOUND,
        content=content,
    )


def record_completed_outbound_text_message(
    *, conversation: Conversation, content: str
) -> Message:
    return record_completed_text_message(
        conversation=conversation,
        direction=MessageDirection.OUTBOUND,
        content=content,
    )


class DefaultAccountConfigurationError(Exception):
    pass


@db_transaction.atomic
def create_transaction_draft_from_extraction(
    *,
    source_message: Message,
    extraction: ExtractedTransaction,
    occurred_at: datetime,
    transaction_account=None,
) -> TransactionDraft:
    user = source_message.conversation.user
    ttl_seconds = settings.TRANSACTION_DRAFT_TTL_SECONDS
    if ttl_seconds <= 0:
        raise ImproperlyConfigured(
            "TRANSACTION_DRAFT_TTL_SECONDS must be greater than zero."
        )
    ensure_default_accounts(user=user)
    accounts = {
        account.system_role: account
        for account in user.accounts.filter(
            system_role__in=AccountSystemRole.values,
            is_active=True,
        )
    }
    required_roles = {
        AccountSystemRole.PRIMARY,
        AccountSystemRole.GENERAL_EXPENSE,
        AccountSystemRole.GENERAL_INCOME,
    }
    if not required_roles <= accounts.keys():
        raise DefaultAccountConfigurationError(
            "User does not have all active default accounts."
        )
    if any(account.currency != user.currency for account in accounts.values()):
        raise DefaultAccountConfigurationError(
            "Default account currencies do not match the user currency."
        )

    if transaction_account is None:
        transaction_account = accounts[AccountSystemRole.PRIMARY]
    if (
        transaction_account.user_id != user.id
        or transaction_account.account_type != AccountType.ASSET
        or not transaction_account.is_active
        or transaction_account.currency != user.currency
    ):
        raise DefaultAccountConfigurationError(
            "Transaction account must be an active asset owned by the user."
        )

    draft = TransactionDraft.objects.create(
        user=user,
        source_message=source_message,
        description=extraction.description,
        currency=user.currency,
        occurred_at=occurred_at,
        expires_at=timezone.now() + timedelta(seconds=ttl_seconds),
    )

    if extraction.kind == TransactionKind.EXPENSE:
        debit_account = accounts[AccountSystemRole.GENERAL_EXPENSE]
        credit_account = transaction_account
    elif extraction.kind == TransactionKind.INCOME:
        debit_account = transaction_account
        credit_account = accounts[AccountSystemRole.GENERAL_INCOME]
    else:
        raise ValueError("Unsupported extracted transaction kind.")

    DraftEntry.objects.bulk_create(
        [
            DraftEntry(
                draft=draft,
                account=debit_account,
                side=EntrySide.DEBIT,
                amount=extraction.amount,
            ),
            DraftEntry(
                draft=draft,
                account=credit_account,
                side=EntrySide.CREDIT,
                amount=extraction.amount,
            ),
        ]
    )
    return draft


class DraftConfirmationError(Exception):
    pass


class DraftExpiredError(DraftConfirmationError):
    pass


class DraftRejectionError(Exception):
    pass


class DraftEditingError(Exception):
    pass


def get_latest_pending_draft(*, user) -> TransactionDraft | None:
    return (
        TransactionDraft.objects.filter(
            user=user,
            status=TransactionDraftStatus.PENDING,
            expires_at__gt=timezone.now(),
        )
        .order_by("-created_at")
        .first()
    )


@db_transaction.atomic
def edit_transaction_draft(
    *,
    draft: TransactionDraft,
    amount: Decimal | None = None,
    description: str | None = None,
    transaction_account=None,
    kind: str | None = None,
) -> TransactionDraft:
    locked = TransactionDraft.objects.select_for_update().get(pk=draft.pk)
    if locked.status != TransactionDraftStatus.PENDING or locked.expires_at <= timezone.now():
        raise DraftEditingError("Only a non-expired pending draft can be edited.")

    if description is not None:
        description = description.strip()
        if not description or len(description) > 255:
            raise DraftEditingError("Invalid draft description.")
        locked.description = description
        locked.save(update_fields=["description", "updated_at"])

    entries = list(locked.entries.select_related("account"))
    if len(entries) != 2:
        raise DraftEditingError("Draft entries are invalid.")

    if amount is not None:
        if amount <= 0 or amount > Decimal("999999999999.99"):
            raise DraftEditingError("Invalid draft amount.")
        for entry in entries:
            entry.amount = amount.quantize(Decimal("0.01"))

    current_kind = (
        TransactionKind.EXPENSE
        if any(
            entry.account.system_role == AccountSystemRole.GENERAL_EXPENSE
            for entry in entries
        )
        else TransactionKind.INCOME
    )
    target_kind = kind or current_kind
    if target_kind not in {TransactionKind.EXPENSE, TransactionKind.INCOME}:
        raise DraftEditingError("Invalid transaction kind.")

    asset_entry = next(
        (entry for entry in entries if entry.account.account_type == AccountType.ASSET),
        None,
    )
    if asset_entry is None:
        raise DraftEditingError("Draft has no asset account.")
    account = transaction_account or asset_entry.account
    if (
        account.user_id != locked.user_id
        or account.account_type != AccountType.ASSET
        or not account.is_active
        or account.currency != locked.currency
    ):
        raise DraftEditingError("Invalid transaction account.")

    defaults = ensure_default_accounts(user=locked.user)
    if target_kind == TransactionKind.EXPENSE:
        asset_account, counterpart = account, defaults.general_expense
        asset_side, counterpart_side = EntrySide.CREDIT, EntrySide.DEBIT
    else:
        asset_account, counterpart = account, defaults.general_income
        asset_side, counterpart_side = EntrySide.DEBIT, EntrySide.CREDIT

    asset_entry.account = asset_account
    asset_entry.side = asset_side
    counterpart_entry = next(entry for entry in entries if entry.pk != asset_entry.pk)
    counterpart_entry.account = counterpart
    counterpart_entry.side = counterpart_side
    for entry in entries:
        entry.save(update_fields=["account", "side", "amount", "updated_at"])
    return locked


def reject_transaction_draft(*, draft: TransactionDraft) -> TransactionDraft:
    expired = False
    with db_transaction.atomic():
        locked_draft = TransactionDraft.objects.select_for_update().get(
            pk=draft.pk
        )
        if locked_draft.status == TransactionDraftStatus.REJECTED:
            return locked_draft
        if locked_draft.status != TransactionDraftStatus.PENDING:
            raise DraftRejectionError(
                "Only pending transaction drafts can be rejected."
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
            locked_draft.status = TransactionDraftStatus.REJECTED
            locked_draft.resolved_at = now
            locked_draft.save(
                update_fields=["status", "resolved_at", "updated_at"]
            )
            return locked_draft

    if expired:
        raise DraftRejectionError("Transaction draft has expired.")


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
