import json
import urllib.error
import urllib.request

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Verify public health and readiness endpoints in a staging environment."

    def add_arguments(self, parser):
        parser.add_argument("--base-url", required=True)
        parser.add_argument("--timeout", type=float, default=10.0)

    def handle(self, *args, **options):
        base_url = options["base_url"].rstrip("/")
        if not base_url.startswith("https://"):
            raise CommandError("Staging URL must use HTTPS.")
        for path in ("/health/", "/ready/"):
            request = urllib.request.Request(f"{base_url}{path}", method="GET")
            try:
                with urllib.request.urlopen(
                    request, timeout=options["timeout"]
                ) as response:
                    payload = json.loads(response.read())
            except (OSError, ValueError, urllib.error.URLError) as exc:
                raise CommandError(f"Staging check failed for {path}.") from None
            if response.status != 200 or payload.get("status") not in {"ok", "ready"}:
                raise CommandError(f"Staging check failed for {path}.")
            self.stdout.write(self.style.SUCCESS(f"{path} is healthy."))
