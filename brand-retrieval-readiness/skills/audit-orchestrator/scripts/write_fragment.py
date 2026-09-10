#!/usr/bin/env python3
"""Canonical fragment writer: validates (and safe-fixes) a finding fragment.

The judgment skills author the judgment content as JSON; this script owns the
mechanics - load, schema-validate, apply safe mechanical fixes, write back,
print one line. Replaces per-run hand-written builder scripts (a recurring
turn cost and the source of heredoc/NameError failures in traced runs).

Two input shapes. Prefer --verdicts.

  python3 write_fragment.py --verdicts --in <verdicts.json> \
      --excerpt audit/excerpts/<skill>.json --out audit/findings/<skill>.json

VERDICTS (recommended): one flat entry per check. You supply a gate and, only
for a finding, prose. The script assembles the nested result, fills in the
observations the collector already measured, sets evidence_quality and affected
surfaces from the check catalog, and records every catalog check you did not
mention as not_evaluated - silence is never a pass.

  {"skill_id": "referral-experience-audit",
   "verdicts": [
     {"check": "REF-SOFT-404",   "gate": "pass"},
     {"check": "REF-PERF-RISK",  "gate": "finding",
      "severity": "low", "confidence": "medium",
      "title": "Product pages ship render-blocking scripts in <head>",
      "evidence": "29 render-blocking head scripts on 5/8 sampled pages.",
      "why": "...", "fix": "...", "verify": "...",
      "owner": "theme", "effort": "small",
      "urls": ["https://example.com/p/1"]},
     {"check": "REF-COLLAPSED-ANSWER", "gate": "not_evaluated",
      "reason": "no browser: default-open state unconfirmed"}],
   "opportunities": []}

Only `check` and `gate` are required. severity, confidence, title, evidence and
affected_surfaces fall back to the catalog and the measured relay when omitted.

RAW (still supported): --in is already a full fragment; it is validated and
safe-fixed, not assembled.

  --in       the verdicts file, or a full drafted fragment. Required.
  --verdicts treat --in as verdicts and assemble.
  --excerpt  that skill's excerpt, for --verdicts (supplies measured observations).
  --out      where to write. Default: overwrite --in.
  --schema   finding_fragment.json path; resolved from the marketplace root when omitted.

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
        # The merge reads urls only on a finding (it becomes affected_urls); on a
        # pass or a not_evaluated it is authored output nothing ever reads, and
        # on a wide sample that is the largest single block of wasted tokens in
        # the fragment. Drop it rather than asking the author to remember.
        if r.get("gate") != "finding" and r.get("urls"):
            n = len(r["urls"])
            del r["urls"]
            notes.append("%s: dropped %d unread urls from a %s result"
                         % (cid, n, r.get("gate")))
        for k, v in list(r.items()):
            if k not in ("check_id", "gate", "observations", "urls", "affected_urls",
                         "evidence_quality", "candidate_finding", "evidence"):
                r["observations"]["_%s" % k] = v
                del r[k]
                notes.append("%s: moved unknown key %r into observations" % (cid, k))
        kept.append(r)
    frag["results"] = kept


def resolve_catalog(orch_dir):
    cand = os.path.join(orch_dir, "..", "references", "check_catalog.json")
    return cand if os.path.exists(cand) else None


VERDICT_PROSE = (("title", "title"), ("evidence", "evidence"),
                 ("why", "why_it_matters"), ("severity", "severity"),
                 ("confidence", "confidence"))
ACTION_PROSE = (("fix", "summary"), ("priority", "priority"), ("effort", "effort"),
                ("owner", "owner"), ("verify", "acceptance_test"))


def assemble_from_verdicts(verdicts_doc, excerpt, catalog, notes):
    """One flat line per check in, a schema-shaped fragment out.

    The judgment is a gate plus, for findings, prose. Everything else - the
    check's evidence grade, its affected surfaces, and the observations the
    collector already measured - is assembled here. Hand-typing those was ~70%
    of a judgment specialist's wall clock and the only source of schema errors.
    """
    # A mis-keyed verdicts file ({"checks": [...]}) used to assemble silently into
    # a fragment where every check was not_evaluated - a wrong answer that looked
    # like a clean run. Refuse instead, and name the key that was found.
    if not isinstance(verdicts_doc.get("verdicts"), list):
        wrong = [k for k in ("checks", "results", "verdict", "entries", "gates")
                 if isinstance(verdicts_doc.get(k), list)]
        raise ValueError(
            "verdicts file has no top-level \"verdicts\" array%s. Expected shape:\n"
            '  {"skill_id": "<this skill>", "verdicts": [{"check": "X-Y", "gate": "pass"}]}'
            % (" (found %r instead)" % wrong[0] if wrong else ""))
    skill_id = verdicts_doc.get("skill_id") or (excerpt or {}).get("skill_id")
    if not skill_id:
        raise ValueError('verdicts file has no top-level "skill_id" and no --excerpt '
                         "to take it from")
    by_check = {c["check_id"]: c for c in (catalog or {}).get("checks", [])
                if c.get("skill_id") == skill_id}
    measured = ((excerpt or {}).get("extras") or {}).get("measured") or {}
    results, ne = [], []
    seen = set()
    for v in verdicts_doc.get("verdicts", []):
        cid = v.get("check") or v.get("check_id")
        if not cid or cid in seen:
            notes.append("skipped verdict without a check id" if not cid
                         else "dropped duplicate verdict %s" % cid)
            continue
        seen.add(cid)
        if by_check and cid not in by_check:
            notes.append("%s is not a %s check; left for the merge to lint" % (cid, skill_id))
        gate = v.get("gate")
        if gate not in ("finding", "pass", "not_evaluated"):
            notes.append("%s: gate %r is not finding/pass/not_evaluated" % (cid, gate))
            gate = "not_evaluated"
        if gate == "not_evaluated":
            ne.append({"check_id": cid,
                       "reason": v.get("reason") or "not judged in this run"})
            continue
        meas = measured.get(cid) or {}
        obs = dict(meas.get("observations") or {})
        obs.update(v.get("observations") or {})
        if meas.get("evidence") and "measured" not in obs:
            obs["measured"] = meas["evidence"]
        res = {"check_id": cid, "gate": gate}
        if obs:
            res["observations"] = obs
        res["evidence_quality"] = (v.get("evidence_quality")
                                   or (by_check.get(cid) or {}).get("evidence_required")
                                   or "semantic-judgment")
        if gate == "finding":
            cand = {}
            for src, dst in VERDICT_PROSE:
                if v.get(src):
                    cand[dst] = v[src]
            cand.setdefault("evidence", meas.get("evidence", ""))
            cand.setdefault("severity", ((by_check.get(cid) or {}).get("severity_band")
                                         or ["medium"])[0])
            cand.setdefault("confidence", "medium")
            cand.setdefault("title", (by_check.get(cid) or {}).get("pattern_template", cid))
            action = {}
            for src, dst in ACTION_PROSE:
                if v.get(src):
                    action[dst] = v[src]
            action.setdefault("summary", v.get("fix") or "")
            action.setdefault("priority", cand["severity"])
            cand["suggested_action"] = action
            surfaces = v.get("affected_surfaces") or \
                (by_check.get(cid) or {}).get("affected_surfaces_default")
            if surfaces:
                cand["affected_surfaces"] = surfaces
            res["candidate_finding"] = cand
            if v.get("urls"):
                res["urls"] = v["urls"]
        results.append(res)
    # Every catalog check this skill owns that no verdict mentioned is honestly
    # not_evaluated - silence is never a pass.
    for cid in by_check:
        if cid not in seen:
            ne.append({"check_id": cid, "reason": "no verdict submitted for this check"})
            notes.append("%s: no verdict submitted; recorded not_evaluated" % cid)
    frag = {"skill_id": skill_id, "mode": verdicts_doc.get("mode", "snapshot"),
            "results": results}
    if ne:
        frag["not_evaluated"] = ne
    if verdicts_doc.get("opportunities"):
        frag["opportunities"] = verdicts_doc["opportunities"]
    return frag


def main(argv=None):
    ap = argparse.ArgumentParser(description="Validate + safe-fix a finding fragment.")
    ap.add_argument("--in", dest="infile", required=True)
    ap.add_argument("--verdicts", action="store_true",
                    help="--in is a flat verdicts file (one line per check); assemble the "
                         "nested fragment from it plus the excerpt's measured observations")
    ap.add_argument("--excerpt", help="that skill's excerpt, for --verdicts")
    ap.add_argument("--complete-gate", metavar="CHECK_ID",
                    help="finish one prepared semantic gate in an existing fragment "
                         "(e.g. ENT-AMBIGUOUS-NAME) instead of assembling a new one")
    ap.add_argument("--gate", choices=("finding", "pass", "not_evaluated"),
                    help="the verdict for --complete-gate")
    ap.add_argument("--reason", help="1-3 sentences recorded as observations.model_completion")
    ap.add_argument("--out", dest="outfile")
    ap.add_argument("--schema", dest="schema")
    args = ap.parse_args(argv)

    try:
        frag = json.load(open(args.infile, encoding="utf-8"))
    except (OSError, ValueError) as e:
        print("INVALID: unreadable draft (%s)" % e)
        return 1
    notes = []
    if args.complete_gate:
        # The one gate the orchestrator asks the model to finish by hand. Without
        # this it was the only nested-JSON hand-edit in a marketplace whose whole
        # design principle is that a script owns the shape.
        if not args.gate or not args.reason:
            print("INVALID: --complete-gate needs both --gate and --reason")
            return 1
        target = None
        for r in frag.get("results", []):
            if r.get("check_id") == args.complete_gate:
                target = r
                break
        if target is None:
            print("INVALID: %s is not a result in %s" % (args.complete_gate, args.infile))
            return 1
        target["gate"] = args.gate
        target.setdefault("observations", {})["model_completion"] = args.reason
        if args.gate == "finding" and "candidate_finding" not in target:
            print("INVALID: promoting %s to a finding needs a candidate_finding; "
                  "use --verdicts for that check instead" % args.complete_gate)
            return 1
        if args.gate != "finding":
            target.pop("candidate_finding", None)
        notes.append("%s completed as %s" % (args.complete_gate, args.gate))
    if args.verdicts:
        excerpt = None
        if args.excerpt:
            try:
                excerpt = json.load(open(args.excerpt, encoding="utf-8"))
            except (OSError, ValueError) as e:
                print("INVALID: unreadable --excerpt (%s)" % e)
                return 1
        catalog = None
        cpath = resolve_catalog(os.path.dirname(os.path.abspath(__file__)))
        if cpath:
            try:
                catalog = json.load(open(cpath, encoding="utf-8"))
            except (OSError, ValueError):
                catalog = None
        try:
            frag = assemble_from_verdicts(frag, excerpt, catalog, notes)
        except ValueError as e:
            print("INVALID: %s" % e)
            return 1
    if not isinstance(frag, dict) or not frag.get("skill_id"):
        print("INVALID: draft has no skill_id")
        return 1

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
