#!/usr/bin/env python3
"""Fixture suite runner - the Phase 5 kill-risk gate.

For each scenario: start the fixture server, run collect_snapshot.py against it
(--allow-private; 127.0.0.1), run the three scripted specialists, then assert
each scenario's expected findings, expected NON-findings, and snapshot
observations. Any unexpected finding (not listed as expected) fails the
scenario - surprise findings are false-positive signal.

Judgment skills (ANS/FRS/OFF/REF) are NOT driven here; fixtures assert the
snapshot observations they consume. Judgment quality is validated by the FP
corpus and live-corpus labeling.

Run:  uv run --python 3.9 tests/run_fixtures.py
"""

import json
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from fixture_server import start, stop  # noqa: E402
from fixtures.scenarios import SCENARIOS  # noqa: E402

ROOT = os.path.dirname(HERE)
BR = os.path.join(ROOT)
ORCH = os.path.join(BR, "skills", "audit-orchestrator")
SCRIPTS = {
    "access-discovery-audit": os.path.join(BR, "skills", "access-discovery-audit", "scripts", "probe_access.py"),
    "representation-parity-audit": os.path.join(BR, "skills", "representation-parity-audit", "scripts", "analyze_representation.py"),
    "entity-consistency-audit": os.path.join(BR, "skills", "entity-consistency-audit", "scripts", "check_entities.py"),
}


def run(cmd):
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc


def dig(d, dotted):
    node = d
    for part in dotted.split("."):
        if isinstance(node, list):
            try:
                node = node[int(part)]
                continue
            except (ValueError, IndexError):
                return None
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def unit_checks():
    """No-server checks: confusable folding, --passages edge cases, --fix."""
    fails = []
    sys.path.insert(0, os.path.join(ORCH, "scripts"))
    from collect_snapshot import _fold_confusables, run_passages
    from types import SimpleNamespace
    if _fold_confusables("2026–27 ‘quoted’\u00a0x") != "2026-27 'quoted' x":
        fails.append("fold confusables mismatch")
    work = tempfile.mkdtemp(prefix="fx-unit-")
    snap = {"pages": [{"requested_url": "http://unit.test/guide",
                         "raw_html": ("<html><head><title>Guide</title></head><body><main>"
                                      "<p>Session 2026–27 runs March.</p></main></body></html>")}]}
    sp = os.path.join(work, "snapshot.json")
    json.dump(snap, open(sp, "w"))
    pp = os.path.join(work, "passages.json")
    json.dump({"kind": "passages", "skill_id": "answer-coverage-audit", "questions": [
        {"question_id": "Q-001", "question": "q", "source": "site-derived",
         "expected_page": "http://unit.test/guide",
         "candidate_passage": "Session 2026–27 runs March."},
        {"question_id": "Q-002", "question": "q", "source": "site-derived",
         "expected_page": "http://unit.test/guide",
         "candidate_passage": "Session 2026-27 runs March."},
        {"question_id": "Q-003", "question": "q", "source": "site-derived",
         "expected_page": "http://unit.test/guide"}]}, open(pp, "w"))
    out = os.path.join(work, "checked.json")
    try:
        run_passages(SimpleNamespace(snapshot=sp, passages=pp, out=out))
    except Exception as e:  # noqa: BLE001 - the point is it must not raise
        fails.append("run_passages raised: %r" % e)
        return fails
    res = {r["question_id"]: r for r in json.load(open(out))["results"]}
    if not res["Q-001"]["contiguous"]:
        fails.append("unit verbatim not contiguous")
    if res["Q-002"]["contiguous"] or "quoting fidelity" not in (res["Q-002"]["note"] or ""):
        fails.append("unit near-match note wrong: %r" % res["Q-002"].get("note"))
    if res["Q-003"]["contiguous"] or "no candidate passage" not in (res["Q-003"]["note"] or ""):
        fails.append("unit omitted note wrong: %r" % res["Q-003"].get("note"))
    fp = os.path.join(work, "frag.json")
    json.dump({"skill_id": "answer-coverage-audit", "results": [
        {"check_id": "ANS-QUESTION-UNANSWERED", "gate": "pass",
         "affected_urls": ["http://unit.test/guide"], "observations": None}]}, open(fp, "w"))
    p = run([sys.executable, os.path.join(ORCH, "scripts", "validate_fragment.py"), "--fix", fp])
    if p.returncode != 0:
        fails.append("--fix exited %d: %s" % (p.returncode, p.stdout[-200:]))
    else:
        fixed = json.load(open(fp))
        r = fixed["results"][0]
        if (fixed.get("mode") != "snapshot" or r.get("urls") != ["http://unit.test/guide"]
                or "observations" in r or "affected_urls" in r):
            fails.append("--fix corrections wrong: %r" % r)
    doc_server, doc_url = start({
        "robots": {"status": 404, "body": ""},
        "pages": {"/": {"status": 200, "headers": {},
                        "body": ("<html><head><title>Home</title></head><body>"
                                 "<nav><a href=\"/doc\">Doc</a></nav><p>Welcome.</p></body></html>")},
                  "/doc": {"status": 200, "headers": {"Content-Type": "application/pdf"},
                           "body": "%PDF-1.4 \x00 binary garbage $999 price token"}},
        "missing_path": None})
    try:
        dout = os.path.join(work, "docsnap.json")
        p = run([sys.executable, os.path.join(ORCH, "scripts", "collect_snapshot.py"),
                 "--url", doc_url, "--out", dout, "--allow-private",
                 "--site-type", "saas", "--capabilities", "web_fetch"])
        if p.returncode != 0:
            fails.append("non-html collector failed: %s" % (p.stderr or "")[-200:])
        else:
            dsnap = json.load(open(dout))
            if "$999" in json.dumps(dsnap["pages"]):
                fails.append("non-html: pdf garbage reached page records")
            pdf_pages = [pg for pg in dsnap["pages"]
                         if (pg.get("content_type") or "").startswith("application/pdf")]
            if not pdf_pages or any(pg.get("claim_index") for pg in pdf_pages):
                fails.append("non-html: pdf page not captured as claim-free skeleton")
    finally:
        stop(doc_server)
    return fails


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    failures = ["unit: %s" % f for f in unit_checks()]
    t0 = time.time()
    for scenario in SCENARIOS:
        name = scenario["name"]
        if only and only not in name:
            continue
        work = tempfile.mkdtemp(prefix="fx-")
        server, url = start(scenario)
        try:
            proc = run([sys.executable, os.path.join(ORCH, "scripts", "collect_snapshot.py"),
                        "--url", url, "--out", os.path.join(work, "snapshot.json"),
                        "--allow-private", "--site-type", scenario["site_type"],
                        "--capabilities", "web_fetch"])
            if proc.returncode != 0:
                failures.append("%s: collector failed: %s" % (name, proc.stderr[-300:]))
                continue
            snap = json.load(open(os.path.join(work, "snapshot.json")))

            findings = {}
            for skill, script in SCRIPTS.items():
                out = os.path.join(work, "%s.json" % skill)
                p = run([sys.executable, script, "--snapshot",
                         os.path.join(work, "snapshot.json"), "--out", out])
                if p.returncode not in (0, 2):
                    failures.append("%s: %s exited %d: %s" % (name, skill, p.returncode, p.stderr[-200:]))
                    continue
                if os.path.exists(out):
                    for r in json.load(open(out)).get("results", []):
                        if r.get("gate") == "finding" and r.get("candidate_finding"):
                            cf = r["candidate_finding"]
                            findings[r["check_id"]] = {"severity": cf["severity"],
                                                       "confidence": cf.get("confidence")}

            expected = scenario.get("expected_findings", {})
            non_expected = scenario.get("expected_non_findings", [])
            for cid, spec in expected.items():
                if cid not in findings:
                    failures.append("%s: EXPECTED %s missing (findings: %s)"
                                    % (name, cid, sorted(findings)))
                else:
                    for key in ("severity", "confidence"):
                        if key in spec and findings[cid].get(key) != spec[key]:
                            failures.append("%s: %s %s=%s expected %s"
                                            % (name, cid, key, findings[cid].get(key), spec[key]))
            for cid in non_expected:
                if cid in findings:
                    failures.append("%s: NON-FINDING %s fired (%s) - false positive"
                                    % (name, cid, findings[cid]))
            stray = sorted(set(findings) - set(expected) - set(non_expected))
            if stray:
                failures.append("%s: UNEXPECTED findings (not declared): %s"
                                % (name, stray))
            for dotted, want in (scenario.get("snapshot_asserts") or {}).items():
                got = dig(snap, dotted)
                if got != want:
                    failures.append("%s: snapshot %s=%r expected %r" % (name, dotted, got, want))
            if scenario.get("passages") is not None:
                pj = {"kind": "passages", "skill_id": "answer-coverage-audit", "questions": []}
                for q in scenario["passages"]:
                    q = dict(q)
                    q["expected_page"] = q["expected_page"].replace("{BASE}", url.rstrip("/"))
                    pj["questions"].append(q)
                pj_path = os.path.join(work, "passages.json")
                json.dump(pj, open(pj_path, "w"))
                pc_path = os.path.join(work, "passages_checked.json")
                p = run([sys.executable, os.path.join(ORCH, "scripts", "collect_snapshot.py"),
                         "--passages", pj_path, "--snapshot",
                         os.path.join(work, "snapshot.json"), "--out", pc_path])
                if p.returncode != 0:
                    failures.append("%s: --passages exited %d: %s"
                                    % (name, p.returncode, (p.stderr or "")[-200:]))
                else:
                    res = {r["question_id"]: r
                           for r in json.load(open(pc_path))["results"]}
                    for qid, spec in (scenario.get("passages_asserts") or {}).items():
                        r = res.get(qid)
                        if r is None:
                            failures.append("%s: passages %s missing from results" % (name, qid))
                        elif r.get("contiguous") != spec["contiguous"]:
                            failures.append("%s: passages %s contiguous=%r expected %r"
                                            % (name, qid, r.get("contiguous"), spec["contiguous"]))
                        elif (spec.get("note_contains") or "") not in (r.get("note") or ""):
                            failures.append("%s: passages %s note=%r" % (name, qid, r.get("note")))
            print("PASS %s (%d findings)" % (name, len(findings))
                  if not any(f.startswith(name + ":") for f in failures)
                  else "FAIL %s" % name)
        finally:
            stop(server)
    elapsed = time.time() - t0
    if failures:
        print("\nFIXTURES: %d FAILURE(S)" % len(failures))
        for f in failures:
            print("  - %s" % f)
        sys.exit(1)
    print("\nFIXTURES: ALL PASS (%.1fs)" % elapsed)


if __name__ == "__main__":
    main()
