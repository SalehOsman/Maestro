# Example: slugify (Real Maestro Feature Cycle)

This example provides an authentic, sanitized record of a complete Maestro feature development cycle (Task 004, `slugify`). It demonstrates how the plan checkpoint caught a real Unicode diacritics bug before any code was written, why the human-in-the-loop review architecture exists, how Maestro itself evolved when a Windows command-line truncation bug was uncovered and fixed in production, and how test-first implementation and independent audit closed the loop.

All artifacts under `.maestro/` are real artifacts from that run. They are kept byte-for-byte identical to the original exchange, sanitized only to replace local project paths with `<project>` and development directories with `src/`.

## Timeline of the Run

| Step | Stage | What Happened |
|---|---|---|
| **1** | **Plan v1 (Checkpoint q1)** | The executor submitted plan v1 using `re.sub(r'[\W_]+', '-', ...)`. The reviewer demonstrated that Python's `\w` regex character class does not match Unicode combining marks (`Mn` and `Mc`), causing Arabic tanween and tashkeel to be treated as separators and dropped (`'مرحباً بك'` became `'مرحبا-بك'`). The reviewer prepared corrections requiring Unicode combining mark preservation. |
| **2** | **Maestro Bug & Fix** | The q1 answer reached the executor truncated to its first line because Windows `cmd.exe` cut the multi-line command argument at the first newline. Because of this truncation, plan v2 did not apply the corrections. The reviewer inspected the stored answer in `.maestro/questions/task-004-q1.answer.md`, identified the `cmd.exe` newline truncation bug, and fixed Maestro directly by introducing `maestro answer --file` (shipped in v0.5.0). Note that `task-004-q1.answer.md` is preserved here in its original truncated state as real evidence of this bug. |
| **3** | **Plan v3 (Checkpoints q2 & q3)** | Question q2 delivered the complete corrections via the new file-based mechanism. Plan v3 adopted all corrections, using `unicodedata.category` to preserve combining marks (`Mn`/`Mc`) after kept characters and treating underscores as separators. The plan was formally approved in q3. No code existed before this checkpoint approval. |
| **4** | **Implementation & Review** | Implementation proceeded strictly test-first in `src/`. The executor delivered all 5 unit tests and implementation code, along with TDD evidence. The reviewer re-ran the tests, performed 15 independent edge-case checks (stacked harakat, Arabic-Indic digits, leading marks, decomposed accents, 10k character inputs, invalid types, and empty slugs), and accepted the feature with one should-fix finding (providing stub functions so red test failures show assertion errors rather than `ModuleNotFoundError`). |

## How to Read the Files

Follow the lifecycle order:

1. **Task Brief (`.maestro/tasks/task-004.md`)**:
   The task definition establishing the required behavior, multilingual requirements, acceptance criteria, and constraints.
2. **Checkpoint Exchanges (`.maestro/questions/`)**:
   - `task-004-q1.json` & `task-004-q1.answer.md`: The initial plan submission and the truncated response resulting from the `cmd.exe` newline bug.
   - `task-004-q2.json` & `task-004-q2.answer.md`: Resubmission and the complete reviewer corrections delivered via `maestro answer --file`.
   - `task-004-q3.json` & `task-004-q3.answer.md`: Final plan v3 submission and the reviewer's approval.
3. **Plan (`.maestro/plans/slugify.md`)**:
   The approved plan detailing the input validation, Unicode normalization and combining mark retention logic, rejected alternatives, named unit tests, and TDD steps.
4. **Source Code & Unit Tests (`src/`)**:
   - `src/test_slugify.py`: Unit tests validating formatting, multilingual preservation (`'مرحبا بالعالم 2'`), Unicode combining marks (`'مرحباً بك'`), and exception paths.
   - `src/slugify.py`: The production function implementing Unicode-aware slugification with combining mark preservation.
5. **Completion Report (`.maestro/reports/task-004.done.md`)**:
   The executor's report containing TDD red/green test execution logs and verification evidence.
6. **Review Verdict (`.maestro/reviews/slugify-round-1.md`)**:
   The reviewer's independent audit, verification results across 15 edge cases, findings, and accepted verdict.
7. **Configuration (`.maestro/config.json`)**:
   An example project configuration utilizing `methodology: custom`.

## Running the Tests

To run the unit test suite from the repository root:

```bash
python -m unittest discover -s examples/slugify/src
```

Or from within the `examples/slugify` directory:

```bash
python -m unittest discover -s src
```
