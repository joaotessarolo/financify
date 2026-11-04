from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from ..client import TelegramUnavailableError
from .fakes import FakeTelegramClient


class RunTelegramBotCommandTests(SimpleTestCase):
    def test_once_processes_batch_and_exits(self):
        updates = [
            {"update_id": 10, "message": {}},
            {"update_id": 11, "callback_query": {}},
        ]
        client = FakeTelegramClient(updates=updates)
        stdout = StringIO()

        with patch(
            "telegram_bot.management.commands.run_telegram_bot.get_telegram_client",
            return_value=client,
        ), patch(
            "telegram_bot.management.commands.run_telegram_bot.process_update"
        ) as mock_process:
            call_command(
                "run_telegram_bot",
                once=True,
                poll_timeout=0,
                stdout=stdout,
            )

        self.assertEqual(
            client.get_updates_calls,
            [{"offset": None, "timeout": 0}],
        )
        self.assertEqual(
            [call.args[0] for call in mock_process.call_args_list],
            updates,
        )
        for call in mock_process.call_args_list:
            self.assertIs(call.kwargs["client"], client)
        self.assertIn("long polling started", stdout.getvalue())

    def test_offsets_next_poll_after_highest_update(self):
        client = FakeTelegramClient(
            updates=[{"update_id": 20, "message": {}}]
        )

        def get_updates(*, offset, timeout):
            client.get_updates_calls.append(
                {"offset": offset, "timeout": timeout}
            )
            if len(client.get_updates_calls) == 1:
                return [{"update_id": 20, "message": {}}]
            raise KeyboardInterrupt

        client.get_updates = get_updates
        with patch(
            "telegram_bot.management.commands.run_telegram_bot.get_telegram_client",
            return_value=client,
        ), patch(
            "telegram_bot.management.commands.run_telegram_bot.process_update"
        ):
            call_command("run_telegram_bot", poll_timeout=0)

        self.assertEqual(
            client.get_updates_calls,
            [
                {"offset": None, "timeout": 0},
                {"offset": 21, "timeout": 0},
            ],
        )

    def test_once_surfaces_network_failure_as_command_error(self):
        client = FakeTelegramClient(
            error=TelegramUnavailableError("Telegram unavailable.")
        )
        with patch(
            "telegram_bot.management.commands.run_telegram_bot.get_telegram_client",
            return_value=client,
        ):
            with self.assertRaisesMessage(CommandError, "Telegram unavailable"):
                call_command("run_telegram_bot", once=True, poll_timeout=0)

    def test_rejects_negative_options(self):
        for options, message in (
            ({"poll_timeout": -1}, "--poll-timeout"),
            ({"idle_delay": -1}, "--idle-delay"),
        ):
            with self.subTest(options=options):
                with self.assertRaisesMessage(CommandError, message):
                    call_command("run_telegram_bot", once=True, **options)
