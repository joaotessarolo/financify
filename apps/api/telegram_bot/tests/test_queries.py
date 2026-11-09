from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from conversations.extraction import ExtractedTransaction, TransactionKind
from conversations.models import Conversation, ConversationChannel, Message, MessageDirection, MessageStatus, MessageType
from conversations.services import create_transaction_draft_from_extraction, confirm_transaction_draft
from ledger.services import ensure_default_accounts

from ..queries import account_statement, expense_summary


class TelegramFinancialQueryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            email="queries@example.com",
            password="StrongPassword!123",
        )
        cls.accounts = ensure_default_accounts(user=cls.user)
        cls.conversation = Conversation.objects.create(
            user=cls.user,
            channel=ConversationChannel.TELEGRAM,
        )

    def _confirm_expense(self, amount: str, occurred_at):
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
            occurred_at=occurred_at,
        )
        return confirm_transaction_draft(draft=draft)

    def test_summarizes_only_confirmed_expenses_in_period(self):
        self._confirm_expense("40.00", timezone.now())
        self._confirm_expense("10.00", timezone.now() - timedelta(days=40))

        self.assertIn("BRL 40,00", expense_summary(user=self.user, period="today"))

    def test_builds_account_statement(self):
        self._confirm_expense("25.00", timezone.now())

        statement = account_statement(
            user=self.user,
            account_name=self.accounts.primary.name,
        )

        self.assertIn("-BRL 25,00", statement)
        self.assertIn("Mercado", statement)
