from decimal import Decimal
import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
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


class Transaction(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="transactions",
    )
    description = models.CharField(
        max_length=255,
    )
    currency = models.CharField(
        max_length=3,
        choices=Currency.choices,
    )
    occurred_at = models.DateTimeField()
    status = models.CharField(
        max_length=20,
        choices=TransactionStatus.choices,
        default=TransactionStatus.DRAFT,
    )
    source = models.CharField(
        max_length=20,
        choices=TransactionSource.choices,
        default=TransactionSource.MANUAL,
    )
    posted_at = models.DateTimeField(
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
                name="ledger_transaction_currency_supported",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=TransactionStatus.values),
                name="ledger_transaction_status_supported",
            ),
            models.CheckConstraint(
                condition=models.Q(source__in=TransactionSource.values),
                name="ledger_transaction_source_supported",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        status=TransactionStatus.DRAFT,
                        posted_at__isnull=True,
                    )
                    | models.Q(
                        status__in=[
                            TransactionStatus.POSTED,
                            TransactionStatus.VOIDED,
                        ],
                        posted_at__isnull=False,
                    )
                ),
                name="ledger_transaction_posted_at_consistency",
            ),
        ]

    def __str__(self):
        return f"{self.description} ({self.status})"


class Entry(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    transaction = models.ForeignKey(
        Transaction,
        on_delete=models.CASCADE,
        related_name="entries",
    )
    account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name="entries",
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
        verbose_name_plural = "entries"
        constraints = [  # noqa: RUF012
            models.CheckConstraint(
                condition=models.Q(side__in=EntrySide.values),
                name="ledger_entry_side_supported",
            ),
            models.CheckConstraint(
                condition=models.Q(amount__gt=Decimal("0.00")),
                name="ledger_entry_amount_positive",
            ),
        ]

    def __str__(self):
        return f"{self.side} {self.amount} ({self.account.name})"
