import logging
from time import monotonic

from celery import shared_task

from conversations.services import record_completed_outbound_text_message

from .client import TelegramClientError, get_telegram_client
from .observability import record_event

logger = logging.getLogger(__name__)


@shared_task(
    autoretry_for=(TelegramClientError,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 2},
)
def process_voice_message(message: dict) -> None:
    from .webhook import handle_message

    started = monotonic()
    try:
        result = handle_message(message, process_voice=True)
    except Exception:
        record_event("voice_failed")
        raise
    record_event("voice_completed", duration_ms=int((monotonic() - started) * 1000))
    if not result.reply:
        return
    chat_id = message["chat"]["id"]
    get_telegram_client().send_message(
        chat_id=chat_id,
        text=result.reply,
        reply_markup=result.reply_markup,
    )
    if result.conversation is not None:
        record_completed_outbound_text_message(
            conversation=result.conversation,
            content=result.reply,
        )
