#!/usr/bin/env python3
"""PreToolUse hook: make .claudeignore actually enforceable.

Claude Code does not natively read .claudeignore. This hook closes that gap:
it reads the repo-root .claudeignore and DENIES any Read / Grep / Glob tool
call whose target path matches an ignore pattern (gitignore-style syntax,
including negation with `!`). Anything not matched falls through to the normal
permission flow untouched (we never auto-allow).

Wired in .claude/settings.local.json under hooks.PreToolUse with the matcher
"Read|Grep|Glob". Stdlib only, so it runs under any Python on PATH.

Protocol: read the tool-call payload as JSON on stdin; to block, print a
PreToolUse "deny" decision as JSON on stdout and exit 0; to allow, print
nothing and exit 0.
"""

import json
import os
import re
import sys

GATED_TOOLS = ("Read", "Grep", "Glob")


def _translate(pattern):
    """Translate one gitignore glob body into a regex fragment.

    Operates on a path that is posix-style and relative to the repo root.
    ** spans path segments, * stays within a segment, ? is one non-slash char,
    and [...] character classes are preserved.
    """
    i, n = 0, len(pattern)
    out = []
    while i < n:
        c = pattern[i]
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif c == "*":
            out.append("[^/]*")
            i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        elif c == "[":
            j = i + 1
            if j < n and pattern[j] in ("!", "^"):
                j += 1
            if j < n and pattern[j] == "]":
                j += 1
            while j < n and pattern[j] != "]":
                j += 1
            if j >= n:  # unterminated class -> literal '['
                out.append(re.escape("["))
                i += 1
            else:
                inner = pattern[i + 1 : j]
                if inner.startswith("!"):
                    inner = "^" + inner[1:]
                out.append("[" + inner + "]")
                i = j + 1
        else:
            out.append(re.escape(c))
            i += 1
    return "".join(out)


class _Rule:
    __slots__ = ("regex", "negated")

    def __init__(self, line):
        self.negated = line.startswith("!")
        if self.negated:
            line = line[1:]
        line = line.rstrip("/")  # trailing slash = dir-only; we match dir + below
        anchored = "/" in line  # a slash anywhere (post-strip) anchors to root
        if line.startswith("/"):
            line = line[1:]
            anchored = True
        body = _translate(line)
        prefix = "^" if anchored else "^(?:.*/)?"
        # also match everything beneath a matched dir
        self.regex = re.compile(prefix + body + r"(?:/.*)?$")

    def matches(self, path):
        return self.regex.match(path) is not None


def _load_rules(ignore_path):
    rules = []
    try:
        with open(ignore_path, encoding="utf-8") as fh:
            for raw in fh:
                line = raw.rstrip("\n").rstrip("\r").rstrip()
                if not line or line.startswith("#"):
                    continue
                rules.append(_Rule(line))
    except FileNotFoundError:
        pass
    return rules


def _ignored(path, rules):
    """gitignore semantics: last matching rule wins; `!` un-ignores."""
    result = False
    for rule in rules:
        if rule.matches(path):
            result = not rule.negated
    return result


def _rel(project_dir, target):
    if not target:
        return None
    ap = target if os.path.isabs(target) else os.path.join(project_dir, target)
    try:
        rel = os.path.relpath(os.path.abspath(ap), project_dir)
    except ValueError:  # e.g. different drive on Windows
        return None
    if rel == ".." or rel.startswith(".." + os.sep):
        return None  # outside the repo -> not our concern
    return rel.replace(os.sep, "/")


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)  # unparseable input -> never interfere

    tool = payload.get("tool_name", "")
    if tool not in GATED_TOOLS:
        sys.exit(0)

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd()
    rules = _load_rules(os.path.join(project_dir, ".claudeignore"))
    if not rules:
        sys.exit(0)

    ti = payload.get("tool_input", {}) or {}
    # Read targets a file; Grep/Glob optionally narrow to a search root.
    target = ti.get("file_path") if tool == "Read" else ti.get("path")

    rel = _rel(project_dir, target)
    if rel and _ignored(rel, rules):
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": (
                            f".claudeignore blocks {tool} on '{rel}'. "
                            f"Edit .claudeignore (or add a '!' negation) to allow it."
                        ),
                    }
                }
            )
        )
        sys.exit(0)

    sys.exit(0)


if __name__ == "__main__":
    main()
