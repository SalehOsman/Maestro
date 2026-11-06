# Review: slugify, round 1 of 2

- Task: task-004
- Depth: quick, because no high-risk area is touched
- Reviewer: Claude (Maestro)

## Checks run
| Check | Result |
|---|---|
| Tests re-run by the reviewer (`python -m unittest discover -s src -v`) | 5/5 OK |
| Diff scope | Only `src/slugify.py` and `src/test_slugify.py`, plus the plan and report |
| `maestro testdiff` | n/a: no pre-existing tests, and `src/` is git-ignored |
| Requirement → test mapping | Every criterion has a named test, including both error paths and the combining-marks correction |
| Independent edge cases (reviewer) | 15/15 OK: stacked harakat, Arabic-Indic digits, a leading mark, decomposed accents, 10k chars, `bytes` → TypeError, a lone mark → ValueError |
| Plan checkpoint | 3 versions. v1 had a real bug (marks dropped); v2 got a truncated answer because of a Maestro bug, since fixed; v3 applied all corrections |

## Findings
| # | Severity | Where | Finding | Required change |
|---|---|---|---|---|
| 1 | should-fix | report, TDD evidence | All five "red" outputs are the same `ModuleNotFoundError`. That proves the tests ran before the module existed, not that each test fails for its own reason. | Next feature: create a stub first, so that each red output is that test's own assertion failure. |
| 2 | note | `slugify.py` | The Persian zero-width non-joiner (U+200C) splits a word: `می‌خواهم` → `می-خواهم`. Not in the criteria. | Optional: keep U+200C between kept letters, if Persian matters. |

## Verdict
accepted
