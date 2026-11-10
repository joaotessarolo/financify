from django.urls import path

from .views import AccountDetailView, AccountListCreateView, CategoryDetailView, CategoryListCreateView, DashboardSummaryView, TransactionDetailView, TransactionListView

app_name = "ledger"

urlpatterns = [
    path("dashboard/summary/", DashboardSummaryView.as_view(), name="dashboard-summary"),
    path("accounts/", AccountListCreateView.as_view(), name="account-list"),
    path("accounts/<uuid:account_id>/", AccountDetailView.as_view(), name="account-detail"),
    path("transactions/", TransactionListView.as_view(), name="transaction-list"),
    path("transactions/<uuid:transaction_id>/", TransactionDetailView.as_view(), name="transaction-detail"),
    path("categories/", CategoryListCreateView.as_view(), name="category-list"),
    path("categories/<uuid:category_id>/", CategoryDetailView.as_view(), name="category-detail"),
]
