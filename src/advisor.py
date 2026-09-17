"""Optional Claude layer: read free-text time constraints, explain a schedule.

The scheduler decides which courses to take. This module only translates and
narrates, so the app works fully without credentials: constraints fall back to a
regex, and the explanation is simply omitted.
"""

import logging
import os
import re

logger = logging.getLogger(__name__)

MODEL = os.environ.get("AIADVISOR_MODEL", "claude-opus-5")

_DAY_WORDS = {
    "monday": "M", "mon": "M",
    "tuesday": "T", "tues": "T", "tue": "T",
    "wednesday": "W", "weds": "W", "wed": "W",
    "thursday": "R", "thurs": "R", "thu": "R",
    "friday": "F", "fri": "F",
}
_CLOCK = r"(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?"


def client():
    """An Anthropic client, or None when the SDK or credentials are missing.

    Broad except on purpose: every failure here means the same thing to callers,
    that there is no model available, which is a fully supported mode.
    """
    try:
        import anthropic

        return anthropic.Anthropic()
    except Exception as error:
        logger.info("Claude unavailable (%s); running without it", error)
        return None


def parse_constraints(text, api=None):
    """Free text -> ``{"earliest": minutes, "latest": minutes, "avoid_days": "F"}``."""
    if not text or not text.strip():
        return {}

    api = api or client()
    if api is not None:
        try:
            return _parse_with_claude(text, api)
        except Exception as error:
            logger.warning("Claude could not parse constraints (%s); using regex", error)
    return parse_constraints_regex(text)


def parse_constraints_regex(text):
    """Fallback parser. Handles the common shapes, not arbitrary English."""
    lowered = text.lower()
    found = {}

    for keyword, key in (("before", "earliest"), ("after", "latest")):
        match = re.search(rf"\b{keyword}\s+{_CLOCK}", lowered)
        if match:
            found[key] = _to_minutes(match.group(1), match.group(2), match.group(3))

    avoid = {
        letter
        for word, letter in _DAY_WORDS.items()
        if re.search(rf"\bno\b[^.]*\b{word}s?\b|\b{word}s?\b[^.]*\boff\b", lowered)
    }
    if avoid:
        found["avoid_days"] = "".join(sorted(avoid, key="MTWRF".index))
    return found


def _to_minutes(hour, minute, meridiem):
    hour, minute = int(hour), int(minute or 0)
    if meridiem and meridiem.startswith("p"):
        hour = hour % 12 + 12
    elif meridiem and meridiem.startswith("a"):
        hour %= 12
    elif hour < 8:
        hour += 12  # "no classes after 5" means 5pm on a campus timetable
    return hour * 60 + minute


def _parse_with_claude(text, api):
    from pydantic import BaseModel

    class TimeConstraints(BaseModel):
        earliest_start: str | None = None  # "HH:MM", 24-hour, or null
        latest_end: str | None = None
        avoid_days: str = ""  # letters from MTWRF, R means Thursday

    response = api.messages.parse(
        model=MODEL,
        max_tokens=512,
        output_config={"effort": "low"},  # single-sentence extraction
        system=(
            "Convert a student's scheduling preference into times. Use 24-hour HH:MM. "
            "earliest_start is the earliest a class may begin, latest_end the latest a "
            "class may end. avoid_days uses M T W R F, where R is Thursday. Leave a "
            "field null or empty when the student did not mention it."
        ),
        messages=[{"role": "user", "content": text}],
        output_format=TimeConstraints,
    )

    parsed = response.parsed_output
    found = {}
    if parsed.earliest_start:
        found["earliest"] = _clock_to_minutes(parsed.earliest_start)
    if parsed.latest_end:
        found["latest"] = _clock_to_minutes(parsed.latest_end)
    days = "".join(d for d in parsed.avoid_days.upper() if d in "MTWRF")
    if days:
        found["avoid_days"] = days
    return found


def _clock_to_minutes(clock):
    hour, _, minute = clock.partition(":")
    return int(hour) * 60 + int(minute or 0)


def explain(schedule, catalog, remaining, api=None):
    """A short note on why this schedule fits. None when Claude is unavailable."""
    if not schedule.picks:
        return None

    api = api or client()
    if api is None:
        return None

    courses = "\n".join(
        f"- {code} {catalog.title(code)} ({catalog.credits(code)} cr) {section}"
        for code, section in schedule.picks
    )
    outstanding = ", ".join(f"{r['name']} ({r['remaining']} cr)" for r in remaining[:6]) or "none"

    try:
        response = api.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=(
                "You are an academic advisor. In at most three sentences, explain why "
                "this term fits the student's degree progress and what it sets up next. "
                "Do not invent courses, times or prerequisites beyond what you are given."
            ),
            messages=[{
                "role": "user",
                "content": (
                    f"Next term ({schedule.credits(catalog)} credits):\n{courses}\n\n"
                    f"Still outstanding: {outstanding}"
                ),
            }],
        )
        return "".join(b.text for b in response.content if b.type == "text").strip()
    except Exception as error:
        logger.warning("Claude could not explain the schedule (%s)", error)
        return None
