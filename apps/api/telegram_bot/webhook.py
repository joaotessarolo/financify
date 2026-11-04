"""Inbound adapter for Telegram webhook updates.

Parses the minimum required shape of a Telegram update, records it
idempotently by ``update_id`` and dispatches to handlers. No financial
rules live here; handlers delegate to application services.

Raw payloads and account-linking tokens are never persisted or logged.
Ordinary text from linked users is stored in the conversation history.
"""

from dataclasses import dataclass
import logging

from django.core.exceptions import ImproperlyConfigured
from django.db import IntegrityError, transaction as db_transaction
from django.utils import timezone

from conversations.models import Conversation, ConversationChannel
from conversations.services import (
    get_or_create_active_conversation,
    record_completed_inbound_text_message,
    record_completed_outbound_text_message,
)

from .client import TelegramClient, TelegramClientError, get_telegram_client
from .models import (
    TelegramIdentity,
    TelegramUpdate,
    TelegramUpdateStatus,
    TelegramUpdateType,
)
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

LINK_SUCCESS_REPLY = (
    "Sua conta Financify foi conectada ao Telegram. "
    "Agora você pode registrar seus gastos por aqui."
)

TEXT_MESSAGE_REPLY = (
    "Recebi sua mensagem. O registro financeiro por texto será habilitado "
    "no próximo passo."
)

# Safe, user-facing replies for known failures. Codes absent from this map
# (e.g. non_private_chat, malformed updates) get no reply at all.
ERROR_REPLIES: dict[str, str] = {
    "start_without_token": (
        "Para conectar sua conta, gere um novo link no Financify "
        "e abra-o por aqui."
    ),
    "invalid_link_token": (
        "Este link de conexão não é válido. Gere um novo link no Financify."
    ),
    "expired_link_token": (
        "Este link de conexão expirou. Gere um novo link no Financify."
    ),
    "used_link_token": (
        "Este link de conexão já foi utilizado. "
        "Gere um novo link no Financify se precisar."
    ),
    "telegram_account_already_linked": (
        "Esta conta do Telegram já está conectada a outro usuário do Financify."
    ),
    "user_already_linked": (
        "Sua conta Financify já está conectada a outro Telegram. "
        "Desconecte-o no Financify antes de continuar."
    ),
    "invalid_chat": "Não foi possível conectar a conta por esta conversa.",
    "unsupported_message": "Ainda não consigo entender esta mensagem.",
    "unsupported_command": "Não reconheço este comando.",
    "telegram_not_linked": (
        "Este Telegram ainda não está conectado ao Financify. "
        "Gere um link de conexão no aplicativo."
    ),
    "internal_error": (
        "Ocorreu um erro inesperado. Tente novamente em alguns instantes."
    ),
}


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


@dataclass(frozen=True, slots=True)
class DispatchResult:
    reply: str | None = None
    conversation: Conversation | None = None


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


def handle_start_command(
    *, argument: str, from_id: int, chat_id: int
) -> DispatchResult:
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
    return DispatchResult(reply=LINK_SUCCESS_REPLY)


def _private_chat_id(parsed: ParsedUpdate) -> int | None:
    """Chat to reply to, only for well-formed private-chat messages."""
    if parsed.update_type != TelegramUpdateType.MESSAGE:
        return None
    chat = parsed.payload["message"].get("chat")
    if not isinstance(chat, dict) or chat.get("type") != "private":
        return None
    chat_id = chat.get("id")
    return chat_id if _is_positive_int(chat_id) else None


def handle_message(message: dict) -> DispatchResult:
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
    if not isinstance(text, str) or not text.strip():
        raise TelegramUpdateProcessingError("unsupported_message")

    normalized_text = text.strip()
    if not normalized_text.startswith("/"):
        identity = TelegramIdentity.objects.select_related("user").filter(
            telegram_user_id=from_id,
            private_chat_id=chat_id,
            revoked_at__isnull=True,
        ).first()
        if identity is None:
            raise TelegramUpdateProcessingError("telegram_not_linked")

        conversation = get_or_create_active_conversation(
            user=identity.user,
            channel=ConversationChannel.TELEGRAM,
        )
        record_completed_inbound_text_message(
            conversation=conversation,
            content=text,
        )
        return DispatchResult(
            reply=TEXT_MESSAGE_REPLY,
            conversation=conversation,
        )

    command, argument = _parse_command(normalized_text)
    if command == START_COMMAND:
        return handle_start_command(
            argument=argument, from_id=from_id, chat_id=chat_id
        )

    raise TelegramUpdateProcessingError("unsupported_command")


def dispatch(parsed: ParsedUpdate) -> DispatchResult:
    if parsed.update_type == TelegramUpdateType.MESSAGE:
        return handle_message(parsed.payload["message"])
    raise TelegramUpdateProcessingError("unsupported_update_type")


def _send_reply(
    client: TelegramClient | None,
    *,
    update_id: int,
    chat_id: int,
    text: str,
) -> bool:
    """Best-effort reply. Return whether Telegram accepted the message."""
    try:
        if client is None:
            client = get_telegram_client()
        client.send_message(chat_id=chat_id, text=text)
        return True
    except ImproperlyConfigured:
        logger.warning(
            "Telegram client not configured; reply for update %s skipped.",
            update_id,
        )
        return False
    except TelegramClientError as exc:
        # Our client errors never contain the bot token or message text.
        logger.warning(
            "Failed to send reply for Telegram update %s: %s",
            update_id,
            exc,
        )
        return False
    except Exception:
        logger.error(
            "Unexpected error sending reply for Telegram update %s.",
            update_id,
        )
        return False


def process_update(payload, *, client: TelegramClient | None = None) -> bool:
    """Record and process an update. Return False if it was a duplicate.

    ``client`` may be injected (tests, workers); otherwise one is built from
    settings when a reply is needed. Replies are sent after the update is
    finalized, so a send failure never undoes completed work.

    Raises InvalidTelegramUpdateError for malformed payloads.
    """
    parsed = parse_update(payload)
    update = _register_update(parsed)
    if update is None:
        return False

    result = DispatchResult()
    try:
        result = dispatch(parsed)
    except TelegramUpdateProcessingError as exc:
        _finish_update(update, error_code=exc.error_code)
        result = DispatchResult(reply=ERROR_REPLIES.get(exc.error_code))
    except Exception:
        logger.error(
            "Unexpected error processing Telegram update %s.", parsed.update_id
        )
        _finish_update(update, error_code="internal_error")
        result = DispatchResult(reply=ERROR_REPLIES["internal_error"])
    else:
        _finish_update(update)

    chat_id = _private_chat_id(parsed)
    if result.reply and chat_id is not None:
        sent = _send_reply(
            client,
            update_id=parsed.update_id,
            chat_id=chat_id,
            text=result.reply,
        )
        if sent and result.conversation is not None:
            try:
                record_completed_outbound_text_message(
                    conversation=result.conversation,
                    content=result.reply,
                )
            except Exception:
                logger.error(
                    "Failed to persist outbound message for Telegram update %s.",
                    parsed.update_id,
                )
    return True
