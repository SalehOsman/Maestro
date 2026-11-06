"""Deliver a prompt to the Antigravity agent app: open the deep link, bring the window to the
front, and press Enter, but only when the foreground window really is Antigravity.

Platforms
  Windows       deep link via os.startfile, window and keys via Win32 (ctypes)      tested
  macOS         `open`, then AppleScript (System Events) for focus and Return       untested
  Linux / X11   `xdg-open`, then `xdotool` for focus and Return                     untested
  Linux / Wayland  deep link only; Enter must be pressed by hand (Wayland forbids it)

send_prompt() returns "sent", or "drafted" with a reason when only the text was placed.
"""
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.parse

DRAFT_SETTLE = 2.0   # seconds for Antigravity to put the prompt into its input box
FOCUS_SETTLE = 0.6
FOCUS_TIMEOUT = 4.0  # seconds to wait for Antigravity to become the foreground window


def build_url(prompt, project_id=None):
    url = "antigravity://open?prompt=" + urllib.parse.quote(prompt, safe="")
    if project_id:
        url += "&project=" + urllib.parse.quote(project_id, safe="")
    return url


def open_url(url):
    if sys.platform == "win32":
        os.startfile(url)  # noqa: S606 - a registered protocol handler, no shell
    elif sys.platform == "darwin":
        subprocess.run(["open", url], check=True)
    else:
        subprocess.run(["xdg-open", url], check=True)


# ---------- Windows ----------

def _win_force_foreground(user32, kernel32, hwnd):
    """Bring hwnd to the front despite Windows' foreground lock.

    Windows only lets the process that owns the foreground window (or one attached to its input
    queue) change the foreground. So attach to the current foreground thread, raise the window,
    then detach. This is the documented AttachThreadInput approach; no keys are sent.
    """
    fg = user32.GetForegroundWindow()
    fg_thread = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    me = kernel32.GetCurrentThreadId()
    attached = bool(fg_thread) and fg_thread != me and user32.AttachThreadInput(me, fg_thread, True)
    try:
        user32.BringWindowToTop(hwnd)
        user32.ShowWindow(hwnd, 5)  # SW_SHOW
        user32.SetForegroundWindow(hwnd)
        user32.SetFocus(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(me, fg_thread, False)


def _win_press_enter():
    import ctypes
    from ctypes import wintypes

    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    exe_suffix = os.path.join("programs", "antigravity", "antigravity.exe")

    def exe_of(pid):
        h = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(1024)
            size = wintypes.DWORD(len(buf))
            ok = kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size))
            return buf.value.lower() if ok else ""
        finally:
            kernel32.CloseHandle(h)

    def pid_of(hwnd):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return pid.value

    def is_agy(hwnd):
        return exe_of(pid_of(hwnd)).endswith(exe_suffix)

    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def enum(hwnd, _):
        if user32.IsWindowVisible(hwnd) and user32.GetWindowTextLengthW(hwnd) > 0 and is_agy(hwnd):
            found.append(hwnd)
            return False
        return True

    user32.EnumWindows(enum, 0)
    if not found:
        return "drafted", "the Antigravity window was not found; press Enter in Antigravity"
    hwnd = found[0]
    time.sleep(DRAFT_SETTLE)
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    # The deep link itself usually brings Antigravity forward, but that can take a few seconds
    # (longer right after Antigravity starts). Keep asking and checking before giving up.
    deadline = time.monotonic() + FOCUS_TIMEOUT
    while not is_agy(user32.GetForegroundWindow()):
        if time.monotonic() >= deadline:
            return "drafted", "Antigravity is not in the foreground; press Enter in Antigravity"
        _win_force_foreground(user32, kernel32, hwnd)
        time.sleep(FOCUS_SETTLE)
    time.sleep(0.3)
    VK_RETURN, KEYUP = 0x0D, 0x0002
    user32.keybd_event(VK_RETURN, 0, 0, 0)
    user32.keybd_event(VK_RETURN, 0, KEYUP, 0)
    return "sent", ""


# ---------- macOS (untested) ----------

def _mac_press_enter():
    def osa(script):
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
        return r.returncode, r.stdout.strip(), r.stderr.strip()

    time.sleep(DRAFT_SETTLE)
    osa('tell application "Antigravity" to activate')
    time.sleep(FOCUS_SETTLE)
    code, front, err = osa('tell application "System Events" to get name of first application process whose frontmost is true')
    if code != 0:
        return "drafted", f"cannot query the front app ({err}); grant Accessibility permission to your terminal"
    if front.lower() != "antigravity":
        return "drafted", f"front app is '{front}', not Antigravity; press Return in Antigravity"
    code, _, err = osa('tell application "System Events" to key code 36')  # Return
    if code != 0:
        return "drafted", f"cannot send Return ({err}); grant Accessibility permission to your terminal"
    return "sent", ""


# ---------- Linux (untested) ----------

def _linux_press_enter():
    if os.environ.get("WAYLAND_DISPLAY") and not os.environ.get("DISPLAY"):
        return "drafted", "Wayland does not allow sending keys; press Enter in Antigravity"
    if not shutil.which("xdotool"):
        return "drafted", "xdotool is not installed; press Enter in Antigravity (or install xdotool)"

    def xdo(*args):
        r = subprocess.run(["xdotool", *args], capture_output=True, text=True)
        return r.returncode, r.stdout.strip()

    time.sleep(DRAFT_SETTLE)
    code, ids = xdo("search", "--onlyvisible", "--class", "antigravity")
    wins = [w for w in ids.split() if w]
    if code != 0 or not wins:
        return "drafted", "the Antigravity window was not found; press Enter in Antigravity"
    xdo("windowactivate", "--sync", wins[0])
    time.sleep(FOCUS_SETTLE)
    _, active = xdo("getactivewindow")
    _, cls = xdo("getwindowclassname", active) if active else (1, "")
    if "antigravity" not in cls.lower():
        return "drafted", "Antigravity is not in the foreground; press Enter in Antigravity"
    xdo("key", "--clearmodifiers", "Return")
    return "sent", ""


def notify(title, message):
    """Best-effort desktop notification; never raises, never blocks."""
    try:
        if sys.platform == "win32":
            ps = ("Add-Type -AssemblyName System.Windows.Forms; $n = New-Object System.Windows.Forms.NotifyIcon; "
                  "$n.Icon = [System.Drawing.SystemIcons]::Information; $n.Visible = $true; "
                  "$n.ShowBalloonTip(15000, $env:MAESTRO_N_TITLE, $env:MAESTRO_N_TEXT, 'Info'); "
                  "Start-Sleep -Seconds 16; $n.Dispose()")
            env = {**os.environ, "MAESTRO_N_TITLE": title, "MAESTRO_N_TEXT": message}  # no quoting issues
            subprocess.Popen(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps], env=env,
                             creationflags=0x08000000, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif sys.platform == "darwin":
            script = f'display notification {json.dumps(message)} with title {json.dumps(title)}'
            subprocess.Popen(["osascript", "-e", script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif shutil.which("notify-send"):
            subprocess.Popen(["notify-send", title, message], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def send_prompt(prompt, project_id=None, press_enter=True):
    open_url(build_url(prompt, project_id))
    if not press_enter:
        return "drafted", "Enter not pressed (--no-enter)"
    if sys.platform == "win32":
        return _win_press_enter()
    if sys.platform == "darwin":
        return _mac_press_enter()
    return _linux_press_enter()
