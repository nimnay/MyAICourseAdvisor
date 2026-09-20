"""Flask front end: weekly calendar and degree progress for a planned term.

    python -m src.web
"""

from pathlib import Path

from flask import Flask, render_template, request

from src import advisor, prereqs, scheduler
from src.catalog import load_catalog, load_sections

BASE = Path(__file__).resolve().parent.parent
app = Flask(
    __name__,
    template_folder=str(BASE / "frontend" / "templates"),
    static_folder=str(BASE / "frontend" / "static"),
)

# Read-only data, so load once per process rather than per request.
CATALOG = load_catalog()
SECTIONS = load_sections()

DAY_START = 8 * 60  # calendar spans 8am to 6pm in quarter-hour rows
DAY_END = 18 * 60
STEP = 15
HOURS = [
    (f"{(hour - 1) % 12 + 1} {'AM' if hour < 12 else 'PM'}", (hour * 60 - DAY_START) // STEP + 1)
    for hour in range(8, 18)
]


def codes(text):
    return [prereqs.normalize(code) for code in (text or "").split(",") if code.strip()]


def calendar_blocks(schedule):
    """Schedule as positioned grid cells: one per meeting day of each section."""
    blocks = []
    for code, section in schedule.picks:
        start = max(section.start, DAY_START)
        end = min(section.end, DAY_END)
        for day in section.day_set:
            blocks.append({
                "day": day,
                "row": (start - DAY_START) // STEP + 1,
                "span": max(1, (end - start) // STEP),
                "code": code,
                "title": CATALOG.title(code),
                "time": section.time_slot,
            })
    return blocks


@app.route("/", methods=["GET", "POST"])
def home():
    if request.method != "POST":
        return render_template("index.html", program=CATALOG.program)

    requested = codes(request.form.get("completed"))
    current = codes(request.form.get("current"))
    unknown = [c for c in requested + current if c not in CATALOG.courses]
    taken = [c for c in requested if c in CATALOG.courses]
    current = [c for c in current if c in CATALOG.courses]

    constraint_text = (request.form.get("constraints") or "").strip()
    api = advisor.client() if request.form.get("use_ai") else None
    if not constraint_text:
        constraints = {}
    elif api is None:
        constraints = advisor.parse_constraints_regex(constraint_text)
    else:
        constraints = advisor.parse_constraints(constraint_text, api)

    schedule = scheduler.build(CATALOG, SECTIONS, taken, current, constraints)
    remaining = scheduler.progress(CATALOG, taken)

    return render_template(
        "index.html",
        program=CATALOG.program,
        submitted=True,
        completed_text=request.form.get("completed", ""),
        current_text=request.form.get("current", ""),
        constraints_text=constraint_text,
        use_ai=bool(request.form.get("use_ai")),
        unknown=unknown,
        constraints=constraints,
        picks=sorted(schedule.picks),
        catalog=CATALOG,
        credits=schedule.credits(CATALOG),
        target=scheduler.TARGET_MIN_CREDITS,
        reasons=list(dict.fromkeys(reason for _, reason in schedule.skipped)),
        blocks=calendar_blocks(schedule),
        hours=HOURS,
        total_rows=(DAY_END - DAY_START) // STEP,
        days=list(zip(scheduler.DAY_ORDER, ("Mon", "Tue", "Wed", "Thu", "Fri"))),
        progress_rows=remaining,
        earned=sum(row["earned"] for row in remaining),
        blocked=scheduler.blocked(CATALOG, taken, current),
        note=advisor.explain(schedule, CATALOG, remaining, api) if api else None,
    )


if __name__ == "__main__":
    app.run(debug=True)
