# AI Advisor

**A course scheduling assistant for Clemson Computer Science students.** Tell it
what you have passed; it returns a conflict-free schedule for next semester made
only of courses you are actually eligible to register for.

*CUHackit 2025 — Winner, Best Use of AWS*

```
$ python -m src.main --completed "CPSC 1010, CPSC 1020, MATH 1060, MATH 1080, ENGL 1030" \
                     --constraints "no classes before 10am"

Reading constraints as: {'earliest': 600}

================================================================
Recommended schedule -- 16 credits
================================================================

1. BIOL 1030   General Biology I                             TTh 2:00 PM - 3:15 PM
2. COMM 1500   Introduction to Human Communication           MWF 12:20 PM - 1:10 PM
3. CPSC 2120   Algorithms and Data Structures                MWF 4:40 PM - 5:30 PM
4. ENSP 2000   Introduction to Environmental Science         MWF 3:35 PM - 4:25 PM
5. STAT 3090   Introductory Business Statistics              TTh 3:30 PM - 4:45 PM

Not yet eligible (21 courses), for example:
   CPSC 2150   needs CPSC 2120
   CPSC 2310   needs CPSC 2120
```

## The design decision that matters

An earlier version of this project asked a language model to pick the courses.
It no longer does, and that is the point of the rewrite.

Prerequisites and time conflicts are *checkable*. "Does this student meet the
prerequisites for CPSC 3720" has exactly one right answer, and a wrong answer
costs someone an advising appointment to undo a registration. So that work
happens in Python, where it is tested and where an invalid schedule trips an
assertion instead of reaching a student.

Claude does the two jobs it is genuinely better at: turning *"no classes before
10am, keep Fridays free"* into structured constraints, and writing the sentence
that explains why the term fits your degree path.

| Step | Handled by |
|---|---|
| Read free-text time constraints | Claude → falls back to regex |
| Work out which requirements are outstanding | `scheduler.progress` |
| Filter to courses whose prerequisites you meet | `prereqs.satisfied` |
| Pick conflict-free sections near the credit target | `scheduler.build` |
| Explain why this term makes sense | Claude → omitted if unavailable |

Two consequences worth stating plainly:

- **Claude is optional.** With no API key the planner runs in full. You lose
  natural-language constraint parsing and the closing comment. Nothing else.
- **Bad data fails loudly.** The catalog is validated on load, so a requirement
  or prerequisite naming a course that does not exist raises immediately. The
  previous version silently dropped every Computer Science course from its own
  recommendations, because its data had drifted from the code reading it.

## Quick start

Requires Python 3.10 or newer.

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

python -m src.offerings      # builds this term's sections -> data/sections.json
python -m src.main           # interactive
```

For natural-language constraints and the advisor comment:

```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-..."
```

### Command line

```powershell
python -m src.main                                      # prompts for input
python -m src.main --completed "CPSC 1010, MATH 1060"   # scripted
```

| Flag | |
|---|---|
| `--completed "..."` | courses you have passed |
| `--current "..."` | courses you are taking now; they count toward prerequisites |
| `--constraints "..."` | free text, e.g. `no classes before 10am` |
| `--credits N` | credit target, default 16 |
| `--no-ai` | skip Claude, use the regex constraint parser |

Constraints that rule out a weekday bite harder than they look: *keep Fridays
free* eliminates every MWF section. When that happens the planner reports how
many credits short it landed and why, rather than quietly returning a thin
schedule.

### Web

```powershell
python -m src.web            # http://127.0.0.1:5000
```

A weekly calendar of the proposed term, degree progress for each requirement,
and the courses you are not yet eligible for with the prerequisites you are
missing.

## How it fits together

```
src/
  prereqs.py     parses "CPSC 2120 AND (MATH 1060 OR MATH 1070)" and evaluates it
  catalog.py     loads and validates the catalog, parses times, detects conflicts
  scheduler.py   requirement progress, eligibility, conflict-free selection
  offerings.py   generates a term of sections
  advisor.py     the optional Claude layer
  main.py        command line
  web.py         Flask app
data/catalog/
  cs_bs.json     76 courses and 24 requirements for the 122-credit degree
tests/
  test_engine.py 13 checks
```

About a thousand lines. Three ideas carry most of it:

**Prerequisites are boolean expressions.** `CPSC 1020 OR CPSC 1070` is a real
requirement in this catalog, so prerequisites go through a small recursive
descent parser instead of being matched against a list of codes. A malformed
expression raises rather than quietly letting a student through.

**Requirements are groups of options.** A requirement whose options are each a
single course is a pool — take any of them until the credits are met. A
requirement with multi-course options is a set of alternative sequences — take
one group and stay in it, which is why a student who started biology is never
told to also start chemistry.

**Courses are claimed, not counted.** The catalog forbids one course satisfying
several requirements, so progress assigns each completed course to exactly one,
with narrow requirements claiming before broad ones.

## Tests

```powershell
python tests/test_engine.py     # or: pytest
```

Thirteen checks over the parts that can be wrong silently: operator precedence
in prerequisites, malformed expressions raising, time parsing and overlap
detection, sequence-versus-pool requirements, no course counted twice, and
end-to-end properties of a built schedule — no conflicts, no ineligible course,
constraints respected, credits within bounds.

## Data

[`data/catalog/cs_bs.json`](data/catalog/cs_bs.json) holds the degree, derived
from the 2024–2025 catalog text in
[`data/catalog_text.txt`](data/catalog_text.txt).

> **Verify against the live catalog before relying on this for real
> registration.** Prerequisites follow the catalog's stated course sequence
> rather than being copied verbatim from each course entry, and the
> general-education option lists are representative samples, not the complete
> approved lists.

Clemson does not publish machine-readable section times, so
`python -m src.offerings` synthesises 228 sections from a fixed seed — the same
catalog always produces the same term, which keeps schedules reproducible and
testable. Replace that one module with a registrar feed and nothing downstream
changes; it is the only place that knows the times are invented.

The remaining files in `data/` are from the original hackathon build and are no
longer read by any code.

## Limitations

- Only the Computer Science BS is modelled. The loader takes a path, so a second
  program is a data file rather than a code change.
- Requirement assignment is greedy rather than a maximum matching, so a
  contrived overlap between requirements can understate progress by one course.
- Section selection is greedy with no backtracking. It can miss a fuller
  schedule when an early pick blocks a later course that had one workable
  section.

Both approximations are marked in the source with the ceiling they hit and the
upgrade path.

## Team

Built at CUHackit 2025 by Nimra Nayyar, Nadia Alexander, Angie Diaz and
Hannah Leach.
