import uuid

from django.conf import settings
from django.db import models


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
