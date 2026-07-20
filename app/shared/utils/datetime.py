import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from app.core.config import get_settings

settings = get_settings()

UB_TIMEZONE = ZoneInfo(settings.tz)

def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def to_ulaanbaatar(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(UB_TIMEZONE)

def now_ulaanbaatar() -> datetime:
    return now_utc().astimezone(UB_TIMEZONE)