#!/usr/bin/env python3
"""Validate specialist finding fragments against finding_fragment.json.

Usage:
  python3 validate_fragment.py <fragment.json> [<fragment2.json> ...]
      [--schema <finding_fragment.json>] [--fix]

Validates every positional fragment argument in one pass (the orchestrator's
step-6 contract); a second positional argument is a second fragment, never an
output path. Exit 0 with one "valid" line per file; exit 1 listing errors.

--fix applies safe mechanical corrections in place and re-validates:
  - result-level "affected_urls" renamed to "urls" (the report-side name does
    not belong in a fragment);
  - "observations: null" dropped (the key is object-or-absent);
  - missing top-level "mode" defaulted to "snapshot" (composed runs; a
    standalone URL-mode run must declare "url" itself, never rely on this).
Applied fixes are printed; anything else still fails. Stdlib only (uses the
vendored draft-07 subset validator in build_report.py).
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from build_report import load_json, validate  # noqa: E402


def apply_fixes(frag):
    fixed = []
    for r in frag.get("results", []):
        if isinstance(r, dict) and "affected_urls" in r and "urls" not in r:
            r["urls"] = r.pop("affected_urls")
            fixed.append("%s: affected_urls -> urls" % r.get("check_id", "?"))
        if isinstance(r, dict) and r.get("observations") is None and "observations" in r:
            del r["observations"]
            fixed.append("%s: dropped null observations" % r.get("check_id", "?"))
    if "mode" not in frag:
        frag["mode"] = "snapshot"
        fixed.append("mode defaulted to snapshot")
    return fixed


def check_one(frag_path, schema, do_fix):
    try:
        frag = load_json(frag_path)
    except (OSError, ValueError) as e:
        return 1, ["%s INVALID (unreadable): %s" % (frag_path, str(e)[:200])]
    if do_fix and isinstance(frag, dict):
        for line in apply_fixes(frag):
            print("  fixed %s: %s" % (frag_path, line))
        try:
            with open(frag_path, "w", encoding="utf-8") as fh:
                json.dump(frag, fh, indent=2, ensure_ascii=False)
                fh.write("\n")
        except OSError as e:
            return 1, ["%s INVALID (unwritable): %s" % (frag_path, str(e)[:200])]
    errs = validate(frag, schema)
    if errs:
        out = ["%s INVALID:" % frag_path]
        out += ["  - %s" % e[:220] for e in errs[:10]]
        return 1, out
    return 0, ["valid: %s (%d results, %d not_evaluated, %d opportunities)"
               % (frag_path, len(frag.get("results", [])),
                  len(frag.get("not_evaluated", [])), len(frag.get("opportunities", [])))]


def main(argv):
    args = [a for a in argv[1:] if a not in ("-h", "--help")]
    do_fix = "--fix" in args
    args = [a for a in args if a != "--fix"]
    if "--schema" in args:
        i = args.index("--schema")
        try:
            schema_path = args.pop(i + 1)
        except IndexError:
            print("usage: validate_fragment.py <fragment.json> [...] [--fix]")
            return 2
        args.pop(i)
    else:
        schema_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "..", "references", "finding_fragment.json")
    if not args or "-h" in argv or "--help" in argv:
        print("usage: validate_fragment.py <fragment.json> [...] [--fix]")
        return 2
    try:
        schema = load_json(schema_path)
    except (OSError, ValueError) as e:
        print("INVALID (schema unreadable): %s" % str(e)[:200])
        return 1
    rc = 0
    for frag_path in args:
        code, lines = check_one(frag_path, schema, do_fix)
        for line in lines:
            print(line)
        rc = rc or code
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv))
