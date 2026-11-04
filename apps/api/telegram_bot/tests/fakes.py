from ..client import TelegramClientError


class FakeTelegramClient:
    """In-memory TelegramClient for tests."""

    def __init__(self, *, error: TelegramClientError | None = None):
        self.sent_messages: list[dict] = []
        self._error = error
        self._next_message_id = 1

    def send_message(self, *, chat_id: int, text: str) -> int:
        if self._error is not None:
            raise self._error
        self.sent_messages.append({"chat_id": chat_id, "text": text})
        message_id = self._next_message_id
        self._next_message_id += 1
        return message_id
