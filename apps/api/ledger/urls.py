from django.urls import path

from .views import DashboardSummaryView

app_name = "ledger"

urlpatterns = [
    path("dashboard/summary/", DashboardSummaryView.as_view(), name="dashboard-summary"),
]
