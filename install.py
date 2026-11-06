"""Install Maestro (Windows, macOS, Linux).

  python install.py               install the Claude Code skill (~/.claude/skills/maestro)
  python install.py --with-mcp    also register the Maestro MCP server in Antigravity
                                  (~/.gemini/antigravity/mcp_config.json, backed up first)
  python install.py --uninstall   remove the skill and the MCP entry

Re-run after moving the Maestro folder or pulling updates.
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

HOME = Path(__file__).resolve().parent
SKILL_SRC = HOME / "skill" / "maestro" / "SKILL.md"
SKILL_DST = Path.home() / ".claude" / "skills" / "maestro"
MCP_CFG = HOME / "scripts" / "agy_mcp_config.py"
AGY_DATA = Path.home() / ".gemini" / "antigravity"
MIN_PYTHON = (3, 10)


def maestro_command():
    """The command the skill tells Claude to run."""
    if sys.platform == "win32":
        return f'"{HOME / "maestro.cmd"}"'
    return f'"{HOME / "maestro"}"'


def check_prerequisites():
    missing = []
    if sys.version_info < MIN_PYTHON:
        missing.append(f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} or newer")
    if sys.platform == "win32":
        app = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "antigravity" / "Antigravity.exe"
        if not app.exists():
            missing.append(f"Antigravity agent app (expected {app})")
    elif sys.platform == "darwin":
        if not any(Path(p).exists() for p in ("/Applications/Antigravity.app", Path.home() / "Applications" / "Antigravity.app")):
            missing.append("Antigravity agent app (/Applications/Antigravity.app)")
    else:
        if not shutil.which("xdg-open"):
            missing.append("xdg-open (package xdg-utils)")
        if os.environ.get("WAYLAND_DISPLAY") and not os.environ.get("DISPLAY"):
            print("NOTE: Wayland session; Maestro will draft prompts but you will press Enter yourself.")
        elif not shutil.which("xdotool"):
            missing.append("xdotool (to press Enter automatically; optional)")
    if not AGY_DATA.exists():
        missing.append(f"Antigravity data folder {AGY_DATA} (sign in to Antigravity once)")
    if missing:
        print("WARNING, missing prerequisites:")
        for m in missing:
            print(f"  - {m}")
    return missing


def run_mcp_config(action):
    subprocess.run([sys.executable, "-I", str(MCP_CFG), action], check=True)


def main():
    ap = argparse.ArgumentParser(description="Install Maestro")
    ap.add_argument("--with-mcp", action="store_true", help="register the MCP server in Antigravity")
    ap.add_argument("--uninstall", action="store_true", help="remove the skill and the MCP entry")
    a = ap.parse_args()

    if a.uninstall:
        if SKILL_DST.exists():
            shutil.rmtree(SKILL_DST)
            print(f"removed {SKILL_DST}")
        else:
            print("skill not installed")
        run_mcp_config("remove")
        return

    check_prerequisites()
    if sys.platform != "win32":
        launcher = HOME / "maestro"
        launcher.chmod(launcher.stat().st_mode | 0o111)
    text = SKILL_SRC.read_text(encoding="utf-8-sig")
    text = text.replace("{{MAESTRO_HOME}}", str(HOME)).replace("{{MAESTRO_CMD}}", maestro_command())
    SKILL_DST.mkdir(parents=True, exist_ok=True)
    (SKILL_DST / "SKILL.md").write_text(text, encoding="utf-8", newline="\n")  # no BOM: keeps frontmatter valid
    print(f"installed skill -> {SKILL_DST} (tool home: {HOME})")
    if a.with_mcp:
        run_mcp_config("add")
    else:
        print("MCP not registered (optional). Re-run with --with-mcp to let Antigravity ask questions mid-task.")
    print("Start a new Claude Code session and type /maestro to use it.")


if __name__ == "__main__":
    main()
