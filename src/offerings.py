"""Build a term of section offerings for every course in the catalog.

Clemson does not publish machine-readable section times, so these are
synthesised. The seed makes a given catalog always produce the same term, so a
schedule is reproducible and testable. Swap this module for a registrar feed
when one is available; nothing downstream knows the times are invented.
"""

import json
import sys

from src.catalog import DATA, DEFAULT_SECTIONS, load_catalog

MWF_SLOTS = [
    "8:00 AM - 8:50 AM",
    "9:05 AM - 9:55 AM",
    "10:10 AM - 11:00 AM",
    "11:15 AM - 12:05 PM",
    "12:20 PM - 1:10 PM",
    "1:25 PM - 2:15 PM",
    "2:30 PM - 3:20 PM",
    "3:35 PM - 4:25 PM",
    "4:40 PM - 5:30 PM",
]

TTH_SLOTS = [
    "8:00 AM - 9:15 AM",
    "9:30 AM - 10:45 AM",
    "11:00 AM - 12:15 PM",
    "12:30 PM - 1:45 PM",
    "2:00 PM - 3:15 PM",
    "3:30 PM - 4:45 PM",
]


def generate(catalog, per_course=3, seed=2025):
    """One entry per (course, section). Every catalog course gets offerings."""
    import random

    rng = random.Random(seed)
    offerings = []
    for code in catalog.courses:
        # Spread sections across days and times so a conflict-free pick usually exists.
        for section_id in range(1, per_course + 1):
            days = "MWF" if (section_id + rng.randrange(2)) % 2 else "TTh"
            slots = MWF_SLOTS if days == "MWF" else TTH_SLOTS
            offerings.append(
                {
                    "course": code,
                    "section_id": section_id,
                    "days": days,
                    "time_slot": rng.choice(slots),
                }
            )
    return offerings


def main():
    catalog = load_catalog()
    offerings = generate(catalog)
    DATA.mkdir(parents=True, exist_ok=True)
    DEFAULT_SECTIONS.write_text(json.dumps(offerings, indent=2) + "\n", encoding="utf-8")
    print(f"{len(offerings)} sections for {len(catalog.courses)} courses -> {DEFAULT_SECTIONS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
