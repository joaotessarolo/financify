import uuid

from django.conf import settings
from django.db import models


class ConversationChannel(models.TextChoices):
    TELEGRAM = "TELEGRAM", "Telegram"


class ConversationStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    ARCHIVED = "ARCHIVED", "Archived"


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
