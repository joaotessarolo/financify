from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from conversations.extraction import ExtractedTransaction, TransactionKind
from conversations.models import (
    Conversation,
    ConversationChannel,
    Message,
    MessageDirection,
    MessageStatus,
    MessageType,
)
from conversations.services import (
    confirm_transaction_draft,
    create_transaction_draft_from_extraction,
)
from ledger.categories import ensure_default_categories, find_category
from ledger.services import ensure_default_accounts

from ..budgets import budget_alert_for_transaction, set_budget


class BudgetServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            email="budgets@example.com",
            password="StrongPassword!123",
        )
        ensure_default_accounts(user=cls.user)
        ensure_default_categories(user=cls.user)
        cls.category = find_category(user=cls.user, name="Mercado")
        cls.conversation = Conversation.objects.create(
            user=cls.user, channel=ConversationChannel.TELEGRAM
        )

    def _expense(self, amount: str):
        message = Message.objects.create(
            conversation=self.conversation,
            direction=MessageDirection.INBOUND,
            message_type=MessageType.TEXT,
            status=MessageStatus.COMPLETED,
            content="expense",
            processed_at=timezone.now(),
        )
        draft = create_transaction_draft_from_extraction(
            source_message=message,
            extraction=ExtractedTransaction(
                kind=TransactionKind.EXPENSE,
                amount=Decimal(amount),
                description="Mercado",
            ),
            occurred_at=timezone.now(),
            category=self.category,
        )
        return confirm_transaction_draft(draft=draft)

    def test_alerts_after_eighty_percent(self):
        set_budget(
            user=self.user,
            category_name="Mercado",
            monthly_limit=Decimal("100.00"),
        )

        alert = budget_alert_for_transaction(transaction=self._expense("85.00"))

        self.assertIn("85%", alert)
        self.assertIn("Mercado", alert)

    def test_does_not_alert_below_threshold(self):
        set_budget(
            user=self.user,
            category_name="Mercado",
            monthly_limit=Decimal("100.00"),
        )

        self.assertIsNone(
            budget_alert_for_transaction(transaction=self._expense("50.00"))
        )
