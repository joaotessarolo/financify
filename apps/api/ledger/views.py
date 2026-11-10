from datetime import datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db.models import Sum
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from .budgets import monthly_category_spend
from .models import AccountSystemRole, AccountType, Budget, EntrySide, TransactionStatus
from .services import calculate_account_balance
from .serializers import AccountCreateSerializer, AccountSerializer, AccountUpdateSerializer


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
