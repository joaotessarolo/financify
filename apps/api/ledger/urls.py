from django.urls import path

from .views import AccountListCreateView, DashboardSummaryView

app_name = "ledger"

urlpatterns = [
    path("dashboard/summary/", DashboardSummaryView.as_view(), name="dashboard-summary"),
    path("accounts/", AccountListCreateView.as_view(), name="account-list"),
]
