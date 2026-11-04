import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class TelegramOnboardingStep(models.TextChoices):
    AWAITING_ACCOUNT = "AWAITING_ACCOUNT", "Awaiting account"
    AWAITING_BALANCE = "AWAITING_BALANCE", "Awaiting balance"
    COMPLETED = "COMPLETED", "Completed"


class TelegramUpdateType(models.TextChoices):
    MESSAGE = "MESSAGE", "Message"
    CALLBACK_QUERY = "CALLBACK_QUERY", "Callback query"
    UNSUPPORTED = "UNSUPPORTED", "Unsupported"


class TelegramUpdateStatus(models.TextChoices):
    RECEIVED = "RECEIVED", "Received"
    PROCESSING = "PROCESSING", "Processing"
    COMPLETED = "COMPLETED", "Completed"
    FAILED = "FAILED", "Failed"


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
    onboarding_step = models.CharField(
        max_length=24,
        choices=TelegramOnboardingStep.choices,
        default=TelegramOnboardingStep.AWAITING_ACCOUNT,
    )
    pending_account_name = models.CharField(
        max_length=120,
        blank=True,
        default="",
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
            models.CheckConstraint(
                condition=models.Q(
                    onboarding_step__in=TelegramOnboardingStep.values
                ),
                name="telegram_bot_identity_onboarding_step_supported",
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


class TelegramUpdate(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    update_id = models.BigIntegerField(
        unique=True,
        validators=[MinValueValidator(1)],
    )
    update_type = models.CharField(
        max_length=20,
        choices=TelegramUpdateType.choices,
    )
    status = models.CharField(
        max_length=20,
        choices=TelegramUpdateStatus.choices,
        default=TelegramUpdateStatus.RECEIVED,
    )
    error_code = models.CharField(
        max_length=64,
        blank=True,
        default="",
    )
    received_at = models.DateTimeField(
        auto_now_add=True,
    )
    processed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:
        constraints = [  # noqa: RUF012
            models.CheckConstraint(
                condition=models.Q(update_id__gt=0),
                name="telegram_bot_update_update_id_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    update_type__in=TelegramUpdateType.values,
                ),
                name="telegram_bot_update_type_supported",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    status__in=TelegramUpdateStatus.values,
                ),
                name="telegram_bot_update_status_supported",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        status__in=[
                            TelegramUpdateStatus.RECEIVED,
                            TelegramUpdateStatus.PROCESSING,
                        ],
                        processed_at__isnull=True,
                    )
                    | models.Q(
                        status__in=[
                            TelegramUpdateStatus.COMPLETED,
                            TelegramUpdateStatus.FAILED,
                        ],
                        processed_at__isnull=False,
                    )
                ),
                name="telegram_bot_update_processed_at_consistency",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(status=TelegramUpdateStatus.FAILED)
                    | models.Q(
                        status__in=[
                            TelegramUpdateStatus.RECEIVED,
                            TelegramUpdateStatus.PROCESSING,
                            TelegramUpdateStatus.COMPLETED,
                        ],
                        error_code="",
                    )
                ),
                name="telegram_bot_update_error_code_consistency",
            ),
        ]

    def __str__(self):
        return f"Telegram update {self.update_id} ({self.get_status_display()})"
