"""Unit and functional tests for the Maestro MCP Server (maestro_mcp.py).

Tests initialize, tools/list, active-task guard conditions, ask-wait-answer flow,
checkpoint verification, concurrency (ping while call blocks), unknown methods,
and UTF-8 BOM handling.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta

# ---------------------------------------------------------------------------
# Process-Level Isolation
# ---------------------------------------------------------------------------
REAL_USER_HOME = os.path.expanduser("~")
SESSION_TEMP = tempfile.mkdtemp(prefix="maestro_mcp_session_")
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

import version


class McpSession:
    """Helper wrapping a live maestro_mcp.py process communicating over stdio."""

    def __init__(self, mcp_py=None):
        if mcp_py is None:
            mcp_py = os.path.join(SCRIPTS_DIR, "maestro_mcp.py")
        self.proc = subprocess.Popen(
            [sys.executable, "-I", mcp_py],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            env=dict(os.environ),
        )
        self.responses = {}
        self.lock = threading.Lock()
        self.thread = threading.Thread(target=self._reader, daemon=True)
        self.thread.start()

    def _reader(self):
        for line in self.proc.stdout:
            try:
                line_str = line.strip()
                if not line_str:
                    continue
                m = json.loads(line_str)
                with self.lock:
                    if "id" in m:
                        self.responses[m["id"]] = m
            except Exception:
                pass

    def send(self, mid, method, params=None):
        msg = {"jsonrpc": "2.0", "method": method}
        if mid is not None:
            msg["id"] = mid
        if params is not None:
            msg["params"] = params
        self.proc.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()

    def send_raw(self, raw_str):
        self.proc.stdin.write(raw_str)
        self.proc.stdin.flush()

    def get(self, mid, timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self.lock:
                if mid in self.responses:
                    return self.responses[mid]
            time.sleep(0.03)
        return None

    def call_tool(self, mid, name, args, timeout=10):
        self.send(mid, "tools/call", {"name": name, "arguments": args})
        return self.get(mid, timeout=timeout)

    def close(self):
        try:
            if self.proc.stdin and not self.proc.stdin.closed:
                self.proc.stdin.close()
            if self.proc.stdout and not self.proc.stdout.closed:
                self.proc.stdout.close()
            self.proc.wait(timeout=3)
        except Exception:
            self.proc.kill()


class TestMcpServer(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="mcp_test_", dir=SESSION_TEMP)
        self.proj = os.path.join(self.test_dir, "proj")
        os.makedirs(self.proj, exist_ok=True)
        self.maestro_py = os.path.join(SCRIPTS_DIR, "maestro.py")

        # Initialize the project structure
        res = subprocess.run(
            [sys.executable, self.maestro_py, "init", self.proj],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=dict(os.environ),
        )
        self.assertEqual(res.returncode, 0)
        self.dot = os.path.join(self.proj, ".maestro")
        self.active_file = os.path.join(self.dot, "active.json")

        # Start standard MCP session
        self.srv = McpSession()
        self.srv.send(
            1,
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-client"},
            },
        )
        r = self.srv.get(1, timeout=5)
        self.assertIsNotNone(r, "Server failed to respond to initialize")
        self.srv.send(None, "notifications/initialized")

    def tearDown(self):
        self.srv.close()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def set_active(self, task_id="001", age_hours=0):
        sent_at = (datetime.now() - timedelta(hours=age_hours)).isoformat(timespec="seconds")
        with open(self.active_file, "w", encoding="utf-8") as f:
            json.dump({"task": task_id, "sent_at": sent_at}, f)

    def text_and_error(self, response):
        self.assertIsNotNone(response, "Response was None")
        res = response.get("result", {})
        content = res.get("content", [{}])
        text = content[0].get("text", "") if content else ""
        return text, res.get("isError", False)

    # -----------------------------------------------------------------------
    # Protocol & Basics
    # -----------------------------------------------------------------------

    def test_initialize(self):
        s = McpSession()
        try:
            s.send(
                10,
                "initialize",
                {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "unit-test"},
                },
            )
            r = s.get(10, timeout=5)
            self.assertIsNotNone(r)
            res = r["result"]
            self.assertEqual(res["protocolVersion"], "2025-03-26")
            self.assertEqual(res["serverInfo"]["name"], "maestro")
            self.assertEqual(res["serverInfo"]["version"], version.__version__)
            self.assertEqual(res["serverInfo"]["version"], "0.6.0")
        finally:
            s.close()

    def test_tools_list(self):
        self.srv.send(2, "tools/list")
        r = self.srv.get(2, timeout=5)
        self.assertIsNotNone(r)
        tool_names = [t["name"] for t in r["result"]["tools"]]
        self.assertEqual(len(tool_names), 4)
        self.assertIn("maestro_ask", tool_names)
        self.assertIn("maestro_check_answer", tool_names)
        self.assertIn("maestro_progress", tool_names)
        self.assertIn("maestro_checkpoint", tool_names)

    def test_unknown_method(self):
        self.srv.send(99, "bogus/method")
        r = self.srv.get(99, timeout=5)
        self.assertIsNotNone(r)
        self.assertIn("error", r)
        self.assertEqual(r["error"]["code"], -32601)

    def test_bom_on_input(self):
        # Prepend UTF-8 BOM character (\ufeff)
        bom_msg = '\ufeff{"jsonrpc": "2.0", "id": 77, "method": "ping"}\n'
        self.srv.send_raw(bom_msg)
        r = self.srv.get(77, timeout=5)
        self.assertIsNotNone(r)
        self.assertEqual(r.get("result"), {})

    def test_bad_project_path(self):
        r = self.srv.call_tool(
            15,
            "maestro_ask",
            {"project": os.path.join(self.test_dir, "nonexistent"), "task_id": "001", "question": "q?"},
        )
        text, is_err = self.text_and_error(r)
        self.assertTrue(is_err)
        self.assertIn("does not exist", text)

    # -----------------------------------------------------------------------
    # Active-Task Guard
    # -----------------------------------------------------------------------

    def test_guard_no_active_marker_refuses_immediately(self):
        if os.path.exists(self.active_file):
            os.remove(self.active_file)
        t0 = time.time()
        r = self.srv.call_tool(
            20,
            "maestro_ask",
            {"project": self.proj, "task_id": "001", "question": "q?", "wait_seconds": 60},
            timeout=5,
        )
        elapsed = time.time() - t0
        text, is_err = self.text_and_error(r)
        self.assertTrue(is_err)
        self.assertIn("No Maestro task is active", text)
        self.assertLess(elapsed, 3.0, f"No-marker refusal took {elapsed}s, expected < 3s")

    def test_guard_wrong_task_id(self):
        self.set_active("001")
        r = self.srv.call_tool(
            21,
            "maestro_ask",
            {"project": self.proj, "task_id": "002", "question": "q?"},
        )
        text, is_err = self.text_and_error(r)
        self.assertTrue(is_err)
        self.assertIn("active Maestro task is 001", text)

    def test_guard_active_right_task_accepted(self):
        self.set_active("001")
        r = self.srv.call_tool(
            22,
            "maestro_ask",
            {"project": self.proj, "task_id": "001", "question": "q?", "wait_seconds": 0},
        )
        text, is_err = self.text_and_error(r)
        self.assertFalse(is_err)
        self.assertIn("No answer yet", text)

    def test_guard_progress_while_active(self):
        self.set_active("001")
        r = self.srv.call_tool(
            23,
            "maestro_progress",
            {"project": self.proj, "task_id": "001", "message": "starting tests"},
        )
        text, is_err = self.text_and_error(r)
        self.assertFalse(is_err)
        self.assertEqual(text, "logged")

        prog_file = os.path.join(self.dot, "progress", "task-001.log")
        self.assertTrue(os.path.exists(prog_file))
        with open(prog_file, "r", encoding="utf-8") as f:
            self.assertIn("starting tests", f.read())

    def test_guard_stale_marker(self):
        self.set_active("001", age_hours=13)
        r = self.srv.call_tool(
            24,
            "maestro_ask",
            {"project": self.proj, "task_id": "001", "question": "q?"},
        )
        text, is_err = self.text_and_error(r)
        self.assertTrue(is_err)
        self.assertIn("stale", text)

    def test_guard_report_exists(self):
        self.set_active("001")
        rep_dir = os.path.join(self.dot, "reports")
        os.makedirs(rep_dir, exist_ok=True)
        with open(os.path.join(rep_dir, "task-001.done.md"), "w", encoding="utf-8") as f:
            f.write("# Done")

        r = self.srv.call_tool(
            25,
            "maestro_ask",
            {"project": self.proj, "task_id": "001", "question": "q?"},
        )
        text, is_err = self.text_and_error(r)
        self.assertTrue(is_err)
        self.assertIn("already reported", text)

    def test_guard_read_answered_when_inactive(self):
        if os.path.exists(self.active_file):
            os.remove(self.active_file)
        qdir = os.path.join(self.dot, "questions")
        os.makedirs(qdir, exist_ok=True)
        with open(os.path.join(qdir, "task-001-q1.json"), "w", encoding="utf-8") as f:
            json.dump({"task": "001", "question": "store?"}, f)
        with open(os.path.join(qdir, "task-001-q1.answer.md"), "w", encoding="utf-8") as f:
            f.write("use sqlite")

        r = self.srv.call_tool(
            26,
            "maestro_check_answer",
            {"project": self.proj, "question_id": "task-001-q1", "wait_seconds": 0},
        )
        text, is_err = self.text_and_error(r)
        self.assertFalse(is_err)
        self.assertIn("use sqlite", text)

    def test_guard_progress_refused_when_inactive(self):
        if os.path.exists(self.active_file):
            os.remove(self.active_file)
        r = self.srv.call_tool(
            27,
            "maestro_progress",
            {"project": self.proj, "task_id": "001", "message": "fail"},
        )
        text, is_err = self.text_and_error(r)
        self.assertTrue(is_err)
        self.assertIn("No Maestro task is active", text)

    # -----------------------------------------------------------------------
    # Ask -> Wait -> Answer Flow & Checkpoints
    # -----------------------------------------------------------------------

    def test_ask_wait_answer_flow(self):
        self.set_active("001")
        # Executor asks question in background
        self.srv.send(
            30,
            "tools/call",
            {
                "name": "maestro_ask",
                "arguments": {
                    "project": self.proj,
                    "task_id": "001",
                    "question": "Use SQLite or PostgreSQL?",
                    "options": ["sqlite", "postgres"],
                    "wait_seconds": 30,
                },
            },
        )

        # Allow question file to be written
        time.sleep(0.5)

        # Reviewer runs wait
        w = subprocess.run(
            [sys.executable, self.maestro_py, "wait", self.proj, "001", "--timeout", "1"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=dict(os.environ),
        )
        self.assertEqual(w.returncode, 3)
        self.assertIn("QUESTION: task-001-q1", w.stdout)

        # Reviewer answers
        a = subprocess.run(
            [sys.executable, self.maestro_py, "answer", self.proj, "task-001-q1", "استخدم sqlite"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=dict(os.environ),
        )
        self.assertEqual(a.returncode, 0)

        # Executor receives the answer
        r = self.srv.get(30, timeout=10)
        text, is_err = self.text_and_error(r)
        self.assertFalse(is_err)
        self.assertIn("استخدم sqlite", text)

    def test_checkpoint_flow_and_stop_points(self):
        self.set_active("001")

        # Missing plan file rejected
        r = self.srv.call_tool(
            40,
            "maestro_checkpoint",
            {
                "project": self.proj,
                "task_id": "001",
                "summary": "plan check",
                "plan_path": ".maestro/plans/missing.md",
            },
        )
        text, is_err = self.text_and_error(r)
        self.assertTrue(is_err)
        self.assertIn("plan file not found", text)

        # Valid plan file + wait
        plans_dir = os.path.join(self.dot, "plans")
        os.makedirs(plans_dir, exist_ok=True)
        plan_file = os.path.join(plans_dir, "test-plan.md")
        with open(plan_file, "w", encoding="utf-8") as f:
            f.write("# Test Plan\nDetails here.")

        self.srv.send(
            41,
            "tools/call",
            {
                "name": "maestro_checkpoint",
                "arguments": {
                    "project": self.proj,
                    "task_id": "001",
                    "summary": "valid plan review",
                    "plan_path": ".maestro/plans/test-plan.md",
                    "wait_seconds": 30,
                },
            },
        )
        time.sleep(0.5)

        w = subprocess.run(
            [sys.executable, self.maestro_py, "wait", self.proj, "001", "--timeout", "1"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=dict(os.environ),
        )
        self.assertEqual(w.returncode, 3)
        self.assertIn("CHECKPOINT: plan", w.stdout)
        qid = w.stdout.split("QUESTION: ")[1].split()[0]

        subprocess.run(
            [sys.executable, self.maestro_py, "answer", self.proj, qid, "APPROVED with no changes"],
            check=True,
            env=dict(os.environ),
        )

        r = self.srv.get(41, timeout=10)
        text, is_err = self.text_and_error(r)
        self.assertFalse(is_err)
        self.assertIn("APPROVED", text)

        # Unanswered checkpoint returns stop-point instructions
        r_unanswered = self.srv.call_tool(
            42,
            "maestro_checkpoint",
            {
                "project": self.proj,
                "task_id": "001",
                "summary": "second checkpoint",
                "wait_seconds": 0,
            },
        )
        t42, _ = self.text_and_error(r_unanswered)
        self.assertIn("do NOT continue", t42)
        self.assertIn("Call maestro_check_answer", t42)

        # check_answer on unanswered checkpoint also repeats stop-point
        qid_unanswered = t42.split("No answer yet for ")[1].split(".")[0]
        r_check = self.srv.call_tool(
            43,
            "maestro_check_answer",
            {
                "project": self.proj,
                "question_id": qid_unanswered,
                "wait_seconds": 0,
            },
        )
        t43, _ = self.text_and_error(r_check)
        self.assertIn("do NOT continue", t43)
        self.assertNotIn("best assumption", t43)

    def test_ping_while_call_blocks(self):
        self.set_active("001")
        # Start blocking ask call
        self.srv.send(
            50,
            "tools/call",
            {
                "name": "maestro_ask",
                "arguments": {
                    "project": self.proj,
                    "task_id": "001",
                    "question": "blocking?",
                    "wait_seconds": 30,
                },
            },
        )
        time.sleep(0.3)

        # Send ping and ensure response arrives promptly
        t0 = time.time()
        self.srv.send(51, "ping")
        r_ping = self.srv.get(51, timeout=3)
        elapsed = time.time() - t0

        self.assertIsNotNone(r_ping, "Server did not answer ping while call blocked")
        self.assertEqual(r_ping.get("result"), {})
        self.assertLess(elapsed, 2.0, f"Ping took {elapsed}s to return")

        # ask is still waiting
        self.assertNotIn(50, self.srv.responses)

    def test_mcp_log_path_overridable(self):
        """MCP server must write to MAESTRO_MCP_LOG when set without touching real logs/mcp.log."""
        tool_root = os.path.abspath(os.path.join(SCRIPTS_DIR, ".."))
        real_log = os.path.join(tool_root, "logs", "mcp.log")
        stat_before = (os.path.getsize(real_log), os.path.getmtime(real_log)) if os.path.exists(real_log) else None

        custom_log_dir = tempfile.mkdtemp(prefix="maestro_custom_log_")
        custom_log = os.path.join(custom_log_dir, "test_override.log")
        try:
            env = dict(os.environ)
            env["MAESTRO_MCP_LOG"] = custom_log
            proc = subprocess.Popen(
                [sys.executable, "-I", os.path.join(SCRIPTS_DIR, "maestro_mcp.py")],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                env=env,
            )
            init_req = {
                "jsonrpc": "2.0",
                "id": 100,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test-override-runner"},
                },
            }
            try:
                stdout_line, _ = proc.communicate(input=json.dumps(init_req) + "\n", timeout=10)
                res = json.loads(stdout_line.strip().splitlines()[0])
                self.assertIn("result", res)
            finally:
                if proc.poll() is None:
                    proc.kill()

            self.assertTrue(os.path.exists(custom_log), "Temp log was not created at MAESTRO_MCP_LOG")
            with open(custom_log, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("recv initialize", content)
            self.assertIn("client={'name': 'test-override-runner'}", content)

            if stat_before is not None:
                stat_after = (os.path.getsize(real_log), os.path.getmtime(real_log))
                self.assertEqual(stat_before, stat_after, "Real logs/mcp.log was modified despite MAESTRO_MCP_LOG")
            else:
                self.assertFalse(os.path.exists(real_log), "Real logs/mcp.log was created despite MAESTRO_MCP_LOG")
        finally:
            shutil.rmtree(custom_log_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
