# Maestro roles and responsibilities

Maestro has three parties. Each duty has exactly one owner, so nothing is done twice and nothing
is left undone. The executor's methodology (standard, uem or custom) changes **how** the executor
works, not this split.

## Who does what

| Stage | Owner | Output / evidence |
|---|---|---|
| Idea, goals, scope, priorities | **User** with Claude | Agreed brief |
| Feature brief: behaviour, acceptance criteria, constraints, risk level | **Claude** | `.maestro/tasks/task-NNN.md` |
| Plan: approach, files, test list, steps | **Executor** | `.maestro/plans/<feature>.md`, then a **plan checkpoint** |
| Plan check: wrong direction, missing requirements, needless complexity, review depth | **Claude** | `APPROVED` or numbered corrections, before most code exists |
| Branch `feature/<id>` (never merged by the executor) | **Executor** | Branch name in the report |
| Tests first (red → green → refactor) | **Executor** | Failing output **before** the code, passing output **after** |
| Code | **Executor** | Diff |
| Self-verification: tests, build/lint, mutation run if configured | **Executor** | Real command output in the report and in `progress.md` |
| Feature state `status: passing` (self-claim) | **Executor** | `feature_list.json` with evidence |
| Review: requirements → tests mapping, test depth, mutation, coverage | **Claude** | `.maestro/reviews/<feature>-round-N.md` |
| Held-out acceptance tests (hidden from the executor) | **Claude** | Stored outside the repository; pass/fail only |
| Code review (fresh context) and security review when the risk calls for it | **Claude** | Numbered findings |
| Verdict `review: accepted` | **Claude only** | `feature_list.json` |
| "How to try it" run before asking for the merge | **Claude** | Result in the review file |
| Merge to the main branch | **User** approves | |

## Two stop points

The executor stops and waits for Claude only twice per feature:

1. **Plan ready:** it calls `maestro_checkpoint` (kind `plan`) and waits for `APPROVED` or
   corrections.
2. **Feature passing:** it writes the report. The task ends there.

Between those two points it works without stopping. `maestro_ask` is still allowed for a real
ambiguity.

## Review depth by risk

Every project lists its high-risk areas in `.maestro/config.json` (`review.full_review_paths` and
`review.full_review_topics`), for example secrets, the server, untrusted user input, payments, and
stored data.

- **Full review** when the change touches a high-risk area: mutation run, held-out tests,
  fresh-context code review, and a security review.
- **Quick review** otherwise: the verify command, the diff, and a reading of the tests.

Claude states the chosen depth, and the reason for it, at the plan check.

## Findings and rounds

Each finding has a number and a severity:

- **blocking:** must be fixed before the merge.
- **should-fix:** recorded for the next feature.
- **note:** optional.

There are at most `review.max_rounds` rounds per feature (default 2). After the last round there
is no further round: Claude and the user decide together how to go on.

## Never

- The executor never sets `review: accepted`, never merges, and never edits `.maestro/` except its
  own plan, report and progress files.
- Claude never edits the executor's code silently. A fix Claude makes is stated as such.
- Nobody deletes or weakens a test without a reason written in `progress.md`. `maestro testdiff`
  finds such changes, and Claude checks each reason.
- No program runs from the network without a pinned version.
