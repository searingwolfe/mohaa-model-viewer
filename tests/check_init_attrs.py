#!/usr/bin/env python3
"""Check that MapApp.__init__ (mohaa_map_launcher.py) sets every attribute that
App.__init__ (mohaa_launcher.py) sets. MapApp repeats App's start-up instead of calling it,
so an attribute added to one and not the other shows up only as an AttributeError at run
time. Exit code 0 = in step, 1 = attributes missing (listed).

Usage: python tests/check_init_attrs.py"""
import ast
import os
import sys

BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin")


def init_attrs(path, cls):
    """Return the set of self.<name> attributes assigned in cls.__init__ in path."""
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == cls:
            for fn in node.body:
                if isinstance(fn, ast.FunctionDef) and fn.name == "__init__":
                    return {x.attr for x in ast.walk(fn)
                            if isinstance(x, ast.Attribute) and isinstance(x.value, ast.Name)
                            and x.value.id == "self" and isinstance(x.ctx, ast.Store)}
    raise SystemExit("class %s.__init__ not found in %s" % (cls, path))


def main():
    """Compare the two constructors; print the result; return the exit code."""
    a = init_attrs(os.path.join(BIN, "mohaa_launcher.py"), "App")
    b = init_attrs(os.path.join(BIN, "mohaa_map_launcher.py"), "MapApp")
    missing = sorted(a - b)
    if missing:
        print("MapApp.__init__ is missing: " + ", ".join(missing))
        return 1
    print("OK: MapApp.__init__ sets all %d attributes App.__init__ sets" % len(a))
    return 0


if __name__ == "__main__":
    sys.exit(main())
