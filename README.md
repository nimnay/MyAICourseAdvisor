# AI Advisor — Student Schedule Planner

### CUHackit 2025 Winner — Best Use of AWS

Plans a Clemson Computer Science student's next semester from their transcript:
checks prerequisites, avoids time conflicts, and aims for a 16–18 credit load.

## How it works

The scheduling decisions are made in plain Python, not by a language model,
because prerequisite and conflict correctness is checkable — so it gets checked
and tested. Claude is used for the two jobs it is actually better at:

| Step | Who does it |
|---|---|
| Read free-text constraints ("no classes before 10am") | Claude, with a regex fallback |
| Decide which requirements are outstanding | `src/scheduler.py` |
| Filter to courses whose prerequisites you meet | `src/prereqs.py` |
| Pick conflict-free sections near the credit target | `src/scheduler.py` |
| Explain why the term fits your degree path | Claude, omitted if unavailable |

Every schedule is asserted conflict-free before it is returned, and the catalog
is validated at load: a requirement or prerequisite naming a course that does
not exist fails immediately rather than silently dropping courses.

**Claude is entirely optional.** With no API key the planner runs in full.

## Setup

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Build this term's section offerings (writes data/sections.json)
python -m src.offerings
```

For the optional Claude features, set a key:

```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-..."
```

## Usage

Command line, interactive:

```powershell
python -m src.main
```

Or with flags, which is also how you script it:

```powershell
python -m src.main --completed "CPSC 1010, CPSC 1020, MATH 1060, MATH 1080, ENGL 1030" `
                  --constraints "no classes before 10am, keep Fridays free"
```

```
================================================================
Recommended schedule -- 16 credits
================================================================

1. BIOL 1040   General Biology II                            TTh 9:30 AM - 10:45 AM
2. COMM 1500   Introduction to Human Communication           MWF 12:20 PM - 1:10 PM
3. CPSC 2120   Algorithms and Data Structures                MWF 4:40 PM - 5:30 PM
4. ENSP 2000   Introduction to Environmental Science         TTh 2:00 PM - 3:15 PM
5. STAT 3090   Introductory Business Statistics              MWF 8:00 AM - 8:50 AM

Still outstanding (20 requirements):
   Core Computing                                   17 cr
   Oral Communication Requirement                    3 cr
   ...

Not yet eligible (21 courses), for example:
   CPSC 2150   needs CPSC 2120
   CPSC 2310   needs CPSC 2120
```

Web interface — weekly calendar, degree progress bars, and what you are not yet
eligible for:

```powershell
python -m src.web     # http://127.0.0.1:5000
```

Useful flags: `--current` for in-progress courses (they count toward
prerequisites), `--credits N` to change the target, `--no-ai` to skip Claude.

## Layout

```
src/
  prereqs.py     prerequisite expressions: "CPSC 2120 AND (MATH 1060 OR MATH 1070)"
  catalog.py     load catalog and sections, parse times, detect conflicts
  scheduler.py   requirement progress, eligibility, conflict-free selection
  offerings.py   generate a term of sections (python -m src.offerings)
  advisor.py     optional Claude layer
  main.py        command line
  web.py         Flask app
data/catalog/
  cs_bs.json     degree requirements and course catalog
tests/
  test_engine.py 12 checks, runs with or without pytest
```

## Tests

```powershell
python tests/test_engine.py     # or: pytest
```

## Data

[data/catalog/cs_bs.json](data/catalog/cs_bs.json) holds the degree
requirements, derived from the 2024–2025 catalog text in
[data/catalog_text.txt](data/catalog_text.txt). Prerequisites follow the
catalog's stated course sequence rather than being copied verbatim from each
course entry, and the general-education option lists are representative samples.
**Verify against the live catalog before relying on this for real registration.**

Clemson does not publish machine-readable section times, so
`python -m src.offerings` synthesises them from a fixed seed — the same catalog
always produces the same term. Swap that module for a registrar feed when one is
available; nothing downstream knows the times are invented.

The other files in `data/` (`course_structure*.json`, `class_schedule.json`) are
from the original hackathon build and are no longer read by any code.

## Known limitations

- A course counts toward every requirement that lists it. The real catalog
  forbids double-counting across requirements, so remaining credits can read low
  for a student who leaned on shared courses.
- Section selection is greedy with no backtracking, so it can miss a fuller
  schedule when an early pick blocks a later course that had one workable
  section. Both limits are marked in the source.
- Only the Computer Science BS is modelled.

## Team

Nimra Nayyar, Nadia Alexander, Angie Diaz, Hannah Leach — CUHackit 2025.
