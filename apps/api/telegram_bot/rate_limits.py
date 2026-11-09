from django.core.cache import cache


def client_ip(request) -> str:
    return request.META.get("REMOTE_ADDR") or "unknown"


def allow_request(*, scope: str, identifier: str, limit: int, window: int) -> bool:
    if limit <= 0 or window <= 0:
        return False
    key = f"rate:{scope}:{identifier}"
    if cache.add(key, 1, timeout=window):
        return True
    try:
        return cache.incr(key) <= limit
    except ValueError:
        cache.set(key, 1, timeout=window)
        return True
