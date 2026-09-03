#!/usr/bin/env python3
"""G1 gate (BUILD_PLAN, redefined per PHASE1_REVIEW section 6).

Dev-time oracle: the real jsonschema package validates the contract schemas,
the sample fragment, and the produced report. build_report.py itself stays
stdlib-only (vendored draft-07 subset validator) and runs as a subprocess.

Run:  uv run --python 3.9 --with jsonschema tests/run_contract_tests.py
"""

import json
import os
import subprocess
import sys
import tempfile

try:
    import jsonschema
except ImportError:
    sys.exit("run with: uv run --python 3.9 --with jsonschema tests/run_contract_tests.py")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORCH = os.path.join(ROOT, "skills", "audit-orchestrator")
REFS = os.path.join(ORCH, "references")
SAMPLE = os.path.join(ROOT, "tests", "sample_fragment.json")


def load(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def main():
    frag_schema = load(os.path.join(REFS, "finding_fragment.json"))
    out_schema = load(os.path.join(REFS, "output_schema.json"))
    snap_schema = load(os.path.join(REFS, "snapshot_schema.json"))
    exc_schema = load(os.path.join(REFS, "excerpts_schema.json"))
    for name, schema in (("finding_fragment.json", frag_schema),
                         ("output_schema.json", out_schema),
                         ("snapshot_schema.json", snap_schema),
                         ("excerpts_schema.json", exc_schema)):
        jsonschema.Draft7Validator.check_schema(schema)
        print("schema OK: " + name)

    fragment = load(SAMPLE)
    jsonschema.Draft7Validator(frag_schema).validate(fragment)
    print("sample fragment validates against finding_fragment.json")

    out_path = os.path.join(tempfile.mkdtemp(), "report.json")
    proc = subprocess.run(
        [sys.executable, os.path.join(ORCH, "scripts", "build_report.py"),
         "--fragment", SAMPLE, "--site", "example.com", "--out", out_path],
        capture_output=True, text=True)
    print(proc.stdout.strip())
    if proc.returncode != 0:
        sys.exit("build_report.py failed:\n" + proc.stderr)

    report = load(out_path)
    jsonschema.Draft7Validator(out_schema).validate(report)
    print("report validates against output_schema.json")

    summary = report["summary"]
    assert summary["total_findings"] == len(report["findings"]), "arithmetic guard failed"
    assert summary["total_findings"] == 1 and summary["high"] == 1, \
        "unexpected routing: %s" % json.dumps(summary)
    assert len(report["needs_verification"]) == 1, \
        "low-confidence candidate must route to needs_verification, not findings"
    finding = report["findings"][0]
    assert finding["id"] == "F-001" and finding["check_id"] == "ACC-ROBOTS-ROLE"
    assert finding["category"] == "access-discovery", "catalog join failed"
    assert finding["suggested_action"]["acceptance_test"], \
        "specialist-supplied acceptance_test must survive the merge"
    assert any(ne["check_id"] == "ACC-HREFLANG-INCONSISTENT"
               for ne in report["not_evaluated"]), "fragment not_evaluated lost"
    print("routing + arithmetic + catalog join + acceptance_test preservation: OK")
    print("G1: PASS")


if __name__ == "__main__":
    main()
