from datetime import datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db.models import Sum
from django.utils import timezone

from .categories import find_category
from .models import AccountSystemRole, Budget, EntrySide, TransactionStatus


def set_budget(*, user, category_name: str, monthly_limit: Decimal) -> Budget:
    if monthly_limit <= 0 or monthly_limit > Decimal("999999999999.99"):
        raise ValueError("Invalid budget limit.")
    category = find_category(user=user, name=category_name)
    if category is None:
        raise ValueError("Category not found.")
    budget, _ = Budget.objects.update_or_create(
        user=user,
        category=category,
        defaults={"monthly_limit": monthly_limit, "is_active": True},
    )
    return budget


def monthly_category_spend(*, budget: Budget) -> Decimal:
    zone = ZoneInfo(budget.user.timezone)
    local_now = timezone.now().astimezone(zone)
    start = datetime.combine(
        local_now.date().replace(day=1), time.min, tzinfo=zone
    ).astimezone(ZoneInfo("UTC"))
    return (
        budget.user.transactions.filter(
            category=budget.category,
            status=TransactionStatus.POSTED,
            occurred_at__gte=start,
            occurred_at__lte=timezone.now(),
            entries__account__system_role=AccountSystemRole.GENERAL_EXPENSE,
            entries__side=EntrySide.DEBIT,
        ).aggregate(total=Sum("entries__amount"))["total"]
        or Decimal("0.00")
    )


def budget_alert_for_transaction(*, transaction) -> str | None:
    if transaction.category_id is None:
        return None
    budget = Budget.objects.select_related("user", "category").filter(
        user_id=transaction.user_id,
        category_id=transaction.category_id,
        is_active=True,
    ).first()
    if budget is None:
        return None
    spent = monthly_category_spend(budget=budget)
    percentage = spent / budget.monthly_limit * 100
    if percentage < 80:
        return None
    if percentage >= 100:
        return (
            f"Atenção: você usou {percentage:.0f}% do orçamento de "
            f"{budget.category.name}."
        )
    return (
        f"Aviso: você já usou {percentage:.0f}% do orçamento de "
        f"{budget.category.name}."
    )
