"""Unit tests for Maestro version reporting and consistency.

Verifies scripts/version.py as the single source of truth, maestro --version,
and maestro_mcp.py serverInfo under both standard and isolated (-I) Python invocation.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

# ---------------------------------------------------------------------------
# Process-Level Isolation
# ---------------------------------------------------------------------------
REAL_USER_HOME = os.path.expanduser("~")
SESSION_TEMP = tempfile.mkdtemp(prefix="maestro_version_session_")
SESSION_HOME = os.path.join(SESSION_TEMP, "home")
SESSION_LOCALAPPDATA = os.path.join(SESSION_TEMP, "localappdata")
SESSION_HELDOUT = os.path.join(SESSION_TEMP, "heldout")
os.makedirs(SESSION_HOME, exist_ok=True)
os.makedirs(SESSION_LOCALAPPDATA, exist_ok=True)
os.makedirs(SESSION_HELDOUT, exist_ok=True)

os.environ["HOME"] = SESSION_HOME
os.environ["USERPROFILE"] = SESSION_HOME
os.environ["LOCALAPPDATA"] = SESSION_LOCALAPPDATA
os.environ["MAESTRO_HELDOUT_HOME"] = SESSION_HELDOUT
os.environ["MAESTRO_MCP_LOG"] = os.path.join(SESSION_TEMP, "mcp.log")

_sanitized_path = []
for _entry in os.environ.get("PATH", "").split(os.pathsep):
    if not _entry:
        continue
    _has_agy = False
    try:
        if shutil.which("agy", path=_entry):
            _has_agy = True
    except Exception:
        pass
    if not _has_agy and os.path.isdir(_entry):
        for _name in ("agy", "agy.exe", "agy.cmd", "agy.bat", "agy.ps1"):
            if os.path.isfile(os.path.join(_entry, _name)):
                _has_agy = True
                break
    if not _has_agy:
        _sanitized_path.append(_entry)
os.environ["PATH"] = os.pathsep.join(_sanitized_path)

os.environ.pop("MAESTRO_AGY", None)
os.environ.pop("MAESTRO_AGY_MCP_CONFIG", None)
os.environ.pop("MAESTRO_AGY_TIMEOUT", None)

SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)


class TestVersion(unittest.TestCase):

    def test_version_file_constant(self):
        import version
        self.assertEqual(version.__version__, "0.6.1")

    def test_cli_version_flag(self):
        import version
        maestro_py = os.path.join(SCRIPTS_DIR, "maestro.py")
        res = subprocess.run(
            [sys.executable, maestro_py, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=dict(os.environ),
        )
        self.assertEqual(res.returncode, 0)
        output = (res.stdout + res.stderr).strip()
        self.assertEqual(output, f"maestro {version.__version__}")

    def test_mcp_server_info_version(self):
        import maestro_mcp
        import version
        self.assertEqual(maestro_mcp.SERVER["version"], version.__version__)

    def test_mcp_server_isolated_python_import(self):
        """Under python -I, the script directory is NOT in sys.path.

        maestro_mcp.py must explicitly add its directory to sys.path to load version.py.
        """
        import version
        mcp_py = os.path.join(SCRIPTS_DIR, "maestro_mcp.py")
        proc = subprocess.Popen(
            [sys.executable, "-I", mcp_py],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            env=dict(os.environ),
        )
        init_req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-runner"},
            },
        }
        try:
            stdout_line, _ = proc.communicate(input=json.dumps(init_req) + "\n", timeout=10)
            res = json.loads(stdout_line.strip().splitlines()[0])
            self.assertIn("result", res)
            server_info = res["result"].get("serverInfo", {})
            self.assertEqual(server_info.get("name"), "maestro")
            self.assertEqual(server_info.get("version"), version.__version__)
        finally:
            if proc.poll() is None:
                proc.kill()


if __name__ == "__main__":
    unittest.main()
