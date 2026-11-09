from datetime import datetime, time
from decimal import Decimal
import re
from zoneinfo import ZoneInfo

from django.db.models import Sum
from django.utils import timezone

from ledger.models import AccountSystemRole, EntrySide, TransactionStatus

from .accounts import find_asset_account


def _period_bounds(*, user, period: str):
    zone = ZoneInfo(user.timezone)
    local_now = timezone.now().astimezone(zone)
    if period == "today":
        start_date = local_now.date()
    else:
        start_date = local_now.date().replace(day=1)
    start = datetime.combine(start_date, time.min, tzinfo=zone)
    return start.astimezone(ZoneInfo("UTC")), local_now


def format_money(value: Decimal, currency: str) -> str:
    formatted = f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"{currency} {formatted}"


def expense_summary(*, user, period: str) -> str:
    start, _ = _period_bounds(user=user, period=period)
    total = (
        user.transactions.filter(
            status=TransactionStatus.POSTED,
            occurred_at__gte=start,
            occurred_at__lte=timezone.now(),
            entries__account__system_role=AccountSystemRole.GENERAL_EXPENSE,
            entries__side=EntrySide.DEBIT,
        ).aggregate(total=Sum("entries__amount"))["total"]
        or Decimal("0.00")
    )
    label = "hoje" if period == "today" else "neste mês"
    return f"Você gastou {format_money(total, user.currency)} {label}."


def account_statement(*, user, account_name: str, limit: int = 10) -> str | None:
    account = find_asset_account(user=user, name=account_name)
    if account is None:
        return None
    entries = list(
        account.entries.filter(transaction__status=TransactionStatus.POSTED)
        .select_related("transaction")
        .order_by("-transaction__occurred_at", "-created_at")[:limit]
    )
    if not entries:
        return f"Ainda não há movimentações confirmadas em {account.name}."
    lines = [f"Últimas movimentações de {account.name}:"]
    for entry in entries:
        signal = "+" if entry.side == EntrySide.DEBIT else "-"
        date = entry.transaction.occurred_at.astimezone(
            ZoneInfo(user.timezone)
        ).strftime("%d/%m")
        lines.append(
            f"• {date} · {signal}{format_money(entry.amount, account.currency)} · "
            f"{entry.transaction.description}"
        )
    return "\n".join(lines)


def handle_financial_query(*, user, text: str) -> str | None:
    normalized = " ".join(text.strip().casefold().rstrip("?").split())
    if normalized in {"meus gastos de hoje", "quanto gastei hoje"}:
        return expense_summary(user=user, period="today")
    if normalized in {
        "meus gastos deste mes",
        "meus gastos deste mês",
        "quanto gastei este mes",
        "quanto gastei este mês",
        "quanto gastei neste mes",
        "quanto gastei neste mês",
    }:
        return expense_summary(user=user, period="month")
    match = re.fullmatch(r"extrato\s+(?:do|da)\s+(.+)", text.strip(), flags=re.I)
    if match:
        return account_statement(user=user, account_name=match.group(1)) or (
            f"Não encontrei a conta “{match.group(1)}”."
        )
    return None
