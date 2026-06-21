"""CityScope calendar (.ics) generation.

.ics calendar file generation.

Turns an event happening into an iCalendar (.ics) file — the universal format
every phone/desktop calendar (Apple, Google, Outlook) imports. Tapping the file
on a phone opens "Add to Calendar" with the event prefilled.

We only have fuzzy times from forum/RSS text ("Saturday 8:30pm", "this weekend"),
so we do a best-effort parse into a concrete datetime and fall back to an all-day
event when we can't pin a time. Honest about uncertainty rather than inventing
precision.
"""

import datetime as dt
import re

_WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}
_TIME_RE = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", re.I)


def _next_weekday(base, weekday):
    """Next date (>= today) that falls on the given weekday index."""
    days = (weekday - base.weekday()) % 7
    return base + dt.timedelta(days=days)


def parse_when(when, now=None):
    """
    Best-effort parse of a fuzzy 'when' string into (start_dt, has_time).
    Returns (None, False) if nothing usable. Times assumed local/naive.
    """
    if not when:
        return None, False
    now = now or dt.datetime.now()
    w = when.lower()

    # Day anchor
    day = None
    if "today" in w or "tonight" in w:
        day = now.date()
    elif "tomorrow" in w:
        day = (now + dt.timedelta(days=1)).date()
    else:
        for name, idx in _WEEKDAYS.items():
            if name in w:
                day = _next_weekday(now, idx).date()
                break
    if day is None and ("this week" in w or "weekend" in w):
        # default to the coming Saturday for "this weekend", else today
        day = _next_weekday(now, 5).date() if "weekend" in w else now.date()
    if day is None:
        return None, False

    # Time
    m = _TIME_RE.search(w)
    if m:
        hour = int(m.group(1)) % 12
        if m.group(3).lower() == "pm":
            hour += 12
        minute = int(m.group(2) or 0)
        return dt.datetime.combine(day, dt.time(hour, minute)), True

    return dt.datetime.combine(day, dt.time(0, 0)), False


def _fmt(dt_obj, all_day=False):
    return dt_obj.strftime("%Y%m%d") if all_day else dt_obj.strftime("%Y%m%dT%H%M%S")


def _escape(text):
    return (text or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def build_ics(*, title, when=None, summary="", url="", location="", uid=None, now=None):
    """
    Build an .ics file body for one event. Returns a string.
    Duration defaults to 2 hours for timed events; all-day otherwise.
    """
    start, has_time = parse_when(when, now=now)
    now = now or dt.datetime.now()
    uid = uid or f"cityscope-{abs(hash((title, when))) % (10**10)}@cityscope.app"
    stamp = (now).strftime("%Y%m%dT%H%M%SZ")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//CityScope//EN",
        "CALSCALE:GREGORIAN",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{stamp}",
        f"SUMMARY:{_escape(title)}",
    ]

    if start and has_time:
        end = start + dt.timedelta(hours=2)
        lines += [f"DTSTART:{_fmt(start)}", f"DTEND:{_fmt(end)}"]
    elif start:
        end = start + dt.timedelta(days=1)
        lines += [f"DTSTART;VALUE=DATE:{_fmt(start, all_day=True)}",
                  f"DTEND;VALUE=DATE:{_fmt(end, all_day=True)}"]
    else:
        # no usable date — make it an all-day event today, flagged in desc
        today = now.date()
        lines += [f"DTSTART;VALUE=DATE:{today.strftime('%Y%m%d')}"]

    desc = summary
    if not (start and has_time) and when:
        desc = (desc + f"\n\n(Time approximate — listing said: {when})").strip()
    if desc:
        lines.append(f"DESCRIPTION:{_escape(desc)}")
    if location:
        lines.append(f"LOCATION:{_escape(location)}")
    if url:
        lines.append(f"URL:{_escape(url)}")

    lines += ["END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(lines) + "\r\n"
