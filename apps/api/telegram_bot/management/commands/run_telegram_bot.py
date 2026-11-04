import time

from django.core.management.base import BaseCommand, CommandError

from telegram_bot.client import TelegramClientError, get_telegram_client
from telegram_bot.webhook import InvalidTelegramUpdateError, process_update


class Command(BaseCommand):
    help = "Run the Telegram bot locally using long polling."

    def add_arguments(self, parser):
        parser.add_argument(
            "--poll-timeout",
            type=int,
            default=30,
            help="Telegram long-poll timeout in seconds.",
        )
        parser.add_argument(
            "--idle-delay",
            type=float,
            default=1.0,
            help="Delay after a transient Telegram error.",
        )
        parser.add_argument(
            "--once",
            action="store_true",
            help="Fetch one batch and exit (useful for diagnostics).",
        )

    def handle(self, *args, **options):
        poll_timeout = options["poll_timeout"]
        idle_delay = options["idle_delay"]
        run_once = options["once"]
        if poll_timeout < 0:
            raise CommandError("--poll-timeout must not be negative.")
        if idle_delay < 0:
            raise CommandError("--idle-delay must not be negative.")

        client = get_telegram_client()
        offset = None
        self.stdout.write("Telegram long polling started.")

        try:
            while True:
                try:
                    updates = client.get_updates(
                        offset=offset,
                        timeout=poll_timeout,
                    )
                except TelegramClientError as exc:
                    if run_once:
                        raise CommandError(str(exc)) from None
                    self.stderr.write(
                        "Telegram temporarily unavailable; retrying."
                    )
                    time.sleep(idle_delay)
                    continue

                for update in updates:
                    update_id = update.get("update_id")
                    try:
                        process_update(update, client=client)
                    except InvalidTelegramUpdateError:
                        self.stderr.write("Ignored malformed Telegram update.")
                    if isinstance(update_id, int) and not isinstance(
                        update_id, bool
                    ):
                        offset = max(offset or 0, update_id + 1)

                if run_once:
                    break
        except KeyboardInterrupt:
            self.stdout.write("Telegram long polling stopped.")
