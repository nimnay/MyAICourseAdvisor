"""Command line schedule planner.

    python -m src.main
    python -m src.main --completed "CPSC 1010, MATH 1060" --constraints "no classes before 10am"
"""

import argparse
import logging
import sys

from src import advisor, prereqs, scheduler
from src.catalog import load_catalog, load_sections

RULE = "=" * 64


def course_list(text):
    """``cpsc1010, MATH 1060`` -> ``["CPSC 1010", "MATH 1060"]``."""
    return [prereqs.normalize(code) for code in (text or "").split(",") if code.strip()]


def known_only(catalog, codes, label):
    """Drop codes the catalog does not have, loudly -- a typo must not pass silently."""
    unknown = [code for code in codes if code not in catalog.courses]
    if unknown:
        print(f"!  ignoring {label} not in the catalog: {', '.join(unknown)}")
    return [code for code in codes if code in catalog.courses]


def show(catalog, schedule, remaining, blocked, note, target):
    print(f"\n{RULE}\nRecommended schedule -- {schedule.credits(catalog)} credits\n{RULE}\n")
    if not schedule.picks:
        print("Nothing could be scheduled. Loosen your time constraints or check your"
              " completed course list.\n")
    for index, (code, section) in enumerate(sorted(schedule.picks), 1):
        print(f"{index}. {code:11} {catalog.title(code):45} {section}")

    shortfall = target - schedule.credits(catalog)
    if shortfall > 0 and schedule.skipped:
        print(f"\n{shortfall} credits short of your {target} target because:")
        for reason in dict.fromkeys(reason for _, reason in schedule.skipped):
            print(f"   - {reason}")

    outstanding = [row for row in remaining if row["remaining"]]
    print(f"\nStill outstanding ({len(outstanding)} requirements):")
    for row in outstanding[:8]:
        print(f"   {row['name']:48} {row['remaining']:>2} cr")
    if len(outstanding) > 8:
        print(f"   ... and {len(outstanding) - 8} more")

    if blocked:
        print(f"\nNot yet eligible ({len(blocked)} courses), for example:")
        for row in blocked[:4]:
            print(f"   {row['course']:11} needs {', '.join(row['missing'])}")

    if note:
        print(f"\nAdvisor note:\n   {note}")
    print()


def main(argv=None):
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Plan next semester from your transcript.")
    parser.add_argument("--completed", help="comma-separated course codes you have passed")
    parser.add_argument("--current", help="comma-separated course codes you are enrolled in")
    parser.add_argument("--constraints", help='free text, e.g. "no classes before 10am"')
    parser.add_argument("--credits", type=int, default=scheduler.TARGET_MIN_CREDITS,
                        help=f"credit target (default {scheduler.TARGET_MIN_CREDITS})")
    parser.add_argument("--no-ai", action="store_true",
                        help="skip Claude entirely, use the regex constraint parser")
    args = parser.parse_args(argv)

    try:
        catalog = load_catalog()
        sections = load_sections()
    except (OSError, ValueError) as error:
        print(f"Could not load course data: {error}")
        return 1

    if args.completed is None:
        print(f"{RULE}\nAI Advisor -- {catalog.program}\n{RULE}")
        args.completed = input("\nCourses you have completed (comma separated): ")
        args.current = input("Courses you are enrolled in now (blank if none): ")
        args.constraints = input('Time constraints (blank if none): ')

    taken = known_only(catalog, course_list(args.completed), "completed courses")
    current = known_only(catalog, course_list(args.current), "current courses")

    api = None if args.no_ai else advisor.client()
    if not args.constraints:
        constraints = {}
    elif api is None:  # no credentials, so do not make parse_constraints retry the client
        constraints = advisor.parse_constraints_regex(args.constraints)
    else:
        constraints = advisor.parse_constraints(args.constraints, api)
    if constraints:
        print(f"\nReading constraints as: {constraints}")

    try:
        schedule = scheduler.build(catalog, sections, taken, current, constraints,
                                   target=args.credits)
    except ValueError as error:
        print(f"Could not build a schedule: {error}")
        return 1

    remaining = scheduler.progress(catalog, taken)
    note = None if api is None else advisor.explain(schedule, catalog, remaining, api)
    show(catalog, schedule, remaining, scheduler.blocked(catalog, taken, current), note,
         args.credits)
    return 0 if schedule.picks else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
