"""Structural check for the extension's JavaScript.

Node is not installed, so there is no linter and no build step to catch a
syntax error — the first sign would be the extension silently failing to load
in Chrome. This scans each file for balanced braces, parens and brackets while
correctly skipping comments, strings, regex literals and nested template
literals.

It is not a parser: it catches structural damage (a bad edit, a botched
splice), not type errors or typos in identifiers.

    python scripts/check_js.py extension/src/**/*.js
    python scripts/check_js.py            # defaults to every extension script
"""
import sys
from pathlib import Path


def scan(s, i, n, stop, state):
    """Scan code from i until `stop` char at this level (or end). Returns idx."""
    while i < n:
        c = s[i]
        # comments
        if c == "/" and i + 1 < n and s[i + 1] == "*":
            j = s.find("*/", i + 2)
            i = n if j == -1 else j + 2
            continue
        if c == "/" and i + 1 < n and s[i + 1] == "/":
            j = s.find("\n", i)
            i = n if j == -1 else j
            continue
        # regex literal: '/' in a position where a value is expected
        if c == "/" and state["prev"] in "(,=:[!&|?{};\n+-*%~^" :
            j, ok = i + 1, False
            while j < n:
                if s[j] == "\\":
                    j += 2
                    continue
                if s[j] == "[":
                    while j < n and s[j] != "]":
                        j += 2 if s[j] == "\\" else 1
                if s[j] == "/":
                    ok = True
                    break
                if s[j] == "\n":
                    break
                j += 1
            if ok:
                i = j + 1
                state["prev"] = "x"
                continue
        # strings
        if c in "\"'":
            j = i + 1
            while j < n:
                if s[j] == "\\":
                    j += 2
                    continue
                if s[j] == c:
                    break
                j += 1
            i = j + 1
            state["prev"] = "x"
            continue
        # template literal, with recursive ${ } handling
        if c == "`":
            j = i + 1
            while j < n:
                if s[j] == "\\":
                    j += 2
                    continue
                if s[j] == "`":
                    break
                if s[j] == "$" and j + 1 < n and s[j + 1] == "{":
                    j = scan(s, j + 2, n, "}", {"prev": "{"})
                    continue
                j += 1
            i = j + 1
            state["prev"] = "x"
            continue
        if c in "{([":
            state["depth"] = state.get("depth", 0)
            i = scan(s, i + 1, n, {"{": "}", "(": ")", "[": "]"}[c], {"prev": c})
            state["prev"] = "x"
            continue
        if c in "})]":
            if stop and c == stop:
                return i + 1
            raise SyntaxError(f"unexpected '{c}' at offset {i}")
        if not c.isspace():
            state["prev"] = c
        elif c == "\n":
            state["prev"] = "\n"
        i += 1
    if stop:
        raise SyntaxError(f"missing '{stop}' before end of file")
    return i


paths = sys.argv[1:]
if not paths:
    root = Path(__file__).resolve().parents[1] / "extension"
    paths = sorted(str(p) for p in root.rglob("*.js") if "node_modules" not in str(p))

failed = False
for path in paths:
    src = open(path, encoding="utf-8").read()
    try:
        scan(src, 0, len(src), None, {"prev": "\n"})
        print(f"  OK        {path}")
    except SyntaxError as e:
        line = src[: int(str(e).split()[-1])].count("\n") + 1 if "offset" in str(e) else "?"
        print(f"  PROBLEM   {path}: {e} (line {line})")
        failed = True

sys.exit(1 if failed else 0)
