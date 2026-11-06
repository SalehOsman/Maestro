"""Unit tests for agy_mcp_config.py.

Verifies agy CLI integration, legacy file cleanup, fallback handling,
forced file mode, and guarantees real host configuration is never touched.
"""
import importlib.util
import io
import json
import math
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Process-Level Isolation (Finding 1)
# MUST execute BEFORE importing agy_mcp_config so that any static/import-time
# path evaluations are strictly constrained to a temporary session folder.
# Restore nothing at exit; this is a test process.
# ---------------------------------------------------------------------------
REAL_USER_HOME = os.path.expanduser("~")
REAL_USER_GEMINI = os.path.join(REAL_USER_HOME, ".gemini")

SESSION_TEMP = tempfile.mkdtemp(prefix="maestro_session_")
SESSION_HOME = os.path.join(SESSION_TEMP, "home")
SESSION_LOCALAPPDATA = os.path.join(SESSION_TEMP, "localappdata")
os.makedirs(SESSION_HOME, exist_ok=True)
os.makedirs(SESSION_LOCALAPPDATA, exist_ok=True)

os.environ["HOME"] = SESSION_HOME
os.environ["USERPROFILE"] = SESSION_HOME
os.environ["LOCALAPPDATA"] = SESSION_LOCALAPPDATA

# Remove every PATH entry containing an agy executable
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

# Clear any override environment variables from host
os.environ.pop("MAESTRO_AGY", None)
os.environ.pop("MAESTRO_AGY_MCP_CONFIG", None)
os.environ.pop("MAESTRO_AGY_TIMEOUT", None)

# Add scripts directory to sys.path
SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import agy_mcp_config

# Immediately assert that agy_mcp_config.gemini_dir() resolves inside SESSION_TEMP
_gemini_resolved = os.path.realpath(agy_mcp_config.gemini_dir())
_session_abs = os.path.realpath(SESSION_TEMP)
assert _gemini_resolved.startswith(_session_abs + os.sep) or _gemini_resolved == _session_abs, (
    f"FATAL / ABORT: agy_mcp_config.gemini_dir() ({_gemini_resolved}) "
    f"does not resolve inside session temp folder ({_session_abs})! "
    f"Aborting entire module before running any tests."
)


class BaseAgyMcpConfigTest(unittest.TestCase):
    def setUp(self):
        # Safety guard: refuse to run if call-time dynamic paths are missing
        if not hasattr(agy_mcp_config, "config_candidates"):
            self.fail("call-time paths missing; refusing to run")

        # Snapshot real home / .gemini paths to ensure safety
        self.real_home = os.path.expanduser("~")
        self.real_gemini = os.path.join(self.real_home, ".gemini")

        # Create isolated temp directory for HOME / USERPROFILE / LOCALAPPDATA
        # Layered inside SESSION_TEMP
        self.temp_dir = tempfile.mkdtemp(prefix="maestro_test_", dir=SESSION_TEMP)
        self.temp_home = os.path.join(self.temp_dir, "home")
        self.temp_localappdata = os.path.join(self.temp_dir, "localappdata")
        os.makedirs(self.temp_home, exist_ok=True)
        os.makedirs(self.temp_localappdata, exist_ok=True)

        # Environment snapshot
        self.orig_env = dict(os.environ)

        # Redirect environment variables to isolated temp paths
        os.environ["HOME"] = self.temp_home
        os.environ["USERPROFILE"] = self.temp_home
        os.environ["LOCALAPPDATA"] = self.temp_localappdata
        os.environ.pop("MAESTRO_AGY", None)
        os.environ.pop("MAESTRO_AGY_MCP_CONFIG", None)
        os.environ.pop("MAESTRO_AGY_TIMEOUT", None)

        # Patch os.path.expanduser so ~ maps to self.temp_home
        self.expanduser_patcher = patch("os.path.expanduser", side_effect=self._fake_expanduser)
        self.mock_expanduser = self.expanduser_patcher.start()

        # Create fake agy script and wrapper in temp_dir
        self.fake_log_file = os.path.join(self.temp_dir, "fake_agy_args.json")
        self.fake_agy_bin = self._create_fake_agy()

    def _fake_expanduser(self, path):
        if path == "~":
            return self.temp_home
        if path.startswith("~/") or path.startswith("~\\"):
            return os.path.join(self.temp_home, path[2:])
        return path

    def _create_fake_agy(self):
        py_script = os.path.join(self.temp_dir, "fake_agy.py")
        code = (
            "import sys, os, json, time\n"
            "log_path = os.environ.get('FAKE_AGY_LOG')\n"
            "if log_path:\n"
            "    with open(log_path, 'w', encoding='utf-8') as f:\n"
            "        json.dump(sys.argv[1:], f)\n"
            "sleep_sec = float(os.environ.get('FAKE_AGY_SLEEP', '0'))\n"
            "if sleep_sec > 0:\n"
            "    time.sleep(sleep_sec)\n"
            "code = int(os.environ.get('FAKE_AGY_EXIT_CODE', '0'))\n"
            "sys.exit(code)\n"
        )
        with open(py_script, "w", encoding="utf-8") as f:
            f.write(code)

        if sys.platform == "win32":
            wrapper = os.path.join(self.temp_dir, "fake_agy.cmd")
            with open(wrapper, "w", encoding="utf-8") as f:
                f.write(f'@"{sys.executable}" "{py_script}" %*\n')
            return wrapper
        else:
            wrapper = os.path.join(self.temp_dir, "fake_agy.sh")
            with open(wrapper, "w", encoding="utf-8") as f:
                f.write(f'#!/bin/sh\nexec "{sys.executable}" "{py_script}" "$@"\n')
            os.chmod(wrapper, os.stat(wrapper).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
            return wrapper

    def tearDown(self):
        self.expanduser_patcher.stop()
        os.environ.clear()
        os.environ.update(self.orig_env)
        shutil.rmtree(self.temp_dir, ignore_errors=True)


class TestAgyMcpConfig(BaseAgyMcpConfigTest):

    def test_add_through_agy(self):
        os.environ["MAESTRO_AGY"] = self.fake_agy_bin
        os.environ["FAKE_AGY_LOG"] = self.fake_log_file

        buf = io.StringIO()
        with redirect_stdout(buf):
            agy_mcp_config.main("add")
        out = buf.getvalue()

        self.assertTrue(os.path.exists(self.fake_log_file), "Fake agy was not invoked")
        with open(self.fake_log_file, "r", encoding="utf-8") as f:
            args = json.load(f)

        expected_args = [
            "mcp", "add", "maestro", "--",
            sys.executable, "-I", agy_mcp_config.SERVER
        ]
        self.assertEqual(args, expected_args)
        self.assertIn("registered 'maestro' through agy", out)

    def test_remove_through_agy_and_legacy_cleanup(self):
        os.environ["MAESTRO_AGY"] = self.fake_agy_bin
        os.environ["FAKE_AGY_LOG"] = self.fake_log_file

        legacy_file = os.path.join(self.temp_home, ".gemini", "antigravity", "mcp_config.json")
        os.makedirs(os.path.dirname(legacy_file), exist_ok=True)
        initial_data = {
            "mcpServers": {
                "maestro": {"command": sys.executable, "args": ["-I", "dummy.py"]},
                "other": {"command": "node", "args": ["server.js"]}
            }
        }
        with open(legacy_file, "w", encoding="utf-8") as f:
            json.dump(initial_data, f)

        buf = io.StringIO()
        with redirect_stdout(buf):
            agy_mcp_config.main("remove")
        out = buf.getvalue()

        self.assertTrue(os.path.exists(self.fake_log_file), "Fake agy was not invoked")
        with open(self.fake_log_file, "r", encoding="utf-8") as f:
            args = json.load(f)

        self.assertEqual(args, ["mcp", "remove", "maestro"])
        self.assertIn("removed 'maestro' through agy", out)

        # Legacy file checks
        self.assertTrue(os.path.exists(legacy_file))
        with open(legacy_file, "r", encoding="utf-8") as f:
            updated_data = json.load(f)
        self.assertNotIn("maestro", updated_data["mcpServers"])
        self.assertIn("other", updated_data["mcpServers"])

        backup_file = legacy_file + ".maestro-backup"
        self.assertTrue(os.path.exists(backup_file), "Backup file was not created")
        with open(backup_file, "r", encoding="utf-8") as f:
            backup_data = json.load(f)
        self.assertIn("maestro", backup_data["mcpServers"])
        self.assertIn(f"removed 'maestro' from {legacy_file}", out)

    def test_fallback_when_agy_missing(self):
        # Ensure all 5 agy candidate searches fail
        os.environ.pop("MAESTRO_AGY", None)
        os.environ["LOCALAPPDATA"] = self.temp_localappdata

        with patch("shutil.which", return_value=None):
            buf = io.StringIO()
            with redirect_stdout(buf):
                agy_mcp_config.main("add")
            out = buf.getvalue()

        self.assertFalse(os.path.exists(self.fake_log_file))
        self.assertIn("falling back to direct configuration file editing", out)
        self.assertIn("not found", out.lower())

        target_file = agy_mcp_config.targets()[0]
        self.assertTrue(os.path.exists(target_file))
        with open(target_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertIn("maestro", data["mcpServers"])

    def test_fallback_when_agy_exits_nonzero(self):
        os.environ["MAESTRO_AGY"] = self.fake_agy_bin
        os.environ["FAKE_AGY_LOG"] = self.fake_log_file
        os.environ["FAKE_AGY_EXIT_CODE"] = "2"

        buf = io.StringIO()
        with redirect_stdout(buf):
            agy_mcp_config.main("add")
        out = buf.getvalue()

        self.assertTrue(os.path.exists(self.fake_log_file))
        self.assertIn("falling back to direct configuration file editing", out)
        self.assertIn("2", out)

        target_file = agy_mcp_config.targets()[0]
        self.assertTrue(os.path.exists(target_file))
        with open(target_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertIn("maestro", data["mcpServers"])

    def test_fallback_when_agy_times_out(self):
        os.environ["MAESTRO_AGY"] = self.fake_agy_bin
        os.environ["FAKE_AGY_LOG"] = self.fake_log_file
        os.environ["FAKE_AGY_SLEEP"] = "1.0"
        os.environ["MAESTRO_AGY_TIMEOUT"] = "0.2"

        buf = io.StringIO()
        with redirect_stdout(buf):
            agy_mcp_config.main("add")
        out = buf.getvalue()

        self.assertTrue(os.path.exists(self.fake_log_file))
        self.assertIn("falling back to direct configuration file editing", out)
        self.assertIn("timed out", out.lower())

        target_file = agy_mcp_config.targets()[0]
        self.assertTrue(os.path.exists(target_file))
        with open(target_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertIn("maestro", data["mcpServers"])

    def test_maestro_agy_mcp_config_forces_file_mode(self):
        os.environ["MAESTRO_AGY"] = self.fake_agy_bin
        os.environ["FAKE_AGY_LOG"] = self.fake_log_file
        custom_file = os.path.join(self.temp_dir, "custom_mcp.json")
        os.environ["MAESTRO_AGY_MCP_CONFIG"] = custom_file

        buf = io.StringIO()
        with redirect_stdout(buf):
            agy_mcp_config.main("add")
        out = buf.getvalue()

        self.assertFalse(os.path.exists(self.fake_log_file), "Fake agy should not be called in file mode")
        self.assertNotIn("falling back", out)
        self.assertTrue(os.path.exists(custom_file))
        with open(custom_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertIn("maestro", data["mcpServers"])

    def test_find_agy_precedence(self):
        # 1. MAESTRO_AGY_MCP_CONFIG set -> None
        os.environ["MAESTRO_AGY_MCP_CONFIG"] = "some_path"
        os.environ["MAESTRO_AGY"] = "override_agy"
        self.assertIsNone(agy_mcp_config.find_agy())
        os.environ.pop("MAESTRO_AGY_MCP_CONFIG", None)

        # 2. MAESTRO_AGY wins
        self.assertEqual(agy_mcp_config.find_agy(), "override_agy")
        os.environ.pop("MAESTRO_AGY", None)

        # 3. shutil.which wins
        with patch("shutil.which", return_value="/mock/which/agy"):
            self.assertEqual(agy_mcp_config.find_agy(), "/mock/which/agy")

        # 4. %LOCALAPPDATA%\agy\bin\agy.exe
        fake_local_agy = os.path.join(self.temp_localappdata, "agy", "bin", "agy.exe")
        os.makedirs(os.path.dirname(fake_local_agy), exist_ok=True)
        with open(fake_local_agy, "w") as f:
            f.write("")
        with patch("shutil.which", return_value=None):
            self.assertEqual(agy_mcp_config.find_agy(), fake_local_agy)

        # 5. ~/.local/bin/agy
        os.remove(fake_local_agy)
        fake_unix_agy = os.path.join(self.temp_home, ".local", "bin", "agy")
        os.makedirs(os.path.dirname(fake_unix_agy), exist_ok=True)
        with open(fake_unix_agy, "w") as f:
            f.write("")
        with patch("shutil.which", return_value=None):
            self.assertEqual(agy_mcp_config.find_agy(), fake_unix_agy)

        # 6. Nothing found -> None
        os.remove(fake_unix_agy)
        with patch("shutil.which", return_value=None):
            self.assertIsNone(agy_mcp_config.find_agy())

    def test_never_touches_real_home(self):
        # Safety-net test: audit every write operation
        written_paths = []
        orig_save = agy_mcp_config.save

        def guarded_save(path, cfg):
            written_paths.append(os.path.abspath(path))
            return orig_save(path, cfg)

        with patch.object(agy_mcp_config, "save", side_effect=guarded_save):
            # Test path A: agy success
            os.environ["MAESTRO_AGY"] = self.fake_agy_bin
            buf = io.StringIO()
            with redirect_stdout(buf):
                agy_mcp_config.main("add")
                agy_mcp_config.main("remove")

            # Test path B: agy non-zero exit fallback
            os.environ["FAKE_AGY_EXIT_CODE"] = "1"
            with redirect_stdout(buf):
                agy_mcp_config.main("add")
            os.environ.pop("FAKE_AGY_EXIT_CODE", None)

            # Test path C: agy missing fallback
            os.environ.pop("MAESTRO_AGY", None)
            with patch("shutil.which", return_value=None):
                with redirect_stdout(buf):
                    agy_mcp_config.main("add")

            # Test path D: agy timeout fallback
            os.environ["MAESTRO_AGY"] = self.fake_agy_bin
            os.environ["FAKE_AGY_SLEEP"] = "1.0"
            os.environ["MAESTRO_AGY_TIMEOUT"] = "0.2"
            with redirect_stdout(buf):
                agy_mcp_config.main("add")

        # Verify that no path written to touches the real home or .gemini
        for p in written_paths:
            self.assertTrue(
                os.path.realpath(p).startswith(os.path.realpath(self.temp_dir)),
                f"Dangerous write outside temp dir: {p}"
            )
            self.assertFalse(
                os.path.realpath(p).startswith(os.path.realpath(self.real_gemini)),
                f"Dangerous write to real .gemini: {p}"
            )
            self.assertFalse(
                os.path.realpath(p).startswith(os.path.realpath(REAL_USER_GEMINI)),
                f"Dangerous write to real host .gemini: {p}"
            )

    def test_import_time_paths_cannot_escape(self):
        # Stop the per-test expanduser mock to simulate what happens during raw module import
        self.expanduser_patcher.stop()
        try:
            # Read real agy_mcp_config.py source code
            with open(agy_mcp_config.__file__, "r", encoding="utf-8") as f:
                source = f.read()

            # Replace gemini_dir with an import-time constant (simulating the mutant / original bug)
            mutant_src = source.replace(
                'def gemini_dir():\n    return os.path.join(os.path.expanduser("~"), ".gemini")',
                '_STATIC_GEMINI = os.path.join(os.path.expanduser("~"), ".gemini")\n\n'
                'def gemini_dir():\n    return _STATIC_GEMINI'
            )
            self.assertIn("_STATIC_GEMINI", mutant_src)

            mutant_file = os.path.join(SESSION_TEMP, "mutant_agy_mcp_config.py")
            with open(mutant_file, "w", encoding="utf-8") as f:
                f.write(mutant_src)

            spec = importlib.util.spec_from_file_location("mutant_agy_mcp_config", mutant_file)
            mutant = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mutant)

            # Ensure file mode with no override
            os.environ.pop("MAESTRO_AGY", None)
            os.environ.pop("MAESTRO_AGY_MCP_CONFIG", None)

            buf = io.StringIO()
            with redirect_stdout(buf):
                mutant.main("add")
            out = buf.getvalue()

            targets = mutant.targets()
            self.assertTrue(len(targets) > 0)
            target = targets[0]
            self.assertTrue(os.path.exists(target))

            target_abs = os.path.realpath(target)
            session_abs = os.path.realpath(SESSION_TEMP)
            self.assertTrue(
                target_abs.startswith(session_abs + os.sep) or target_abs == session_abs,
                f"Target path {target_abs} escaped session temp {session_abs}"
            )
            self.assertFalse(
                target_abs.startswith(os.path.realpath(REAL_USER_GEMINI)),
                f"Target path {target_abs} touched real host .gemini directory"
            )
        finally:
            self.expanduser_patcher.start()

    def test_invalid_timeout_falls_back_to_default(self):
        os.environ["MAESTRO_AGY"] = self.fake_agy_bin
        os.environ["FAKE_AGY_LOG"] = self.fake_log_file

        # Non-numeric string
        os.environ["MAESTRO_AGY_TIMEOUT"] = "not-a-number"
        buf = io.StringIO()
        with redirect_stdout(buf):
            agy_mcp_config.main("add")
        out = buf.getvalue()

        self.assertTrue(os.path.exists(self.fake_log_file), "Fake agy should be invoked")
        self.assertIn("invalid MAESTRO_AGY_TIMEOUT 'not-a-number'; falling back to 60s", out)
        self.assertIn("registered 'maestro' through agy", out)

        # Non-positive or non-finite values ("-5", "0", "nan", "inf")
        for bad_val in ("-5", "0", "nan", "inf"):
            if os.path.exists(self.fake_log_file):
                os.remove(self.fake_log_file)
            os.environ["MAESTRO_AGY_TIMEOUT"] = bad_val
            buf = io.StringIO()
            with redirect_stdout(buf):
                agy_mcp_config.main("add")
            out = buf.getvalue()

            self.assertTrue(os.path.exists(self.fake_log_file), f"Fake agy should be invoked for {bad_val}")
            self.assertIn(f"invalid MAESTRO_AGY_TIMEOUT '{bad_val}'; falling back to 60s", out)
            self.assertIn("registered 'maestro' through agy", out)


if __name__ == "__main__":
    unittest.main()
