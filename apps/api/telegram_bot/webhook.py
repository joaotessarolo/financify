"""Inbound adapter for Telegram webhook updates.

Parses the minimum required shape of a Telegram update, records it
idempotently by ``update_id`` and dispatches to handlers. No financial
rules live here; handlers delegate to application services.

Raw payloads and account-linking tokens are never persisted or logged.
Ordinary text from linked users is stored in the conversation history.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
import logging
import unicodedata
import uuid

from django.core.exceptions import ImproperlyConfigured
from django.db import IntegrityError, transaction as db_transaction
from django.utils import timezone

from ledger.models import AccountSystemRole
from ledger.services import calculate_account_balance, ensure_default_accounts

from conversations.models import (
    Conversation,
    ConversationChannel,
    TransactionDraft,
    TransactionDraftStatus,
)
from conversations.extraction import (
    TextExtractionError,
    get_transaction_extractor,
)
from conversations.services import (
    create_transaction_draft_from_extraction,
    DraftConfirmationError,
    DraftRejectionError,
    confirm_transaction_draft,
    get_or_create_active_conversation,
    record_completed_inbound_text_message,
    record_completed_outbound_text_message,
    reject_transaction_draft,
)

from .client import TelegramClient, TelegramClientError, get_telegram_client
from .models import (
    TelegramIdentity,
    TelegramOnboardingStep,
    TelegramUpdate,
    TelegramUpdateStatus,
    TelegramUpdateType,
)
from .messages import (
    ACCOUNT_ONBOARDING_PROMPT,
    INVALID_ACCOUNT_SETUP,
    INVALID_BALANCE,
    account_balance,
    balance_prompt,
    onboarding_complete,
)
from .onboarding import (
    OnboardingParseError,
    complete_account_onboarding,
    parse_account_setup,
    parse_balance,
    remember_primary_account_name,
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

TEXT_FORMAT_REPLY = (
    "Não consegui criar o rascunho. Use algo como “gastei 35,90 no almoço” "
    "ou “receita de 2500 salário”."
)

BALANCE_QUERY_PHRASES = {
    "saldo",
    "meu saldo",
    "qual meu saldo",
    "qual e meu saldo",
    "quanto tenho",
    "quanto eu tenho",
}

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
    reply_markup: dict | None = None
    callback_query_id: str | None = None
    callback_answer: str = ""
    edit_message_id: int | None = None
    edit_text: str | None = None


def _draft_reply(*, description: str, amount, currency: str) -> str:
    formatted_amount = f"{amount:.2f}".replace(".", ",")
    return (
        f"Rascunho criado: {description} — {currency} {formatted_amount}. "
        "Revise os dados e confirme ou cancele abaixo."
    )


def _draft_reply_markup(draft_id) -> dict:
    return {
        "inline_keyboard": [
            [
                {
                    "text": "Confirmar",
                    "callback_data": f"draft:confirm:{draft_id}",
                },
                {
                    "text": "Cancelar",
                    "callback_data": f"draft:cancel:{draft_id}",
                },
            ]
        ]
    }


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


def _balance_query_account(text: str) -> str | None:
    normalized = unicodedata.normalize("NFKD", text.strip().lower().rstrip("?"))
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    normalized = " ".join(normalized.split())
    if normalized in BALANCE_QUERY_PHRASES:
        return ""
    for prefix in ("saldo do ", "saldo da "):
        if normalized.startswith(prefix) and normalized[len(prefix) :].strip():
            return normalized[len(prefix) :].strip()
    return None


def handle_start_command(
    *, argument: str, from_id: int, chat_id: int
) -> DispatchResult:
    if not argument:
        raise TelegramUpdateProcessingError("start_without_token")
    try:
        identity = consume_telegram_link(
            raw_token=argument,
            telegram_user_id=from_id,
            private_chat_id=chat_id,
        )
    except TelegramLinkError as exc:
        raise TelegramUpdateProcessingError(_link_error_code(exc)) from exc
    reply = (
        ACCOUNT_ONBOARDING_PROMPT
        if identity.onboarding_step != TelegramOnboardingStep.COMPLETED
        else LINK_SUCCESS_REPLY
    )
    return DispatchResult(reply=reply)


def _handle_onboarding_message(
    *, identity: TelegramIdentity, text: str, conversation: Conversation
) -> DispatchResult:
    if identity.onboarding_step == TelegramOnboardingStep.AWAITING_ACCOUNT:
        try:
            setup = parse_account_setup(text)
        except OnboardingParseError:
            return DispatchResult(
                reply=INVALID_ACCOUNT_SETUP,
                conversation=conversation,
            )
        if setup.balance is None:
            remember_primary_account_name(
                identity=identity,
                account_name=setup.name,
            )
            return DispatchResult(
                reply=balance_prompt(setup.name),
                conversation=conversation,
            )
        primary = complete_account_onboarding(
            identity=identity,
            account_name=setup.name,
            balance=setup.balance,
        )
        return DispatchResult(
            reply=onboarding_complete(
                primary.name,
                primary.currency,
                setup.balance,
            ),
            conversation=conversation,
        )

    if identity.onboarding_step == TelegramOnboardingStep.AWAITING_BALANCE:
        try:
            balance = parse_balance(text)
        except OnboardingParseError:
            return DispatchResult(
                reply=INVALID_BALANCE,
                conversation=conversation,
            )
        primary = complete_account_onboarding(
            identity=identity,
            account_name=identity.pending_account_name,
            balance=balance,
        )
        return DispatchResult(
            reply=onboarding_complete(
                primary.name,
                primary.currency,
                balance,
            ),
            conversation=conversation,
        )

    raise TelegramUpdateProcessingError("invalid_onboarding_state")


def _private_chat_id(parsed: ParsedUpdate) -> int | None:
    """Chat to reply to, only for well-formed private-chat messages."""
    if parsed.update_type == TelegramUpdateType.MESSAGE:
        container = parsed.payload["message"]
    elif parsed.update_type == TelegramUpdateType.CALLBACK_QUERY:
        callback = parsed.payload["callback_query"]
        container = callback.get("message") if isinstance(callback, dict) else None
        if not isinstance(container, dict):
            return None
    else:
        return None
    chat = container.get("chat")
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
        message_date = message.get("date")
        if not _is_positive_int(message_date):
            raise TelegramUpdateProcessingError("malformed_message")
        occurred_at = datetime.fromtimestamp(message_date, tz=UTC)

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
        source_message = record_completed_inbound_text_message(
            conversation=conversation,
            content=text,
        )

        if identity.onboarding_step != TelegramOnboardingStep.COMPLETED:
            return _handle_onboarding_message(
                identity=identity,
                text=normalized_text,
                conversation=conversation,
            )

        requested_account = _balance_query_account(normalized_text)
        if requested_account is not None:
            primary = ensure_default_accounts(user=identity.user).primary
            normalized_name = unicodedata.normalize("NFKD", primary.name.lower())
            normalized_name = "".join(
                char for char in normalized_name if not unicodedata.combining(char)
            )
            if requested_account and requested_account != normalized_name:
                return DispatchResult(
                    reply=f"Não encontrei a conta “{requested_account}”. Sua conta principal é “{primary.name}”.",
                    conversation=conversation,
                )
            return DispatchResult(
                reply=account_balance(
                    primary.name,
                    primary.currency,
                    calculate_account_balance(account=primary),
                ),
                conversation=conversation,
            )

        try:
            extraction = get_transaction_extractor().extract(normalized_text)
        except TextExtractionError:
            return DispatchResult(
                reply=TEXT_FORMAT_REPLY,
                conversation=conversation,
            )

        draft = create_transaction_draft_from_extraction(
            source_message=source_message,
            extraction=extraction,
            occurred_at=occurred_at,
        )
        return DispatchResult(
            reply=_draft_reply(
                description=draft.description,
                amount=extraction.amount,
                currency=draft.currency,
            ),
            conversation=conversation,
            reply_markup=_draft_reply_markup(draft.id),
        )

    command, argument = _parse_command(normalized_text)
    if command == START_COMMAND:
        return handle_start_command(
            argument=argument, from_id=from_id, chat_id=chat_id
        )

    raise TelegramUpdateProcessingError("unsupported_command")


def handle_callback_query(callback: dict) -> DispatchResult:
    callback_id = callback.get("id")
    sender = callback.get("from")
    message = callback.get("message")
    data = callback.get("data")
    message_id = message.get("message_id") if isinstance(message, dict) else None
    if (
        not isinstance(callback_id, str)
        or not callback_id
        or not isinstance(sender, dict)
        or not isinstance(message, dict)
        or not isinstance(data, str)
        or not _is_positive_int(message_id)
    ):
        raise TelegramUpdateProcessingError("malformed_callback_query")

    chat = message.get("chat")
    if not isinstance(chat, dict) or chat.get("type") != "private":
        raise TelegramUpdateProcessingError("non_private_chat")
    chat_id = chat.get("id")
    from_id = sender.get("id")
    if not _is_positive_int(chat_id) or not _is_positive_int(from_id):
        raise TelegramUpdateProcessingError("malformed_callback_query")

    identity = TelegramIdentity.objects.filter(
        telegram_user_id=from_id,
        private_chat_id=chat_id,
        revoked_at__isnull=True,
    ).first()
    if identity is None:
        return DispatchResult(
            reply=ERROR_REPLIES["telegram_not_linked"],
            callback_query_id=callback_id,
            callback_answer="Conta não conectada.",
        )

    parts = data.split(":")
    if len(parts) != 3 or parts[0] != "draft" or parts[1] not in {
        "confirm",
        "cancel",
    }:
        return DispatchResult(
            reply="Esta ação não é válida.",
            callback_query_id=callback_id,
            callback_answer="Ação inválida.",
        )
    try:
        draft_id = uuid.UUID(parts[2])
    except ValueError:
        return DispatchResult(
            reply="Esta ação não é válida.",
            callback_query_id=callback_id,
            callback_answer="Ação inválida.",
        )

    draft = (
        TransactionDraft.objects.select_related("source_message__conversation")
        .filter(pk=draft_id, user_id=identity.user_id)
        .first()
    )
    if draft is None:
        return DispatchResult(
            reply="Este rascunho não foi encontrado.",
            callback_query_id=callback_id,
            callback_answer="Rascunho não encontrado.",
        )

    conversation = draft.source_message.conversation
    if parts[1] == "confirm":
        if draft.status == TransactionDraftStatus.CONFIRMED:
            return DispatchResult(
                callback_query_id=callback_id,
                callback_answer="Registro já confirmado.",
            )
        try:
            transaction = confirm_transaction_draft(draft=draft)
        except DraftConfirmationError:
            edit_text = "Este rascunho não pode mais ser confirmado."
            answer = "Não foi possível confirmar."
        else:
            edit_text = f"Registro confirmado: {transaction.description}."
            answer = "Registro confirmado."
    else:
        if draft.status == TransactionDraftStatus.REJECTED:
            return DispatchResult(
                callback_query_id=callback_id,
                callback_answer="Rascunho já cancelado.",
            )
        try:
            reject_transaction_draft(draft=draft)
        except DraftRejectionError:
            edit_text = "Este rascunho não pode mais ser cancelado."
            answer = "Não foi possível cancelar."
        else:
            edit_text = f"Rascunho cancelado: {draft.description}."
            answer = "Rascunho cancelado."

    return DispatchResult(
        conversation=conversation,
        callback_query_id=callback_id,
        callback_answer=answer,
        edit_message_id=message_id,
        edit_text=edit_text,
    )


def dispatch(parsed: ParsedUpdate) -> DispatchResult:
    if parsed.update_type == TelegramUpdateType.MESSAGE:
        return handle_message(parsed.payload["message"])
    if parsed.update_type == TelegramUpdateType.CALLBACK_QUERY:
        return handle_callback_query(parsed.payload["callback_query"])
    raise TelegramUpdateProcessingError("unsupported_update_type")


def _send_reply(
    client: TelegramClient | None,
    *,
    update_id: int,
    chat_id: int,
    text: str,
    reply_markup: dict | None = None,
) -> bool:
    """Best-effort reply. Return whether Telegram accepted the message."""
    try:
        if client is None:
            client = get_telegram_client()
        client.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
        )
        return True
    except ImproperlyConfigured:
        logger.warning(
            "Telegram client not configured; reply for update %s skipped.",
            update_id,
            extra={"telegram_update_id": update_id},
        )
        return False
    except TelegramClientError as exc:
        # Our client errors never contain the bot token or message text.
        logger.warning(
            "Failed to send reply for Telegram update %s: %s",
            update_id,
            exc,
            extra={"telegram_update_id": update_id},
        )
        return False
    except Exception:
        logger.error(
            "Unexpected error sending reply for Telegram update %s.",
            update_id,
            extra={"telegram_update_id": update_id},
        )
        return False


def _answer_callback(
    client: TelegramClient | None,
    *,
    update_id: int,
    callback_query_id: str,
    text: str,
) -> TelegramClient | None:
    try:
        if client is None:
            client = get_telegram_client()
        client.answer_callback_query(
            callback_query_id=callback_query_id,
            text=text,
        )
    except (ImproperlyConfigured, TelegramClientError):
        logger.warning(
            "Failed to answer callback for Telegram update %s.",
            update_id,
            extra={"telegram_update_id": update_id},
        )
    except Exception:
        logger.error(
            "Unexpected error answering callback for Telegram update %s.",
            update_id,
            extra={"telegram_update_id": update_id},
        )
    return client


def _edit_callback_message(
    client: TelegramClient | None,
    *,
    update_id: int,
    chat_id: int,
    message_id: int,
    text: str,
) -> None:
    try:
        if client is None:
            client = get_telegram_client()
        client.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
        )
    except (ImproperlyConfigured, TelegramClientError):
        logger.warning(
            "Failed to edit callback message for Telegram update %s.",
            update_id,
            extra={"telegram_update_id": update_id},
        )
    except Exception:
        logger.error(
            "Unexpected error editing callback message for Telegram update %s.",
            update_id,
            extra={"telegram_update_id": update_id},
        )


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
            "Unexpected error processing Telegram update %s.",
            parsed.update_id,
            extra={"telegram_update_id": parsed.update_id},
        )
        _finish_update(update, error_code="internal_error")
        result = DispatchResult(reply=ERROR_REPLIES["internal_error"])
    else:
        _finish_update(update)

    chat_id = _private_chat_id(parsed)
    if result.callback_query_id:
        client = _answer_callback(
            client,
            update_id=parsed.update_id,
            callback_query_id=result.callback_query_id,
            text=result.callback_answer,
        )
    if (
        result.edit_message_id is not None
        and result.edit_text
        and chat_id is not None
    ):
        _edit_callback_message(
            client,
            update_id=parsed.update_id,
            chat_id=chat_id,
            message_id=result.edit_message_id,
            text=result.edit_text,
        )
    if result.reply and chat_id is not None:
        sent = _send_reply(
            client,
            update_id=parsed.update_id,
            chat_id=chat_id,
            text=result.reply,
            reply_markup=result.reply_markup,
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
                    extra={"telegram_update_id": parsed.update_id},
                )
    return True
