#!/usr/bin/env python3
"""Validate one specialist finding fragment against finding_fragment.json.

Usage:
  python3 validate_fragment.py <fragment.json> [--schema <finding_fragment.json>]

Exit 0 with "valid" on success; exit 1 listing the first errors otherwise.
Stdlib only (uses the vendored draft-07 subset validator in build_report.py).
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from build_report import load_json, validate  # noqa: E402


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(__doc__.strip().splitlines()[2].strip())
        return 2
    frag_path = argv[1]
    if "--schema" in argv:
        schema_path = argv[argv.index("--schema") + 1]
    else:
        schema_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "..", "references", "finding_fragment.json")
    try:
        frag = load_json(frag_path)
    except (OSError, ValueError) as e:
        print("INVALID (unreadable): %s" % str(e)[:200])
        return 1
    try:
        schema = load_json(schema_path)
    except (OSError, ValueError) as e:
        print("INVALID (schema unreadable): %s" % str(e)[:200])
        return 1
    errs = validate(frag, schema)
    if errs:
        print("INVALID:")
        for e in errs[:10]:
            print("  - %s" % e[:220])
        return 1
    print("valid: %s (%d results, %d not_evaluated, %d opportunities)"
          % (frag_path, len(frag.get("results", [])),
             len(frag.get("not_evaluated", [])), len(frag.get("opportunities", []))))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
