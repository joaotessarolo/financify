from ..client import TelegramClientError


class FakeTelegramClient:
    """In-memory TelegramClient for tests."""

    def __init__(self, *, error: TelegramClientError | None = None):
        self.sent_messages: list[dict] = []
        self.answered_callbacks: list[dict] = []
        self.webhook_configurations: list[dict] = []
        self._error = error
        self._next_message_id = 1

    def send_message(
        self,
        *,
        chat_id: int,
        text: str,
        reply_markup: dict | None = None,
    ) -> int:
        if self._error is not None:
            raise self._error
        sent = {"chat_id": chat_id, "text": text}
        if reply_markup is not None:
            sent["reply_markup"] = reply_markup
        self.sent_messages.append(sent)
        message_id = self._next_message_id
        self._next_message_id += 1
        return message_id

    def answer_callback_query(
        self, *, callback_query_id: str, text: str = ""
    ) -> None:
        if self._error is not None:
            raise self._error
        self.answered_callbacks.append(
            {"callback_query_id": callback_query_id, "text": text}
        )

    def set_webhook(self, *, url: str, secret_token: str) -> None:
        if self._error is not None:
            raise self._error
        self.webhook_configurations.append(
            {"url": url, "secret_token": secret_token}
        )
