from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET


@require_GET
def health(request):
    return JsonResponse({"status": "ok"})


@require_GET
def readiness(request):
    missing_configuration = [
        name
        for name in (
            "TELEGRAM_BOT_TOKEN",
            "TELEGRAM_BOT_USERNAME",
            "TELEGRAM_WEBHOOK_SECRET",
        )
        if not getattr(settings, name, "")
    ]
    database_ready = True
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        database_ready = False

    ready = database_ready and not missing_configuration
    return JsonResponse(
        {
            "status": "ready" if ready else "not_ready",
            "database": "ok" if database_ready else "unavailable",
            "configuration": "ok" if not missing_configuration else "missing",
        },
        status=200 if ready else 503,
    )
