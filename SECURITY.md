# Security Policy

## System Boundaries and Touchpoints

Maestro operates locally using Python's standard library. It touches the following locations on a user's machine:

- `~/.claude/skills/maestro`: Contains the installed Claude Code skill files.
- `~/.gemini/config/mcp_config.json` and `~/.gemini/antigravity/mcp_config.json`: Registers the Maestro MCP server through `agy mcp add` when available, or by updating the configuration file with a timestamped `.bak` backup created beforehand.
- `~/.maestro/heldout`: Holds hidden acceptance test suites stored outside the target project repository.
- Project `.maestro/` directories: Holds feature briefs, implementation plans, execution reports, review files, and the transient active task marker (`.maestro/active.json`).
- `agyhub_summaries_proto.pb`: Performs a read-only scan of Antigravity project metadata to resolve project IDs from folder paths without modifying the file.

## Security Controls

- **MCP Active-Task Guard**: The Maestro MCP server tools reject calls immediately unless an active, unreported task younger than 12 hours is registered in `.maestro/active.json`. This ensures Antigravity cannot be commanded or blocked outside an authorized Maestro session.
- **Pinned Tool Requirements**: External tools defined in methodology requirements are pinned to explicit sources and versions. Tools are installed only with explicit per-tool user approval via `maestro tools --approve`; unpinned or dynamic commands such as `npx --yes` are never used.
- **No Network Calls**: Maestro itself never initiates network requests, collects analytics, or transmits telemetry.
- **No Secrets Stored**: Maestro does not collect, handle, or store API keys, authentication credentials, or secrets.

## Reporting a Vulnerability

If you identify a security issue or vulnerability:

1. Open a GitHub Security Advisory at [SalehOsman/Maestro Security Advisories](https://github.com/SalehOsman/Maestro/security/advisories).
2. Or open an issue on the `SalehOsman/Maestro` repository without disclosing sensitive details.

Reports are not handled via email.
