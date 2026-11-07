# Methodologies and Tools in Maestro

Maestro separates the duties of planning, execution, and supervision between the user, the Antigravity agent, and Claude Code. The executor methodology defines **how the executor works** during implementation—its internal phases, conventions, disciplines, and optional external tooling.

Choosing a methodology never changes the core role split defined in [Roles and responsibilities](../../methodologies/ROLES.md):
- **User (Decider):** Owns goals, scope, priorities, and approves every branch merge.
- **Antigravity (Executor):** Owns planning, test-first construction, self-verification with concrete evidence, and the completion report.
- **Claude Code (Reviewer):** Owns feature briefs, plan checkpoint approvals, independent verification (re-running tests, inspecting diffs, running mutation testing and held-out tests), and review verdicts.

The reviewer never takes the executor's report or claims as proof. Regardless of which methodology is selected, the reviewer re-runs tests, checks test diffs, and evaluates code independently.

---

## Methodology Comparison

| Methodology | Best For | What the Executor Does | External Tools | State Files Created | Setup Effort |
|---|---|---|---|---|---|
| `standard` (recommended) | Any project; default zero-dependency workflow | Plan checkpoint -> branch -> TDD (red/green/refactor) -> self-verify -> report | None (uses native test runners & linters) | `feature_list.json`, `progress.md`, `session-handoff.md` | Immediate (0 commands) |
| `uem` | Teams using the Unified Engineering Methodology | 4 phases: Foundation, Plan, Construction, Verification/Handoff with AgentShield | Superpowers, EGM, Harness Engineering, AgentShield, ECC (optional) | `feature_list.json`, `progress.md`, `session-handoff.md` | One-time tool install with user approval per tool |
| `custom` | Projects with their own established agent methodology or rules | Follows project's own `AGENTS.md` / `GEMINI.md` within Maestro's 8-point minimum contract | None required by Maestro | None created automatically | Zero extra setup |

---

## 1. The `standard` Methodology

The `standard` methodology is Maestro's built-in default. It requires no third-party agent plugins or external skills, relying entirely on the native tools already present in your project stack (such as `pytest`, `npm test`, `vitest`, `cargo test`, or `go test`).

### Executor Phases

The executor follows the lifecycle documented in `methodologies/standard/EXECUTOR_RULES.md`:

1. **Before Starting:**
   - Reads the task brief (`.maestro/tasks/task-NNN.md`), `.maestro/config.json`, and existing state files (`feature_list.json`, `progress.md`, `session-handoff.md`).
   - Limits work strictly to one feature at a time.
2. **Phase 1 — Plan (Stop Point 1):**
   - Writes an implementation plan to `.maestro/plans/<feature-id>.md` specifying the approach, a rejected alternative with rationale, files to modify, named test cases (covering requirements and error paths), and ordered steps.
   - Calls `maestro_checkpoint(kind="plan")` via MCP and blocks until Claude responds with `APPROVED` or applies numbered corrections.
3. **Phase 2 — Branch:**
   - Works on a dedicated branch (`feature/<feature-id>`). Never merges, rebases, or pushes.
4. **Phase 3 — Test-Driven Development (TDD):**
   - For every behaviour:
     - **Red:** Writes the test, executes it, and captures the failing output.
     - **Green:** Writes the minimal code necessary to make the test pass, and captures the passing output.
     - **Refactor:** Cleans up implementation while keeping tests green.
   - Preserves existing tests: never deletes, skips, or weakens existing tests without documenting the justification in `progress.md`.
5. **Phase 4 — Verify Before Completion:**
   - Runs full test suites and project verification commands (`verify_cmd`).
   - If configured in `.maestro/config.json`, executes mutation testing (`mutation_cmd`) on modified files and records surviving mutants.
   - Updates `feature_list.json` with `status: "passing"` and concrete execution evidence. The executor **never** sets `review`.
   - Records decisions and progress in `progress.md` and provides a "How to try it" walkthrough in `session-handoff.md`.
6. **Phase 5 — Report (Stop Point 2):**
   - Writes `.maestro/reports/task-NNN.done.md` following `.maestro/report-template.md` as the very last step.

### What the Reviewer Checks

Claude Code reviews the implementation independently:
- Re-runs the project's test suite and `verify_cmd`.
- Examines `git diff` to ensure changes stay strictly within the assigned feature boundary.
- Runs `maestro testdiff` to detect removed assertions, deleted test files, or newly introduced skip markers.
- Evaluates requirement-to-test mapping and error handling coverage.
- Inspects TDD evidence (red failure captured before green pass).
- For high-risk areas (full review), runs mutation testing, executes hidden held-out tests (`maestro heldout run`), conducts fresh-context code review, and performs security checks.

---

## 2. The `uem` Methodology (Unified Engineering Methodology)

The `uem` methodology integrates four established agent capabilities: Superpowers (process and TDD), Elephant-Goldfish Model / EGM (adversarial audit and review), Harness Engineering (state files and continuity), and AgentShield (security gate).

### Harness Invariants

UEM enforces three core operational invariants:
1. **Repository as the System of Record:** Project state lives in committed files at the repository root (`feature_list.json`, `progress.md`, and `session-handoff.md`), not in transient chat memory.
2. **One Active Feature at a Time:** Only one unfinished feature row in `feature_list.json` is actively worked on.
3. **Pass-State Gating:** A feature cannot be marked `passing` without executing its exact verification command and attaching the real terminal output.

### The 4 UEM Phases

1. **Phase 1 — Foundation:**
   - Brainstorming technical approaches and trade-offs using Superpowers.
   - Adversarial scrutiny using EGM personas (evaluating scalability, failure points, and YAGNI simplification).
   - Seeding the feature row in `feature_list.json` with `status: "not-started"`.
2. **Phase 2 — Plan (Stop Point 1):**
   - Writing structured, atomic implementation plans to `.maestro/plans/<feature-id>.md`.
   - EGM implementation-readiness audit to confirm no design decisions are left ambiguous.
   - Calling `maestro_checkpoint(kind="plan")` and pausing for Claude's `APPROVED` verdict.
   - Transitioning feature state to `active` in `feature_list.json`.
3. **Phase 3 — Construction:**
   - Workspace isolation using Git worktrees or a `feature/<id>` branch.
   - Strict TDD (Red -> Green -> Refactor), capturing real test output at each stage.
   - Continuous verification using `verify_cmd` after each logical unit.
4. **Phase 4 — Verification and Handoff (Stop Point 2):**
   - Full verification suite, linter execution, and mutation testing if configured.
   - Self-conducted code review before requesting external review.
   - Automated security audit using the **pinned, locally installed** AgentShield scanner:
     ```bash
     npx --no-install ecc-agentshield scan --path .
     ```
   - Transitioning feature state to `status: "passing"` with real command output.
   - Updating `progress.md` and `session-handoff.md` with verification tables and "How to try it" instructions.
   - Writing the completion report `.maestro/reports/task-NNN.done.md` as the final action.

### Role Alignment with Maestro

UEM rules adapt to Maestro's multi-agent supervision contract:
- **Verdict boundary:** In standard UEM, agents may manage their own lifecycle. Under Maestro, **only Claude Code sets `review: accepted`**. The executor sets only `status: "passing"`.
- **Security pinning:** AgentShield runs exclusively via the pinned, locally installed version (`npx --no-install ecc-agentshield`). Network execution via `npx --yes` is strictly forbidden.

---

## 3. The `custom` Methodology

The `custom` methodology is designed for teams or repositories that maintain their own agent instructions, coding standards, prompt frameworks, or existing `AGENTS.md` / `GEMINI.md` files.

Instead of imposing external toolsets or prescribing specific internal phases, Maestro enforces only the **8-point minimum contract** necessary for Claude Code to supervise and verify safely:

### The 8-Point Minimum Contract

1. **Scope:** Work only on the task specified in the task brief (`task-NNN.md`). If specific files are listed, modify only those files. If more are needed, ask via `maestro_ask` or report `Status: blocked`.
2. **Plan Checkpoint:** Before writing code, submit a concise plan via `maestro_checkpoint(kind="plan")` and wait for `APPROVED`. On "No answer yet", poll with `maestro_check_answer`.
3. **Git Safety:** Never merge, rebase, or push. Never switch branches unless instructed by the task brief.
4. **Evidence:** Run every acceptance command and record actual terminal output in the report. Never claim a test passed without running it.
5. **Test Protection:** Never delete, skip, or weaken an existing test without documenting the explicit technical reason in the report.
6. **State Verdict Boundary:** Never set `review: accepted` or any equivalent verdict. That decision belongs solely to the reviewer.
7. **Report:** Write `.maestro/reports/task-NNN.done.md` following `.maestro/report-template.md` as the very last step (also when blocked or partial).
8. **Safety:** Never touch secrets, credentials, or API keys. Never run programs from the network without a pinned version.

### Enforcement by the Reviewer

Even under `custom`, Claude Code performs its full independent review:
- Re-running test commands.
- Inspecting git diffs.
- Checking test modifications with `maestro testdiff`.
- Executing held-out acceptance tests and security reviews for high-risk topics.

---

## Tools for `uem`

When using the `uem` methodology, Maestro references five external tools. The metadata below is copied directly from `methodologies/uem/requirements.json`:

| Tool ID | Name & Description | Official Source | Version | License | Scope | Optional |
|---|---|---|---|---|---|---|
| `superpowers` | Superpowers (skills: brainstorming, writing-plans, test-driven-development, verification-before-completion, requesting-code-review, using-git-worktrees) | [https://github.com/obra/superpowers](https://github.com/obra/superpowers) | `v7.0.2` | MIT | user (Antigravity plugin, `~/.gemini/config/plugins/superpowers`) | No |
| `egm` | Elephant-Goldfish Model (skills: egm-brainstorm, egm-review, egm-draft; fresh-context adversarial review) | [https://github.com/google/elephant-goldfish-model](https://github.com/google/elephant-goldfish-model) | `v0.1.0` | Apache-2.0 | user (Antigravity plugin, `~/.gemini/config/plugins/egm`) | No |
| `harness-creator` | Harness Engineering: harness-creator skill (AGENTS.md, feature_list.json, init.sh, progress and handoff files) | [https://github.com/walkinglabs/learn-harness-engineering](https://github.com/walkinglabs/learn-harness-engineering) | `commit a9342ff471f2c0e60be0c08b9f4a7c502df4e442` | MIT | project (`<project>/.agents/skills/harness-creator`) | No |
| `ecc` | Everything Claude Code, minimal profile for Antigravity (rules, workflows, skills, agents in .agents/) | [https://github.com/affaan-m/ecc](https://github.com/affaan-m/ecc) (npm package `ecc-universal`) | `2.2.3` | MIT | project (`<project>/.agents/`) | Yes |
| `agentshield` | AgentShield security scanner (secrets, tool and shell permissions, MCP configuration) | [https://github.com/affaan-m/agentshield](https://github.com/affaan-m/agentshield) (npm package `ecc-agentshield`) | `1.6.0` | MIT | project (pinned devDependency; needs a `package.json`) | No |

---

## How Tool Installation Works

Maestro never downloads or installs software silently. All tool installations follow a strict, auditable verification pipeline:

1. **Audit Environment:**
   Running `maestro tools <project>` inspects the project environment against the methodology's `requirements.json`. For each tool, it displays:
   - Status: `[OK]`, `[MISSING]`, or `[OPTIONAL]`
   - Tool name and purpose
   - Verified official source URL
   - Exact pinned version or git commit
   - Software license and installation scope (user plugin vs. project local)
2. **Explicit User Approval:**
   You review the list and approve each tool individually. Neither Claude Code nor Antigravity can install tools without your approval.
3. **Generating the Install Brief:**
   Running `maestro tools <project> --approve <id...>` creates a dedicated setup brief (`.maestro/tasks/task-NNN.md`). This brief contains only the exact pinned commands defined in `requirements.json` (such as checking out specific git commit hashes or installing exact npm versions).
4. **Isolated Execution:**
   The brief is dispatched to Antigravity (`maestro send`), which executes only the exact approved commands and records terminal output in a report.
5. **Re-Verification:**
   Claude re-runs `maestro tools <project>` to verify that all approved tools now report `[OK]`.
6. **Zero Unpinned Installs:**
   Commands like `npx --yes <pkg>` or dynamic `git clone` without tags/commits are prohibited.

---

## How to Choose

- **Choose `standard`** if:
  - You want to start immediately with zero external dependencies.
  - Your project already has adequate test suites (`pytest`, `jest`, `vitest`, `go test`, `cargo test`, etc.).
  - You prefer a lightweight setup that relies purely on built-in TDD and plan checkpoints.
- **Choose `uem`** if:
  - You want formal multi-phase engineering with structured brainstorming, adversarial architectural critiques, and automated security scans.
  - You are working on high-complexity features that benefit from EGM audit personas and the full Harness Engineering lifecycle.
  - You are willing to approve the required user plugins and project dependencies.
- **Choose `custom`** if:
  - Your repository already defines custom prompt guidelines, agent rules, or proprietary internal workflows in `AGENTS.md` or `GEMINI.md`.
  - You want Maestro's supervisory oversight, plan checkpoints, and independent reviews without changing your existing developer conventions.

---

## Switching Later

You can change methodologies at any time without losing project progress:

```bash
maestro init <project> --methodology <new-methodology>
```

Re-running `maestro init` is completely safe:
- It updates `.maestro/config.json` with the new methodology.
- It refreshes `.maestro/EXECUTOR_RULES.md` and `.maestro/ROLES.md` to match the new selection.
- It **preserves all existing state files** (`feature_list.json`, `progress.md`, and `session-handoff.md`), existing task briefs, reports, and review records.
