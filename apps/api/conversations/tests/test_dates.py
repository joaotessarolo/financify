from datetime import UTC, datetime

from django.test import SimpleTestCase

from ..dates import resolve_occurrence_date


class ResolveOccurrenceDateTests(SimpleTestCase):
    reference = datetime(2026, 11, 9, 15, 30, tzinfo=UTC)

    def test_resolves_relative_dates_in_user_timezone(self):
        cases = {
            "hoje": "2026-11-09",
            "ontem": "2026-11-08",
            "sexta": "2026-11-06",
            "dia 5": "2026-11-05",
            "mês passado": "2026-10-09",
        }
        for expression, expected in cases.items():
            with self.subTest(expression=expression):
                result = resolve_occurrence_date(
                    expression=expression,
                    reference=self.reference,
                    timezone_name="America/Sao_Paulo",
                )
                self.assertEqual(result.date().isoformat(), expected)

    def test_preserves_message_time_when_date_is_absent(self):
        self.assertEqual(
            resolve_occurrence_date(
                expression=None,
                reference=self.reference,
                timezone_name="America/Sao_Paulo",
            ),
            self.reference,
        )
