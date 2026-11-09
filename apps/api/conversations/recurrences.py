from datetime import date, timedelta
from decimal import Decimal
import re

from django.db import transaction as db_transaction
from django.utils import timezone

from ledger.categories import classify_category
from ledger.services import ensure_default_accounts

from .extraction import ExtractedTransaction, TransactionKind
from .models import (
    ConversationChannel,
    MessageType,
    RecurringTransaction,
)
from .services import (
    create_transaction_draft_from_extraction,
    get_or_create_active_conversation,
    record_completed_inbound_text_message,
)


class RecurrenceError(ValueError):
    pass


def parse_recurrence(text: str):
    match = re.fullmatch(
        r"criar\s+recorr[eê]ncia\s+(?P<kind>gasto|despesa|receita|ganho)\s+"
        r"(?P<amount>\d+(?:[.,]\d{1,2})?)\s+(?P<description>.+?)\s+"
        r"todo\s+dia\s+(?P<day>\d{1,2})",
        text.strip(),
        flags=re.I,
    )
    if match is None:
        return None
    day = int(match.group("day"))
    if day < 1 or day > 28:
        raise RecurrenceError("Recurring day must be between 1 and 28.")
    amount = Decimal(match.group("amount").replace(",", "."))
    if amount <= 0:
        raise RecurrenceError("Recurring amount must be positive.")
    kind = (
        TransactionKind.INCOME
        if match.group("kind").casefold() in {"receita", "ganho"}
        else TransactionKind.EXPENSE
    )
    return kind, amount.quantize(Decimal("0.01")), match.group("description"), day


def _next_date(*, day: int, reference: date) -> date:
    if reference.day <= day:
        return reference.replace(day=day)
    month = 1 if reference.month == 12 else reference.month + 1
    year = reference.year + 1 if reference.month == 12 else reference.year
    return date(year, month, day)


def create_recurrence(*, user, kind: str, amount: Decimal, description: str, day: int):
    account = ensure_default_accounts(user=user).primary
    return RecurringTransaction.objects.create(
        user=user,
        kind=kind,
        amount=amount,
        description=description.strip(),
        account=account,
        category=classify_category(user=user, description=description),
        day_of_month=day,
        next_run_on=_next_date(day=day, reference=timezone.localdate()),
    )


@db_transaction.atomic
def generate_due_draft(*, recurrence: RecurringTransaction, run_date: date):
    locked = RecurringTransaction.objects.select_for_update(of=("self",)).select_related(
        "user", "account", "category"
    ).get(pk=recurrence.pk)
    if not locked.is_active or locked.next_run_on > run_date:
        return None
    conversation = get_or_create_active_conversation(
        user=locked.user, channel=ConversationChannel.TELEGRAM
    )
    message = record_completed_inbound_text_message(
        conversation=conversation,
        content="Recorrência mensal",
        message_type=MessageType.SYSTEM,
    )
    draft = create_transaction_draft_from_extraction(
        source_message=message,
        extraction=ExtractedTransaction(
            kind=locked.kind,
            amount=locked.amount,
            description=locked.description,
        ),
        occurred_at=timezone.now(),
        transaction_account=locked.account,
        category=locked.category,
    )
    locked.last_draft = draft
    locked.next_run_on = _next_date(
        day=locked.day_of_month,
        reference=run_date.replace(day=28) + timedelta(days=4),
    )
    locked.save(update_fields=["last_draft", "next_run_on", "updated_at"])
    return draft
