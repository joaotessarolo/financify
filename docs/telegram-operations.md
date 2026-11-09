# Telegram operations

## Data retention

Financify stores the normalized conversation text needed to explain and audit a
financial draft. It stores the Telegram message ID for correlation, but not the
raw update payload, Telegram file URL, bot token, provider response, or audio.

Voice bytes are held in memory only while the worker sends them to the configured
transcription provider. They are discarded when the task finishes. Application
logs and metrics must contain IDs, timings, status, and error codes only—not the
message body, transcript, amount, account name, provider payload, or credentials.

## Worker

Run Redis and the Celery worker alongside the API. Monitor the queue and retry
counts; voice tasks use bounded retries for Telegram delivery failures.

## Staging checklist

1. Deploy the API and worker with separate production-style secrets.
2. Run migrations and configure the Telegram webhook on the staging bot.
3. Run `uv run python manage.py verify_staging --base-url https://staging.example.com`.
4. Link a test user and verify text, voice, edit, confirm, cancel, transfer, and
   duplicate callback flows.
5. Verify `/api/v1/telegram/metrics/` as a staff user and inspect worker logs for
   structured events without financial content.
6. Revoke the Telegram link and confirm that later financial messages are rejected.

Do not reuse the production bot token or production user data in staging.
