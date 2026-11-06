# Quick Start Guide

This guide walks you through installing Maestro, setting up a project, and running your first supervised feature from start to finish.

---

## 1. Prerequisites and Installation

### Prerequisites

Make sure you have installed and configured:
1. **Claude Code** (CLI or desktop application).
2. The **Antigravity agent app**, signed in. (*Note: Antigravity IDE, the code editor, is a separate application and is not used.*)
3. **Python 3.10 or newer** (using standard library only), available as `python` on Windows or `python3` on macOS and Linux.
4. **macOS**: Accessibility permission for your terminal or host app running Claude Code. This allows Maestro to send the Return key to Antigravity. macOS prompts for this on first execution.
5. **Linux**: `xdg-utils` (and `xdotool` on X11 if you want Enter pressed automatically).

### Install Maestro

Clone the Maestro repository and run the installer:

**Windows (PowerShell):**

```powershell
git clone https://github.com/SalehOsman/Maestro C:\Tools\Maestro
python C:\Tools\Maestro\install.py --with-mcp
```

**macOS / Linux (Bash):**

```bash
git clone https://github.com/SalehOsman/Maestro ~/tools/maestro
python3 ~/tools/maestro/install.py --with-mcp
```

The installer verifies your environment and registers the Claude Code skill under `~/.claude/skills/maestro`.

> **Important: Why `--with-mcp` is recommended**  
> Running `install.py --with-mcp` registers the Maestro MCP server in Antigravity's configuration. This allows Antigravity to pause at the **plan checkpoint** and ask clarifying questions mid-task. Without MCP, the executor drafts its plan and immediately implements code without a checkpoint review.  
> **After running with `--with-mcp`, fully restart the Antigravity agent app.**

---

## 2. One-Time Project Setup

Before running tasks on any project for the first time, perform these two quick steps:

### Step 1: Register the workspace in Antigravity

Open your project folder in the Antigravity agent app and send any single message in the chat box (for example, "hello" or "init").

Antigravity registers the project folder internally only after a conversation has taken place. Maestro reads this registration so it can deliver task prompts to the exact window.

### Step 2: Start your first session in Claude Code

Open the same project folder in Claude Code and invoke Maestro:

```
/maestro Add a CSV export button to the transactions table
```

You do not need to run `maestro init` manually. Claude invokes `init` behind the scenes, asks you which methodology to use, and configures the project:
- **`standard` (recommended):** Maestro's built-in workflow. No external tools required; uses your project's existing test runners.
- **`uem`:** Unified Engineering Methodology with Superpowers, EGM, and AgentShield.
- **`custom`:** For teams with established custom workflows.

*(If you prefer manual control, you can run `maestro init <project> [--methodology standard|uem|custom]` from your shell.)*

---

## 3. Your First Feature End to End

Here is how a feature proceeds through the entire loop:

### Step 3.1: Brainstorming and Brief Creation
Claude discusses the requirements with you, clarifying acceptance criteria, edge cases, and constraints. Once you agree, Claude writes a feature brief to `.maestro/tasks/task-001.md`.

### Step 3.2: Task Dispatch
Claude dispatches the brief to Antigravity using `maestro send`. Maestro focuses the Antigravity agent app window and presses Enter automatically. Claude then runs `maestro wait` in the background, idling at zero token cost.

### Step 3.3: Plan Checkpoint (Stop Point 1)
In Antigravity, the agent reads the brief, examines the repository, and writes an implementation plan to `.maestro/plans/<feature>.md`.

With MCP enabled, the executor pauses and calls `maestro_checkpoint`. Claude wakes up (exit code 3), reviews the plan for scope creep, missing tests, or unnecessary complexity, and responds with `APPROVED` (or numbered corrections) along with the review depth (quick vs. full).

### Step 3.4: Test-Driven Implementation
Antigravity executes the approved plan test-first (Red -> Green -> Refactor):
1. Writes failing tests and captures test failure output.
2. Writes the minimal implementation to pass the tests.
3. Runs the test suite and self-verification commands to capture passing evidence.
4. Writes the final completion report to `.maestro/reports/task-001.done.md` as its final step.

### Step 3.5: Review and Verification (Stop Point 2)
When the report file appears, Claude wakes up automatically:
- Claude never takes the report as proof. It re-runs the tests independently.
- Claude inspects `git diff` for out-of-scope edits or accidental changes.
- Claude runs `maestro testdiff` to ensure no existing tests were deleted, weakened, or skipped.
- For full reviews, Claude runs mutation testing and held-out acceptance tests stored outside the repository.
- Claude creates a review record in `.maestro/reviews/<feature>-round-1.md`. If fixes are required, Claude sends a fix brief (up to at most 2 review rounds).

### Step 3.6: Merge Approval
Once all acceptance criteria and quality gates pass, Claude marks the feature accepted in `feature_list.json` and presents the completed work, evidence, and manual verification steps. You inspect the work and give final approval to merge the branch.

---

## 4. What Maestro Adds to a Project

Maestro maintains a clean, structured workspace layout. It never modifies your project's existing `AGENTS.md` or `GEMINI.md`:

```
<project>/
  feature_list.json              Feature registry: status, evidence, review verdict [standard, uem]
  progress.md                    Architectural log, test adjustments, mutation notes [standard, uem]
  session-handoff.md             Summary of work done, verification, and next steps  [standard, uem]
<project>/.maestro/
  config.json                    Project settings: test commands, risk paths, review rounds
  ROLES.md                       Contract defining roles and responsibilities
  EXECUTOR_RULES.md              Instructions followed by the Antigravity executor
  report-template.md             Standard template for completion reports
  tasks/task-NNN.md              Feature briefs generated by Claude
  plans/<feature>.md             Implementation plans authored by Antigravity
  reports/task-NNN.done.md       Final execution reports with TDD evidence
  reviews/<feature>-round-N.md   Review rounds with findings (at most 2 rounds)
  questions/task-NNN-qN.*        Mid-task questions and answers (exchanged via MCP)
  progress/task-NNN.log          Progress log stream from long-running tasks
  active.json                    Transient marker present only while a task is in flight
```

> **Tip:** You may commit `.maestro/` to version control to preserve a history of briefs, plans, and reviews. Always add `.maestro/active.json` to `.gitignore`, as it is a temporary lock file.

---

## 5. Troubleshooting

| Symptom | Cause | Solution |
|---|---|---|
| `init` reports Antigravity does not know the folder | Antigravity has not indexed the workspace | Open the folder in the Antigravity agent app and send one message. Then re-run `init` or `/maestro`. |
| `send` exits with code 2 | Antigravity window could not be focused or automatic Enter was prevented | Check the terminal output. On Windows, ensure Antigravity is not minimized. On macOS, grant Accessibility permissions to your terminal. On Linux Wayland or without `xdotool`, press Enter in Antigravity manually; Claude continues waiting. |
| The prompt lands in the wrong Antigravity project | Project ID lookup could not resolve the folder | Ensure you sent a message in that folder within Antigravity so its path is recorded in Antigravity's project summaries. |
| `wait` times out after 45 minutes | Antigravity hit an error, paused for user input, or had complex steps | Check the Antigravity application window for error messages or permission dialogs. |
| `wait` exits with code 3 repeatedly | An unanswered executor question or checkpoint is pending | Answer the pending question using `maestro answer <project> <question-id> "<text>"` (single-line) or `maestro answer <project> <question-id> --file <file>` (multi-line). |
| `send` says another task "is still in flight" | A previous task was interrupted without reporting | If the prior task was abandoned, clear the marker by running `maestro release <project>`. |
| `maestro` is not visible in Antigravity's MCP UI settings | The settings page only displays plugin-installed servers | This is normal. Antigravity loads servers registered in `mcp_config.json`. Check `<Maestro folder>/logs/mcp.log` (or the file set by `MAESTRO_MCP_LOG`) to confirm `recv tools/list`. |
| Antigravity does not offer `maestro_*` tools | MCP server was not registered or Antigravity was not restarted | Run `python install.py --with-mcp`, verify `~/.gemini/config/mcp_config.json` contains a `maestro` entry, and restart the Antigravity agent app completely. |
| Nothing happens when running `send` | The `antigravity://` protocol handler is not registered | Reinstall the Antigravity agent app to re-register its protocol handler. |
| `./maestro: bad interpreter` error on macOS or Linux | Script has Windows CRLF line endings | Run `git config core.autocrlf input`, then checkout or pull the files again. |
