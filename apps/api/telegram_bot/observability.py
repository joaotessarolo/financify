import logging

from django.core.cache import cache

logger = logging.getLogger("financify.events")

METRIC_NAMES = (
    "updates_accepted",
    "updates_completed",
    "updates_duplicate",
    "updates_failed",
    "outbound_failed",
    "voice_completed",
    "voice_failed",
    "extraction_failed",
    "drafts_created",
    "drafts_confirmed",
    "drafts_cancelled",
)


def record_event(name: str, **dimensions) -> None:
    key = f"metric:{name}"
    if cache.add(key, 1, timeout=None) is False:
        try:
            cache.incr(key)
        except ValueError:
            cache.set(key, 1, timeout=None)
    logger.info("event=%s", name, extra={"event_name": name, **dimensions})


def metrics_snapshot() -> dict[str, int]:
    return {name: int(cache.get(f"metric:{name}", 0)) for name in METRIC_NAMES}
