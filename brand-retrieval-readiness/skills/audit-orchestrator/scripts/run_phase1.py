#!/usr/bin/env python3
"""Phase-1 runner: snapshot + scripted specialists in one call.

Runs collect_snapshot.py, then probe_access.py, analyze_representation.py and
check_entities.py over the snapshot, validates the fragments, and prints one
status table. Pure composition for turn-count: the model makes one call and
reads one table instead of run-read-act cycling per script. No behavior change
- every script keeps its CLI and runs unchanged; the merge still owns ids,
dedup, severity, and the report.

Failure semantics: a specialist that fails or writes no fragment contributes
not_evaluated (its row says so); only a fatal snapshot aborts with exit 1.
Every directory is created here - a missing dir never fails a run.

Usage:
  python3 run_phase1.py --url <URL> --out-dir ./audit
      --site-type saas,ecommerce --capabilities web_fetch[,web_search][,browser][,subagents]
      [--max-pages N] [--deadline S] [--allow-private]
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

SPECIALISTS = (
    ("access-discovery-audit", "access-discovery-audit/scripts/probe_access.py"),
    ("representation-parity-audit",
     "representation-parity-audit/scripts/analyze_representation.py"),
    ("entity-consistency-audit", "entity-consistency-audit/scripts/check_entities.py"),
)


def resolve_scripts(here):
    """Sibling skill dirs first, else the marketplace manifest walk. Never raises."""
    sib = os.path.normpath(os.path.join(here, "..", ".."))
    found = [(sid, os.path.join(sib, rel)) for sid, rel in SPECIALISTS]
    if all(os.path.exists(p) for _, p in found):
        return found
    cur = os.path.abspath(here)
    for _ in range(6):
        for name in ("marketplace.json", os.path.join(".agents", "marketplace.json")):
            mp = os.path.join(cur, name)
            if os.path.exists(mp):
                try:
                    manifest = json.load(open(mp))
                    by_id = {s["id"]: s.get("path") for s in manifest.get("skills", [])}
                    root = os.path.dirname(mp)
                    out = []
                    for sid, rel in SPECIALISTS:
                        mp_rel = by_id.get(sid)
                        p = (os.path.join(root, mp_rel, "scripts", os.path.basename(rel))
                             if mp_rel else os.path.join(sib, rel))
                        out.append((sid, p if os.path.exists(p) else None))
                    return out
                except (OSError, ValueError, KeyError):
                    pass
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return [(sid, (p if os.path.exists(p) else None)) for sid, p in found]


def run(cmd, timeout):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or ""), (p.stderr or "")
    except Exception as e:  # noqa: BLE001 - record, never raise
        return 99, "", "runner: %s" % e


def summarize_fragment(path):
    try:
        frag = json.load(open(path))
    except (OSError, ValueError):
        return None
    gates: dict = {}
    for r in frag.get("results", []):
        gates[r.get("gate", "?")] = gates.get(r.get("gate", "?"), 0) + 1
    findings = [{"check_id": r.get("check_id"),
                 "title": (r.get("candidate_finding") or {}).get("title", "")[:90]}
                for r in frag.get("results", []) if r.get("gate") == "finding"]
    return (len(findings),
            gates.get("pass", 0),
            len(frag.get("not_evaluated", [])) + gates.get("not_evaluated", 0),
            findings)


def inject_extras(out_dir, frag_paths):
    """Relay phase-1 deterministic facts into the judgment excerpts so the model
    never re-reads phase-1 fragments for pairing, and never re-derives the
    boilerplate gate numbers (analyze_representation already measured them)."""
    phase1_findings, extraction_obs, extraction_gate = [], None, None
    for frag in frag_paths:
        try:
            data = json.load(open(frag))
        except (OSError, ValueError):
            continue
        for r in data.get("results", []):
            if r.get("gate") == "finding":
                phase1_findings.append({"skill_id": data.get("skill_id"),
                                        "check_id": r.get("check_id"),
                                        "title": (r.get("candidate_finding") or {}).get("title", "")[:110]})
            if r.get("check_id") == "REP-EXTRACTION-LOSS":
                extraction_obs = r.get("observations") or {}
                extraction_gate = r.get("gate")
    if not phase1_findings and not extraction_obs:
        return
    phase1_findings = [{k: v for k, v in f.items() if v} for f in phase1_findings]
    for name in ("answer-coverage-audit", "freshness-consistency-audit",
                 "referral-experience-audit"):
        path = os.path.join(out_dir, "excerpts", "%s.json" % name)
        try:
            exc = json.load(open(path))
        except (OSError, ValueError):
            continue
        extras = exc.setdefault("extras", {})
        extras["phase1_findings"] = phase1_findings
        if name == "answer-coverage-audit" and extraction_obs:
            extras["boilerplate"] = {
                "pages_sharing_preamble": extraction_obs.get("pages_sharing_preamble",
                    extraction_obs.get("pages_sharing_long_preamble", 0)),
                "preamble_chars": extraction_obs.get("preamble_chars", 0),
                "median_unique_content_offset": extraction_obs.get("median_unique_content_offset", 0),
                "rep_extraction_loss_gate": extraction_gate or "pass",
                "note": "measured by analyze_representation.py (REP-EXTRACTION-LOSS); "
                        "the ANS-BOILERPLATE-DROWNING gate is shared-preamble pages >= half "
                        "the sample AND median offset > 1500 chars"}
        try:
            json.dump(exc, open(path, "w"), indent=1, ensure_ascii=False)
        except OSError:
            pass


def main(argv=None):
    ap = argparse.ArgumentParser(description="Phase 1: snapshot + scripted specialists, one call.")
    ap.add_argument("--url", required=True)
    ap.add_argument("--out-dir", default="audit")
    ap.add_argument("--site-type", default="")
    ap.add_argument("--capabilities", default="web_fetch")
    ap.add_argument("--max-pages", type=int, default=8)
    ap.add_argument("--deadline", type=int, default=120)
    ap.add_argument("--allow-private", action="store_true")
    args = ap.parse_args(argv)

    here = os.path.dirname(os.path.abspath(__file__))
    out_dir = os.path.abspath(args.out_dir)
    frag_dir = os.path.join(out_dir, "findings")
    os.makedirs(frag_dir, exist_ok=True)
    snap = os.path.join(out_dir, "snapshot.json")
    t0 = time.monotonic()
    started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print("phase1 wall-clock: started %s (shed off-site probes if more than 210 s "
          "have elapsed when wave 2 begins)" % started)

    cmd = [sys.executable, os.path.join(here, "collect_snapshot.py"),
           "--url", args.url, "--out", snap, "--site-type", args.site_type,
           "--capabilities", args.capabilities, "--max-pages", str(args.max_pages),
           "--deadline", str(args.deadline)]
    if args.allow_private:
        cmd.append("--allow-private")
    rc, out, err = run(cmd, args.deadline + 120)
    tail = [ln for ln in out.strip().splitlines() if ln.strip()][-6:]
    print("phase1: snapshot %s" % ("OK" if rc == 0 else "FATAL (rc=%d)" % rc))
    for ln in tail:
        print("  | %s" % ln[:220])
    if err.strip() and rc != 0:
        print("  ! %s" % err.strip().splitlines()[-1][:220])
    if rc != 0 or not os.path.exists(snap):
        print("phase1 status: snapshot failed - specialists skipped, record the notes above")
        return 1

    rows = []
    frag_paths = []
    for skill_id, script in resolve_scripts(here):
        frag = os.path.join(frag_dir, "%s.json" % skill_id)
        if script is None:
            rows.append((skill_id, "missing script - contributes not_evaluated"))
            continue
        rc, out, err = run([sys.executable, script, "--snapshot", snap, "--out", frag], 180)
        summary = summarize_fragment(frag) if os.path.exists(frag) else None
        if summary is None:
            rows.append((skill_id, "no fragment (rc=%d) - contributes not_evaluated" % rc))
        else:
            f, ps, ne, fl = summary
            rows.append((skill_id, "fragment ok: %d finding(s), %d pass, %d ne" % (f, ps, ne)))
            for item in fl:
                rows.append(("", "FINDING %s: %s" % (item["check_id"], item["title"])))
            frag_paths.append(frag)
    validator = os.path.join(here, "validate_fragment.py")
    if frag_paths and os.path.exists(validator):
        rc, out, _ = run([sys.executable, validator] + frag_paths, 120)
        rows.append(("validate", "clean" if rc == 0 else "REJECTS - read lines below"))
        if rc != 0:
            for ln in out.strip().splitlines()[:8]:
                rows.append(("", ln[:200]))
    inject_extras(out_dir, frag_paths)
    print("phase1 status:")
    for skill_id, status in rows:
        print("  %-28s %s" % (skill_id, status))
    print("BUDGET %ds/300s after phase1 | SHED: %s | TIMEBOX: %s" %
          (int(time.monotonic() - t0),
           "offsite (+referral 3q)" if time.monotonic() - t0 > 210 else "none",
           "answer-coverage=core-only" if time.monotonic() - t0 > 150 else "full"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
