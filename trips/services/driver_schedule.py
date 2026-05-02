"""Parse driver-facing date/time inputs for trip planning."""

from datetime import date, datetime, time, timedelta
from typing import Any, Dict, Optional, Tuple


def parse_log_date(raw: Any) -> Optional[date]:
    """Parse YYYY-MM-DD from client JSON."""
    if raw is None:
        return None
    s = str(raw).strip()
    if len(s) < 10:
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def parse_duty_clock(raw: Any) -> Tuple[Optional[float], Optional[time], Optional[str]]:
    """
    Expect 'HH:MM' or 'HH:MM:SS' (24-hour). Returns (hours since midnight as float, error message).
    """
    if raw is None or raw == "":
        return 0.0, time(0, 0), None

    s = str(raw).strip()
    parts = s.split(":")

    try:
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
        sec = int(parts[2]) if len(parts) > 2 else 0
    except (ValueError, IndexError):
        return None, None, "Invalid duty_start_time (use HH:MM)"

    if not (0 <= h <= 23 and 0 <= m <= 59 and 0 <= sec <= 59):
        return None, None, "duty_start_time out of range"

    frac = h + m / 60.0 + sec / 3600.0

    # Allow exactly 24 meaning end-of-day interpreted as midnight next — reject for simplicity.
    if frac >= 24.0 - 1e-9:
        return None, None, "duty_start_time must be before midnight"

    return frac, time(hour=h, minute=m, second=sec), None


def annotate_calendar_dates(logs: list, log_date: date) -> None:
    """In-place attach ISO calendar_date to each log row in sequential order."""
    for i, entry in enumerate(logs):
        entry["calendar_date"] = (log_date + timedelta(days=i)).isoformat()


def persisted_driver_payload(
    name: str, log_date: date, duty_t: datetime.time
) -> Dict[str, str]:
    return {
        "driver_name": name,
        "log_date": log_date.isoformat(),
        "duty_start_time": duty_t.strftime("%H:%M"),
    }
