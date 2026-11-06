"""Maestro MCP server: lets the Antigravity executor talk to the Maestro reviewer mid-task.

Standard library only. Speaks MCP over stdio (newline-delimited JSON-RPC 2.0).

Tools
  maestro_ask(project, task_id, question, options?, wait_seconds?)
      Writes <project>/.maestro/questions/<qid>.json and blocks until the reviewer writes
      <qid>.answer.md, or until wait_seconds pass. Returns the answer, or the question id
      so the executor can poll with maestro_check_answer.
  maestro_check_answer(project, question_id, wait_seconds?)
      Waits again for an answer to an earlier question.
  maestro_progress(project, task_id, message)
      Appends a line to <project>/.maestro/progress/task-NNN.log. It does not wake the reviewer.

The reviewer side (`maestro wait`) wakes up when a question has no answer yet. The reviewer
answers with `maestro answer <project> <qid> "<text>"`.

Files are only ever written inside <project>/.maestro/, and only if that folder already exists.
The tools work only while <project>/.maestro/active.json names the task (written by
`maestro send`, removed by `maestro wait`); otherwise they refuse at once, so ordinary
Antigravity use outside Maestro is never affected.
"""
import json
import os
import re
import sys
import threading
import time
from datetime import datetime

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)
from version import __version__

SERVER = {"name": "maestro", "version": __version__}
DEFAULT_WAIT, MAX_WAIT, POLL = 300, 900, 2
TASK_RE = re.compile(r"^\d{1,4}$")
QID_RE = re.compile(r"^task-\d{3,4}-q\d{1,3}$")
_out_lock = threading.Lock()


# ---------- helpers ----------

class ToolError(Exception):
    pass


def _dot(project):
    if not project or not os.path.isabs(project):
        raise ToolError("project must be the absolute path of the project root")
    dot = os.path.join(os.path.normpath(project), ".maestro")
    if not os.path.isdir(dot):
        raise ToolError(f"{dot} does not exist; this project is not set up for Maestro")
    return dot


def _task(task_id):
    t = str(task_id).strip().lower()
    if t.startswith("task-"):
        t = t[5:]
    if not TASK_RE.match(t):
        raise ToolError("task_id must look like 001 or task-001")
    return f"{int(t):03d}"


MAX_ACTIVE_HOURS = 12  # an older marker is treated as stale


class Inactive(Exception):
    """No Maestro task is in flight: refuse immediately instead of blocking."""


def _require_active(dot, task):
    """Allow the tools only while `maestro send` has marked this task as in flight.

    This keeps ordinary Antigravity conversations (outside Maestro) from ever blocking on a
    question nobody will answer.
    """
    path = os.path.join(dot, "active.json")
    try:
        with open(path, encoding="utf-8-sig") as f:
            active = json.load(f)
        current = f"{int(str(active.get('task'))):03d}"
        sent = datetime.fromisoformat(str(active.get("sent_at")))
    except (OSError, ValueError, TypeError):
        raise Inactive("No Maestro task is active in this project. You are not running as the "
                       "Maestro executor right now: do not use the maestro_* tools; continue normally.")
    if os.path.exists(os.path.join(dot, "reports", f"task-{current}.done.md")):
        raise Inactive(f"Maestro task {current} is already reported; no task is active. Continue normally.")
    if (datetime.now() - sent).total_seconds() > MAX_ACTIVE_HOURS * 3600:
        raise Inactive("The Maestro active-task marker is stale; no task is active. Continue normally.")
    if task != current:
        raise Inactive(f"The active Maestro task is {current}, not {task}. Use task_id '{current}' "
                       "only if that is the task you are executing; otherwise continue normally.")


def _wait_seconds(v):
    try:
        v = int(v) if v is not None else DEFAULT_WAIT
    except (TypeError, ValueError):
        v = DEFAULT_WAIT
    return max(0, min(v, MAX_WAIT))


def _write_atomic(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def _await_answer(qdir, qid, wait):
    answer = os.path.join(qdir, qid + ".answer.md")
    deadline = time.monotonic() + wait
    while True:
        if os.path.exists(answer):
            time.sleep(0.3)
            with open(answer, encoding="utf-8") as f:
                return f.read().strip()
        if time.monotonic() >= deadline:
            return None
        time.sleep(POLL)


def _no_answer(qid):
    return (f"No answer yet for {qid}. Either call maestro_check_answer with question_id='{qid}' "
            "to keep waiting, or continue with your best assumption and state it under "
            "'Problems / assumptions' in your report.")


# ---------- tools ----------

def _post(dot, task, record, wait):
    """Write a question/checkpoint record and block for the reviewer's answer."""
    qdir = os.path.join(dot, "questions")
    os.makedirs(qdir, exist_ok=True)
    n = 1
    while os.path.exists(os.path.join(qdir, f"task-{task}-q{n}.json")):
        n += 1
    qid = f"task-{task}-q{n}"
    record = {"id": qid, "task": task, **record, "asked_at": datetime.now().isoformat(timespec="seconds")}
    _write_atomic(os.path.join(qdir, qid + ".json"), json.dumps(record, ensure_ascii=False, indent=2))
    return qid, _await_answer(qdir, qid, _wait_seconds(wait))


def tool_ask(a):
    dot = _dot(a.get("project"))
    task = _task(a.get("task_id"))
    _require_active(dot, task)
    question = (a.get("question") or "").strip()
    if not question:
        raise ToolError("question is required")
    qid, ans = _post(dot, task, {"kind": "question", "question": question,
                                 "options": [str(o) for o in (a.get("options") or [])]}, a.get("wait_seconds"))
    return f"Answer from the reviewer ({qid}):\n{ans}" if ans is not None else _no_answer(qid)


CHECKPOINT_KINDS = ("plan",)


def tool_checkpoint(a):
    dot = _dot(a.get("project"))
    task = _task(a.get("task_id"))
    _require_active(dot, task)
    kind = (a.get("kind") or "plan").strip().lower()
    if kind not in CHECKPOINT_KINDS:
        raise ToolError(f"kind must be one of {CHECKPOINT_KINDS}")
    summary = (a.get("summary") or "").strip()
    plan_path = (a.get("plan_path") or "").strip()
    if not summary:
        raise ToolError("summary is required")
    if plan_path:
        full = plan_path if os.path.isabs(plan_path) else os.path.join(os.path.dirname(dot), plan_path)
        if not os.path.exists(full):
            raise ToolError(f"plan file not found: {plan_path}; write the plan first")
    qid, ans = _post(dot, task, {"kind": kind, "question": f"[{kind} checkpoint] {summary}",
                                 "plan_path": plan_path, "options": ["APPROVED", "corrections"]},
                     a.get("wait_seconds", MAX_WAIT))
    if ans is None:
        return (f"No answer yet for {qid}. This is a stop point: do NOT continue. Call "
                f"maestro_check_answer with question_id='{qid}' and keep calling it until the reviewer answers.")
    return f"Reviewer's verdict on the {kind} ({qid}):\n{ans}"


def tool_check(a):
    dot = _dot(a.get("project"))
    qid = (a.get("question_id") or "").strip()
    if not QID_RE.match(qid):
        raise ToolError("question_id must look like task-001-q1")
    qdir = os.path.join(dot, "questions")
    if not os.path.exists(os.path.join(qdir, qid + ".json")):
        raise ToolError(f"unknown question {qid}")
    answer = os.path.join(qdir, qid + ".answer.md")
    if not os.path.exists(answer):   # already-given answers can always be read back
        _require_active(dot, qid.split("-")[1])
    try:
        with open(os.path.join(qdir, qid + ".json"), encoding="utf-8") as f:
            kind = json.load(f).get("kind", "question")
    except (OSError, ValueError):
        kind = "question"
    ans = _await_answer(qdir, qid, _wait_seconds(a.get("wait_seconds")))
    if ans is not None:
        return f"Answer from the reviewer ({qid}):\n{ans}"
    if kind != "question":   # checkpoints are stop points: never continue without a verdict
        return (f"No answer yet for {qid}. This is a stop point: do NOT continue. "
                f"Call maestro_check_answer with question_id='{qid}' again.")
    return _no_answer(qid)


def tool_progress(a):
    dot = _dot(a.get("project"))
    task = _task(a.get("task_id"))
    _require_active(dot, task)
    msg = " ".join((a.get("message") or "").split())
    if not msg:
        raise ToolError("message is required")
    pdir = os.path.join(dot, "progress")
    os.makedirs(pdir, exist_ok=True)
    with open(os.path.join(pdir, f"task-{task}.log"), "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().isoformat(timespec='seconds')}  {msg}\n")
    return "logged"


_PROJECT = {"type": "string", "description": "Absolute path of the project root (shown in the task file as 'Project root')."}
_TASK = {"type": "string", "description": "Task number, e.g. '001'."}
_WAIT = {"type": "integer", "description": f"Seconds to wait for the answer (default {DEFAULT_WAIT}, max {MAX_WAIT})."}

TOOLS = {
    "maestro_ask": (tool_ask, {
        "description": ("Only for the Maestro executor (your prompt says so and you are executing a "
                        ".maestro/tasks/task-NNN.md file); otherwise do not use. "
                        "Ask the Maestro reviewer a question when the task is ambiguous or a decision is "
                        "outside your authority, such as a choice between approaches, a missing requirement, "
                        "or a needed file outside the allowed list. Blocks until the reviewer answers. "
                        "Ask only when it matters; do not ask for confirmation of things the task already states."),
        "inputSchema": {"type": "object", "properties": {
            "project": _PROJECT, "task_id": _TASK,
            "question": {"type": "string", "description": "One clear question with the context needed to answer it."},
            "options": {"type": "array", "items": {"type": "string"}, "description": "Optional candidate answers."},
            "wait_seconds": _WAIT},
            "required": ["project", "task_id", "question"]}}),
    "maestro_checkpoint": (tool_checkpoint, {
        "description": ("Only for the Maestro executor. A stop point: submit your plan to the reviewer and wait "
                        "for its verdict before writing code. The answer starts with APPROVED, or lists numbered "
                        "corrections to apply before calling this again. If it returns 'No answer yet', do not "
                        "continue: call maestro_check_answer until the reviewer answers."),
        "inputSchema": {"type": "object", "properties": {
            "project": _PROJECT, "task_id": _TASK,
            "kind": {"type": "string", "enum": list(CHECKPOINT_KINDS), "description": "Checkpoint kind; 'plan'."},
            "summary": {"type": "string", "description": "Short summary: approach, files, tests, and steps."},
            "plan_path": {"type": "string", "description": "Path of the plan file, e.g. .maestro/plans/<feature>.md."},
            "wait_seconds": _WAIT},
            "required": ["project", "task_id", "summary"]}}),
    "maestro_check_answer": (tool_check, {
        "description": "Keep waiting for the reviewer's answer to a question or checkpoint (maestro_ask / maestro_checkpoint).",
        "inputSchema": {"type": "object", "properties": {
            "project": _PROJECT,
            "question_id": {"type": "string", "description": "Id returned by maestro_ask, e.g. task-001-q1."},
            "wait_seconds": _WAIT},
            "required": ["project", "question_id"]}}),
    "maestro_progress": (tool_progress, {
        "description": ("Record a short progress note for a long task (for example 'tests written, implementing parser'). "
                        "It does not interrupt the reviewer. The final report is still required."),
        "inputSchema": {"type": "object", "properties": {
            "project": _PROJECT, "task_id": _TASK,
            "message": {"type": "string", "description": "One line."}},
            "required": ["project", "task_id", "message"]}}),
}


# ---------- JSON-RPC over stdio ----------

def _send(obj):
    line = json.dumps(obj, ensure_ascii=False)
    with _out_lock:
        sys.stdout.write(line + "\n")
        sys.stdout.flush()


def _result(mid, result):
    _send({"jsonrpc": "2.0", "id": mid, "result": result})


def _error(mid, code, message):
    _send({"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}})


def _call_tool(mid, params):
    name = params.get("name")
    entry = TOOLS.get(name)
    if not entry:
        _error(mid, -32602, f"unknown tool {name}")
        return
    try:
        text, is_error = entry[0](params.get("arguments") or {}), False
    except Inactive as e:
        text, is_error = str(e), True
    except ToolError as e:
        text, is_error = f"Error: {e}", True
    except Exception as e:  # keep the server alive on unexpected failures
        text, is_error = f"Internal error: {type(e).__name__}: {e}", True
    _result(mid, {"content": [{"type": "text", "text": text}], "isError": is_error})


def handle(msg):
    method, mid, params = msg.get("method"), msg.get("id"), msg.get("params") or {}
    log(f"recv {method}" + (f" tool={params.get('name')}" if method == "tools/call" else "")
        + (f" client={params.get('clientInfo')} proto={params.get('protocolVersion')}" if method == "initialize" else ""))
    if mid is None:  # notification (initialized, cancelled, ...)
        return
    if method == "initialize":
        _result(mid, {"protocolVersion": params.get("protocolVersion", "2024-11-05"),
                      "capabilities": {"tools": {}}, "serverInfo": SERVER})
    elif method == "ping":
        _result(mid, {})
    elif method == "tools/list":
        _result(mid, {"tools": [dict(name=n, **spec) for n, (_, spec) in TOOLS.items()]})
    elif method == "tools/call":
        # Run in a thread: maestro_ask can block for minutes, and pings must still be answered.
        threading.Thread(target=_call_tool, args=(mid, params), daemon=True).start()
    else:
        _error(mid, -32601, f"method not found: {method}")


DEFAULT_LOG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "mcp.log")


def _log_path():
    override = os.environ.get("MAESTRO_MCP_LOG")
    if override:
        return override
    return DEFAULT_LOG


def log(msg):
    """Small diagnostic log (<tool>/logs/mcp.log): startup, methods, failures. No tool arguments."""
    try:
        path = _log_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if os.path.exists(path) and os.path.getsize(path) > 512_000:
            os.replace(path, path + ".1")
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat(timespec='seconds')} pid={os.getpid()} {msg}\n")
    except OSError:
        pass


def main():
    log(f"start python={sys.executable} cwd={os.getcwd()}")
    try:
        sys.stdin.reconfigure(encoding="utf-8")
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")
        _loop()
    except Exception as e:
        log(f"crash {type(e).__name__}: {e}")
        raise
    finally:
        log("exit")


def _loop():
    for line in sys.stdin:
        line = line.strip().lstrip("﻿")  # some shells prepend a BOM when piping
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            _error(None, -32700, "parse error")
            continue
        handle(msg)


if __name__ == "__main__":
    main()
