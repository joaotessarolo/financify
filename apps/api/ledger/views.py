from datetime import datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db.models import Count, Q, Sum
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from .budgets import monthly_category_spend
from .models import AccountSystemRole, AccountType, Budget, EntrySide, TransactionStatus
from .services import calculate_account_balance
from .serializers import AccountCreateSerializer, AccountSerializer, AccountUpdateSerializer, BudgetSerializer, CategorySerializer, RecurringTransactionSerializer, TransactionSerializer, TransactionUpdateSerializer
from conversations.extraction import TransactionKind
from conversations.recurrences import create_recurrence


class DashboardSummaryView(APIView):
    def get(self, request):
        user = request.user
        zone = ZoneInfo(user.timezone)
        local_now = timezone.now().astimezone(zone)
        month_start = datetime.combine(
            local_now.date().replace(day=1), time.min, tzinfo=zone
        ).astimezone(ZoneInfo("UTC"))
        accounts = list(
            user.accounts.filter(account_type=AccountType.ASSET, is_active=True)
            .order_by("created_at")
        )
        balances = [
            {
                "id": str(account.id),
                "name": account.name,
                "currency": account.currency,
                "balance": calculate_account_balance(account=account),
            }
            for account in accounts
        ]
        posted = user.transactions.filter(
            status=TransactionStatus.POSTED,
            occurred_at__gte=month_start,
            occurred_at__lte=timezone.now(),
        )
        income = posted.filter(
            entries__account__system_role=AccountSystemRole.GENERAL_INCOME,
            entries__side=EntrySide.CREDIT,
        ).aggregate(total=Sum("entries__amount"))["total"] or Decimal("0.00")
        expenses = posted.filter(
            entries__account__system_role=AccountSystemRole.GENERAL_EXPENSE,
            entries__side=EntrySide.DEBIT,
        ).aggregate(total=Sum("entries__amount"))["total"] or Decimal("0.00")
        spending_by_category = (
            posted.filter(
                entries__account__system_role=AccountSystemRole.GENERAL_EXPENSE,
                entries__side=EntrySide.DEBIT,
            )
            .values("category__name")
            .annotate(
                total=Sum(
                    "entries__amount",
                    filter=Q(
                        entries__account__system_role=AccountSystemRole.GENERAL_EXPENSE,
                        entries__side=EntrySide.DEBIT,
                    ),
                )
            )
            .order_by("-total")[:6]
        )
        recent = user.transactions.filter(status=TransactionStatus.POSTED).select_related(
            "category"
        ).order_by("-occurred_at")[:10]
        budgets = Budget.objects.filter(user=user, is_active=True).select_related(
            "category", "user"
        )
        recurrences = user.recurring_transactions.filter(is_active=True).order_by(
            "next_run_on"
        )[:5]
        return Response(
            {
                "currency": user.currency,
                "total_balance": sum(
                    (item["balance"] for item in balances), Decimal("0.00")
                ),
                "accounts": balances,
                "month": {
                    "income": income,
                    "expenses": expenses,
                    "net": income - expenses,
                },
                "spending_by_category": [
                    {
                        "category": item["category__name"] or "Sem categoria",
                        "amount": item["total"],
                    }
                    for item in spending_by_category
                ],
                "recent_transactions": [
                    {
                        "id": str(item.id),
                        "description": item.description,
                        "amount": next(iter(item.entries.values_list("amount", flat=True)), Decimal("0.00")),
                        "category": item.category.name if item.category else None,
                        "occurred_at": item.occurred_at,
                    }
                    for item in recent
                ],
                "budgets": [
                    {
                        "category": item.category.name,
                        "limit": item.monthly_limit,
                        "spent": monthly_category_spend(budget=item),
                    }
                    for item in budgets
                ],
                "upcoming_recurrences": [
                    {
                        "id": str(item.id),
                        "description": item.description,
                        "amount": item.amount,
                        "next_run_on": item.next_run_on,
                    }
                    for item in recurrences
                ],
            }
        )


class AccountListCreateView(APIView):
    def get(self, request):
        accounts = request.user.accounts.filter(
            account_type=AccountType.ASSET, is_active=True
        ).order_by("created_at")
        return Response(AccountSerializer(accounts, many=True).data)

    def post(self, request):
        serializer = AccountCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        account = serializer.save()
        return Response(AccountSerializer(account).data, status=201)


class AccountDetailView(APIView):
    def get_account(self, request, account_id):
        return request.user.accounts.filter(
            pk=account_id, account_type=AccountType.ASSET, is_active=True
        ).first()

    def patch(self, request, account_id):
        account = self.get_account(request, account_id)
        if account is None:
            return Response(status=404)
        serializer = AccountUpdateSerializer(
            account, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(AccountSerializer(account).data)

    def delete(self, request, account_id):
        account = self.get_account(request, account_id)
        if account is None:
            return Response(status=404)
        if account.system_role == AccountSystemRole.PRIMARY:
            return Response(
                {"detail": "The primary account cannot be archived."}, status=400
            )
        account.is_active = False
        account.save(update_fields=["is_active", "updated_at"])
        return Response(status=204)

class TransactionListView(APIView):
    def get(self, request):
        transactions = request.user.transactions.filter(
            status=TransactionStatus.POSTED
        )
        search = request.query_params.get("q", "").strip()
        kind = request.query_params.get("kind", "").upper()
        account_id = request.query_params.get("account", "")
        if search:
            transactions = transactions.filter(description__icontains=search)
        if kind == "EXPENSE":
            transactions = transactions.filter(
                entries__account__system_role=AccountSystemRole.GENERAL_EXPENSE
            )
        elif kind == "INCOME":
            transactions = transactions.filter(
                entries__account__system_role=AccountSystemRole.GENERAL_INCOME
            )
        elif kind == "TRANSFER":
            transactions = transactions.exclude(
                entries__account__system_role__in=[
                    AccountSystemRole.GENERAL_EXPENSE,
                    AccountSystemRole.GENERAL_INCOME,
                ]
            )
        if account_id:
            transactions = transactions.filter(
                entries__account_id=account_id,
                entries__account__account_type=AccountType.ASSET,
            )
        if request.query_params.get("from"):
            transactions = transactions.filter(occurred_at__date__gte=request.query_params["from"])
        if request.query_params.get("to"):
            transactions = transactions.filter(occurred_at__date__lte=request.query_params["to"])
        transactions = transactions.distinct().select_related("category").prefetch_related("entries__account").order_by(
            "-occurred_at", "-created_at"
        )[:100]
        return Response(TransactionSerializer(transactions, many=True).data)


class TransactionDetailView(APIView):
    def get_transaction(self, request, transaction_id):
        return request.user.transactions.filter(
            pk=transaction_id, status=TransactionStatus.POSTED
        ).select_related("category").prefetch_related("entries__account").first()

    def get(self, request, transaction_id):
        transaction = self.get_transaction(request, transaction_id)
        if transaction is None:
            return Response(status=404)
        return Response(TransactionSerializer(transaction).data)

    def patch(self, request, transaction_id):
        transaction = self.get_transaction(request, transaction_id)
        if transaction is None:
            return Response(status=404)
        serializer = TransactionUpdateSerializer(transaction, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(TransactionSerializer(transaction).data)


class CategoryListCreateView(APIView):
    def get(self, request):
        categories = request.user.categories.filter(is_active=True).annotate(
            transaction_count=Count("transactions")
        ).order_by("name")
        return Response(CategorySerializer(categories, many=True).data)

    def post(self, request):
        serializer = CategorySerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        category = serializer.save()
        return Response(CategorySerializer(category).data, status=201)


class CategoryDetailView(APIView):
    def get_category(self, request, category_id):
        return request.user.categories.filter(pk=category_id, is_active=True).first()

    def patch(self, request, category_id):
        category = self.get_category(request, category_id)
        if category is None:
            return Response(status=404)
        serializer = CategorySerializer(
            category, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(CategorySerializer(category).data)

    def delete(self, request, category_id):
        category = self.get_category(request, category_id)
        if category is None:
            return Response(status=404)
        category.is_active = False
        category.save(update_fields=["is_active", "updated_at"])
        return Response(status=204)


class BudgetListCreateView(APIView):
    def get(self, request):
        budgets = request.user.budgets.filter(is_active=True).select_related(
            "category", "user"
        ).order_by("category__name")
        return Response(BudgetSerializer(budgets, many=True).data)

    def post(self, request):
        category = request.user.categories.filter(
            pk=request.data.get("category_id"), is_active=True
        ).first()
        if category is None:
            return Response({"category_id": ["Invalid category."]}, status=400)
        try:
            limit = Decimal(str(request.data.get("monthly_limit")))
        except Exception:
            return Response({"monthly_limit": ["Invalid limit."]}, status=400)
        if limit <= 0:
            return Response({"monthly_limit": ["Limit must be positive."]}, status=400)
        budget, _ = Budget.objects.update_or_create(
            user=request.user,
            category=category,
            defaults={"monthly_limit": limit, "is_active": True},
        )
        return Response(BudgetSerializer(budget).data, status=201)


class BudgetDetailView(APIView):
    def delete(self, request, budget_id):
        budget = request.user.budgets.filter(pk=budget_id, is_active=True).first()
        if budget is None:
            return Response(status=404)
        budget.is_active = False
        budget.save(update_fields=["is_active", "updated_at"])
        return Response(status=204)


class RecurrenceListCreateView(APIView):
    def get(self, request):
        items = request.user.recurring_transactions.select_related(
            "account", "category"
        ).order_by("day_of_month", "description")
        return Response(RecurringTransactionSerializer(items, many=True).data)

    def post(self, request):
        kind = str(request.data.get("kind", "")).upper()
        if kind not in {TransactionKind.EXPENSE, TransactionKind.INCOME}:
            return Response({"kind": ["Invalid kind."]}, status=400)
        try:
            amount = Decimal(str(request.data.get("amount")))
            day = int(request.data.get("day_of_month"))
        except Exception:
            return Response({"detail": "Invalid amount or day."}, status=400)
        if amount <= 0 or day < 1 or day > 28:
            return Response({"detail": "Amount must be positive and day between 1 and 28."}, status=400)
        description = str(request.data.get("description", "")).strip()
        if not description:
            return Response({"description": ["This field is required."]}, status=400)
        item = create_recurrence(
            user=request.user, kind=kind, amount=amount, description=description, day=day
        )
        return Response(RecurringTransactionSerializer(item).data, status=201)


class RecurrenceDetailView(APIView):
    def patch(self, request, recurrence_id):
        item = request.user.recurring_transactions.filter(pk=recurrence_id).first()
        if item is None:
            return Response(status=404)
        if "is_active" in request.data:
            item.is_active = request.data["is_active"] in {True, "true", "True", "1", 1}
            item.save(update_fields=["is_active", "updated_at"])
        return Response(RecurringTransactionSerializer(item).data)

    def delete(self, request, recurrence_id):
        item = request.user.recurring_transactions.filter(pk=recurrence_id).first()
        if item is None:
            return Response(status=404)
        item.delete()
        return Response(status=204)
