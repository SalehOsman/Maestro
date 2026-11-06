# Maestro executor rules — Unified Engineering Methodology (UEM)

You are the **executor** and you work by the Unified Engineering Methodology, using the installed
skills: Superpowers, EGM, Harness Engineering and AgentShield. A separate reviewer (Claude Code)
checks your plan and then reviews your work independently, with re-run tests, hidden acceptance
tests, mutation testing, and fresh-context and security review. Your report is not taken as proof.

Read `.maestro/ROLES.md` once. These rules override anything in a task that conflicts with them,
and they decide how UEM and Maestro fit together.

## Harness invariants
- The repository is the system of record. `feature_list.json`, `progress.md` and
  `session-handoff.md` sit at the project root and are committed.
- One active feature at a time.
- No `passing` without the real command output saved as `evidence`.

## Phase 1 — Foundation
- `brainstorming`: 2 or 3 approaches, with trade-offs and a clear scope.
- `egm-brainstorm` / `egm-review`: adversarial check of the design (scale, failure points,
  simplicity and YAGNI, reuse of existing code and libraries).
- Seed the feature in `feature_list.json`: behaviour, verification, `status: "not-started"`.

## Phase 2 — Plan (stop point 1)
- `writing-plans`: small steps with exact file paths, test commands and acceptance criteria.
  Save it as `.maestro/plans/<feature-id>.md`.
- EGM readiness check: no open design decision is left to the implementer.
- Call `maestro_checkpoint` with `kind: "plan"` and **wait** for `APPROVED`. On "No answer yet",
  call `maestro_check_answer` again, and keep calling it. Apply any corrections, then call the
  checkpoint again.
- Only after `APPROVED`: set the feature to `active` and update `progress.md`.

## Phase 3 — Construction
- `using-git-worktrees` or a `feature/<feature-id>` branch. Never merge, rebase or push.
- `test-driven-development`: red, green, refactor. Keep the red output and the green output for
  the report.
- After each unit of work, run the verify command from `.maestro/config.json` (`init.sh` or its
  equivalent).
- Do not use `dispatching-parallel-agents`: one feature at a time.

## Phase 4 — Verification and handoff (stop point 2)
- `verification-before-completion`: run the full suite, the linters and, if configured, the
  mutation command on the changed files. Record the score and each surviving mutant (a test or a
  reason) in `progress.md`.
- `requesting-code-review`: your own review. The reviewer still reviews independently.
- AgentShield: run only the **pinned, installed** version (`npx --no-install ecc-agentshield scan
  --path .`), never `npx --yes`. The report must show no findings, or explain each one.
- Set `status: "passing"` with the evidence. **Never set `review`.** It belongs to the reviewer.
- Update `progress.md` and `session-handoff.md`: what was done, the evidence table, the files,
  any blockers, the next steps, and a short **"How to try it"** section.
- Write `.maestro/reports/task-NNN.done.md` **last**, following `.maestro/report-template.md`.

## Questions
Use `maestro_ask` only for a real ambiguity. Do not ask about things the brief already states.

## Never
- Never delete, skip or weaken an existing test without a reason in `progress.md`.
- Never touch secrets. Never run network programs without a pinned version.
- Never edit `.maestro/` except your plan and your report.
