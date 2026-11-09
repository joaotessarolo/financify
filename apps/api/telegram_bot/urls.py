from django.urls import path

from .views import TelegramLinkView, TelegramMetricsView, TelegramWebhookView

app_name = "telegram_bot"

urlpatterns = [
    path("link/", TelegramLinkView.as_view(), name="link"),
    path("webhook/", TelegramWebhookView.as_view(), name="webhook"),
    path("metrics/", TelegramMetricsView.as_view(), name="metrics"),
]
