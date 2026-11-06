# Task 004: Slugify helper (checkpoint test)

- Feature id: `slugify`
- Project root: `<project>`
- Methodology: `custom` (rules: `.maestro/EXECUTOR_RULES.md`)
- Kind: feature

## Behaviour
A function `slugify(text)` turns a title into a URL slug.

## Acceptance criteria
- [ ] Lowercase; runs of spaces and punctuation become a single `-`; no leading or trailing `-`.
      Example: `"  Hello, World!  "` → `"hello-world"`.
- [ ] Letters and digits from any script are kept (Arabic included): `"مرحبا بالعالم 2"` → `"مرحبا-بالعالم-2"`.
- [ ] Error path: `slugify("")` and `slugify("!!!")` raise `ValueError` (nothing left to slug).
- [ ] Error path: a non-string argument raises `TypeError`.
- [ ] Tests pass: `python -m unittest discover -s src` (run from `<project>`).

## Constraints
- In scope: create `src/slugify.py` and `src/test_slugify.py` only.
- Python 3.10 standard library only.
- Do NOT run git commands (this workspace is the tool's own repository).

## Plan first
Before any code, write your plan to `.maestro/plans/slugify.md`: the approach, one alternative you
rejected with the reason, the files, a named test for each criterion, and the steps. Then call
`maestro_checkpoint` (project `<project>`, task_id `004`, kind `plan`, plan_path
`.maestro/plans/slugify.md`) and wait for the verdict before writing code.

## Review depth
quick, because no high-risk area is touched.

## When done
Write `.maestro/reports/task-004.done.md` (template `.maestro/report-template.md`) LAST.
