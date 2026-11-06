"""Resolve the Antigravity project id for a workspace folder.

Antigravity keeps conversation summaries in ~/.gemini/antigravity/agyhub_summaries_proto.pb
(protobuf, undocumented). Each conversation's metadata (field 17) holds the workspace URI
(field 7) and the project id (field 18). We scan it read-only and return the project id whose
workspace matches the given folder.

Limitation: a project is only discoverable after it has at least one conversation.

Usage: python -I agy_project.py <folder>   -> prints the id, or nothing (exit 1) if unknown
"""
import os
import sys
import urllib.parse

PB = os.path.join(os.path.expanduser("~"), ".gemini", "antigravity", "agyhub_summaries_proto.pb")
NON_PROJECT = {"outside-of-project", "default-cli-project"}


def _varint(b, i):
    r = s = 0
    while True:
        x = b[i]
        i += 1
        r |= (x & 0x7F) << s
        s += 7
        if x < 0x80:
            return r, i


def _fields(b):
    """Decode one protobuf message into (field, wiretype, value) tuples; None if invalid."""
    out, i = [], 0
    try:
        while i < len(b):
            key, i = _varint(b, i)
            f, wt = key >> 3, key & 7
            if f == 0:
                return None
            if wt == 0:
                v, i = _varint(b, i)
            elif wt == 1:
                v, i = b[i:i + 8], i + 8
            elif wt == 5:
                v, i = b[i:i + 4], i + 4
            elif wt == 2:
                n, i = _varint(b, i)
                v = b[i:i + n]
                if len(v) != n:
                    return None
                i += n
            else:
                return None
            out.append((f, wt, v))
        return out
    except IndexError:
        return None


def _sub(b, field):
    for f, wt, v in _fields(b) or []:
        if f == field and wt == 2:
            yield v


def _text(b, field):
    for v in _sub(b, field):
        try:
            return v.decode("utf-8")
        except UnicodeDecodeError:
            return None
    return None


def _norm(path_or_uri):
    p = path_or_uri
    if p.lower().startswith("file:"):
        p = urllib.parse.unquote(p[5:])
        p = p.lstrip("/") if os.name == "nt" else "/" + p.lstrip("/")  # file:///c:/x vs file:///home/x
    return os.path.normcase(os.path.normpath(p))


def project_ids():
    """Map normalized workspace path -> project id."""
    if not os.path.exists(PB):
        return {}
    with open(PB, "rb") as f:
        data = f.read()
    result = {}
    for entry in _sub(data, 1):
        for summary in _sub(entry, 2):
            for meta in _sub(summary, 17):
                ws, pid = _text(meta, 7), _text(meta, 18)
                if ws and pid and pid not in NON_PROJECT:
                    result[_norm(ws)] = pid
    return result


def resolve(folder):
    return project_ids().get(_norm(os.path.abspath(folder)))


if __name__ == "__main__":
    pid = resolve(sys.argv[1] if len(sys.argv) > 1 else os.getcwd())
    if pid:
        print(pid)
    sys.exit(0 if pid else 1)
