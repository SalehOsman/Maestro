# Maestro

Arabic version: [README.ar.md](README.ar.md)

**The Antigravity agent plans and builds. Claude Code supervises and reviews.**

Maestro turns [Claude Code](https://claude.com/claude-code) into a supervising lead for the Antigravity agent app. You brainstorm and agree on a feature with Claude, and Claude sends Antigravity a brief. Antigravity writes a plan and builds the feature test-first, then Claude independently verifies the code and tests before asking for your merge approval. Waiting for Antigravity costs **no tokens**.

```
 You ──brainstorm──▶ Claude Code (Maestro) ──task-NNN.md──▶ Antigravity agent
                          ▲      │                                │
                          │      └─ waits idle (no tokens)        │ implements
                          │                                       │ (may ask a question, MCP)
                          └──── verifies: tests, diff ◀── task-NNN.done.md (report)
                                 │
                                 └─ fails? ──▶ fix task ──▶ Antigravity ...
```

## Status

**Version 0.6.0 (experimental).** Maestro relies on undocumented Antigravity internals (see [Architecture: Limitations](docs/en/architecture.md#limitations)).

| Platform | State |
|---|---|
| Windows 10/11 | Tested with Antigravity 2.29, including the MCP question channel end to end |
| macOS | Implemented, **untested** |
| Linux (X11) | Implemented, **untested** |
| Linux (Wayland) | Implemented, **untested**. Prompts are drafted, and you press Enter yourself. |

### Tested with

| Component | Tested environment |
|---|---|
| Operating system | Windows 11 |
| Agent application | Antigravity agent app 2.29 |
| Executor model | Gemini 3.8 Flash (reasoning level: High) |
| Reviewer | Claude Code |

Other models, reasoning levels, and operating systems have not been tested.

## Requirements

- [Claude Code](https://claude.com/claude-code) (CLI or desktop app)
- The **Antigravity agent app**, signed in (*Antigravity IDE*, the editor, is a separate app and is not used)
- Python 3.10+ (standard library only), available as `python` on Windows and `python3` on macOS/Linux
- macOS: Accessibility permission for the terminal or app that runs Claude Code (required to send Return to Antigravity)
- Linux: `xdg-utils` (and `xdotool` on X11 to press Enter automatically)

## Install

**Windows**

```powershell
git clone https://github.com/SalehOsman/Maestro C:\Tools\Maestro
python C:\Tools\Maestro\install.py
```

**macOS / Linux**

```bash
git clone https://github.com/SalehOsman/Maestro ~/tools/maestro
python3 ~/tools/maestro/install.py
```

The installer verifies prerequisites and installs the Claude Code skill to `~/.claude/skills/maestro`.

**Optional: enable plan checkpoints and mid-task questions (MCP).**
Run the installer with `--with-mcp`:

```bash
python install.py --with-mcp
```

This registers the Maestro MCP server in Antigravity's configuration. Fully restart the Antigravity agent app afterwards. This is strongly recommended so Claude can check plans before code is written.

To remove the skill and MCP registration:

```bash
python install.py --uninstall
```

## Quick start

1. **Open the project folder** in the Antigravity agent app and send any one message to register the folder with Antigravity.
2. **Open the same folder in Claude Code** and request a feature:
   ```
   /maestro Add a CSV export to the reports page
   ```
3. **Approve the brief and leave Antigravity open.** Claude coordinates the task, reviews the executor's plan and tests, and presents the finished work for your merge approval.

For a full walkthrough, state files reference, and troubleshooting, see the [Quick start guide](docs/en/quickstart.md).

## Roles and methodologies

Each party has fixed duties. See [`methodologies/ROLES.md`](methodologies/ROLES.md) for the complete contract.

| Role | Party | Owns |
|---|---|---|
| **Decider** | **You** | What to build, priorities, and approving every merge |
| **Executor** | **Antigravity** | The plan, test-first implementation, self-verification with concrete evidence, and the completion report |
| **Reviewer** | **Claude Code** | Feature briefs, plan checks at checkpoints, independent verification (tests, diff, held-out tests, mutation), and review verdicts |

There are **two stop points** per feature: the plan checkpoint and the final report. Review findings are numbered as `blocking`, `should-fix`, or `note`, with at most **two review rounds**.

| Methodology | For | External tools |
|---|---|---|
| `standard` (recommended) | Any project | None. Uses the project's own test runner and linters. |
| `uem` | Unified Engineering Methodology users | Superpowers, EGM, Harness Engineering, AgentShield, ECC (optional) |
| `custom` | Projects with their own workflow | None. Enforces Maestro's minimum contract; the full review remains intact. |

External tools are installed only with your **explicit approval of each tool**, using the **source and pinned version** defined in `methodologies/<name>/requirements.json`.

## Commands

The CLI launcher is `maestro.cmd` on Windows and `./maestro` on macOS/Linux. `python scripts/maestro.py` works on all platforms.

| Command | Purpose |
|---|---|
| `maestro --version` | Print the program version |
| `maestro init <project> [--methodology standard\|uem\|custom]` | Create `<project>/.maestro/`. Safe to re-run to refresh templates and rules. |
| `maestro tools <project> [--approve ID...]` | Check methodology tools; write an install task for approved tools |
| `maestro new <project> "<title>" [--feature ID]` | Create the next feature brief (`task-NNN.md`) |
| `maestro send <project> [NNN] [--no-enter]` | Send task NNN (default: latest) to Antigravity |
| `maestro wait <project> [NNN] [--timeout 45]` | Block until report arrives (no tokens spent; exits 3 on questions/checkpoints) |
| `maestro answer <project> <question-id> "<text>" \| --file FILE` | Answer an executor question (use `--file` for multi-line answers) |
| `maestro heldout <project> add\|list\|run <feature> [files]` | Manage hidden acceptance tests stored outside the repository |
| `maestro review <project> new <feature> [--task NNN]` | Create next review-round file (exit 4 when no rounds remain) |
| `maestro review <project> verdict <feature> accepted\|changes-requested` | Record reviewer verdict in `feature_list.json` |
| `maestro testdiff <project> [--base REF]` | Identify deleted, weakened, or skipped tests since the base branch (exit 5 if found) |
| `maestro release <project>` | Clear the active-task marker after abandoning a task |
| `maestro status <project>` | Display tasks, questions, and active task state |

Exit codes:

| Code | Meaning |
|---|---|
| 0 | Success, task sent, or report ready |
| 1 | Error, wait timed out, or held-out test failure |
| 2 | Prompt drafted in Antigravity, but Enter was not pressed (see notification or printed reason) |
| 3 | Wait woke on an unanswered question or plan checkpoint |
| 4 | No review rounds left (`review new`); escalate to user |
| 5 | Test changes found by `testdiff` that require a written reason |

## Documentation

- [Quick start guide](docs/en/quickstart.md) - Detailed setup, end-to-end workflow, project state files, and troubleshooting.
- [Architecture and design](docs/en/architecture.md) - Deep dive into delivery, MCP protocol, quality gates, and design decisions.
- [Roles and responsibilities](methodologies/ROLES.md) - Detailed role split and review rules.
- [Changelog](CHANGELOG.md) - Version release history and changes.
- [Contributing](CONTRIBUTING.md) - Guidelines for contributing to Maestro.
- [Security](SECURITY.md) - Security policy and reporting vulnerabilities.

## Disclaimer

Maestro is an independent project. It is not affiliated with, endorsed by, or supported by Google or Anthropic. "Antigravity" and "Claude" are trademarks of their respective owners.

## License

[MIT](LICENSE)
