import uuid

from django.conf import settings
from django.db import models

from common.money import Currency


class AccountType(models.TextChoices):
    ASSET = "ASSET", "Asset"
    LIABILITY = "LIABILITY", "Liability"
    INCOME = "INCOME", "Income"
    EXPENSE = "EXPENSE", "Expense"
    EQUITY = "EQUITY", "Equity"


class TransactionStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    POSTED = "POSTED", "Posted"
    VOIDED = "VOIDED", "Voided"


class TransactionSource(models.TextChoices):
    MANUAL = "MANUAL", "Manual"
    CHAT = "CHAT", "Chat"
    AUDIO = "AUDIO", "Audio"
    IMPORT = "IMPORT", "Import"


class EntrySide(models.TextChoices):
    DEBIT = "DEBIT", "Debit"
    CREDIT = "CREDIT", "Credit"


class Account(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="accounts",
    )
    name = models.CharField(
        max_length=120,
    )
    account_type = models.CharField(
        max_length=20,
        choices=AccountType.choices,
    )
    currency = models.CharField(
        max_length=3,
        choices=Currency.choices,
    )
    is_active = models.BooleanField(
        default=True,
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
                condition=models.Q(account_type__in=AccountType.values),
                name="ledger_account_type_supported",
            ),
            models.CheckConstraint(
                condition=models.Q(currency__in=Currency.values),
                name="ledger_account_currency_supported",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.currency})"
