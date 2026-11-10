from django.urls import path

from .views import AccountDetailView, AccountListCreateView, DashboardSummaryView

app_name = "ledger"

urlpatterns = [
    path("dashboard/summary/", DashboardSummaryView.as_view(), name="dashboard-summary"),
    path("accounts/", AccountListCreateView.as_view(), name="account-list"),
    path("accounts/<uuid:account_id>/", AccountDetailView.as_view(), name="account-detail"),
]
