"""Checks for the parts that can be wrong silently: prerequisites, conflicts, selection.

Runs under pytest, or standalone: ``python tests/test_engine.py``
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import advisor, prereqs, scheduler  # noqa: E402
from src.catalog import Section, load_catalog, load_sections, parse_time_slot  # noqa: E402


def section(course, days, slot, section_id=1):
    start, end = parse_time_slot(slot)
    return Section(course, section_id, days, slot, start, end)


def test_prereq_operators():
    assert prereqs.satisfied("", [])
    assert prereqs.satisfied(None, [])
    assert prereqs.satisfied("CPSC 2120", ["CPSC 2120"])
    assert not prereqs.satisfied("CPSC 2120", ["CPSC 2150"])
    assert prereqs.satisfied("CPSC 1020 OR CPSC 1070", ["CPSC 1070"])
    assert not prereqs.satisfied("CPSC 2120 AND CPSC 2070", ["CPSC 2120"])
    assert prereqs.satisfied("CPSC 2120 AND CPSC 2070", ["CPSC 2120", "CPSC 2070"])


def test_prereq_precedence_and_parens():
    # AND binds tighter than OR: false AND false OR true -> true
    assert prereqs.satisfied("CPSC 9998 AND CPSC 9999 OR MATH 1060", ["MATH 1060"])
    # Parentheses override it: (false OR true) AND false -> false
    assert not prereqs.satisfied("(CPSC 9999 OR MATH 1060) AND CPSC 9998", ["MATH 1060"])
    assert prereqs.satisfied("(CPSC 9999 OR MATH 1060) AND CPSC 2120", ["MATH 1060", "CPSC 2120"])


def test_prereq_code_normalizing():
    assert prereqs.normalize("cpsc2120") == "CPSC 2120"
    assert prereqs.normalize("CH 1010") == "CH 1010"
    assert prereqs.satisfied("CPSC 2120", ["cpsc2120"])
    assert prereqs.courses_in("CPSC 2120 AND (MATH 1060 OR MATH 1070)") == [
        "CPSC 2120", "MATH 1060", "MATH 1070"]


def test_prereq_malformed_is_loud():
    """A bad expression must raise, never quietly let a student through."""
    for bad in ["CPSC 2120 AND", "(CPSC 2120", "AND CPSC 2120", "CPSC 2120 )"]:
        try:
            prereqs.satisfied(bad, ["CPSC 2120"])
        except ValueError:
            continue
        raise AssertionError(f"{bad!r} should have raised")


def test_time_and_conflicts():
    assert parse_time_slot("10:10 AM - 11:00 AM") == (610, 660)
    assert parse_time_slot("12:20 PM - 1:10 PM") == (740, 790)

    a = section("A", "MWF", "10:10 AM - 11:00 AM")
    assert a.conflicts_with(section("B", "MWF", "10:30 AM - 11:20 AM"))  # overlap, shared days
    assert not a.conflicts_with(section("B", "MWF", "11:15 AM - 12:05 PM"))  # back to back
    assert not a.conflicts_with(section("B", "TTh", "10:10 AM - 11:00 AM"))  # no shared day
    # TTh is Tuesday+Thursday, so it must clash with a Tuesday-only meeting
    assert section("A", "TTh", "9:30 AM - 10:45 AM").conflicts_with(
        section("B", "T", "10:00 AM - 10:50 AM"))


def test_option_pool_sequence_vs_pool():
    catalog = load_catalog()
    science = next(r for r in catalog.requirements if r["id"] == "natural_science")
    core = next(r for r in catalog.requirements if r["id"] == "cs_core")

    # Alternative sequences: a student who started biology stays in biology.
    assert "BIOL 1030" in scheduler.option_pool(catalog, science, {"BIOL 1030"})
    assert "CH 1010" not in scheduler.option_pool(catalog, science, {"BIOL 1030"})
    # A pool of single courses offers everything.
    assert set(scheduler.option_pool(catalog, core, set())) >= {"CPSC 2070", "CPSC 2120"}


def test_no_course_counts_toward_two_requirements():
    """The catalog forbids one course satisfying several requirements."""
    catalog = load_catalog()
    # Each of these is listed under two requirements in the catalog.
    taken = ["ECON 2110", "PSYC 2010", "PHIL 3250", "MUSC 3140"]

    claimed = scheduler.assign(catalog, taken)
    assert sorted(claimed) == sorted(taken), "each usable course should be claimed once"

    rows = scheduler.progress(catalog, taken)
    assert sum(row["earned"] for row in rows) == sum(catalog.credits(c) for c in taken)

    # A claimed course must actually belong to the requirement claiming it.
    by_id = {r["id"]: r for r in catalog.requirements}
    for code, requirement_id in claimed.items():
        assert code in scheduler.option_pool(catalog, by_id[requirement_id], set(taken))


def test_built_schedule_is_valid():
    catalog, sections = load_catalog(), load_sections()
    taken = ["CPSC 1010", "CPSC 1020", "MATH 1060", "MATH 1080", "ENGL 1030"]
    schedule = scheduler.build(catalog, sections, taken)

    assert schedule.picks, "a sophomore with intro CS done should get a schedule"
    assert schedule.conflict() is None
    assert schedule.credits(catalog) <= scheduler.TARGET_MAX_CREDITS
    for code, _ in schedule.picks:
        assert code not in taken, f"{code} was already completed"
        assert scheduler.eligible(catalog, code, set(taken)), f"{code} prerequisites unmet"


def test_schedule_never_recommends_a_blocked_course():
    """CPSC 2150 needs CPSC 2120, so a freshman must not be offered it."""
    catalog, sections = load_catalog(), load_sections()
    schedule = scheduler.build(catalog, sections, [])
    assert "CPSC 2150" not in [code for code, _ in schedule.picks]


def test_in_progress_courses_unlock_the_next_one():
    catalog, sections = load_catalog(), load_sections()
    taken = ["CPSC 1010", "CPSC 1020", "MATH 1060"]
    assert not scheduler.eligible(catalog, "CPSC 2150", set(taken))
    assert scheduler.eligible(catalog, "CPSC 2150", set(taken) | {"CPSC 2120"})


def test_constraints_are_respected():
    catalog, sections = load_catalog(), load_sections()
    taken = ["CPSC 1010", "CPSC 1020", "MATH 1060", "MATH 1080", "ENGL 1030"]
    constraints = {"earliest": 600, "avoid_days": "F"}
    schedule = scheduler.build(catalog, sections, taken, constraints=constraints)

    for code, chosen in schedule.picks:
        assert chosen.start >= 600, f"{code} starts before 10am"
        assert "F" not in chosen.day_set, f"{code} meets on Friday"


def test_catalog_rejects_unknown_course_references():
    """The failure mode that broke the old version: data drifting from the code."""
    broken = {
        "program": "Broken", "total_credits": 1,
        "courses": {"AAA 1000": {"title": "Real", "credits": 3}},
        "requirements": [{"id": "r", "name": "R", "credits": 3, "options": [["ZZZ 9999"]]}],
    }
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "broken.json"
        path.write_text(json.dumps(broken), encoding="utf-8")
        try:
            load_catalog(path)
        except ValueError as error:
            assert "ZZZ 9999" in str(error)
            return
    raise AssertionError("a requirement naming an unknown course should not load")


def test_constraint_regex_fallback():
    assert advisor.parse_constraints_regex("no classes before 10am") == {"earliest": 600}
    assert advisor.parse_constraints_regex("nothing after 3pm") == {"latest": 900}
    assert advisor.parse_constraints_regex("keep fridays off")["avoid_days"] == "F"
    assert advisor.parse_constraints_regex("") == {}


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"ok  {test.__name__}")
    print(f"\n{len(tests)} passed")
