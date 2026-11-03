import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class TelegramIdentity(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="telegram_identity",
    )
    telegram_user_id = models.BigIntegerField(
        unique=True,
        validators=[MinValueValidator(1)],
    )
    private_chat_id = models.BigIntegerField(
        unique=True,
        validators=[MinValueValidator(1)],
    )
    linked_at = models.DateTimeField(
        auto_now_add=True,
    )
    revoked_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        verbose_name_plural = "telegram identities"
        constraints = [  # noqa: RUF012
            models.CheckConstraint(
                condition=models.Q(telegram_user_id__gt=0),
                name="telegram_bot_identity_user_id_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(private_chat_id__gt=0),
                name="telegram_bot_identity_private_chat_id_positive",
            ),
        ]

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None

    def __str__(self):
        return f"Telegram {self.telegram_user_id}"


class TelegramLinkToken(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="telegram_link_tokens",
    )
    token_digest = models.CharField(
        max_length=64,
        unique=True,
        editable=False,
    )
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        constraints = [  # noqa: RUF012
            models.CheckConstraint(
                condition=models.Q(expires_at__gt=models.F("created_at")),
                name="telegram_bot_linktoken_expires_after_creation",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(used_at__isnull=True)
                    | models.Q(
                        used_at__gte=models.F("created_at"),
                        used_at__lte=models.F("expires_at"),
                    )
                ),
                name="telegram_bot_linktoken_used_at_consistency",
            ),
        ]

    @property
    def is_used(self) -> bool:
        return self.used_at is not None

    def __str__(self):
        return f"Telegram link token {self.id}"
