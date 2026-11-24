from datetime import datetime, timezone
from zoneinfo import ZoneInfo

ROMA = ZoneInfo("Europe/Rome")


def adesso() -> datetime:
    return datetime.now(timezone.utc)


def come_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def come_roma(value: datetime) -> datetime:
    return come_utc(value).astimezone(ROMA)
