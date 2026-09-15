"""Degree catalog and section offerings, loaded from ``data/``."""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from src import prereqs

DATA = Path(__file__).resolve().parent.parent / "data"
DEFAULT_CATALOG = DATA / "catalog" / "cs_bs.json"
DEFAULT_SECTIONS = DATA / "sections.json"

_TIME = re.compile(r"\s*(\d{1,2}):(\d{2})\s*([AaPp])\.?[Mm]\.?\s*")
# TTh is two characters for one day each; every other day code is one character per day.
_DAY_SETS = {"TTH": frozenset("TR")}


def parse_time(text):
    """``10:10 AM`` -> 610, minutes since midnight."""
    match = _TIME.fullmatch(text)
    if not match:
        raise ValueError(f"unparsable time {text!r}")
    hour, minute = int(match.group(1)), int(match.group(2))
    if not 1 <= hour <= 12 or minute > 59:
        raise ValueError(f"time out of range {text!r}")
    return (hour % 12 + (12 if match.group(3).upper() == "P" else 0)) * 60 + minute


def parse_time_slot(slot):
    """``10:10 AM - 11:00 AM`` -> (610, 660)."""
    halves = slot.split("-")
    if len(halves) != 2:
        raise ValueError(f"time slot needs exactly one dash: {slot!r}")
    start, end = (parse_time(half) for half in halves)
    if start >= end:
        raise ValueError(f"time slot does not move forward: {slot!r}")
    return start, end


@dataclass(frozen=True)
class Section:
    course: str
    section_id: int
    days: str  # "MWF", "TTh", ...
    time_slot: str
    start: int
    end: int

    @property
    def day_set(self):
        return _DAY_SETS.get(self.days.upper(), frozenset(self.days.upper()))

    def conflicts_with(self, other):
        """Shared day and overlapping half-open time range. The only conflict rule."""
        return bool(self.day_set & other.day_set) and self.start < other.end and other.start < self.end

    def __str__(self):
        return f"{self.days} {self.time_slot}"


@dataclass(frozen=True)
class Catalog:
    program: str
    total_credits: int
    courses: dict
    requirements: list

    def credits(self, code):
        return self._course(code)["credits"]

    def title(self, code):
        return self._course(code)["title"]

    def prereqs(self, code):
        return self._course(code).get("prereqs", "")

    def _course(self, code):
        try:
            return self.courses[code]
        except KeyError:
            raise KeyError(f"{code} is not in the {self.program} catalog") from None


def requirement_courses(requirement):
    """Every distinct course across a requirement's option groups, in order."""
    seen = {}
    for group in requirement["options"]:
        for code in group:
            seen[code] = None
    return list(seen)


def load_catalog(path=DEFAULT_CATALOG):
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    catalog = Catalog(raw["program"], raw["total_credits"], raw["courses"], raw["requirements"])
    _validate(catalog, path)
    return catalog


def _validate(catalog, path):
    """Reject a catalog whose requirements or prerequisites name courses it lacks.

    The previous version of this project shipped data whose shape had drifted
    from the code reading it, and the symptom was a schedule that silently
    dropped every major course. Fail loudly at load instead.
    """
    unknown = {
        code
        for requirement in catalog.requirements
        for code in requirement_courses(requirement)
        if code not in catalog.courses
    }
    for code, course in catalog.courses.items():
        expression = course.get("prereqs", "")
        prereqs.satisfied(expression, ())  # raises on a malformed expression
        unknown |= {c for c in prereqs.courses_in(expression) if c not in catalog.courses}

    if unknown:
        raise ValueError(f"{path}: references unknown courses {sorted(unknown)}")


def load_sections(path=DEFAULT_SECTIONS):
    """Section offerings grouped by course code. Run ``python -m src.offerings`` to build."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing -- run: python -m src.offerings")

    by_course = {}
    for entry in json.loads(path.read_text(encoding="utf-8")):
        start, end = parse_time_slot(entry["time_slot"])
        section = Section(entry["course"], entry["section_id"], entry["days"], entry["time_slot"], start, end)
        by_course.setdefault(section.course, []).append(section)
    return by_course
