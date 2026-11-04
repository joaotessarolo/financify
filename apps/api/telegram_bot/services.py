from dataclasses import dataclass, field
from datetime import datetime, timedelta
import hashlib
import secrets

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import IntegrityError, models, transaction as db_transaction
from django.utils import timezone

from .models import TelegramIdentity, TelegramLinkToken


class TelegramLinkError(Exception):
    pass


class InvalidTelegramLinkTokenError(TelegramLinkError):
    pass


class ExpiredTelegramLinkTokenError(TelegramLinkError):
    pass


class UsedTelegramLinkTokenError(TelegramLinkError):
    pass


class InvalidTelegramChatError(TelegramLinkError):
    pass


class TelegramLinkConflictError(TelegramLinkError):
    pass


class TelegramAccountAlreadyLinkedError(TelegramLinkConflictError):
    pass


class UserAlreadyLinkedToTelegramError(TelegramLinkConflictError):
    pass


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


def consume_telegram_link(
    *,
    raw_token: str,
    telegram_user_id: int,
    private_chat_id: int,
) -> TelegramIdentity:
    if (
        isinstance(telegram_user_id, bool)
        or not isinstance(telegram_user_id, int)
        or telegram_user_id <= 0
    ):
        raise InvalidTelegramChatError(
            "telegram_user_id must be a positive integer."
        )

    if (
        isinstance(private_chat_id, bool)
        or not isinstance(private_chat_id, int)
        or private_chat_id <= 0
        or private_chat_id != telegram_user_id
    ):
        raise InvalidTelegramChatError(
            "Telegram account linking requires a private chat."
        )

    normalized_token = raw_token.strip() if isinstance(raw_token, str) else ""
    if not normalized_token:
        raise InvalidTelegramLinkTokenError("Invalid Telegram link token.")

    digest = _digest_token(normalized_token)

    with db_transaction.atomic():
        try:
            token = (
                TelegramLinkToken.objects.select_for_update()
                .select_related("user")
                .get(token_digest=digest)
            )
        except TelegramLinkToken.DoesNotExist as exc:
            raise InvalidTelegramLinkTokenError(
                "Invalid Telegram link token."
            ) from exc

        if token.used_at is not None:
            raise UsedTelegramLinkTokenError(
                "Telegram link token has already been used."
            )

        now = timezone.now()
        if token.expires_at <= now:
            raise ExpiredTelegramLinkTokenError(
                "Telegram link token has expired."
            )

        conflicting_telegram_identity = (
            TelegramIdentity.objects.select_for_update()
            .filter(
                models.Q(telegram_user_id=telegram_user_id)
                | models.Q(private_chat_id=private_chat_id)
            )
            .exclude(user_id=token.user_id)
            .first()
        )
        if conflicting_telegram_identity is not None:
            raise TelegramAccountAlreadyLinkedError(
                "This Telegram account is already linked to another user."
            )

        user_identity = (
            TelegramIdentity.objects.select_for_update()
            .filter(user_id=token.user_id)
            .first()
        )

        if user_identity is None:
            try:
                identity = TelegramIdentity.objects.create(
                    user=token.user,
                    telegram_user_id=telegram_user_id,
                    private_chat_id=private_chat_id,
                )
            except IntegrityError as exc:
                raise TelegramAccountAlreadyLinkedError(
                    "This Telegram account is already linked to another user."
                ) from exc
        else:
            if user_identity.telegram_user_id == telegram_user_id:
                if (
                    user_identity.revoked_at is not None
                    or user_identity.private_chat_id != private_chat_id
                ):
                    user_identity.private_chat_id = private_chat_id
                    user_identity.revoked_at = None
                    user_identity.save(
                        update_fields=[
                            "private_chat_id",
                            "revoked_at",
                            "updated_at",
                        ]
                    )
                identity = user_identity
            elif user_identity.is_active:
                raise UserAlreadyLinkedToTelegramError(
                    "User is already linked to another Telegram account."
                )
            else:
                user_identity.telegram_user_id = telegram_user_id
                user_identity.private_chat_id = private_chat_id
                user_identity.revoked_at = None
                user_identity.save(
                    update_fields=[
                        "telegram_user_id",
                        "private_chat_id",
                        "revoked_at",
                        "updated_at",
                    ]
                )
                identity = user_identity

        used_at = max(now, token.created_at)
        token.used_at = used_at
        token.save(update_fields=["used_at"])

        return identity
