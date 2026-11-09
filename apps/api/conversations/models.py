from decimal import Decimal
import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from common.money import Currency
from ledger.models import Account, EntrySide


class ConversationChannel(models.TextChoices):
    TELEGRAM = "TELEGRAM", "Telegram"


class ConversationStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    ARCHIVED = "ARCHIVED", "Archived"


class MessageDirection(models.TextChoices):
    INBOUND = "INBOUND", "Inbound"
    OUTBOUND = "OUTBOUND", "Outbound"


class MessageType(models.TextChoices):
    TEXT = "TEXT", "Text"
    VOICE = "VOICE", "Voice"
    SYSTEM = "SYSTEM", "System"


class MessageStatus(models.TextChoices):
    RECEIVED = "RECEIVED", "Received"
    PROCESSING = "PROCESSING", "Processing"
    COMPLETED = "COMPLETED", "Completed"
    FAILED = "FAILED", "Failed"


class TransactionDraftStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    CONFIRMED = "CONFIRMED", "Confirmed"
    REJECTED = "REJECTED", "Rejected"
    EXPIRED = "EXPIRED", "Expired"


class Conversation(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="conversations",
    )
    channel = models.CharField(
        max_length=20,
        choices=ConversationChannel.choices,
    )
    status = models.CharField(
        max_length=20,
        choices=ConversationStatus.choices,
        default=ConversationStatus.ACTIVE,
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        constraints = [  # noqa: RUF012
            models.CheckConstraint(
                condition=models.Q(channel__in=ConversationChannel.values),
                name="conversations_conversation_channel_supported",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=ConversationStatus.values),
                name="conversations_conversation_status_supported",
            ),
            models.UniqueConstraint(
                fields=["user", "channel"],
                condition=models.Q(status=ConversationStatus.ACTIVE),
                name="conversations_one_active_per_user_channel",
            ),
        ]

    def __str__(self):
        return (
            f"{self.user} - {self.get_channel_display()} "
            f"({self.get_status_display()})"
        )


class Message(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    direction = models.CharField(
        max_length=20,
        choices=MessageDirection.choices,
    )
    message_type = models.CharField(
        max_length=20,
        choices=MessageType.choices,
    )
    status = models.CharField(
        max_length=20,
        choices=MessageStatus.choices,
        default=MessageStatus.RECEIVED,
    )
    content = models.TextField(
        blank=True,
        default="",
    )
    external_message_id = models.BigIntegerField(null=True, blank=True)
    processed_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        constraints = [  # noqa: RUF012
            models.CheckConstraint(
                condition=models.Q(direction__in=MessageDirection.values),
                name="conversations_message_direction_supported",
            ),
            models.CheckConstraint(
                condition=models.Q(message_type__in=MessageType.values),
                name="conversations_message_type_supported",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=MessageStatus.values),
                name="conversations_message_status_supported",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        status__in=[
                            MessageStatus.RECEIVED,
                            MessageStatus.PROCESSING,
                        ],
                        processed_at__isnull=True,
                    )
                    | models.Q(
                        status__in=[
                            MessageStatus.COMPLETED,
                            MessageStatus.FAILED,
                        ],
                        processed_at__isnull=False,
                    )
                ),
                name="conversations_message_processed_at_consistency",
            ),
        ]

    def __str__(self):
        return (
            f"{self.get_direction_display()} {self.get_message_type_display()} "
            f"({self.get_status_display()})"
        )


class TransactionDraft(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="transaction_drafts",
    )
    source_message = models.ForeignKey(
        Message,
        on_delete=models.RESTRICT,
        related_name="transaction_drafts",
    )
    transaction = models.OneToOneField(
        "ledger.Transaction",
        on_delete=models.RESTRICT,
        related_name="source_draft",
        null=True,
        blank=True,
    )
    description = models.CharField(
        max_length=255,
    )
    currency = models.CharField(
        max_length=3,
        choices=Currency.choices,
    )
    category = models.ForeignKey(
        "ledger.Category",
        on_delete=models.PROTECT,
        related_name="drafts",
        null=True,
        blank=True,
    )
    occurred_at = models.DateTimeField()
    status = models.CharField(
        max_length=20,
        choices=TransactionDraftStatus.choices,
        default=TransactionDraftStatus.PENDING,
    )
    expires_at = models.DateTimeField()
    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        constraints = [  # noqa: RUF012
            models.CheckConstraint(
                condition=models.Q(currency__in=Currency.values),
                name="conversations_transactiondraft_currency_supported",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=TransactionDraftStatus.values),
                name="conversations_transactiondraft_status_supported",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        status=TransactionDraftStatus.PENDING,
                        resolved_at__isnull=True,
                    )
                    | models.Q(
                        status__in=[
                            TransactionDraftStatus.CONFIRMED,
                            TransactionDraftStatus.REJECTED,
                            TransactionDraftStatus.EXPIRED,
                        ],
                        resolved_at__isnull=False,
                    )
                ),
                name="conversations_transactiondraft_resolved_at_consistency",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        status=TransactionDraftStatus.CONFIRMED,
                        transaction__isnull=False,
                    )
                    | models.Q(
                        status__in=[
                            TransactionDraftStatus.PENDING,
                            TransactionDraftStatus.REJECTED,
                            TransactionDraftStatus.EXPIRED,
                        ],
                        transaction__isnull=True,
                    )
                ),
                name="conversations_transactiondraft_transaction_consistency",
            ),
        ]

    def __str__(self):
        return f"{self.description} ({self.get_status_display()})"


class DraftEntry(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    draft = models.ForeignKey(
        TransactionDraft,
        on_delete=models.CASCADE,
        related_name="entries",
    )
    account = models.ForeignKey(
        Account,
        on_delete=models.RESTRICT,
        related_name="draft_entries",
    )
    side = models.CharField(
        max_length=10,
        choices=EntrySide.choices,
    )
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    memo = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        verbose_name_plural = "draft entries"
        constraints = [  # noqa: RUF012
            models.CheckConstraint(
                condition=models.Q(side__in=EntrySide.values),
                name="conversations_draftentry_side_supported",
            ),
            models.CheckConstraint(
                condition=models.Q(amount__gt=Decimal("0.00")),
                name="conversations_draftentry_amount_positive",
            ),
        ]

    def __str__(self):
        return f"{self.get_side_display()} {self.amount} ({self.account.name})"


class RecurringTransaction(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="recurring_transactions",
    )
    kind = models.CharField(max_length=20)
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    description = models.CharField(max_length=255)
    account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name="recurring_transactions",
    )
    category = models.ForeignKey(
        "ledger.Category",
        on_delete=models.PROTECT,
        related_name="recurring_transactions",
        null=True,
        blank=True,
    )
    day_of_month = models.PositiveSmallIntegerField()
    next_run_on = models.DateField()
    is_active = models.BooleanField(default=True)
    last_draft = models.ForeignKey(
        TransactionDraft,
        on_delete=models.SET_NULL,
        related_name="generated_by_recurrences",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [  # noqa: RUF012
            models.CheckConstraint(
                condition=models.Q(kind__in=["EXPENSE", "INCOME"]),
                name="conversations_recurrence_kind_supported",
            ),
            models.CheckConstraint(
                condition=models.Q(day_of_month__gte=1, day_of_month__lte=28),
                name="conversations_recurrence_day_supported",
            ),
        ]
