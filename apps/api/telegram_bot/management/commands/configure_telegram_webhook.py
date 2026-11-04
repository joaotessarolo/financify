from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand, CommandError

from telegram_bot.client import TelegramClientError, get_telegram_client


class Command(BaseCommand):
    help = "Configure the Telegram Bot API webhook for Financify."

    def add_arguments(self, parser):
        parser.add_argument(
            "--url",
            required=True,
            help="Public HTTPS URL for /api/v1/telegram/webhook/.",
        )

    def handle(self, *args, **options):
        url = options["url"].strip()
        secret = settings.TELEGRAM_WEBHOOK_SECRET
        if not url.startswith("https://"):
            raise CommandError("Telegram webhook URL must use HTTPS.")
        if not secret:
            raise CommandError("TELEGRAM_WEBHOOK_SECRET must be configured.")

        try:
            client = get_telegram_client()
            client.set_webhook(url=url, secret_token=secret)
        except (ImproperlyConfigured, TelegramClientError, ValueError) as exc:
            raise CommandError(str(exc)) from None

        self.stdout.write(self.style.SUCCESS("Telegram webhook configured."))
