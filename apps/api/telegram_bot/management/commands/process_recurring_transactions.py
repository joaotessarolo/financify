from django.core.management.base import BaseCommand
from django.utils import timezone

from conversations.models import RecurringTransaction
from conversations.recurrences import generate_due_draft
from telegram_bot.client import get_telegram_client
from telegram_bot.models import TelegramIdentity


class Command(BaseCommand):
    help = "Create pending drafts for due monthly recurring transactions."

    def handle(self, *args, **options):
        run_date = timezone.localdate()
        client = get_telegram_client()
        generated = 0
        for recurrence in RecurringTransaction.objects.filter(
            is_active=True, next_run_on__lte=run_date
        ):
            draft = generate_due_draft(recurrence=recurrence, run_date=run_date)
            if draft is None:
                continue
            identity = TelegramIdentity.objects.filter(
                user_id=recurrence.user_id,
                revoked_at__isnull=True,
            ).first()
            if identity is not None:
                client.send_message(
                    chat_id=identity.private_chat_id,
                    text=(
                        f"Lembrete mensal: {draft.description} — "
                        f"{draft.currency} {recurrence.amount:.2f}. "
                        "Revise o rascunho no bot antes de confirmar."
                    ),
                    reply_markup={
                        "inline_keyboard": [[
                            {
                                "text": "Confirmar",
                                "callback_data": f"draft:confirm:{draft.id}",
                            },
                            {
                                "text": "Cancelar",
                                "callback_data": f"draft:cancel:{draft.id}",
                            },
                        ]]
                    },
                )
            generated += 1
        self.stdout.write(self.style.SUCCESS(f"Generated {generated} recurring drafts."))
