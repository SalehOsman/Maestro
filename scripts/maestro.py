"""Maestro CLI: a central tool that works on any project folder (Windows, macOS, Linux).

  maestro init    <project> [--methodology standard|uem|custom]
                                             create <project>/.maestro/ (re-run to refresh templates and rules)
  maestro new     <project> "<title>" [--feature ID]   next feature brief / task file, print its path
  maestro tools   <project> [--approve ID...] check the methodology's tools; write an install task for approved ones
  maestro heldout <project> add|list|run <feature> [files]  hidden acceptance tests, stored outside the repo
  maestro review  <project> new <feature> [--task NNN]      next review round file (exit 4: no rounds left)
  maestro review  <project> verdict <feature> accepted|changes-requested   reviewer-only verdict
  maestro testdiff <project> [--base REF]    deleted / weakened / skipped tests since the base (exit 5 if any)
  maestro send    <project> [NNN] [--no-enter]   send task NNN (default: latest) to Antigravity
  maestro wait    <project> [NNN] [--timeout 45] wait (no tokens) for the report or a question
  maestro answer  <project> <question-id> "<text>"  answer an executor question
  maestro release <project>                  clear the active-task marker (after abandoning a task)
  maestro status  <project>                  tasks, questions and the active task

Exit codes: 0 ok / sent / report ready; 1 error, wait timeout, or held-out failure; 2 send drafted
the prompt but did not press Enter; 3 wait woke on an unanswered question or checkpoint; 4 no review
rounds left; 5 testdiff found test changes that need a reason.

While a task is in flight, <project>/.maestro/active.json names it. The executor's MCP tools
refuse to work without it, so Antigravity used outside Maestro can never block on a question.
"""
import argparse
from collections import Counter
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
TEMPLATES = ROOT / "templates"
METHODOLOGIES = ROOT / "methodologies"
METHODOLOGY_NAMES = ("standard", "uem", "custom")
HELDOUT_HOME = Path(os.environ.get("MAESTRO_HELDOUT_HOME") or Path.home() / ".maestro" / "heldout")
sys.path.insert(0, str(SCRIPTS))

import agy_project  # noqa: E402
import sender  # noqa: E402
from version import __version__  # noqa: E402

QID_RE = re.compile(r"^task-\d{3,4}-q\d{1,3}$")
POLL_SECONDS = 5


class Fail(Exception):
    pass


def write_text(path, text):
    """UTF-8 without BOM, written atomically."""
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def load_feature_list(path):
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8-sig")
    except OSError as e:
        raise Fail(f"unreadable feature_list.json: {e}")
    try:
        data = json.loads(text)
    except Exception as e:
        raise Fail(f"unreadable feature_list.json: {e}")
    if isinstance(data, list):
        return data, data
    if isinstance(data, dict) and isinstance(data.get("features"), list):
        return data, data["features"]
    raise Fail('unsupported feature_list.json format: expected a list or {"features": [...]}')


class Project:
    def __init__(self, path):
        p = Path(path).expanduser()
        if not p.is_dir():
            raise Fail(f"not a folder: {path}")
        self.root = p.resolve()
        self.dot = self.root / ".maestro"
        self.tasks = self.dot / "tasks"
        self.reports = self.dot / "reports"
        self.questions = self.dot / "questions"
        self.plans = self.dot / "plans"
        self.reviews = self.dot / "reviews"
        self.config_file = self.dot / "config.json"
        self.active_file = self.dot / "active.json"

    def config(self):
        try:
            return json.loads(self.config_file.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            return {}

    def methodology(self):
        m = self.config().get("methodology", "standard")
        return m if (METHODOLOGIES / m).is_dir() else "standard"

    def require_init(self):
        if not self.tasks.is_dir():
            raise Fail(f'{self.root} is not initialised; run: maestro init "{self.root}"')

    def task_ids(self):
        return sorted(f.stem[5:] for f in self.tasks.glob("task-*.md") if re.fullmatch(r"\d{3,4}", f.stem[5:]))

    def pick(self, task_id):
        if task_id:
            if not task_id.isdigit():
                raise Fail(f"task number must be digits, got {task_id!r}")
            return f"{int(task_id):03d}"
        ids = self.task_ids()
        if not ids:
            raise Fail(f"no tasks in {self.tasks}")
        return ids[-1]

    def task_file(self, tid):
        return self.tasks / f"task-{tid}.md"

    def report_file(self, tid):
        return self.reports / f"task-{tid}.done.md"

    def active(self):
        try:
            return f"{int(json.loads(self.active_file.read_text(encoding='utf-8-sig'))['task']):03d}"
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def open_question(self):
        if not self.questions.is_dir():
            return None
        pending = [q for q in self.questions.glob("task-*-q*.json")
                   if not (self.questions / (q.stem + ".answer.md")).exists()]
        return min(pending, key=lambda q: q.stat().st_mtime) if pending else None


# ---------- commands ----------

def detect_stack(root):
    """Best-effort defaults for the project's commands; Claude reviews and edits config.json."""
    cfg = {"stack": "unknown", "test_cmd": "", "verify_cmd": "", "mutation_cmd": "", "heldout_cmd": ""}
    pkg = root / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8-sig"))
        except ValueError:
            data = {}
        scripts = data.get("scripts", {})
        deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
        runner = "pnpm" if (root / "pnpm-lock.yaml").exists() else "yarn" if (root / "yarn.lock").exists() else "npm"
        cfg.update(stack="node", test_cmd=f"{runner} test",
                   verify_cmd=f"{runner} run verify" if "verify" in scripts else f"{runner} test")
        if "@stryker-mutator/core" in deps:
            cfg["mutation_cmd"] = "npx --no-install stryker run --mutate {files}"
        if "vitest" in deps:
            cfg["heldout_cmd"] = "npx --no-install vitest run {dir}"
        elif "jest" in deps:
            cfg["heldout_cmd"] = "npx --no-install jest {dir}"
    elif any((root / f).exists() for f in ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt")):
        cfg.update(stack="python", test_cmd="python -m pytest", verify_cmd="python -m pytest",
                   heldout_cmd="python -m pytest {dir}")
        if shutil.which("mutmut"):
            cfg["mutation_cmd"] = "mutmut run --paths-to-mutate {files}"
    return cfg


def default_config(root, methodology):
    return {
        "methodology": methodology,
        **detect_stack(root),
        "base_branch": "main",
        "branch_prefix": "feature/",
        "review": {
            "max_rounds": 2,
            "full_review_paths": [],
            "full_review_topics": ["secrets", "server", "untrusted user input", "authentication",
                                   "payments", "stored data"],
        },
    }


def cmd_init(a):
    p = Project(a.project)
    for d in (p.tasks, p.reports, p.questions, p.plans, p.reviews):
        d.mkdir(parents=True, exist_ok=True)
    cfg = p.config()
    if a.methodology:
        if cfg and cfg.get("methodology") != a.methodology:
            print(f"methodology: {cfg.get('methodology')} -> {a.methodology}")
        cfg = {**(cfg or default_config(p.root, a.methodology)), "methodology": a.methodology}
    elif not cfg:
        cfg = default_config(p.root, "standard")
    write_text(p.config_file, json.dumps(cfg, indent=2, ensure_ascii=False) + "\n")
    m = cfg["methodology"]
    shutil.copyfile(TEMPLATES / "report.md", p.dot / "report-template.md")
    shutil.copyfile(METHODOLOGIES / m / "EXECUTOR_RULES.md", p.dot / "EXECUTOR_RULES.md")
    shutil.copyfile(METHODOLOGIES / "ROLES.md", p.dot / "ROLES.md")
    created = []
    if m in ("standard", "uem"):  # repository is the system of record: state files at the root
        for name in ("feature_list.json", "progress.md", "session-handoff.md"):
            if not (p.root / name).exists():
                shutil.copyfile(TEMPLATES / "state" / name, p.root / name)
                created.append(name)
    print(f"initialised {p.dot} (methodology: {m})")
    if created:
        print("created at the project root: " + ", ".join(created))
    print(f"commands (edit {p.config_file.name} if wrong): stack={cfg.get('stack')} "
          f"verify='{cfg.get('verify_cmd')}' mutation='{cfg.get('mutation_cmd') or '-'}' "
          f"heldout='{cfg.get('heldout_cmd') or '-'}'")
    pid = agy_project.resolve(str(p.root))
    if pid:
        print(f"Antigravity project: {pid}")
    else:
        print("NOTE: Antigravity does not know this folder yet. Open it in the Antigravity agent app "
              "and start one conversation there, once. 'maestro send' will refuse until the id is found.")
    missing = [r for r, ok, _ in check_tools(p) if not ok and not r.get("optional")]
    if missing:
        print(f"NOTE: {len(missing)} required tool(s) missing for '{m}'; run: maestro tools \"{p.root}\"")
    return 0


def cmd_new(a):
    p = Project(a.project)
    p.require_init()
    ids = p.task_ids()
    tid = f"{(int(ids[-1]) if ids else 0) + 1:03d}"
    feature = a.feature or re.sub(r"[^a-z0-9]+", "-", a.title.lower()).strip("-")[:40] or f"task-{tid}"
    text = (TEMPLATES / "task.md").read_text(encoding="utf-8-sig")
    for k, v in {"ID": tid, "TITLE": a.title, "PROJECT": str(p.root), "FEATURE": feature,
                 "METHODOLOGY": p.methodology()}.items():
        text = text.replace("{{" + k + "}}", v)
    write_text(p.task_file(tid), text)
    print(p.task_file(tid))
    return 0


# ---------- methodology tools ----------

def _agy():
    for c in (shutil.which("agy"),
              Path(os.environ.get("LOCALAPPDATA", "")) / "agy" / "bin" / "agy.exe",
              Path.home() / ".local" / "bin" / "agy"):
        if c and Path(c).exists():
            return str(c)
    return None


def _version_tuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", str(v))[:3]) or (0,)


_plugin_cache = None


def _agy_plugins():
    global _plugin_cache
    if _plugin_cache is None:
        _plugin_cache = {}
        agy = _agy()
        if agy:
            try:
                out = subprocess.run([agy, "plugin", "list", "--json"], capture_output=True, text=True,
                                     encoding="utf-8", timeout=60).stdout
                _plugin_cache = {pl["name"]: pl for pl in json.loads(out or "[]")}
            except (OSError, ValueError, subprocess.SubprocessError):
                pass
    return _plugin_cache


def check_tools(p):
    """[(requirement, ok, detail)] for the project's methodology."""
    req_file = METHODOLOGIES / p.methodology() / "requirements.json"
    reqs = json.loads(req_file.read_text(encoding="utf-8")).get("requirements", []) if req_file.exists() else []
    results = []
    for r in reqs:
        c = r["check"]
        if c["type"] == "agy-plugin":
            pl = _agy_plugins().get(c["name"])
            ok = bool(pl) and pl.get("enabled", True) and _version_tuple(pl.get("version")) >= _version_tuple(c["min_version"])
            detail = f"installed {pl.get('version')}" if pl else ("agy CLI not found" if not _agy() else "not installed")
        elif c["type"] == "path":
            path = Path(c["path"].replace("{project}", str(p.root)))
            ok, detail = path.exists(), ("present" if path.exists() else "missing")
        elif c["type"] == "npm-dev-dependency":
            pkg = p.root / "package.json"
            dev = json.loads(pkg.read_text(encoding="utf-8-sig")).get("devDependencies", {}) if pkg.exists() else {}
            have = dev.get(c["name"])
            ok = have == c["version"]
            detail = "no package.json (run it in CI)" if not pkg.exists() else (f"devDependency {have}" if have else "not a devDependency")
        else:
            ok, detail = False, f"unknown check {c['type']}"
        results.append((r, ok, detail))
    return results


def cmd_tools(a):
    p = Project(a.project)
    p.require_init()
    results = check_tools(p)
    if not results:
        print(f"methodology '{p.methodology()}' needs no external tools")
        return 0
    for r, ok, detail in results:
        flag = "OK     " if ok else ("OPTIONAL" if r.get("optional") else "MISSING")
        print(f"[{flag}] {r['id']}: {r['name']}\n          source {r['source']}  version {r['version']}  "
              f"license {r.get('license', '?')}  scope {r['scope']}\n          {detail}")
    if not a.approve:
        todo = [r["id"] for r, ok, _ in results if not ok]
        if todo:
            print("\nTo install, get the user's explicit approval for each tool (source and version above), then run:\n"
                  f"  maestro tools \"{p.root}\" --approve {' '.join(todo)}")
        return 0
    by_id = {r["id"]: r for r, _, _ in results}
    unknown = [i for i in a.approve if i not in by_id]
    if unknown:
        raise Fail(f"unknown tool id(s): {', '.join(unknown)}")
    tmp = (Path(tempfile.gettempdir()) / "maestro-install").as_posix()
    ids = p.task_ids()
    tid = f"{(int(ids[-1]) if ids else 0) + 1:03d}"
    lines = [f"# Task {tid}: Install approved methodology tools", "",
             f"- Project root: `{p.root}`", "- Kind: setup", "",
             "The user explicitly approved installing exactly the tools below, from exactly these sources and",
             "versions. Run the commands as written. Do not substitute another source, version or package.",
             "If a command fails, stop and report the failure; do not improvise a workaround.", ""]
    for i in a.approve:
        r = by_id[i]
        lines += [f"## {r['id']} — {r['name']}", f"- Source: {r['source']} (version {r['version']})", "- Commands:"]
        lines += [f"  {n}. `{cmd.replace('{tmp}', tmp).replace('{project}', str(p.root))}`"
                  for n, cmd in enumerate(r["install"], 1)]
        if r.get("note"):
            lines.append(f"- Note: {r['note']}")
        lines.append("")
    lines += ["## Acceptance criteria",
              f"- [ ] `maestro tools \"{p.root}\"` would show each approved tool as OK (the reviewer re-checks).",
              "- [ ] Do NOT run git commands that merge, rebase or push.", "",
              "## When done",
              f"Write `.maestro/reports/task-{tid}.done.md` (template `.maestro/report-template.md`) LAST,",
              "with each command and its real output."]
    write_text(p.task_file(tid), "\n".join(lines) + "\n")
    print(f"\ninstall task written: {p.task_file(tid)}\nsend it with: maestro send \"{p.root}\" {tid}")
    return 0


# ---------- review support ----------

def _heldout_dir(p, feature):
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", p.root.name) + "-" + hashlib.sha1(str(p.root).lower().encode()).hexdigest()[:8]
    return HELDOUT_HOME / slug / re.sub(r"[^A-Za-z0-9_.-]+", "-", feature)


def cmd_heldout(a):
    p = Project(a.project)
    p.require_init()
    store = _heldout_dir(p, a.feature)
    if a.action == "add":
        if not a.files:
            raise Fail("usage: maestro heldout <project> add <feature> <test-file>...")
        store.mkdir(parents=True, exist_ok=True)
        for f in a.files:
            src = Path(f)
            if not src.is_file():
                raise Fail(f"not a file: {f}")
            shutil.copyfile(src, store / src.name)
            print(f"stored {src.name} -> {store} (outside the repository)")
        return 0
    if a.action == "list":
        files = sorted(x.name for x in store.glob("*")) if store.exists() else []
        print("\n".join(files) if files else f"no held-out tests for {a.feature}")
        return 0
    # run
    if p.active():
        raise Fail("a task is in flight; run held-out tests only during review (no active task), "
                   "so the executor never sees them")
    files = sorted(store.glob("*")) if store.exists() else []
    if not files:
        raise Fail(f"no held-out tests stored for {a.feature}")
    cmd_t = p.config().get("heldout_cmd", "")
    if "{dir}" not in cmd_t:
        raise Fail("set heldout_cmd in .maestro/config.json, with {dir} for the test folder")
    # A plain, importable folder name: test runners (unittest in particular) cannot discover tests
    # under a dot-folder such as .maestro or a name with dashes.
    run_root = p.root / "_maestro_heldout"
    run_dir = run_root / re.sub(r"\W+", "_", a.feature)
    shutil.rmtree(run_root, ignore_errors=True)
    run_dir.mkdir(parents=True)
    try:
        for pkg in (run_root, run_dir):
            (pkg / "__init__.py").write_text("", encoding="utf-8")
        for f in files:
            shutil.copyfile(f, run_dir / f.name)
        rel = run_dir.relative_to(p.root).as_posix()
        r = subprocess.run(cmd_t.replace("{dir}", rel), shell=True, cwd=p.root, capture_output=True,  # noqa: S602 - reviewer-configured command
                           text=True, encoding="utf-8", errors="replace")
        tail = (r.stdout + r.stderr).strip().splitlines()[-15:]
        print("\n".join(tail))
        print(f"HELDOUT {'PASS' if r.returncode == 0 else 'FAIL'} ({len(files)} file(s), exit {r.returncode})")
        return 0 if r.returncode == 0 else 1
    finally:
        shutil.rmtree(run_root, ignore_errors=True)


def cmd_review(a):
    p = Project(a.project)
    p.require_init()
    max_rounds = int(p.config().get("review", {}).get("max_rounds", 2))
    rounds = sorted(p.reviews.glob(f"{a.feature}-round-*.md"))
    if a.action == "new":
        n = len(rounds) + 1
        if n > max_rounds:
            print(f"ESCALATE: {a.feature} already had {len(rounds)} review round(s) (max {max_rounds}). "
                  "No further round: decide with the user how to go on.")
            return 4
        text = (TEMPLATES / "review.md").read_text(encoding="utf-8-sig")
        for k, v in {"FEATURE": a.feature, "ROUND": str(n), "MAX": str(max_rounds), "TASK": a.task or "?"}.items():
            text = text.replace("{{" + k + "}}", v)
        path = p.reviews / f"{a.feature}-round-{n}.md"
        write_text(path, text)
        print(path)
        return 0
    # verdict
    if a.verdict not in ("accepted", "changes-requested"):
        raise Fail("verdict must be accepted or changes-requested")
    fl = p.root / "feature_list.json"
    if not fl.exists():
        raise Fail("no feature_list.json at the project root")
    data, features = load_feature_list(fl)
    counts = Counter()
    for feat in features:
        if isinstance(feat, dict):
            fid = feat.get("id")
            if fid is not None:
                counts[fid] += 1

    if counts.get(a.feature, 0) > 1:
        raise Fail(f"duplicate feature id '{a.feature}' ({counts[a.feature]} entries) in feature_list.json")

    other_dups = {fid: cnt for fid, cnt in counts.items() if cnt > 1 and fid != a.feature}
    if other_dups:
        dup_desc = ", ".join(f"{fid} ({cnt})" for fid, cnt in other_dups.items())
        print(f"WARN: duplicate feature id(s) in feature_list.json: {dup_desc}")

    for feat in features:
        if not isinstance(feat, dict):
            continue
        if feat.get("id") == a.feature:
            if a.verdict == "accepted" and feat.get("status") != "passing":
                raise Fail(f"{a.feature} is '{feat.get('status')}', not 'passing'; it cannot be accepted")
            feat["review"] = a.verdict
            feat["review_rounds"] = len(rounds)
            write_text(fl, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
            print(f"{a.feature}: review = {a.verdict} (rounds: {len(rounds)})")
            return 0
    raise Fail(f"feature {a.feature} not found in feature_list.json")


TEST_FILE_RE = re.compile(r"(^|/)(tests?|__tests__|spec)/|(^|/)test_[^/]*\.py$|_test\.(py|go)$|\.(test|spec)\.[cm]?[jt]sx?$", re.I)
ASSERT_RE = re.compile(r"\b(assert\w*|expect\s*\(|should\b|self\.assert\w+|t\.(Error|Fatal)\w*|toBe|toEqual|toThrow)", re.I)
SKIP_RE = re.compile(r"(@pytest\.mark\.(skip|xfail)|@unittest\.skip|\bunittest\.skip|\b(it|test|describe)\.(skip|only|todo)\s*\(|\bx(it|describe|test)\s*\(|\bt\.Skip\(|@Disabled|@Ignore)")


def _git(p, *args):
    r = subprocess.run(["git", *args], cwd=p.root, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise Fail(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout


def cmd_testdiff(a):
    """Find deleted test files, removed assertions and newly skipped tests since the base branch."""
    p = Project(a.project)
    base = a.base or p.config().get("base_branch", "main")
    merge_base = _git(p, "merge-base", "HEAD", base).strip()
    findings = []
    for line in _git(p, "diff", "--name-status", merge_base).splitlines():
        status, *paths = line.split("\t")
        if status.startswith("D") and TEST_FILE_RE.search(paths[0].replace("\\", "/")):
            findings.append(f"DELETED test file: {paths[0]}")
    current = None
    for line in _git(p, "diff", "-U0", merge_base).splitlines():
        if line.startswith("+++ "):
            current = line[6:] if line.startswith("+++ b/") else None
            continue
        if not current or not TEST_FILE_RE.search(current) or line.startswith(("---", "@@")):
            continue
        if line.startswith("-") and ASSERT_RE.search(line):
            findings.append(f"REMOVED assertion in {current}: {line[1:].strip()[:120]}")
        elif line.startswith("+") and SKIP_RE.search(line):
            findings.append(f"SKIP/ONLY added in {current}: {line[1:].strip()[:120]}")
    if not findings:
        print(f"no deleted, weakened or skipped tests since {base} ({merge_base[:8]})")
        return 0
    print(f"{len(findings)} test change(s) since {base} ({merge_base[:8]}) need a reason in progress.md:")
    for f in findings:
        print("  - " + f)
    return 5


def cmd_send(a):
    p = Project(a.project)
    p.require_init()
    tid = p.pick(a.task)
    task = p.task_file(tid)
    if not task.exists():
        raise Fail(f"missing {task}")
    if p.report_file(tid).exists():
        raise Fail(f"task-{tid} already has a report; delete it first to resend")
    cur = p.active()
    if cur and cur != tid:
        raise Fail(f'task-{cur} is still in flight; finish it (or run: maestro release "{p.root}") before sending task-{tid}')

    project_id = agy_project.resolve(str(p.root))
    if not project_id:
        if not a.allow_current_project:
            raise Fail(f"Antigravity does not know {p.root} yet, so the task would land in whatever "
                       "project is selected. Open the folder in the Antigravity agent app, start one "
                       f"conversation there, then run 'maestro init {p.root}' until it prints the project id. "
                       "(To send to the currently selected project anyway: --allow-current-project)")
        print(f"WARN: no Antigravity project found for {p.root} (open it in Antigravity once); "
              "the prompt goes to the currently selected project.")
    rules = p.dot / "EXECUTOR_RULES.md"
    prompt = (f"You are the Maestro executor. First read {rules} and follow it strictly. "
              f"Then execute the task in {task}. Write the report file it specifies as the very last step.")

    # Mark the task active BEFORE sending, so the executor's first MCP call already sees it.
    marker = {"task": tid, "sent_at": datetime.now().isoformat(timespec="seconds")}
    write_text(p.active_file, json.dumps(marker))
    where = project_id or "current"
    try:
        state, why = sender.send_prompt(prompt, project_id, press_enter=not a.no_enter)
    except Exception:
        p.active_file.unlink(missing_ok=True)
        raise
    if state == "sent":
        print(f"sent task-{tid} (project: {where})")
        return 0
    print(f"drafted task-{tid} (project: {where}): {why}")
    if not a.no_enter:
        sender.notify("Maestro: press Enter in Antigravity",
                      f"Task {tid} is typed in Antigravity's chat box. Press Enter there to start it.")
    return 2   # still in flight: the user presses Enter


def cmd_wait(a):
    p = Project(a.project)
    p.require_init()
    tid = p.pick(a.task)
    report = p.report_file(tid)
    deadline = time.monotonic() + a.timeout * 60
    code = 1
    while True:
        if report.exists():
            time.sleep(3)  # let the writer finish
            print(f"REPORT READY: {report}")
            code = 0
            break
        q = p.open_question()
        if q:
            time.sleep(0.5)
            body = q.read_text(encoding="utf-8-sig")
            try:
                kind = json.loads(body).get("kind", "question")
            except ValueError:
                kind = "question"
            print(f"QUESTION: {q.stem}" if kind == "question" else f"QUESTION: {q.stem} (CHECKPOINT: {kind})")
            print(body)
            return 3   # task stays active: the executor is waiting for the answer
        if time.monotonic() >= deadline:
            print(f"TIMEOUT: no report after {a.timeout} min ({report})")
            break
        time.sleep(POLL_SECONDS)
    if p.active() == tid:
        p.active_file.unlink(missing_ok=True)
    return code


def cmd_answer(a):
    p = Project(a.project)
    p.require_init()
    # Multi-line answers must come from a file or stdin: Windows cmd.exe (maestro.cmd) cuts a
    # command-line argument at its first newline, which silently truncated numbered corrections.
    if a.file:
        a.text = (sys.stdin.read() if a.file == "-" else Path(a.file).read_text(encoding="utf-8-sig"))
    elif a.text and "\n" in a.text and sys.platform == "win32":
        print("WARN: multi-line text on the command line may be cut by cmd.exe; prefer --file", file=sys.stderr)
    if not QID_RE.match(a.question_id) or not (a.text or "").strip():
        raise Fail('usage: maestro answer <project> task-NNN-qN "<text>"  |  --file <path>  |  --file - (stdin)')
    if not (p.questions / f"{a.question_id}.json").exists():
        raise Fail(f"unknown question {a.question_id}")
    ans = p.questions / f"{a.question_id}.answer.md"
    if ans.exists():
        raise Fail(f"{a.question_id} is already answered")
    write_text(ans, a.text)
    print(f"answered {a.question_id}")
    return 0


def cmd_release(a):
    p = Project(a.project)
    p.require_init()
    if p.active_file.exists():
        p.active_file.unlink()
        print("released active task")
    else:
        print("no active task")
    return 0


def cmd_status(a):
    p = Project(a.project)
    p.require_init()
    for tid in p.task_ids():
        print(f"task-{tid}  {'reported' if p.report_file(tid).exists() else 'open'}")
    if p.questions.is_dir():
        for q in sorted(p.questions.glob("task-*-q*.json")):
            answered = (p.questions / (q.stem + ".answer.md")).exists()
            print(f"{q.stem}  {'answered' if answered else 'WAITING FOR ANSWER'}")
    fl = p.root / "feature_list.json"
    if fl.exists():
        try:
            _, features = load_feature_list(fl)
            non_objects = sum(1 for feat in features if not isinstance(feat, dict))
            if non_objects:
                msg = f"{non_objects} entry in feature_list.json is not an object" if non_objects == 1 else f"{non_objects} entries in feature_list.json are not objects"
                print(f"WARN: {msg}")
            counts = Counter()
            for feat in features:
                if isinstance(feat, dict):
                    fid = feat.get("id")
                    if fid is not None:
                        counts[fid] += 1
            for fid, cnt in counts.items():
                if cnt > 1:
                    print(f"WARN: duplicate feature id '{fid}' in feature_list.json ({cnt} entries)")
        except Fail as e:
            print(f"WARN: {e}")
        except Exception as e:
            print(f"WARN: could not read feature_list.json: {e}")
    cur = p.active()
    print(f"active: {'task-' + cur if cur else 'none'}")
    return 0


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(prog="maestro", description="Claude plans and verifies; Antigravity executes.")
    ap.add_argument("--version", action="version", version=f"maestro {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("init");    s.add_argument("project")
    s.add_argument("--methodology", choices=METHODOLOGY_NAMES, help="executor methodology (default: keep, or standard)")
    s.set_defaults(fn=cmd_init)
    s = sub.add_parser("new");     s.add_argument("project"); s.add_argument("title")
    s.add_argument("--feature", help="feature id (default: derived from the title)"); s.set_defaults(fn=cmd_new)
    s = sub.add_parser("tools");   s.add_argument("project")
    s.add_argument("--approve", nargs="+", metavar="ID", help="tool ids the user explicitly approved"); s.set_defaults(fn=cmd_tools)
    s = sub.add_parser("heldout"); s.add_argument("project"); s.add_argument("action", choices=("add", "list", "run"))
    s.add_argument("feature"); s.add_argument("files", nargs="*"); s.set_defaults(fn=cmd_heldout)
    s = sub.add_parser("review");  s.add_argument("project"); s.add_argument("action", choices=("new", "verdict"))
    s.add_argument("feature"); s.add_argument("verdict", nargs="?"); s.add_argument("--task")
    s.set_defaults(fn=cmd_review)
    s = sub.add_parser("testdiff"); s.add_argument("project"); s.add_argument("--base"); s.set_defaults(fn=cmd_testdiff)
    s = sub.add_parser("send");    s.add_argument("project"); s.add_argument("task", nargs="?")
    s.add_argument("--no-enter", action="store_true", help="window mode: only draft the prompt")
    s.add_argument("--allow-current-project", action="store_true",
                   help="send to currently selected project if Antigravity does not know this project yet")
    s.set_defaults(fn=cmd_send)
    s = sub.add_parser("wait");    s.add_argument("project"); s.add_argument("task", nargs="?")
    s.add_argument("--timeout", type=int, default=45, help="minutes (default 45)"); s.set_defaults(fn=cmd_wait)
    s = sub.add_parser("answer");  s.add_argument("project"); s.add_argument("question_id"); s.add_argument("text", nargs="?")
    s.add_argument("--file", help="read the answer from a UTF-8 file, or '-' for stdin (use for multi-line answers)")
    s.set_defaults(fn=cmd_answer)
    s = sub.add_parser("release"); s.add_argument("project"); s.set_defaults(fn=cmd_release)
    s = sub.add_parser("status");  s.add_argument("project"); s.set_defaults(fn=cmd_status)
    a = ap.parse_args(argv)
    try:
        return a.fn(a)
    except Fail as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
