"""Unit and functional tests for the Maestro CLI.

Tests all CLI commands (init, new, tools, heldout, review, testdiff, wait,
answer, release, status, and send refusals) under strict process-level
isolation and without touching real host configuration, agy, or GUI links.
"""
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Process-Level Isolation
# ---------------------------------------------------------------------------
REAL_USER_HOME = os.path.expanduser("~")
SESSION_TEMP = tempfile.mkdtemp(prefix="maestro_cli_session_")
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

import maestro
import sender


class BaseCliTest(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="cli_test_", dir=SESSION_TEMP)
        self.maestro_py = os.path.join(SCRIPTS_DIR, "maestro.py")

        # Delivery safety net: never allow delivery calls in tests
        self.patch_send_prompt = patch.object(
            sender, "send_prompt", side_effect=AssertionError("delivery must not run in tests")
        )
        self.patch_open_url = patch.object(
            sender, "open_url", side_effect=AssertionError("delivery must not run in tests")
        )
        self.patch_send_prompt.start()
        self.patch_open_url.start()

    def tearDown(self):
        self.patch_open_url.stop()
        self.patch_send_prompt.stop()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def run_cli(self, *args):
        """Run maestro CLI via subprocess in isolated environment."""
        res = subprocess.run(
            [sys.executable, self.maestro_py] + [str(a) for a in args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=dict(os.environ),
        )
        return res.returncode, res.stdout, res.stderr

    def run_in_process(self, *args):
        """Run maestro.main in-process with output captured."""
        buf_out, buf_err = io.StringIO(), io.StringIO()
        with redirect_stdout(buf_out), redirect_stderr(buf_err):
            try:
                code = maestro.main(list(args))
            except SystemExit as e:
                code = e.code
        return code, buf_out.getvalue(), buf_err.getvalue()

    def git_init_repo(self, path):
        """Initialize a local git repo with user.name and user.email configured."""
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=path, check=True)
        subprocess.run(["git", "config", "user.name", "Tester"], cwd=path, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
        subprocess.run(["git", "config", "core.autocrlf", "false"], cwd=path, check=True)


class TestCliSenderAndOptions(BaseCliTest):

    def test_sender_build_url(self):
        # Pure function test: prompt quoting, project quoting, and omitting &project= when None
        url_simple = sender.build_url("hello world")
        self.assertEqual(url_simple, "antigravity://open?prompt=hello%20world")
        self.assertNotIn("project", url_simple)

        url_proj = sender.build_url("read & test", project_id="proj/alpha beta")
        self.assertEqual(
            url_proj,
            "antigravity://open?prompt=read%20%26%20test&project=proj%2Falpha%20beta",
        )

    def test_send_help_no_via(self):
        code, out, _ = self.run_cli("send", "--help")
        self.assertEqual(code, 0)
        self.assertIn("--no-enter", out)
        self.assertNotIn("--via", out)

    def test_send_rejects_via_flag(self):
        proj = os.path.join(self.test_dir, "proj")
        os.makedirs(proj, exist_ok=True)
        self.run_cli("init", proj)
        self.run_cli("new", proj, "task 1")

        code, out, err = self.run_cli("send", proj, "1", "--via", "headless")
        self.assertEqual(code, 2)
        self.assertIn("unrecognized arguments", out + err)

    def test_send_refusal_missing_task(self):
        proj = os.path.join(self.test_dir, "proj")
        os.makedirs(proj, exist_ok=True)
        self.run_cli("init", proj)

        code, out, err = self.run_cli("send", proj, "999")
        self.assertEqual(code, 1)
        self.assertIn("missing", out + err)

    def test_send_refusal_already_reported(self):
        proj = os.path.join(self.test_dir, "proj")
        os.makedirs(proj, exist_ok=True)
        self.run_cli("init", proj)
        self.run_cli("new", proj, "task 1")
        report = os.path.join(proj, ".maestro", "reports", "task-001.done.md")
        with open(report, "w", encoding="utf-8") as f:
            f.write("# Report done")

        code, out, err = self.run_cli("send", proj, "1")
        self.assertEqual(code, 1)
        self.assertIn("already has a report", out + err)

    def test_send_refusal_active_in_flight(self):
        proj = os.path.join(self.test_dir, "proj")
        os.makedirs(proj, exist_ok=True)
        self.run_cli("init", proj)
        self.run_cli("new", proj, "task 1")
        self.run_cli("new", proj, "task 2")
        active = os.path.join(proj, ".maestro", "active.json")
        with open(active, "w", encoding="utf-8") as f:
            json.dump({"task": "001", "sent_at": "2026-11-06T10:00:00"}, f)

        code, out, err = self.run_cli("send", proj, "002")
        self.assertEqual(code, 1)
        self.assertIn("still in flight", out + err)

    def test_send_refuses_unknown_project(self):
        proj = os.path.join(self.test_dir, "proj")
        os.makedirs(proj, exist_ok=True)
        self.run_cli("init", proj)
        self.run_cli("new", proj, "task 1")

        code, out, err = self.run_cli("send", proj, "1")
        self.assertEqual(code, 1)
        combined = out + err
        self.assertIn("error: Antigravity does not know", combined)
        self.assertIn("--allow-current-project", combined)
        active = os.path.join(proj, ".maestro", "active.json")
        self.assertFalse(os.path.exists(active))

        # Also verify in-process: delivery safety net (which raises) must not be hit
        code_in, out_in, err_in = self.run_in_process("send", proj, "1")
        self.assertEqual(code_in, 1)
        self.assertIn("error: Antigravity does not know", out_in + err_in)
        self.assertFalse(os.path.exists(active))

    def test_send_allow_current_project_attempts_delivery(self):
        proj = os.path.join(self.test_dir, "proj")
        os.makedirs(proj, exist_ok=True)
        self.run_cli("init", proj)
        self.run_cli("new", proj, "task 1")

        calls = []

        def fake_send(prompt, project_id, press_enter=True):
            calls.append((prompt, project_id, press_enter))
            return ("sent", "")

        with patch.object(sender, "send_prompt", side_effect=fake_send):
            code, out, err = self.run_in_process("send", proj, "1", "--allow-current-project")

        self.assertEqual(code, 0)
        self.assertIn("WARN: no Antigravity project found", out + err)
        self.assertEqual(len(calls), 1)
        self.assertIsNone(calls[0][1])  # project_id=None
        active = os.path.join(proj, ".maestro", "active.json")
        self.assertTrue(os.path.exists(active))
        with open(active, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data.get("task"), "001")


class TestCliInit(BaseCliTest):

    def test_init_standard(self):
        proj = os.path.join(self.test_dir, "py_proj")
        os.makedirs(proj, exist_ok=True)
        with open(os.path.join(proj, "pyproject.toml"), "w", encoding="utf-8") as f:
            f.write("[project]\nname='test'\n")

        code, out, _ = self.run_cli("init", proj)
        self.assertEqual(code, 0)
        self.assertIn("NOTE: Antigravity does not know this folder yet", out)
        self.assertIn("'maestro send' will refuse until the id is found", out)

        cfg_path = os.path.join(proj, ".maestro", "config.json")
        self.assertTrue(os.path.exists(cfg_path))
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        self.assertEqual(cfg.get("methodology"), "standard")
        self.assertEqual(cfg.get("stack"), "python")
        self.assertNotIn("delivery", cfg)

        # Standard state files at root
        for name in ("feature_list.json", "progress.md", "session-handoff.md"):
            self.assertTrue(os.path.exists(os.path.join(proj, name)), f"Missing {name}")

        # ROLES and EXECUTOR_RULES copied
        roles = os.path.join(proj, ".maestro", "ROLES.md")
        rules = os.path.join(proj, ".maestro", "EXECUTOR_RULES.md")
        self.assertTrue(os.path.exists(roles))
        self.assertTrue(os.path.exists(rules))
        with open(rules, "r", encoding="utf-8") as f:
            rules_content = f.read()
        self.assertIn("standard methodology", rules_content)

    def test_init_uem(self):
        proj = os.path.join(self.test_dir, "uem_proj")
        os.makedirs(proj, exist_ok=True)
        code, out, _ = self.run_cli("init", proj, "--methodology", "uem")
        self.assertEqual(code, 0)

        rules = os.path.join(proj, ".maestro", "EXECUTOR_RULES.md")
        with open(rules, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("Unified Engineering", content)

    def test_init_custom(self):
        proj = os.path.join(self.test_dir, "custom_proj")
        os.makedirs(proj, exist_ok=True)
        code, out, _ = self.run_cli("init", proj, "--methodology", "custom")
        self.assertEqual(code, 0)

        rules = os.path.join(proj, ".maestro", "EXECUTOR_RULES.md")
        with open(rules, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("custom methodology", content)

    def test_init_reinit_preserves_methodology(self):
        proj = os.path.join(self.test_dir, "proj")
        os.makedirs(proj, exist_ok=True)
        self.run_cli("init", proj, "--methodology", "uem")
        self.run_cli("init", proj)

        cfg_path = os.path.join(proj, ".maestro", "config.json")
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        self.assertEqual(cfg.get("methodology"), "uem")

    def test_init_rejects_delivery_flag(self):
        proj = os.path.join(self.test_dir, "proj")
        os.makedirs(proj, exist_ok=True)
        code, out, err = self.run_cli("init", proj, "--delivery", "headless")
        self.assertEqual(code, 2)
        self.assertIn("unrecognized arguments", out + err)


class TestCliNewStatusRelease(BaseCliTest):

    def test_new_and_status_and_release(self):
        proj = os.path.join(self.test_dir, "proj")
        os.makedirs(proj, exist_ok=True)
        self.run_cli("init", proj)

        # new
        code, out, _ = self.run_cli("new", proj, "Add math ops", "--feature", "math-ops")
        self.assertEqual(code, 0)
        task_path = out.strip().splitlines()[-1]
        self.assertTrue(os.path.exists(task_path))
        with open(task_path, "r", encoding="utf-8") as f:
            brief = f.read()
        self.assertIn("`math-ops`", brief)
        self.assertIn("`standard`", brief)

        # status before active
        code, out, _ = self.run_cli("status", proj)
        self.assertEqual(code, 0)
        lines = out.strip().splitlines()
        self.assertEqual(lines[-1], "active: none")
        self.assertFalse(any(l.startswith("delivery") for l in lines))

        # set active
        active_file = os.path.join(proj, ".maestro", "active.json")
        with open(active_file, "w", encoding="utf-8") as f:
            json.dump({"task": "001", "sent_at": "2026-11-06T12:00:00"}, f)

        # status with active
        code, out, _ = self.run_cli("status", proj)
        lines = out.strip().splitlines()
        self.assertEqual(lines[-1], "active: task-001")

        # release
        code, out, _ = self.run_cli("release", proj)
        self.assertEqual(code, 0)
        self.assertFalse(os.path.exists(active_file))
        self.assertIn("released active task", out)

        # release when already none
        code, out, _ = self.run_cli("release", proj)
        self.assertEqual(code, 0)
        self.assertIn("no active task", out)


class TestCliAnswer(BaseCliTest):

    def setUp(self):
        super().setUp()
        self.proj = os.path.join(self.test_dir, "proj")
        os.makedirs(self.proj, exist_ok=True)
        self.run_cli("init", self.proj)
        self.qdir = os.path.join(self.proj, ".maestro", "questions")
        os.makedirs(self.qdir, exist_ok=True)

    def test_answer_inline_text(self):
        qfile = os.path.join(self.qdir, "task-001-q1.json")
        with open(qfile, "w", encoding="utf-8") as f:
            json.dump({"task": "001", "question": "Use sqlite?"}, f)

        code, out, _ = self.run_cli("answer", self.proj, "task-001-q1", "yes sqlite")
        self.assertEqual(code, 0)
        ans_file = os.path.join(self.qdir, "task-001-q1.answer.md")
        self.assertTrue(os.path.exists(ans_file))
        with open(ans_file, "r", encoding="utf-8") as f:
            self.assertEqual(f.read().strip(), "yes sqlite")

    def test_answer_file_multiline_arabic(self):
        qfile = os.path.join(self.qdir, "task-001-q2.json")
        with open(qfile, "w", encoding="utf-8") as f:
            json.dump({"task": "001", "question": "كيفية التخزين؟"}, f)

        arabic_text = "استخدم sqlite لتخزين البيانات\nسطر ثانٍ بالعربية للتأكيد"
        ans_src = os.path.join(self.test_dir, "arabic_ans.txt")
        with open(ans_src, "w", encoding="utf-8") as f:
            f.write(arabic_text)

        code, out, _ = self.run_cli("answer", self.proj, "task-001-q2", "--file", ans_src)
        self.assertEqual(code, 0)
        ans_file = os.path.join(self.qdir, "task-001-q2.answer.md")
        self.assertTrue(os.path.exists(ans_file))
        with open(ans_file, "r", encoding="utf-8") as f:
            self.assertEqual(f.read().strip(), arabic_text.strip())

    def test_answer_stdin(self):
        qfile = os.path.join(self.qdir, "task-001-q3.json")
        with open(qfile, "w", encoding="utf-8") as f:
            json.dump({"task": "001", "question": "stdin test?"}, f)

        res = subprocess.run(
            [sys.executable, self.maestro_py, "answer", self.proj, "task-001-q3", "--file", "-"],
            input="answer via stdin stream\nsecond line",
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=dict(os.environ),
        )
        self.assertEqual(res.returncode, 0)
        ans_file = os.path.join(self.qdir, "task-001-q3.answer.md")
        with open(ans_file, "r", encoding="utf-8") as f:
            self.assertEqual(f.read().strip(), "answer via stdin stream\nsecond line")

    def test_answer_errors(self):
        # unknown question
        code, out, err = self.run_cli("answer", self.proj, "task-001-q9", "text")
        self.assertEqual(code, 1)
        self.assertIn("unknown question", out + err)

        # malformed id
        code, out, err = self.run_cli("answer", self.proj, "bogus-id", "text")
        self.assertEqual(code, 1)

        # already answered
        qfile = os.path.join(self.qdir, "task-001-q1.json")
        with open(qfile, "w", encoding="utf-8") as f:
            json.dump({"task": "001", "question": "q"}, f)
        self.run_cli("answer", self.proj, "task-001-q1", "first")
        code, out, err = self.run_cli("answer", self.proj, "task-001-q1", "second")
        self.assertEqual(code, 1)
        self.assertIn("already answered", out + err)


class TestCliWait(BaseCliTest):

    def setUp(self):
        super().setUp()
        self.proj = os.path.join(self.test_dir, "proj")
        os.makedirs(self.proj, exist_ok=True)
        self.run_cli("init", self.proj)
        self.run_cli("new", self.proj, "task 1")

    def test_wait_timeout_exit_1(self):
        code, out, _ = self.run_cli("wait", self.proj, "1", "--timeout", "0")
        self.assertEqual(code, 1)
        self.assertIn("TIMEOUT", out)

    def test_wait_report_ready_exit_0(self):
        active = os.path.join(self.proj, ".maestro", "active.json")
        with open(active, "w", encoding="utf-8") as f:
            json.dump({"task": "001", "sent_at": "2026-11-06T10:00:00"}, f)

        rep = os.path.join(self.proj, ".maestro", "reports", "task-001.done.md")
        with open(rep, "w", encoding="utf-8") as f:
            f.write("# Report done")

        code, out, _ = self.run_cli("wait", self.proj, "1", "--timeout", "1")
        self.assertEqual(code, 0)
        self.assertIn("REPORT READY", out)
        self.assertFalse(os.path.exists(active), "wait did not clear active.json marker")

    def test_wait_wakes_on_question_exit_3(self):
        qdir = os.path.join(self.proj, ".maestro", "questions")
        os.makedirs(qdir, exist_ok=True)
        with open(os.path.join(qdir, "task-001-q1.json"), "w", encoding="utf-8") as f:
            json.dump({"task": "001", "question": "Need clarification?"}, f)

        code, out, _ = self.run_cli("wait", self.proj, "1", "--timeout", "1")
        self.assertEqual(code, 3)
        self.assertIn("QUESTION: task-001-q1", out)


class TestCliReview(BaseCliTest):

    def setUp(self):
        super().setUp()
        self.proj = os.path.join(self.test_dir, "proj")
        os.makedirs(self.proj, exist_ok=True)
        self.run_cli("init", self.proj)

    def test_review_rounds_and_escalate(self):
        c1, o1, _ = self.run_cli("review", self.proj, "new", "feat1", "--task", "001")
        self.assertEqual(c1, 0)
        self.assertIn("feat1-round-1.md", o1)

        c2, o2, _ = self.run_cli("review", self.proj, "new", "feat1")
        self.assertEqual(c2, 0)
        self.assertIn("feat1-round-2.md", o2)

        c3, o3, _ = self.run_cli("review", self.proj, "new", "feat1")
        self.assertEqual(c3, 4)
        self.assertIn("ESCALATE", o3)

    def test_review_verdict_refuses_non_passing(self):
        fl_path = os.path.join(self.proj, "feature_list.json")
        fl = {"features": [{"id": "feat1", "status": "active"}]}
        with open(fl_path, "w", encoding="utf-8") as f:
            json.dump(fl, f)

        code, out, err = self.run_cli("review", self.proj, "verdict", "feat1", "accepted")
        self.assertEqual(code, 1)
        self.assertIn("cannot be accepted", out + err)

    def test_review_verdict_accepted_success(self):
        # Create 2 review rounds first
        self.run_cli("review", self.proj, "new", "feat1")
        self.run_cli("review", self.proj, "new", "feat1")

        fl_path = os.path.join(self.proj, "feature_list.json")
        fl = {"features": [{"id": "feat1", "status": "passing"}]}
        with open(fl_path, "w", encoding="utf-8") as f:
            json.dump(fl, f)

        code, out, _ = self.run_cli("review", self.proj, "verdict", "feat1", "accepted")
        self.assertEqual(code, 0)
        with open(fl_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        feat = data["features"][0]
        self.assertEqual(feat.get("review"), "accepted")
        self.assertEqual(feat.get("review_rounds"), 2)


class TestCliTestDiff(BaseCliTest):

    def test_testdiff_clean_and_modified(self):
        proj = os.path.join(self.test_dir, "git_proj")
        os.makedirs(proj, exist_ok=True)
        self.git_init_repo(proj)

        tests_dir = os.path.join(proj, "tests")
        os.makedirs(tests_dir, exist_ok=True)
        test_calc = os.path.join(tests_dir, "test_calc.py")
        with open(test_calc, "w", encoding="utf-8") as f:
            f.write("def test_add():\n    assert 1 + 1 == 2\n")

        test_del = os.path.join(tests_dir, "test_del.py")
        with open(test_del, "w", encoding="utf-8") as f:
            f.write("def test_del():\n    assert True\n")

        subprocess.run(["git", "add", "-A"], cwd=proj, check=True)
        subprocess.run(["git", "commit", "-qm", "initial"], cwd=proj, check=True)

        self.run_cli("init", proj)

        # Clean diff
        code, out, _ = self.run_cli("testdiff", proj)
        self.assertEqual(code, 0)
        self.assertIn("no deleted", out)

        # Branch and weaken tests
        subprocess.run(["git", "checkout", "-qb", "feature/calc"], cwd=proj, check=True)
        with open(test_calc, "w", encoding="utf-8") as f:
            f.write("import unittest\n@unittest.skip('skip')\ndef test_add():\n    pass\n")

        os.remove(test_del)
        subprocess.run(["git", "add", "-A"], cwd=proj, check=True)
        subprocess.run(["git", "commit", "-qm", "weaken"], cwd=proj, check=True)

        code, out, _ = self.run_cli("testdiff", proj)
        self.assertEqual(code, 5)
        self.assertIn("SKIP/ONLY", out)
        self.assertIn("REMOVED assertion", out)
        self.assertIn("DELETED test file", out)


class TestCliHeldout(BaseCliTest):

    def setUp(self):
        super().setUp()
        self.proj = os.path.join(self.test_dir, "proj")
        os.makedirs(self.proj, exist_ok=True)
        self.run_cli("init", self.proj)

        # Configure heldout_cmd with stdlib unittest
        cfg_file = os.path.join(self.proj, ".maestro", "config.json")
        with open(cfg_file, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        cfg["heldout_cmd"] = f'"{sys.executable}" -m unittest discover -s {{dir}} -t .'
        with open(cfg_file, "w", encoding="utf-8") as f:
            json.dump(cfg, f)

        # Add target calc module
        with open(os.path.join(self.proj, "calc.py"), "w", encoding="utf-8") as f:
            f.write("def add(a, b):\n    return a + b\n")

    def test_heldout_add_and_run(self):
        ho_test = os.path.join(self.test_dir, "test_hidden.py")
        with open(ho_test, "w", encoding="utf-8") as f:
            f.write(
                "import unittest\nfrom calc import add\nclass T(unittest.TestCase):\n"
                "    def test_h(self):\n        self.assertEqual(add(2, 2), 4)\n"
            )

        code, out, _ = self.run_cli("heldout", self.proj, "add", "math", ho_test)
        self.assertEqual(code, 0)
        self.assertFalse(os.path.exists(os.path.join(self.proj, "test_hidden.py")))
        self.assertTrue(os.path.exists(SESSION_HELDOUT))

        # Run passes
        code, out, _ = self.run_cli("heldout", self.proj, "run", "math")
        self.assertEqual(code, 0)
        self.assertIn("HELDOUT PASS", out)
        self.assertFalse(os.path.exists(os.path.join(self.proj, "test_hidden.py")))

        # Replace with failing test
        with open(ho_test, "w", encoding="utf-8") as f:
            f.write(
                "import unittest\nfrom calc import add\nclass T(unittest.TestCase):\n"
                "    def test_h(self):\n        self.assertEqual(add(2, 2), 5)\n"
            )
        self.run_cli("heldout", self.proj, "add", "math", ho_test)
        code, out, _ = self.run_cli("heldout", self.proj, "run", "math")
        self.assertEqual(code, 1)
        self.assertIn("HELDOUT FAIL", out)

        # Refusal when active task in flight
        active = os.path.join(self.proj, ".maestro", "active.json")
        with open(active, "w", encoding="utf-8") as f:
            json.dump({"task": "001", "sent_at": "2026-11-06T10:00:00"}, f)

        code, out, err = self.run_cli("heldout", self.proj, "run", "math")
        self.assertEqual(code, 1)
        self.assertIn("in flight", out + err)


class TestCliTools(BaseCliTest):

    def test_tools_standard(self):
        proj = os.path.join(self.test_dir, "proj")
        os.makedirs(proj, exist_ok=True)
        self.run_cli("init", proj)

        code, out, _ = self.run_cli("tools", proj)
        self.assertEqual(code, 0)
        self.assertIn("needs no external tools", out)

    def test_tools_uem_mocked(self):
        proj = os.path.join(self.test_dir, "proj")
        os.makedirs(proj, exist_ok=True)
        self.run_cli("init", proj, "--methodology", "uem")

        # Scenario 1: all plugins installed and valid version
        mock_plugins_ok = {
            "superpowers": {"name": "superpowers", "version": "7.0.2", "enabled": True},
            "egm": {"name": "egm", "version": "0.1.0", "enabled": True},
        }
        with patch.object(maestro, "_agy_plugins", return_value=mock_plugins_ok):
            code, out, _ = self.run_in_process("tools", proj)
            self.assertEqual(code, 0)
            self.assertIn("[OK     ] superpowers", out)
            self.assertIn("[OK     ] egm", out)

        # Scenario 2: superpowers installed but below min_version (e.g. 6.5.0 < 7.0.0) -> MISSING
        mock_plugins_outdated = {
            "superpowers": {"name": "superpowers", "version": "6.5.0", "enabled": True},
            "egm": {"name": "egm", "version": "0.1.0", "enabled": True},
        }
        with patch.object(maestro, "_agy_plugins", return_value=mock_plugins_outdated):
            code, out, _ = self.run_in_process("tools", proj)
            self.assertEqual(code, 0)
            self.assertIn("[MISSING] superpowers", out)
            self.assertIn("[OK     ] egm", out)

    def test_tools_approve_writes_install_task(self):
        proj = os.path.join(self.test_dir, "proj")
        os.makedirs(proj, exist_ok=True)
        self.run_cli("init", proj, "--methodology", "uem")

        code, out, _ = self.run_cli("tools", proj, "--approve", "harness-creator", "agentshield")
        self.assertEqual(code, 0)
        self.assertIn("install task written: ", out)
        task_path = out.split("install task written: ")[1].splitlines()[0].strip()
        self.assertTrue(os.path.exists(task_path))
        with open(task_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("a9342ff471f2c0e60be0c08b9f4a7c502df4e442", content)
        self.assertIn("ecc-agentshield@1.6.0", content)

    def test_tools_approve_unknown_rejected(self):
        proj = os.path.join(self.test_dir, "proj")
        os.makedirs(proj, exist_ok=True)
        self.run_cli("init", proj, "--methodology", "uem")

        code, out, err = self.run_cli("tools", proj, "--approve", "bogus_tool")
        self.assertEqual(code, 1)
        self.assertIn("unknown tool", out + err)


if __name__ == "__main__":
    unittest.main()
