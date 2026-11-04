"""Outbound client for the Telegram Bot API.

The bot token is part of every request URL, so URLs, request bodies and
underlying library exceptions are never logged or chained into the
exceptions raised here.
"""

import json
import logging
import socket
from typing import Protocol
import urllib.error
import urllib.request

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE_URL = "https://api.telegram.org"
MAX_MESSAGE_LENGTH = 4096


class TelegramClientError(Exception):
    """Base error for outbound Telegram calls. Messages never contain secrets."""


class TelegramUnavailableError(TelegramClientError):
    """Network failure, timeout or 5xx/429 response. Safe to retry later."""


class TelegramAPIError(TelegramClientError):
    """Telegram rejected the request (4xx or ok=false)."""

    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class TelegramInvalidResponseError(TelegramClientError):
    """Telegram answered with something that is not a valid API response."""


class TelegramClient(Protocol):
    def send_message(self, *, chat_id: int, text: str) -> int:
        """Send a text message and return Telegram's message_id."""
        ...


class HttpTelegramClient:
    def __init__(
        self,
        *,
        bot_token: str,
        timeout_seconds: float,
        base_url: str = TELEGRAM_API_BASE_URL,
    ):
        if not bot_token:
            raise ImproperlyConfigured("TELEGRAM_BOT_TOKEN must be configured.")
        if timeout_seconds <= 0:
            raise ImproperlyConfigured(
                "TELEGRAM_API_TIMEOUT_SECONDS must be greater than zero."
            )
        self._bot_token = bot_token
        self._timeout_seconds = timeout_seconds
        self._base_url = base_url.rstrip("/")

    def __repr__(self) -> str:
        return f"HttpTelegramClient(timeout_seconds={self._timeout_seconds})"

    def send_message(self, *, chat_id: int, text: str) -> int:
        if not text:
            raise ValueError("text must not be empty.")
        result = self._call(
            "sendMessage",
            {"chat_id": chat_id, "text": text[:MAX_MESSAGE_LENGTH]},
        )
        message_id = result.get("message_id") if isinstance(result, dict) else None
        if isinstance(message_id, bool) or not isinstance(message_id, int):
            raise TelegramInvalidResponseError(
                "Telegram sendMessage response has no message_id."
            )
        return message_id

    def _call(self, method: str, params: dict):
        request = urllib.request.Request(
            f"{self._base_url}/bot{self._bot_token}/{method}",
            data=json.dumps(params).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        # `from None` everywhere: the original exceptions may carry the URL.
        try:
            with urllib.request.urlopen(
                request, timeout=self._timeout_seconds
            ) as response:
                status_code = response.status
                body = response.read()
        except urllib.error.HTTPError as exc:
            status_code = exc.code
            try:
                body = exc.read()
            except Exception:
                body = b""
            finally:
                exc.close()
        except (TimeoutError, socket.timeout):
            raise TelegramUnavailableError(
                f"Telegram {method} timed out."
            ) from None
        except (urllib.error.URLError, OSError):
            raise TelegramUnavailableError(
                f"Telegram {method} network error."
            ) from None

        if status_code == 429 or status_code >= 500:
            raise TelegramUnavailableError(
                f"Telegram {method} unavailable (HTTP {status_code})."
            )

        try:
            payload = json.loads(body)
        except (ValueError, TypeError):
            raise TelegramInvalidResponseError(
                f"Telegram {method} returned a non-JSON response "
                f"(HTTP {status_code})."
            ) from None

        if not isinstance(payload, dict) or not isinstance(payload.get("ok"), bool):
            raise TelegramInvalidResponseError(
                f"Telegram {method} returned an unexpected response "
                f"(HTTP {status_code})."
            )

        if not payload["ok"] or status_code >= 400:
            # Telegram's `description` describes the request, not our
            # secrets, but we keep only the status code to be conservative.
            raise TelegramAPIError(
                f"Telegram {method} rejected the request (HTTP {status_code}).",
                status_code=status_code,
            )

        return payload.get("result")


def get_telegram_client() -> TelegramClient:
    return HttpTelegramClient(
        bot_token=settings.TELEGRAM_BOT_TOKEN,
        timeout_seconds=settings.TELEGRAM_API_TIMEOUT_SECONDS,
    )
