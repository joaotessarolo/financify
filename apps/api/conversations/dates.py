from calendar import monthrange
from datetime import datetime, timedelta
import re
from zoneinfo import ZoneInfo


class OccurrenceDateError(ValueError):
    pass


def resolve_occurrence_date(*, expression: str | None, reference: datetime, timezone_name: str) -> datetime:
    if not expression:
        return reference
    zone = ZoneInfo(timezone_name)
    local_reference = reference.astimezone(zone)
    normalized = " ".join(expression.strip().casefold().split())

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", normalized):
        try:
            target_date = datetime.strptime(normalized, "%Y-%m-%d").date()
        except ValueError as exc:
            raise OccurrenceDateError("Invalid ISO date.") from exc
    elif normalized == "hoje":
        target_date = local_reference.date()
    elif normalized == "ontem":
        target_date = local_reference.date() - timedelta(days=1)
    elif normalized in {"sexta", "na sexta", "sexta-feira", "na sexta-feira"}:
        days_back = (local_reference.weekday() - 4) % 7
        target_date = local_reference.date() - timedelta(days=days_back)
    elif normalized.startswith("dia "):
        day = int(normalized.split()[1])
        year, month = local_reference.year, local_reference.month
        if day > monthrange(year, month)[1]:
            raise OccurrenceDateError("Day does not exist in reference month.")
        target_date = local_reference.date().replace(day=day)
        if target_date > local_reference.date():
            month = 12 if month == 1 else month - 1
            year = year - 1 if local_reference.month == 1 else year
            target_date = target_date.replace(year=year, month=month, day=min(day, monthrange(year, month)[1]))
    elif normalized in {"mes passado", "mês passado"}:
        month = 12 if local_reference.month == 1 else local_reference.month - 1
        year = local_reference.year - 1 if local_reference.month == 1 else local_reference.year
        target_date = local_reference.date().replace(
            year=year,
            month=month,
            day=min(local_reference.day, monthrange(year, month)[1]),
        )
    else:
        raise OccurrenceDateError("Unsupported occurrence date.")

    return local_reference.replace(
        year=target_date.year,
        month=target_date.month,
        day=target_date.day,
    ).astimezone(ZoneInfo("UTC"))
