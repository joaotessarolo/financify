"""Outbound client for the Telegram Bot API.

The bot token is part of every request URL, so URLs, request bodies and
underlying library exceptions are never logged or chained into the
exceptions raised here.
"""

import json
import logging
import socket
import ssl
import time
from typing import Protocol
import urllib.error
import urllib.request

import certifi
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
    def send_message(
        self,
        *,
        chat_id: int,
        text: str,
        reply_markup: dict | None = None,
    ) -> int:
        """Send a text message and return Telegram's message_id."""
        ...

    def answer_callback_query(
        self, *, callback_query_id: str, text: str = ""
    ) -> None:
        """Acknowledge a callback query and remove Telegram's loading state."""
        ...

    def set_webhook(self, *, url: str, secret_token: str) -> None:
        """Configure Telegram to deliver updates to the given HTTPS URL."""
        ...

    def get_updates(self, *, offset: int | None, timeout: int) -> list[dict]:
        """Fetch the next batch of updates using Telegram long polling."""
        ...


class HttpTelegramClient:
    def __init__(
        self,
        *,
        bot_token: str,
        timeout_seconds: float,
        max_retries: int = 0,
        retry_delay_seconds: float = 0.25,
        base_url: str = TELEGRAM_API_BASE_URL,
    ):
        if not bot_token:
            raise ImproperlyConfigured("TELEGRAM_BOT_TOKEN must be configured.")
        if timeout_seconds <= 0:
            raise ImproperlyConfigured(
                "TELEGRAM_API_TIMEOUT_SECONDS must be greater than zero."
            )
        if max_retries < 0:
            raise ImproperlyConfigured(
                "TELEGRAM_API_MAX_RETRIES must not be negative."
            )
        if retry_delay_seconds < 0:
            raise ImproperlyConfigured(
                "TELEGRAM_API_RETRY_DELAY_SECONDS must not be negative."
            )
        self._bot_token = bot_token
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._retry_delay_seconds = retry_delay_seconds
        self._base_url = base_url.rstrip("/")
        self._ssl_context = ssl.create_default_context(cafile=certifi.where())

    def __repr__(self) -> str:
        return (
            "HttpTelegramClient("
            f"timeout_seconds={self._timeout_seconds}, "
            f"max_retries={self._max_retries})"
        )

    def send_message(
        self,
        *,
        chat_id: int,
        text: str,
        reply_markup: dict | None = None,
    ) -> int:
        if not text:
            raise ValueError("text must not be empty.")
        params = {"chat_id": chat_id, "text": text[:MAX_MESSAGE_LENGTH]}
        if reply_markup is not None:
            params["reply_markup"] = reply_markup
        result = self._call("sendMessage", params)
        message_id = result.get("message_id") if isinstance(result, dict) else None
        if isinstance(message_id, bool) or not isinstance(message_id, int):
            raise TelegramInvalidResponseError(
                "Telegram sendMessage response has no message_id."
            )
        return message_id

    def answer_callback_query(
        self, *, callback_query_id: str, text: str = ""
    ) -> None:
        if not callback_query_id:
            raise ValueError("callback_query_id must not be empty.")
        params = {"callback_query_id": callback_query_id}
        if text:
            params["text"] = text
        self._call("answerCallbackQuery", params)

    def set_webhook(self, *, url: str, secret_token: str) -> None:
        if not url.startswith("https://"):
            raise ValueError("Telegram webhook URL must use HTTPS.")
        if not secret_token:
            raise ValueError("secret_token must not be empty.")
        self._call(
            "setWebhook",
            {
                "url": url,
                "secret_token": secret_token,
                "allowed_updates": ["message", "callback_query"],
            },
        )

    def get_updates(self, *, offset: int | None, timeout: int) -> list[dict]:
        if timeout < 0:
            raise ValueError("timeout must not be negative.")
        params = {
            "timeout": timeout,
            "allowed_updates": ["message", "callback_query"],
        }
        if offset is not None:
            params["offset"] = offset
        result = self._call(
            "getUpdates",
            params,
            timeout_seconds=max(self._timeout_seconds, timeout + 5),
        )
        if not isinstance(result, list) or not all(
            isinstance(update, dict) for update in result
        ):
            raise TelegramInvalidResponseError(
                "Telegram getUpdates returned an invalid result."
            )
        return result

    def _call(
        self,
        method: str,
        params: dict,
        *,
        timeout_seconds: float | None = None,
    ):
        for attempt in range(self._max_retries + 1):
            try:
                return self._call_once(
                    method,
                    params,
                    timeout_seconds=timeout_seconds,
                )
            except TelegramUnavailableError:
                if attempt >= self._max_retries:
                    raise
                time.sleep(self._retry_delay_seconds * (2**attempt))
        raise AssertionError("unreachable")

    def _call_once(
        self,
        method: str,
        params: dict,
        *,
        timeout_seconds: float | None = None,
    ):
        request = urllib.request.Request(
            f"{self._base_url}/bot{self._bot_token}/{method}",
            data=json.dumps(params).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        # `from None` everywhere: the original exceptions may carry the URL.
        try:
            with urllib.request.urlopen(
                request,
                timeout=timeout_seconds or self._timeout_seconds,
                context=self._ssl_context,
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
        max_retries=settings.TELEGRAM_API_MAX_RETRIES,
        retry_delay_seconds=settings.TELEGRAM_API_RETRY_DELAY_SECONDS,
    )
