"""Inbound adapter for Telegram webhook updates.

Parses the minimum required shape of a Telegram update, records it
idempotently by ``update_id`` and dispatches to handlers. No financial
rules live here; handlers delegate to application services.

Neither raw payloads nor message text (which may contain link tokens)
are persisted or logged.
"""

from dataclasses import dataclass
import logging

from django.db import IntegrityError, transaction as db_transaction
from django.utils import timezone

from .models import TelegramUpdate, TelegramUpdateStatus, TelegramUpdateType
from .services import (
    ExpiredTelegramLinkTokenError,
    InvalidTelegramChatError,
    InvalidTelegramLinkTokenError,
    TelegramAccountAlreadyLinkedError,
    TelegramLinkError,
    UsedTelegramLinkTokenError,
    UserAlreadyLinkedToTelegramError,
    consume_telegram_link,
)

logger = logging.getLogger(__name__)

START_COMMAND = "/start"


class InvalidTelegramUpdateError(Exception):
    pass


class TelegramUpdateProcessingError(Exception):
    def __init__(self, error_code: str):
        super().__init__(error_code)
        self.error_code = error_code


@dataclass(frozen=True, slots=True)
class ParsedUpdate:
    update_id: int
    update_type: str
    payload: dict


def _is_positive_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def parse_update(payload) -> ParsedUpdate:
    if not isinstance(payload, dict):
        raise InvalidTelegramUpdateError("Update must be a JSON object.")

    update_id = payload.get("update_id")
    if not _is_positive_int(update_id):
        raise InvalidTelegramUpdateError("update_id must be a positive integer.")

    if "message" in payload:
        update_type = TelegramUpdateType.MESSAGE
        if not isinstance(payload["message"], dict):
            raise InvalidTelegramUpdateError("message must be an object.")
    elif "callback_query" in payload:
        update_type = TelegramUpdateType.CALLBACK_QUERY
        if not isinstance(payload["callback_query"], dict):
            raise InvalidTelegramUpdateError("callback_query must be an object.")
    else:
        update_type = TelegramUpdateType.UNSUPPORTED

    return ParsedUpdate(
        update_id=update_id,
        update_type=update_type,
        payload=payload,
    )


def _register_update(parsed: ParsedUpdate) -> TelegramUpdate | None:
    """Create the TelegramUpdate record. Return None if it already exists."""
    try:
        with db_transaction.atomic():
            return TelegramUpdate.objects.create(
                update_id=parsed.update_id,
                update_type=parsed.update_type,
                status=TelegramUpdateStatus.PROCESSING,
            )
    except IntegrityError:
        if TelegramUpdate.objects.filter(update_id=parsed.update_id).exists():
            return None
        raise


def _finish_update(update: TelegramUpdate, *, error_code: str = "") -> None:
    update.status = (
        TelegramUpdateStatus.FAILED if error_code else TelegramUpdateStatus.COMPLETED
    )
    update.error_code = error_code
    update.processed_at = timezone.now()
    update.save(update_fields=["status", "error_code", "processed_at"])


_LINK_ERROR_CODES: dict[type[TelegramLinkError], str] = {
    InvalidTelegramLinkTokenError: "invalid_link_token",
    ExpiredTelegramLinkTokenError: "expired_link_token",
    UsedTelegramLinkTokenError: "used_link_token",
    InvalidTelegramChatError: "invalid_chat",
    TelegramAccountAlreadyLinkedError: "telegram_account_already_linked",
    UserAlreadyLinkedToTelegramError: "user_already_linked",
}


def _link_error_code(exc: TelegramLinkError) -> str:
    for exc_type, code in _LINK_ERROR_CODES.items():
        if isinstance(exc, exc_type):
            return code
    return "link_failed"


def _parse_command(text: str) -> tuple[str, str]:
    """Split '/cmd@bot arg' into ('/cmd', 'arg')."""
    head, _, rest = text.strip().partition(" ")
    command = head.split("@", 1)[0].lower()
    return command, rest.strip()


def handle_start_command(*, argument: str, from_id: int, chat_id: int) -> None:
    if not argument:
        raise TelegramUpdateProcessingError("start_without_token")
    try:
        consume_telegram_link(
            raw_token=argument,
            telegram_user_id=from_id,
            private_chat_id=chat_id,
        )
    except TelegramLinkError as exc:
        raise TelegramUpdateProcessingError(_link_error_code(exc)) from exc


def handle_message(message: dict) -> None:
    chat = message.get("chat")
    sender = message.get("from")
    if not isinstance(chat, dict) or not isinstance(sender, dict):
        raise TelegramUpdateProcessingError("malformed_message")

    if chat.get("type") != "private":
        raise TelegramUpdateProcessingError("non_private_chat")

    chat_id = chat.get("id")
    from_id = sender.get("id")
    if not _is_positive_int(chat_id) or not _is_positive_int(from_id):
        raise TelegramUpdateProcessingError("malformed_message")

    text = message.get("text")
    if not isinstance(text, str) or not text.startswith("/"):
        raise TelegramUpdateProcessingError("unsupported_message")

    command, argument = _parse_command(text)
    if command == START_COMMAND:
        handle_start_command(argument=argument, from_id=from_id, chat_id=chat_id)
        return

    raise TelegramUpdateProcessingError("unsupported_command")


def dispatch(parsed: ParsedUpdate) -> None:
    if parsed.update_type == TelegramUpdateType.MESSAGE:
        handle_message(parsed.payload["message"])
        return
    raise TelegramUpdateProcessingError("unsupported_update_type")


def process_update(payload) -> bool:
    """Record and process an update. Return False if it was a duplicate.

    Raises InvalidTelegramUpdateError for malformed payloads.
    """
    parsed = parse_update(payload)
    update = _register_update(parsed)
    if update is None:
        return False

    try:
        dispatch(parsed)
    except TelegramUpdateProcessingError as exc:
        _finish_update(update, error_code=exc.error_code)
    except Exception:
        logger.exception(
            "Unexpected error processing Telegram update %s", parsed.update_id
        )
        _finish_update(update, error_code="internal_error")
    else:
        _finish_update(update)
    return True
