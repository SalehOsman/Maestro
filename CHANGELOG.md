# Changelog

## 0.6.1 — 2026-11-07

- **Methodology documentation and official source links**: Added comprehensive guide in `docs/en/methodologies.md` comparing `standard`, `uem`, and `custom` methodologies, lifecycle phases, and state file management. Restored official verified source URLs for all `uem` tools (Superpowers, EGM, Harness Engineering, AgentShield, ECC) in READMEs and documentation. Documented explicit tool audit and approval workflow via `maestro tools --approve`, and added Arabic methodology summary section in `docs/ar/quickstart.md`.
- **Review verdict and feature list fixes**: Supported both `feature_list.json` data formats (top-level list and `{"features": [...]}` object) in `load_feature_list`. Enforced refusal of duplicate feature IDs in `review verdict` and added detection and non-object warnings in `maestro status` to guard against malformed state files found in real-world usage.

## 0.6.0 — 2026-11-07

- **Safe send refusal**: `send` refuses by default when the Antigravity project is unknown (found when running on `F:\arabictyping`, where the task landed in the selected project instead); `--allow-current-project` allows sending anyway.
- **Documentation split**: Complete documentation in English (`docs/en/`), with parallel Arabic documentation for the README and quick start guide (`README.ar.md` and `docs/ar/quickstart.md`).
- **Comprehensive documentation in `docs/en/`**: Added `docs/en/quickstart.md` (end-to-end walkthrough, state files reference, and troubleshooting) and `docs/en/architecture.md` (deep dive into delivery mechanics, MCP protocols, and quality gates).
- **Official test suite**: 82 unit tests with strict process-level environment isolation (`HOME`, `USERPROFILE`, `LOCALAPPDATA`, `MAESTRO_HELDOUT_HOME`, `MAESTRO_MCP_LOG`) and mock execution boundaries.
- **GitHub Actions CI**: Automated cross-platform CI matrix across Windows, Linux, and macOS with Python 3.10 and 3.14, including an automated language separation check.
- **Language validation script**: Added `scripts/check_lang.py` enforcing Unicode Arabic character restrictions in English documentation and English prose restrictions in Arabic files.
- **Version management**: Added `scripts/version.py` and `maestro --version` CLI flag.
- **Configurable MCP logging**: `scripts/maestro_mcp.py` respects `MAESTRO_MCP_LOG` environment variable for test and runtime redirection.
- **Python 3.10 minimum requirement**: Updated prerequisite checks in `install.py` and documentation to require Python 3.10 or newer. The first CI run showed that `Path.write_text(newline=)` needs 3.10, and that Ubuntu 26.04 runners have no Python 3.9.
- **Python 3.8 MCP compatibility**: Fallback for `str.removeprefix` in `scripts/maestro_mcp.py`.
- **New relay example**: Added `examples/slugify` (verified multi-task relay demonstrating briefs, plans, questions, and review rounds), replacing `examples/calculator`.
- **Tested environment**: Validated on Windows 11, Antigravity 2.29, Gemini 3.8 Flash (High reasoning), and Claude Code.
- **Release cleanup**: Removed deprecated Arabic draft files (`docs/DESIGN.ar.md`, `docs/QUICKSTART.ar.md`) and added `CONTRIBUTING.md` and `SECURITY.md`.

## 0.5.0 — 2026-11-06

- Window delivery: the sender gets past the Windows foreground lock (`AttachThreadInput`). When
  Enter still cannot be pressed, a desktop notification asks the user to do it.
- Fix: `answer --file <path>|-` for multi-line answers. Windows `cmd.exe` cut command-line
  arguments at the first newline, which truncated numbered corrections.
- `status` shows tasks, questions and the active task.
- Headless delivery was tried, then removed; it is kept on branch `exp/headless`; the reasons are documented in `docs/en/architecture.md` (originally in historical design notes).

## 0.4.0 — 2026-11-06

**Roles and methodologies.** The executor plans and writes the code and the tests. Claude supervises
and reviews in depth. This follows DR-020.

- `methodologies/ROLES.md`: one owner per duty, two stop points, review depth by risk, numbered
  findings with a severity, and at most 2 rounds.
- Three executor methodologies, chosen at `init --methodology`:
  - `standard`: built in, needs no external tools. Plan checkpoint, TDD with red and green
    evidence, state files.
  - `uem`: Unified Engineering Methodology, with Superpowers, EGM, Harness Engineering and
    AgentShield.
  - `custom`: the project's own workflow, with Maestro's minimum contract.
- `methodologies/uem/requirements.json` pins the source and version of every tool. `maestro tools`
  checks them, including installed Antigravity plugins through `agy plugin list`. `--approve`
  writes an install task with the exact pinned commands, for the tools the user approved.
- MCP `maestro_checkpoint` (plan stop point). Unanswered checkpoints tell the executor not to
  continue. `wait` marks them `CHECKPOINT: plan`.
- `.maestro/config.json` per project. The stack is detected: verify, test, mutation and held-out
  commands. It also holds the high-risk paths and topics and the maximum number of review rounds.
- `heldout add|list|run`: hidden acceptance tests stored outside the repository, run only while no
  task is in flight, and removed after the run.
- `review new` (round files, exit 4 when no rounds are left) and `review verdict` (reviewer-only;
  only `passing` features can be accepted).
- `testdiff`: deleted test files, removed assertions, and new skip/only markers since the base
  branch (exit 5).
- New templates: feature brief, report with TDD evidence, review round, `feature_list.json`,
  `progress.md`, `session-handoff.md`.
- The skill is rewritten for the new workflow.

## 0.3.0 — 2026-11-06

- **Cross-platform rewrite in Python.** The PowerShell scripts (`maestro.ps1`, `send-task.ps1`,
  `wait-report.ps1`, `install.ps1`) are replaced by `scripts/maestro.py`, `scripts/sender.py` and
  `install.py`. Python's standard library is the only dependency.
- Launchers: `maestro.cmd` (Windows) and `maestro` (macOS/Linux, LF endings enforced through
  `.gitattributes`).
- Sending per platform:
  - Windows: Win32 through ctypes. Tested.
  - macOS: `open` plus AppleScript. Untested.
  - Linux X11: `xdg-open` plus `xdotool`. Untested.
  - Wayland: the prompt is drafted, and the user presses Enter.
  `send` prints why it could not press Enter.
- Flags renamed: `-NoEnter` is now `--no-enter`, `-TimeoutMinutes` is now `--timeout`, and
  `install.ps1 -WithMcp` / `-Uninstall` are now `install.py --with-mcp` / `--uninstall`.
- The skill is installed with the launcher that fits the platform.
- Fix: Antigravity 2.x reads MCP servers from `~/.gemini/config/mcp_config.json`. Before this fix,
  Maestro registered only in `~/.gemini/antigravity/mcp_config.json`, so the server never loaded.
  Registration now covers every config file that exists.
- The MCP server writes a small diagnostic log to `logs/mcp.log` (startup and the methods it
  receives, without tool arguments).
- `send` waits up to 4 seconds for Antigravity to reach the foreground before it falls back to
  drafting. A single 0.6-second check failed right after Antigravity started.
- `agy_project.py` and `agy_mcp_config.py` use portable paths. `agy_project.py` handles a missing
  summaries file.

## 0.2.0 — 2026-11-06

- Optional MCP server `scripts/maestro_mcp.py` (standard library, stdio) with three tools:
  `maestro_ask`, `maestro_check_answer` and `maestro_progress`. The executor can ask the reviewer
  questions mid-task.
- `wait` returns early with exit 3 and the question when one is unanswered.
- New `answer` command. `status` now also lists questions.
- `install.ps1 -WithMcp` registers the server in Antigravity's `mcp_config.json` and backs the file
  up first. `-Uninstall` removes both the skill and the MCP entry.
- Executor rules and the skill updated for the question flow.
- Active-task guard. `send` writes `.maestro/active.json` and `wait` clears it. The MCP tools refuse
  at once unless a matching, unreported task younger than 12 hours is active, so Antigravity used
  outside Maestro never blocks. `send` refuses while another task is in flight. New `release`
  command. `status` shows the active task.
- The MCP server tolerates a BOM at the start of input.

## 0.1.0 — 2026-11-06

First experimental release.

- `maestro.cmd` CLI with `init`, `new`, `send`, `wait` and `status`. It works on any project folder.
- Sending through the `antigravity://open?prompt=&project=` deep link. Enter is pressed only when the
  Antigravity agent window is in the foreground.
- `agy_project.py` resolves the Antigravity project id from a folder path (read-only).
- Token-free waiting for the executor's report, with a 45-minute timeout.
- `EXECUTOR_RULES.md` is copied into each project and read by Antigravity before every task.
- Claude Code skill `/maestro` covering the whole loop: brainstorm, spec, tasks, send, wait,
  independent verification, and fix loop with at most 3 rounds.
- `install.ps1` checks the prerequisites and installs the skill.
- Example: `examples/calculator` (historical demonstration, replaced by `examples/slugify` in 0.6.0).
