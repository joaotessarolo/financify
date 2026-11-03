from dataclasses import dataclass, field
from datetime import datetime, timedelta
import hashlib
import secrets

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone

from .models import TelegramLinkToken


@dataclass(frozen=True, slots=True)
class TelegramLink:
    url: str = field(repr=False)
    expires_at: datetime


def _digest_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def create_telegram_link(*, user) -> TelegramLink:
    bot_username = settings.TELEGRAM_BOT_USERNAME
    ttl_seconds = settings.TELEGRAM_LINK_TOKEN_TTL_SECONDS

    if not bot_username:
        raise ImproperlyConfigured("TELEGRAM_BOT_USERNAME must be configured.")

    if bot_username.startswith("@"):
        raise ImproperlyConfigured(
            "TELEGRAM_BOT_USERNAME must not start with '@'."
        )

    if ttl_seconds <= 0:
        raise ImproperlyConfigured(
            "TELEGRAM_LINK_TOKEN_TTL_SECONDS must be greater than zero."
        )

    raw_token = secrets.token_urlsafe(32)
    digest = _digest_token(raw_token)
    expires_at = timezone.now() + timedelta(seconds=ttl_seconds)

    TelegramLinkToken.objects.create(
        user=user,
        token_digest=digest,
        expires_at=expires_at,
    )

    url = f"https://t.me/{bot_username}?start={raw_token}"
    return TelegramLink(url=url, expires_at=expires_at)
