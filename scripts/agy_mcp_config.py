"""Add or remove the Maestro MCP server in Antigravity's MCP config.

Usage: python -I agy_mcp_config.py add|remove

When the `agy` CLI is available, uses `agy mcp add|remove`. Otherwise falls back
to editing Antigravity's JSON configuration files directly:
  ~/.gemini/config/mcp_config.json        Antigravity agent app 2.x
  ~/.gemini/antigravity/mcp_config.json   older builds / Antigravity IDE
In file mode, `add` writes the entry to every one of these that exists (creating
the first if none does); `remove` deletes it from all. Every other server is kept
untouched, and each file is backed up (<file>.maestro-backup) before Maestro
first changes it.
Set MAESTRO_AGY_MCP_CONFIG to target a single file instead (file mode only).
"""
import json
import math
import os
import shutil
import subprocess
import sys

SERVER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "maestro_mcp.py")
NAME = "maestro"


def gemini_dir():
    return os.path.join(os.path.expanduser("~"), ".gemini")


def config_candidates():
    gemini = gemini_dir()
    return [os.path.join(gemini, "config", "mcp_config.json"),
            os.path.join(gemini, "antigravity", "mcp_config.json")]


def legacy_config_path():
    return os.path.join(gemini_dir(), "antigravity", "mcp_config.json")


def targets():
    override = os.environ.get("MAESTRO_AGY_MCP_CONFIG")
    if override:
        return [override]
    candidates = config_candidates()
    existing = [p for p in candidates if os.path.exists(p)]
    return existing or candidates[:1]


def load(path):
    if not os.path.exists(path):
        return {"mcpServers": {}}
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def save(path, cfg):
    backup = path + ".maestro-backup"
    if os.path.exists(path) and not os.path.exists(backup):
        shutil.copy2(path, backup)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def modify_files(action):
    paths = targets()
    candidates = config_candidates()
    if action == "remove":
        paths = [p for p in (paths + candidates if not os.environ.get("MAESTRO_AGY_MCP_CONFIG") else paths)
                 if os.path.exists(p)]
    for path in dict.fromkeys(paths):
        cfg = load(path)
        servers = cfg.setdefault("mcpServers", {})
        if action == "add":
            servers[NAME] = {"command": sys.executable, "args": ["-I", SERVER],
                             "description": "Maestro: lets the executor ask the reviewer questions mid-task"}
            save(path, cfg)
            print(f"registered '{NAME}' in {path}")
        elif NAME in servers:
            del servers[NAME]
            save(path, cfg)
            print(f"removed '{NAME}' from {path}")
    if action == "add":
        print(f"command: {sys.executable} -I {SERVER}")
    print("Restart Antigravity to apply.")


def clean_legacy_config():
    legacy = legacy_config_path()
    if os.path.exists(legacy):
        cfg = load(legacy)
        servers = cfg.setdefault("mcpServers", {})
        if NAME in servers:
            del servers[NAME]
            save(legacy, cfg)
            print(f"removed '{NAME}' from {legacy}")


def find_agy():
    if os.environ.get("MAESTRO_AGY_MCP_CONFIG"):
        return None
    override = os.environ.get("MAESTRO_AGY")
    if override:
        return override
    which = shutil.which("agy")
    if which:
        return which
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        win_path = os.path.join(local_app_data, "agy", "bin", "agy.exe")
        if os.path.isfile(win_path):
            return win_path
    unix_path = os.path.normpath(os.path.expanduser("~/.local/bin/agy"))
    if os.path.isfile(unix_path):
        return unix_path
    return None


def run_agy(agy_bin, action):
    raw_timeout = os.environ.get("MAESTRO_AGY_TIMEOUT", "60")
    try:
        timeout = float(raw_timeout)
        if not (math.isfinite(timeout) and timeout > 0):
            raise ValueError(f"non-positive or non-finite timeout: {raw_timeout}")
    except (ValueError, TypeError):
        print(f"invalid MAESTRO_AGY_TIMEOUT '{raw_timeout}'; falling back to 60s")
        timeout = 60.0
    if action == "add":
        cmd = [agy_bin, "mcp", "add", NAME, "--", sys.executable, "-I", SERVER]
    else:
        cmd = [agy_bin, "mcp", "remove", NAME]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        print(f"agy {action} timed out after {timeout}s; falling back to direct configuration file editing")
        modify_files(action)
        return
    except OSError as err:
        print(f"agy {action} execution failed ({err}); falling back to direct configuration file editing")
        modify_files(action)
        return

    if proc.returncode != 0:
        print(f"agy {action} failed (exit code {proc.returncode}); falling back to direct configuration file editing")
        modify_files(action)
        return

    if action == "add":
        print(f"registered '{NAME}' through agy")
    else:
        print(f"removed '{NAME}' through agy")
        clean_legacy_config()


def main(action):
    if action not in ("add", "remove"):
        sys.exit("usage: agy_mcp_config.py add|remove")

    if os.environ.get("MAESTRO_AGY_MCP_CONFIG"):
        modify_files(action)
        return

    agy = find_agy()
    if not agy:
        print("agy CLI not found; falling back to direct configuration file editing")
        modify_files(action)
        return

    run_agy(agy, action)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "")
