from django.urls import path

from .views import TelegramLinkView

app_name = "telegram_bot"

urlpatterns = [
    path("link/", TelegramLinkView.as_view(), name="link"),
]
