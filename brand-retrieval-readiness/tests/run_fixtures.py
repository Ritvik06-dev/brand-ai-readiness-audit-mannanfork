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


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    failures = []
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
