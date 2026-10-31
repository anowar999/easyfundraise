"""AGT-06: deterministic note parsing -> reminders + suggested card changes (no LLM needed)."""

import re
from datetime import date, timedelta

from .tracker_import import to_date

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]


def _next_weekday(today: date, wd: int) -> date:
    return today + timedelta(days=(wd - today.weekday() - 1) % 7 + 1)


def find_date(text: str, today: date) -> date | None:
    t = text.lower()
    if re.search(r"\btomorrow\b", t):
        return today + timedelta(days=1)
    if m := re.search(r"\bin (\d{1,2}) (day|week)s?\b", t):
        n = int(m.group(1))
        return today + timedelta(days=n * (7 if m.group(2) == "week" else 1))
    if re.search(r"\bnext week\b", t):
        return _next_weekday(today, 0)
    if m := re.search(r"\b(?:on |next )?(" + "|".join(WEEKDAYS) + r")\b", t):
        return _next_weekday(today, WEEKDAYS.index(m.group(1)))
    if m := re.search(r"\bq([1-4])\b", t):
        q = int(m.group(1))
        d = date(today.year, 3 * (q - 1) + 1, 1)
        return d if d > today else date(today.year + 1, d.month, 1)
    if m := re.search(r"\b(\d{1,2})[/.](\d{1,2})(?:[/.](\d{2,4}))?\b", t):
        dd, mm, yy = int(m.group(1)), int(m.group(2)), m.group(3)
        y = int(yy) + (2000 if yy and len(yy) == 2 else 0) if yy else today.year
        try:
            d = date(y, mm, dd)  # founders' trackers are mostly dd/mm
        except ValueError:
            try:
                d = date(y, dd, mm)
            except ValueError:
                return None
        return d if yy or d >= today else date(y + 1, d.month, d.day)
    if m := re.search(r"\b(\d{1,2}) (" + "|".join(MONTHS) + r")[a-z]*\b", t):
        try:
            d = date(today.year, MONTHS.index(m.group(2)) + 1, int(m.group(1)))
            return d if d >= today else d.replace(year=today.year + 1)
        except ValueError:
            return None
    return to_date(text) if len(text) < 20 else None


def parse_note(text: str, today: date) -> dict:
    """Returns {reminder_date, suggestions: [{field, value, reason}]}."""
    t = text.lower()
    out: dict = {"reminder_date": find_date(text, today), "suggestions": []}
    sug = out["suggestions"]
    if re.search(r"(asked|requested|wants|send).{0,20}\bdeck\b|\bdeck requested\b", t):
        sug.append({"field": "stage", "value": 5, "reason": "They asked for the deck"})
    if re.search(r"\b(call|meeting|zoom|coffee) (booked|arranged|scheduled|set)\b|\bmeeting on\b", t):
        sug.append({"field": "stage", "value": 4, "reason": "A call was arranged"})
    if re.search(r"\bterm ?sheet\b", t):
        sug.append({"field": "stage", "value": 7, "reason": "Term sheet mentioned"})
    if m := re.search(r"\bintro (?:via|from|by) ([A-Z][\w.'-]+(?: [A-Z][\w.'-]+)?)", text, re.I):
        sug.append({"field": "referrer", "value": m.group(1), "reason": "Intro source mentioned"})
    if re.search(r"\bghost(ing|ed)?\b|\bno (reply|response)\b", t):
        sug.append({"field": "status", "value": "Ghosting", "reason": "No response noted"})
    if re.search(r"\b(pass(ed)?|not a fit|declined|no thanks)\b", t):
        sug.append({"field": "status", "value": "Rejection", "reason": "They passed"})
    if re.search(r"\bnot now\b|\btoo early\b|\bcome back\b", t) and out["reminder_date"]:
        sug.append({"field": "next_contact_date", "value": out["reminder_date"].isoformat(),
                    "reason": "Snooze and re-engage"})
    return out
