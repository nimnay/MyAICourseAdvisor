"""Build a conflict-free schedule from the catalog, the offerings and a transcript.

This is the part that decides. The model in ``advisor`` reads free-text
constraints and explains the result; it never picks the courses, because
prerequisite and time-conflict correctness is checkable and so it gets checked.
"""

from dataclasses import dataclass, field
from itertools import zip_longest

from src import prereqs

MIN_CREDITS = 12
TARGET_MIN_CREDITS = 16
TARGET_MAX_CREDITS = 18

DAY_ORDER = "MTWRF"
DAY_NAMES = {"M": "Monday", "T": "Tuesday", "W": "Wednesday", "R": "Thursday", "F": "Friday"}


@dataclass
class Schedule:
    picks: list = field(default_factory=list)  # [(course_code, Section)]
    skipped: list = field(default_factory=list)  # [(course_code, reason)]

    def credits(self, catalog):
        return sum(catalog.credits(code) for code, _ in self.picks)

    def conflict(self):
        """Any conflicting pair, or None. Cheap enough to assert on every build."""
        for i, (code_a, a) in enumerate(self.picks):
            for code_b, b in self.picks[i + 1:]:
                if a.conflicts_with(b):
                    return code_a, code_b
        return None


def option_pool(catalog, requirement, have):
    """The courses this requirement can still be satisfied with.

    Options that are multi-course groups are alternative sequences -- take the
    group the student is furthest into and stay in it, so a student who started
    biology is never told to also start chemistry. Options that are all single
    courses are a pool, and any of them counts.
    """
    groups = requirement["options"]
    if all(len(group) == 1 for group in groups):
        return [code for group in groups for code in group]
    # max() keeps the first group on a tie, so an untouched requirement is deterministic.
    return max(groups, key=lambda group: sum(catalog.credits(c) for c in group if c in have))


def progress(catalog, taken):
    """Per-requirement credit progress toward the degree.

    ponytail: counts a course toward every requirement that lists it. The real
    catalog forbids double-counting across several requirements, so remaining
    credits can read low for a student who leaned on shared courses. Track
    assignments per course if that matters.
    """
    have = {prereqs.normalize(code) for code in taken}
    rows = []
    for requirement in catalog.requirements:
        earned = sum(
            catalog.credits(code)
            for code in option_pool(catalog, requirement, have)
            if code in have
        )
        required = requirement["credits"]
        rows.append(
            {
                "id": requirement["id"],
                "name": requirement["name"],
                "required": required,
                "earned": min(earned, required),
                "remaining": max(0, required - earned),
            }
        )
    return rows


def unlock_counts(catalog):
    """How many catalog courses each course is a prerequisite for."""
    counts = {}
    for course in catalog.courses.values():
        for code in prereqs.courses_in(course.get("prereqs", "")):
            counts[code] = counts.get(code, 0) + 1
    return counts


def eligible(catalog, code, completed):
    """Prerequisites met. ``completed`` should include in-progress courses."""
    return prereqs.satisfied(catalog.prereqs(code), completed)


def candidates(catalog, taken, in_progress=()):
    """Courses worth taking next, best first.

    One course from each unmet requirement in degree-sequence order, then a
    second from each, and so on. Draining requirements one at a time instead
    would spend a whole term on whichever is earliest in the catalog.
    """
    have = {prereqs.normalize(c) for c in taken}
    completed = have | {prereqs.normalize(c) for c in in_progress}
    unlocks = unlock_counts(catalog)

    queues = []
    for position, row in enumerate(progress(catalog, taken)):
        if not row["remaining"]:
            continue
        queue = [
            code
            for code in option_pool(catalog, catalog.requirements[position], have)
            if code not in completed and eligible(catalog, code, completed)
        ]
        if queue:
            queues.append(sorted(queue, key=lambda code: (-unlocks.get(code, 0), code)))

    seen = {}
    for tier in zip_longest(*queues):
        for code in tier:
            if code is not None:
                seen[code] = None
    return list(seen)


def allowed(section, constraints):
    """Does a section fit the student's stated time constraints?"""
    if not constraints:
        return True
    if section.start < constraints.get("earliest", 0):
        return False
    if section.end > constraints.get("latest", 24 * 60):
        return False
    return not set(constraints.get("avoid_days", "")) & section.day_set


def build(catalog, sections, taken, in_progress=(), constraints=None,
          target=TARGET_MIN_CREDITS, maximum=TARGET_MAX_CREDITS):
    """Pick a conflict-free schedule of roughly ``target`` credits.

    ponytail: greedy, first fitting section wins, no backtracking. It can miss a
    fuller schedule when an early pick blocks a later course that had only one
    workable section. Swap the section loop for a DFS over section choices if
    students start hitting that.
    """
    schedule = Schedule()
    credits = 0

    for code in candidates(catalog, taken, in_progress):
        cost = catalog.credits(code)
        if credits + cost > maximum:
            schedule.skipped.append((code, f"would exceed {maximum} credits"))
            continue

        offered = sections.get(code)
        if not offered:
            schedule.skipped.append((code, "no sections offered this term"))
            continue

        fits = [s for s in offered if allowed(s, constraints)]
        if not fits:
            schedule.skipped.append((code, "every section is outside your time constraints"))
            continue

        chosen = next(
            (s for s in fits if not any(s.conflicts_with(p) for _, p in schedule.picks)),
            None,
        )
        if chosen is None:
            schedule.skipped.append((code, "every section clashes with a course already picked"))
            continue

        schedule.picks.append((code, chosen))
        credits += cost
        if credits >= target:
            break

    clash = schedule.conflict()
    assert clash is None, f"built a conflicting schedule: {clash}"
    return schedule


def blocked(catalog, taken, in_progress=()):
    """Courses still needed but not yet takeable, with the prerequisites missing."""
    completed = {prereqs.normalize(c) for c in taken} | {prereqs.normalize(c) for c in in_progress}
    rows = []
    for position, requirement in enumerate(progress(catalog, taken)):
        if not requirement["remaining"]:
            continue
        for code in option_pool(catalog, catalog.requirements[position], completed):
            if code in completed or eligible(catalog, code, completed):
                continue
            missing = [c for c in prereqs.courses_in(catalog.prereqs(code)) if c not in completed]
            rows.append({"course": code, "requirement": requirement["name"], "missing": missing})
    return rows


def weekly_grid(schedule, catalog):
    """Schedule as ``{day: [(start, end, code, title, section)]}``, each day time-sorted."""
    grid = {day: [] for day in DAY_ORDER}
    for code, section in schedule.picks:
        for day in section.day_set:
            grid[day].append((section.start, section.end, code, catalog.title(code), section))
    for day in grid:
        grid[day].sort()
    return grid
