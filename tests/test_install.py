"""Unit tests for Maestro installer prerequisites and configuration (install.py).

Verifies the minimum required Python version constant and prerequisite check
under process-level home isolation.
"""
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Process-Level Isolation
# ---------------------------------------------------------------------------
REAL_USER_HOME = os.path.expanduser("~")
SESSION_TEMP = tempfile.mkdtemp(prefix="maestro_install_session_")
SESSION_HOME = os.path.join(SESSION_TEMP, "home")
SESSION_LOCALAPPDATA = os.path.join(SESSION_TEMP, "localappdata")
SESSION_HELDOUT = os.path.join(SESSION_TEMP, "heldout")
SESSION_MCP_LOG = os.path.join(SESSION_TEMP, "mcp.log")
os.makedirs(SESSION_HOME, exist_ok=True)
os.makedirs(SESSION_LOCALAPPDATA, exist_ok=True)
os.makedirs(SESSION_HELDOUT, exist_ok=True)

os.environ["HOME"] = SESSION_HOME
os.environ["USERPROFILE"] = SESSION_HOME
os.environ["LOCALAPPDATA"] = SESSION_LOCALAPPDATA
os.environ["MAESTRO_HELDOUT_HOME"] = SESSION_HELDOUT
os.environ["MAESTRO_MCP_LOG"] = SESSION_MCP_LOG

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

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import install


class TestInstall(unittest.TestCase):

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(SESSION_TEMP, ignore_errors=True)

    def test_min_python_constant(self):
        """MIN_PYTHON must be defined as (3, 10)."""
        self.assertTrue(hasattr(install, "MIN_PYTHON"), "install.py must define MIN_PYTHON")
        self.assertEqual(install.MIN_PYTHON, (3, 10))

    def test_check_prerequisites_fails_below_3_10(self):
        """Python versions below (3, 10) must report 'Python 3.10 or newer'."""
        with patch.object(install.sys, "version_info", (3, 9, 0, "final", 0)):
            missing = install.check_prerequisites()
            self.assertIsNotNone(missing, "check_prerequisites should return the missing prerequisites list")
            self.assertIn("Python 3.10 or newer", missing)

    def test_check_prerequisites_passes_3_10_and_above(self):
        """Python versions at or above (3, 10) must not report Python as missing."""
        with patch.object(install.sys, "version_info", (3, 10, 0, "final", 0)):
            missing = install.check_prerequisites()
            self.assertIsNotNone(missing, "check_prerequisites should return the missing prerequisites list")
            self.assertNotIn("Python 3.10 or newer", missing)
            self.assertFalse(any("Python" in m for m in missing))


if __name__ == "__main__":
    unittest.main()
