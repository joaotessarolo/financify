from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from ..extraction import TransactionKind
from ..recurrences import create_recurrence, generate_due_draft, parse_recurrence


class RecurrenceServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            email="recurrence@example.com",
            password="StrongPassword!123",
        )

    def test_parses_monthly_recurrence(self):
        result = parse_recurrence(
            "criar recorrência gasto 99,90 assinatura todo dia 10"
        )

        self.assertEqual(result[0], TransactionKind.EXPENSE)
        self.assertEqual(result[1], Decimal("99.90"))
        self.assertEqual(result[2], "assinatura")
        self.assertEqual(result[3], 10)

    def test_due_recurrence_generates_only_one_pending_draft(self):
        recurrence = create_recurrence(
            user=self.user,
            kind=TransactionKind.INCOME,
            amount=Decimal("2500.00"),
            description="Salário",
            day=5,
        )
        recurrence.next_run_on = date(2026, 11, 5)
        recurrence.save(update_fields=["next_run_on", "updated_at"])

        draft = generate_due_draft(
            recurrence=recurrence,
            run_date=date(2026, 11, 9),
        )
        second = generate_due_draft(
            recurrence=recurrence,
            run_date=date(2026, 11, 9),
        )

        self.assertIsNotNone(draft)
        self.assertIsNone(second)
        recurrence.refresh_from_db()
        self.assertEqual(recurrence.last_draft, draft)
        self.assertEqual(recurrence.next_run_on, date(2026, 12, 5))
