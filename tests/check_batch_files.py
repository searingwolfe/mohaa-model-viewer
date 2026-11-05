#!/usr/bin/env python3
"""Byte-level checks for every .bat file in the project (hardened coding practices):
  * CRLF on every line (no lone LF), ASCII only;
  * no '>' inside a double-quoted string (cmd can still treat it as redirection),
    unless escaped as ^>;
  * exactly one 'pause' and no 'timeout' (single pause at the very end).
Exit 0 = all pass. Usage: python tests/check_batch_files.py"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def quoted_gt(line):
    """Columns of unescaped '>' characters inside double quotes on one line."""
    out, inq, prev = [], False, ""
    for i, ch in enumerate(line):
        if ch == '"':
            inq = not inq
        elif ch == ">" and inq and prev != "^":
            out.append(i)
        prev = ch
    return out


def check(path):
    """Return a list of problems found in one .bat file."""
    b = open(path, "rb").read()
    probs = []
    crlf = b.count(b"\r\n")
    lone = b.count(b"\n") - crlf
    if lone:
        probs.append("%d lone LF line ending(s)" % lone)
    try:
        text = b.decode("ascii")
    except UnicodeDecodeError as e:
        probs.append("non-ASCII byte: %s" % e)
        text = b.decode("latin-1")
    pauses = 0
    for n, line in enumerate(text.split("\r\n"), 1):
        s = line.strip()
        if re.match(r"(?i)rem\b|::", s):
            continue
        if re.match(r"(?i)pause\b", s):
            pauses += 1
        if re.search(r"(?i)\btimeout\b", s):
            probs.append("line %d: timeout" % n)
        for col in quoted_gt(line):
            probs.append("line %d col %d: '>' inside quotes" % (n, col + 1))
    if pauses != 1:
        probs.append("%d pause commands (want exactly 1)" % pauses)
    return probs, crlf


def main():
    """Check every .bat; print a report; return the exit code."""
    bad = 0
    for dp, _dn, fs in os.walk(ROOT):
        if ".git" in dp or "libs" in os.path.basename(dp):
            continue
        for f in sorted(fs):
            if f.lower().endswith(".bat"):
                p = os.path.join(dp, f)
                probs, crlf = check(p)
                print("%-45s %4d CRLF  %s" % (os.path.relpath(p, ROOT), crlf, "OK" if not probs else "FAIL"))
                for x in probs:
                    print("    " + x)
                bad += bool(probs)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
