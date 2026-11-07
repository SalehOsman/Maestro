# Maestro Architecture and Design

This document details Maestro's internal mechanics, system boundaries, integration protocols, and architectural decisions. It is written for contributors and maintainers.

---

## 1. Roles and Core Principles

Maestro pairs two different AI systems with strict, non-overlapping responsibilities:

| Party | Role | Responsibilities |
|---|---|---|
| **User** | Decider | Defines business goals, sets priorities, clarifies ambiguities, and approves every final branch merge. |
| **Claude Code** | Reviewer & Supervisor | Leads brainstorming, writes feature briefs, verifies executor plans at checkpoints, runs independent verification (test suites, diff inspection, test weakening checks, mutation testing, held-out acceptance tests), and decides the review verdict. |
| **Antigravity** | Executor | Writes implementation plans, develops features test-first (TDD: Red -> Green -> Refactor), executes self-verification, and writes structured completion reports. |

### The Two Stop Points

To maintain momentum while safeguarding project integrity, the executor stops for reviewer interaction at exactly two points during any feature:

1. **The Plan Checkpoint:** The executor writes its plan to `.maestro/plans/<feature>.md` and calls the MCP tool `maestro_checkpoint`. It blocks until Claude returns an `APPROVED` verdict (with review depth) or numbered corrections.
2. **The Completion Report:** The executor verifies its code, logs concrete evidence, and writes `.maestro/reports/task-NNN.done.md` as its final step.

Between these two points, the executor operates autonomously without interruption, except when a genuine ambiguity requires asking a question via `maestro_ask`.

Review findings use three severities (`blocking`, `should-fix`, `note`) with a strict maximum of **two review rounds** per feature. If blocking issues remain after two rounds, the supervisor escalates to the user.

---

## 2. System Lifecycle Loop

The end-to-end execution loop proceeds through these phases:

```
 User ──brainstorm──▶ Claude Code (Supervisor) ──task-NNN.md──▶ Antigravity (Executor)
                           ▲       │                                  │
                           │       └─ waits idle (no tokens)          │ implements (TDD)
                           │                                          │ (plan checkpoint, MCP)
                           └───── verifies: tests, diff ◀── task-NNN.done.md (report)
                                   │
                                   └─ changes needed? ──▶ fix brief ──▶ Antigravity ...
```

1. **Specification:** The user and Claude formulate measurable acceptance criteria. Claude creates `.maestro/tasks/task-NNN.md`.
2. **Delivery:** `maestro send` constructs a deep link and transfers the prompt to Antigravity.
3. **Planning & Checkpoint:** Antigravity explores the repository, writes the plan, and calls `maestro_checkpoint`. Claude reviews the plan and approves it.
4. **Implementation:** Antigravity writes failing tests first, implements code to pass them, and records verification evidence.
5. **Idle Waiting:** Claude monitors the workspace using a background polling command with zero token overhead.
6. **Supervised Review:** The completion report wakes Claude. Claude independently executes the tests, reviews git diffs, inspects for weakened tests (`maestro testdiff`), and evaluates code quality.
7. **Resolution:** If all quality gates pass, Claude sets the review verdict to accepted; the user is prompted to approve the merge.

---

## 3. Task Delivery Mechanism

Tasks are delivered to the Antigravity agent app using a URI protocol and foreground automation:

### 1. Protocol URI
Maestro formats prompts into a registered protocol URL:

```
antigravity://open?prompt=<url-encoded-prompt>&project=<project-id>
```

When Antigravity opens this URL, it loads the prompt into the active chat input field of the target workspace.

### 2. Workspace Project ID Lookup
Antigravity stores workspace registrations in a protobuf database located at `~/.gemini/antigravity/agyhub_summaries_proto.pb`.

The module `scripts/agy_project.py` reads this binary file in read-only mode, parsing project metadata to match the canonical workspace directory path with its corresponding internal project ID. If no match is found (for instance, on a brand-new project), the URL omits the project parameter, targeting the currently active project window.

### 3. Window Activation and Foreground Lock Handling
Under modern desktop operating systems, background processes are restricted from forcibly stealing focus:

- **Windows (`scripts/sender.py`):** Uses the Win32 API `AttachThreadInput` via `ctypes`. It attaches the current thread's input processing mechanism to the thread owning the current foreground window, raises the Antigravity window (`SW_RESTORE` and `SW_SHOW`), brings it to the top, sets focus, and detaches. Once Antigravity is confirmed as the foreground window, it synthesizes virtual `Return` keystrokes (`VK_RETURN`).
- **macOS:** Invokes AppleScript via `osascript` to activate process `"Antigravity"` through System Events and send key code 36 (Return). Requires Accessibility permission.
- **Linux (X11):** Uses `xdotool` to search for windows with class `antigravity`, activate the window with `--sync`, verify the window class, and send key `Return`.
- **Linux (Wayland):** Wayland security protocols prohibit programmatic keystroke synthesis across applications. Maestro opens the URL to draft the prompt, and the user presses Enter manually.

### 4. Desktop Notification Fallback (Exit Code 2)
If the window cannot be brought to the foreground or keystrokes cannot be delivered automatically, `maestro send` exits with code 2. It posts a non-blocking desktop notification (Windows balloon tip / toast, macOS notification, or Linux `notify-send`) instructing the user to press Enter manually in Antigravity. The reviewer continues waiting seamlessly.

---

## 4. Token-Free Waiting

Waiting for an LLM executor to complete complex tasks can take anywhere from tens of seconds to nearly an hour. Polling an agent via LLM turns would consume excessive tokens and context space.

Maestro implements token-free waiting through `maestro wait <project> [task] [--timeout 45]`:
- Runs as a lightweight local Python subprocess in Claude Code's background execution environment.
- Polls the filesystem every 5 seconds for the arrival of `.maestro/reports/task-NNN.done.md` or new records in `.maestro/questions/`.
- If an unanswered question or plan checkpoint appears, `maestro wait` exits immediately with exit code 3, outputting the question ID and content to wake Claude.
- If the report appears, `maestro wait` exits with code 0, returning execution control to Claude.
- If the operation exceeds the timeout (default: 45 minutes), it exits with code 1.
- During the entire waiting period, zero LLM tokens are consumed.

---

## 5. The MCP Server and Mid-Task Communication

Mid-task communication is powered by `scripts/maestro_mcp.py`, an MCP server communicating over standard input/output (newline-delimited JSON-RPC 2.0).

### Available Tools

1. **`maestro_checkpoint(project, task_id, summary, plan_path?, kind='plan', wait_seconds?)`**  
   Submits an implementation plan for reviewer approval. Blocks the executor until Claude reviews the plan and records an answer, or until the wait timeout expires.
2. **`maestro_ask(project, task_id, question, options?, wait_seconds?)`**  
   Submits an urgent technical question when requirements are ambiguous. Writes to `.maestro/questions/<qid>.json` and blocks for up to 5 minutes (default) for Claude's response.
3. **`maestro_check_answer(project, question_id, wait_seconds?)`**  
   Allows the executor to resume waiting if a previous call to `maestro_ask` or `maestro_checkpoint` timed out before an answer was posted.
4. **`maestro_progress(project, task_id, message)`**  
   Appends a timestamped status note to `.maestro/progress/task-NNN.log`. Does not wake the reviewer.

### Active-Task Guard

Because the Maestro MCP server is registered globally in Antigravity's configuration, its tools are visible to the agent across all conversations, including sessions outside Maestro.

To prevent accidental blocking or unintended behavior during non-Maestro usage, every MCP tool call is guarded by `_require_active()`:
- Verifies that `<project>/.maestro/active.json` exists.
- Confirms the active task number matches the `task_id` argument.
- Verifies that `sent_at` timestamp is less than 12 hours old.
- Verifies that the task report `.maestro/reports/task-NNN.done.md` does not already exist.

If any check fails, the MCP tool throws an `Inactive` exception immediately, instructing the agent that no Maestro task is active and to proceed with normal operation without blocking.

---

## 6. Methodologies and Pinned Tool Management

When a project is initialized, the user selects one of three executor methodologies (for complete lifecycle details, comparison, and tool sources, see [Methodologies and tools](methodologies.md)):

1. **`standard` (recommended):** Maestro's zero-dependency workflow. Relies purely on the project's native test runner, compiler, and linter.
2. **`uem`:** Unified Engineering Methodology. Integrates Superpowers, EGM, Harness Engineering, AgentShield, and ECC.
3. **`custom`:** Minimal contract for existing enterprise or bespoke agent workflows.

### Tool Security and Pinning

For methodologies that use external utilities (such as `uem`), all tools are defined in `methodologies/<name>/requirements.json` with immutable sources and pinned versions.

- Maestro never allows the executor or reviewer to dynamically install unpinned software from the internet.
- `maestro tools <project>` audits the environment and reports installed and missing tools.
- External tools are installed only after the user explicitly reviews and approves each tool individually. `maestro tools <project> --approve <id...>` creates an install brief containing only the exact pinned commands.

---

## 7. Review Support and Verification Engine

Maestro gives the reviewer an arsenal of independent verification tools:

### Held-Out Acceptance Tests (`maestro heldout`)
To ensure that an executor writes generalizable code rather than overfitting to known tests, Claude can write held-out acceptance tests.
- These tests are stored strictly outside the target repository under `~/.maestro/heldout/<project-hash>/<feature>/`.
- The executor has no access to these tests.
- Claude executes them using `maestro heldout <project> run <feature>` only after the executor submits its completion report.

### Test Weakening Detection (`maestro testdiff`)
To prevent tests from being quietly deleted, modified, or skipped to achieve a passing status:
- `maestro testdiff <project> [--base REF]` compares the current working tree against the base git branch.
- Inspects test files for deleted files, removed assertions, or newly introduced skip/ignore markers.
- If changes are detected without an explicit rationale in `progress.md`, `testdiff` exits with code 5, blocking acceptance.

### Review Rounds and File Tracking
- Each review cycle is documented in `.maestro/reviews/<feature>-round-N.md`.
- Numbered findings detail exact file paths, severities, and remediation steps.
- At most 2 review rounds are permitted before mandatory escalation to the user.

---

## 8. MCP Server Registration and Configuration

The module `scripts/agy_mcp_config.py` manages the integration of the Maestro MCP server into Antigravity:

1. **Primary Mechanism (`agy` CLI):**  
   If the `agy` command-line utility is detected on the system `PATH` or in standard installation directories, Maestro invokes:
   ```bash
   agy mcp add maestro -- python -I scripts/maestro_mcp.py
   ```
2. **Fallback Mechanism (Direct Configuration Editing):**  
   If `agy` is not available, Maestro edits Antigravity's JSON configuration files directly:
   - Modern 2.x agent app: `~/.gemini/config/mcp_config.json`
   - Legacy / IDE builds: `~/.gemini/antigravity/mcp_config.json`
   Before modifying any JSON configuration file, Maestro creates an automatic backup (`<file>.maestro-backup`). Existing server entries are preserved untouched.
3. **Removal:**  
   `install.py --uninstall` cleans up both the registered MCP entry and legacy configuration traces.

---

## 9. Tested Environment

This release was developed and tested against the following configuration:

| Component | Tested Version / Specification |
|---|---|
| Operating System | Windows 11 |
| Agent Application | Antigravity agent app 2.29 |
| Executor Model | Gemini 3.8 Flash (reasoning level: High) |
| Reviewer | Claude Code |

> **Important:** Other LLM models, alternative reasoning levels (e.g. Low/Medium), and other operating systems have not been tested.

---

## 10. Limitations

- **Undocumented Antigravity Internals:** The deep link format (`antigravity://open`) and the conversation summary protobuf schema (`agyhub_summaries_proto.pb`) are internal mechanisms subject to change across Antigravity updates.
- **Untested Platforms:** While macOS and Linux implementations are provided in `scripts/sender.py`, full end-to-end testing has only been verified on Windows 11.
- **Window Focus Requirement:** Keystroke synthesis requires that the Antigravity window can successfully be restored and gain foreground status.
- **Single Task Concurrency:** Only one task may be in flight per project at a time, enforced by `.maestro/active.json`.
- **Reviewer Session Continuity:** The Claude Code session must remain active during task execution to maintain the background wait loop and receive wake signals.

---

## 11. Repository Layout

```
.github/workflows/ci.yml     GitHub Actions continuous integration workflow
README.md / README.ar.md     Project documentation in English and Arabic
CONTRIBUTING.md              Contribution guidelines, test rules, and PR process
SECURITY.md                  Security policy, system touchpoints, and disclosure
CHANGELOG.md                 Release history and version changelog
LICENSE                      MIT License
maestro.cmd / maestro        Launchers for Windows (cmd) and macOS/Linux (shell)
install.py                   Installs Claude Code skill and registers MCP server
scripts/
  maestro.py                 Core CLI interface and subcommand dispatch
  sender.py                  Deep link dispatch, window focus, and Enter simulation
  agy_project.py             Antigravity protobuf parser for project workspace lookup
  maestro_mcp.py             Stdio MCP server for questions and plan checkpoints
  agy_mcp_config.py          Registration manager for Antigravity MCP configuration
  check_lang.py              Language separation validator across documentation
  version.py                 Version string definition
methodologies/
  ROLES.md                   The core roles and responsibilities contract
  standard/                  Default methodology rules and empty tool requirement
  uem/                       Unified Engineering Methodology rules and pinned tools
  custom/                    Minimal rules template for custom workflows
templates/
  task.md                    Task brief template
  report.md                  Execution report template with TDD sections
  review.md                  Review round template with findings structure
  state/                     Templates for feature_list.json, progress.md, session-handoff.md
skill/maestro/
  SKILL.md                   Claude Code skill definition and workflow rules
docs/
  en/                        English documentation suite (quickstart, architecture, methodologies)
  ar/                        Arabic documentation suite (quickstart)
examples/slugify/            End-to-end demonstration runs with briefs, plans, and reports
tests/                       Automated test suite
```

---

## 12. Design Decisions

### Window Mode as the Only Delivery Mode
Maestro delivers tasks exclusively by raising the Antigravity application window and inserting prompts into its chat interface.
- Direct editor integration (e.g. `antigravity-ide chat`) opens the code editor rather than the autonomous agent environment.
- Programmatic UI automation provides a direct, observable execution environment where users can watch the agent work, review tool authorizations, and intervene if necessary.

### The Headless Experiment (`agy -p`) and Lessons Learned

During the 0.5 cycle, Maestro experimentally evaluated headless execution using the Antigravity CLI print mode:
```bash
agy -p "<prompt>" --project <id> --output-format json
```
The intention was to run tasks entirely in the background without raising windows or simulating keystrokes.

**What worked:**
- Commands executed correctly inside the designated project workspace.
- The executor recognized all four Maestro MCP tools (`maestro_*`).
- The `--mode accept-edits` flag permitted file modifications within the workspace.
- Session-only permissions (`--settings '{"permissions":{"allow":["command(<exact>)"]}}'`) enabled precise command whitelisting without altering global settings.

**Why it was removed (5 failure causes):**
1. **Console Window Popups:** When launched with `DETACHED_PROCESS`, every console child process spawned by terminal units and MCP helpers opened its own visible console window (dozens of windows popped up across approximately 8 test runs). After switching to `CREATE_NO_WINDOW`, at least one window still opened while `agy` initialized its MCP servers before any user command was executed.
2. **Session Abort on Single Rejection:** If any single command was rejected (such as an innocent `dir` or exploratory command), the entire `agy` process terminated immediately, losing task progress.
3. **Exact Command Matching Only:** Permission rules required literal exact matching; wildcard command patterns like `command(dir *)` were rejected.
4. **Lack of `--mode auto`:** The autonomous execution mode was not available for owner accounts.
5. **Invisible Conversations:** Background tasks were recorded in Antigravity's data files but never displayed in the application UI list, preventing the user from inspecting ongoing sessions.

**Decision & Branch Preservation:**  
Headless mode was completely removed to ensure system stability. The full experimental implementation is preserved on branch `exp/headless` at commit `4e25928`.

**Discoveries Retained from the Experiment:**
- Foreground focus restoration via `AttachThreadInput` in window mode.
- Non-blocking desktop notifications when automatic Enter delivery fails.
- The `maestro answer --file` option for multi-line inputs.

**Conditions Required to Revisit Headless Execution:**
1. The `agy` tool must support command patterns or tolerate denied commands without aborting the session.
2. Background sessions must appear in Antigravity's application UI.
3. The underlying MCP/terminal child process console window popup issue must be resolved.

### Why MCP Cannot Start a Task
Model Context Protocol (MCP) servers operate as passive stdio JSON-RPC responders hosted by the client (Antigravity). An MCP server cannot initiate actions, send unsolicited inbound requests to the model, or trigger new conversation threads. Therefore, initial task delivery must rely on external invocation (the `antigravity://open` protocol URI). Once the task is actively executing, the MCP channel handles two-way mid-task questions and checkpoints.

### Why Answers Go Through `--file`
When passing multi-line strings (such as detailed plan review corrections or numbered review findings) as command-line arguments on Windows, `cmd.exe` truncates arguments at the first newline character. To prevent truncated instructions and corrupted markdown, `maestro answer` accepts `--file <path>` (or `-` for stdin), reading UTF-8 files cleanly without shell-escaping limitations.

### Why Tests Isolate the Home Folder at Process Level
During test runs and especially mutation testing, tests exercise code that reads and writes configuration files. If tests run with access to the real user environment, a mutant or buggy test could corrupt critical user configuration files in `~/.gemini` (such as `mcp_config.json` or `agyhub_summaries_proto.pb`) or `~/.claude`.

To guarantee absolute isolation:
- Tests and mutation commands override environment variables at the process level: `HOME`, `USERPROFILE`, and `LOCALAPPDATA` point to temporary directories.
- Real tools such as `agy` are excluded from the test process `PATH`.
- Real configuration files are fingerprinted before and after execution to confirm zero unintended mutations.
