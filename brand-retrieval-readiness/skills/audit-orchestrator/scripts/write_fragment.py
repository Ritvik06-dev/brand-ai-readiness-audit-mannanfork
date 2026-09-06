#!/usr/bin/env python3
"""Canonical fragment writer: validates (and safe-fixes) a finding fragment.

The judgment skills author the judgment content as JSON; this script owns the
mechanics - load, schema-validate, apply safe mechanical fixes, write back,
print one line. Replaces per-run hand-written builder scripts (a recurring
turn cost and the source of heredoc/NameError failures in traced runs).

Usage:
  python3 write_fragment.py --in <draft.json> [--out <final path>] [--schema <path>]

  --in     the drafted fragment (JSON). Required.
  --out    where to write the validated fragment. Default: overwrite --in.
  --schema finding_fragment.json path; resolved from the marketplace root when
           omitted.

Exit 0 = written and valid. Exit 1 = INVALID after fixes (the JSON is still
written; run again after hand-fixing what the fixer could not).
"""
import argparse
import json
import os
import sys


def resolve_schema(explicit):
    if explicit:
        return explicit
    here = os.path.dirname(os.path.abspath(__file__))
    for cand in (os.path.join(here, "..", "references", "finding_fragment.json"),):
        if os.path.exists(cand):
            return cand
    cur = here
    for _ in range(6):
        for name in ("marketplace.json", os.path.join(".agents", "marketplace.json")):
            mp = os.path.join(cur, name)
            if os.path.exists(mp):
                cand = os.path.join(cur, "skills", "audit-orchestrator",
                                    "references", "finding_fragment.json")
                if os.path.exists(cand):
                    return cand
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return None


SAFE_FIXES = [
    # (description, mutator) - applied in order, each reported when it fires.
    ("drop unknown top-level keys", lambda f: {k: v for k, v in f.items()
        if k in ("skill_id", "mode", "generated_at", "results", "opportunities", "not_evaluated")}),
]


def fix_results(frag, notes):
    results = frag.get("results")
    if not isinstance(results, list):
        return
    seen = set()
    kept = []
    for r in results:
        if not isinstance(r, dict) or not r.get("check_id"):
            notes.append("dropped result without check_id")
            continue
        cid = r["check_id"]
        if cid in seen:
            notes.append("dropped duplicate result %s" % cid)
            continue
        seen.add(cid)
        # results[] gates must live in results, not the top-level not_evaluated
        ne = frag.get("not_evaluated")
        if isinstance(ne, list) and any(isinstance(x, dict) and x.get("check_id") == cid for x in ne):
            notes.append("%s listed in both results and not_evaluated; kept the results verdict" % cid)
            frag["not_evaluated"] = [x for x in ne if not (isinstance(x, dict) and x.get("check_id") == cid)]
        obs = r.get("observations")
        if not isinstance(obs, dict):
            r["observations"] = {}
        for k, v in list(r.items()):
            if k not in ("check_id", "gate", "observations", "urls", "affected_urls",
                         "evidence_quality", "candidate_finding", "evidence"):
                r["observations"]["_%s" % k] = v
                del r[k]
                notes.append("%s: moved unknown key %r into observations" % (cid, k))
        kept.append(r)
    frag["results"] = kept


def main(argv=None):
    ap = argparse.ArgumentParser(description="Validate + safe-fix a finding fragment.")
    ap.add_argument("--in", dest="infile", required=True)
    ap.add_argument("--out", dest="outfile")
    ap.add_argument("--schema", dest="schema")
    args = ap.parse_args(argv)

    try:
        frag = json.load(open(args.infile, encoding="utf-8"))
    except (OSError, ValueError) as e:
        print("INVALID: unreadable draft (%s)" % e)
        return 1
    if not isinstance(frag, dict) or not frag.get("skill_id"):
        print("INVALID: draft has no skill_id")
        return 1

    notes = []
    for desc, mut in SAFE_FIXES:
        fixed = mut(dict(frag))
        if fixed != frag:
            notes.append(desc)
        frag = fixed
    fix_results(frag, notes)
    frag.setdefault("generated_at", "")

    out = args.outfile or args.infile
    try:
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(frag, fh, indent=1, ensure_ascii=False)
            fh.write("\n")
    except OSError as e:
        print("INVALID: cannot write %s (%s)" % (out, e))
        return 1

    validator = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "validate_fragment.py")
    cmd = [sys.executable, validator, out]
    schema = args.schema or resolve_schema(None)
    if schema:
        cmd += ["--schema", schema]
    rc = subprocess_val(cmd)
    if rc == 0:
        print("valid: %s%s" % (out, (" (%s)" % "; ".join(notes)) if notes else ""))
        return 0
    print("INVALID after fixes: validate_fragment.py rejected %s" % out)
    return 1


def subprocess_val(cmd):
    import subprocess
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if p.returncode != 0 and p.stdout.strip():
            print(p.stdout.strip()[:400])
        return p.returncode
    except Exception as e:  # noqa: BLE001
        print("validator error: %s" % e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
