# Quick reference

Command cheatsheet. See [../README.md](../README.md) for how it works and why.

## First run

```powershell
pip install -r requirements.txt
python -m src.offerings          # builds data/sections.json
```

## Plan a semester

```powershell
python -m src.main                                    # interactive
python -m src.main --completed "CPSC 1010, MATH 1060" # scripted
python -m src.web                                     # http://127.0.0.1:5000
```

| Flag | Effect |
|---|---|
| `--completed "..."` | comma-separated courses you have passed |
| `--current "..."` | courses you are enrolled in now; count toward prerequisites |
| `--constraints "..."` | free text, e.g. `no classes before 10am, keep Fridays free` |
| `--credits N` | credit target, default 16 |
| `--no-ai` | skip Claude, use the regex constraint parser |

## Tests

```powershell
python tests/test_engine.py      # or: pytest
```

## Optional Claude features

```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-..."
$env:AIADVISOR_MODEL = "claude-opus-5"   # optional override
```

Without a key, constraint parsing falls back to a regex and the advisor note is
omitted. Nothing else changes.

## Adding a requirement or course

Edit [../data/catalog/cs_bs.json](../data/catalog/cs_bs.json). Courses go in
`courses`; requirements are `{id, name, credits, options}` where `options` is a
list of course groups. A requirement whose groups each hold one course is a pool
(take any of them until the credits are met); a requirement with multi-course
groups is a set of alternative sequences (take one group). The catalog is
validated on load, so a typo in a course code fails immediately.
