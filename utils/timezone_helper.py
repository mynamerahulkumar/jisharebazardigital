from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def now_ist() -> datetime:
    return datetime.now(tz=IST)


def format_ist(dt: datetime | None = None) -> str:
    value = dt or now_ist()
    if value.tzinfo is None:
        value = value.replace(tzinfo=IST)
    return value.astimezone(IST).strftime("%Y-%m-%d %H:%M:%S")


def today_ist() -> str:
    return now_ist().strftime("%Y-%m-%d")


def parse_hhmm(value: str) -> time:
    hour, minute = value.split(":", maxsplit=1)
    return time(hour=int(hour), minute=int(minute), tzinfo=IST)


def is_time_between(start: str, end: str, current: datetime | None = None) -> bool:
    current_time = (current or now_ist()).timetz()
    start_time = parse_hhmm(start)
    end_time = parse_hhmm(end)
    if start_time <= end_time:
        return start_time <= current_time <= end_time
    return current_time >= start_time or current_time <= end_time
