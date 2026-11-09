from io import BytesIO, StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase


class Response(BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class VerifyStagingCommandTests(SimpleTestCase):
    @patch("urllib.request.urlopen")
    def test_checks_health_and_readiness(self, urlopen):
        urlopen.side_effect = [
            Response(b'{"status":"ok"}'),
            Response(b'{"status":"ready"}'),
        ]
        stdout = StringIO()

        call_command(
            "verify_staging",
            base_url="https://staging.example.com",
            stdout=stdout,
        )

        self.assertIn("/health/ is healthy", stdout.getvalue())
        self.assertIn("/ready/ is healthy", stdout.getvalue())
