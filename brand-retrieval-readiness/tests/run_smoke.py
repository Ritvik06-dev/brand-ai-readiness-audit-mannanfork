#!/usr/bin/env python3
"""One-command smoke gate - re-runnable, not anecdotal.

Runs the collector + degraded report against a real site, schema-validates every
artifact with the real jsonschema (dev-time oracle), and prints timings. Exit 0
only if everything validates. Extend in Phase 3 to include specialist fragments.

Run:
  uv run --python 3.9 --with jsonschema tests/run_smoke.py
  uv run --python 3.9 --with jsonschema tests/run_smoke.py --url https://docs.python.org \
      --site-type docs-developer --capabilities web_fetch
"""

import argparse
import glob
import json
import os
import subprocess
import sys
import tempfile
import time

try:
    from jsonschema import Draft7Validator
except ImportError:
    sys.exit("run with: uv run --python 3.9 --with jsonschema tests/run_smoke.py")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORCH = os.path.join(ROOT, "skills", "audit-orchestrator")
SCRIPTS = os.path.join(ORCH, "scripts")
REFS = os.path.join(ORCH, "references")


def load(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def run(cmd, **kw):
    proc = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if proc.returncode != 0:
        sys.exit("FAILED (%s):\n%s%s" % (" ".join(os.path.basename(c) for c in cmd[:2]),
                                         proc.stdout[-2000:], proc.stderr[-2000:]))
    return proc


def errors_against(instance, schema_path):
    validator = Draft7Validator(load(schema_path))
    out = []
    for err in validator.iter_errors(instance):
        for c in (err.context or [err]):
            out.append("%s: %s" % ("/".join(map(str, c.absolute_path)) or "$", c.message[:140]))
    return out


def main():
    ap = argparse.ArgumentParser(description="Re-runnable end-to-end smoke gate.")
    ap.add_argument("--url", default="https://agentskills.io")
    ap.add_argument("--site-type", default="docs-developer")
    ap.add_argument("--capabilities", default="web_fetch,subagents")
    args = ap.parse_args()

    work = tempfile.mkdtemp(prefix="smoke-")
    t0 = time.time()
    site = args.url.split("//", 1)[-1].rstrip("/")

    proc = run([sys.executable, os.path.join(SCRIPTS, "collect_snapshot.py"),
                "--url", args.url, "--out", os.path.join(work, "audit", "snapshot.json"),
                "--site-type", args.site_type, "--capabilities", args.capabilities])
    t_collect = time.time() - t0
    print(proc.stdout.strip())

    snap = load(os.path.join(work, "audit", "snapshot.json"))
    errs = errors_against(snap, os.path.join(REFS, "snapshot_schema.json"))
    assert not errs, errs[:5]
    for exc_path in glob.glob(os.path.join(work, "audit", "excerpts", "*.json")):
        errs = errors_against(load(exc_path), os.path.join(REFS, "excerpts_schema.json"))
        assert not errs, (exc_path, errs[:5])
    assert snap["site_type"] == [s.strip() for s in args.site_type.split(",")]
    assert all(p.get("page_class") for p in snap["pages"])

    t1 = time.time()
    run([sys.executable, os.path.join(SCRIPTS, "build_report.py"),
         "--site", site, "--out", os.path.join(work, "audit", "report.json"),
         "--snapshot", os.path.join(work, "audit", "snapshot.json"),
         "--degraded"])
    t_report = time.time() - t1
    rep = load(os.path.join(work, "audit", "report.json"))
    errs = errors_against(rep, os.path.join(REFS, "output_schema.json"))
    assert not errs, errs[:5]
    assert rep["coverage"]["specialists_resolved"] == 0
    assert rep["summary"]["total_findings"] == len(rep["findings"])

    print("smoke: PASS | %s | collect %.1fs, report %.1fs, total %.1fs | artifacts in %s"
          % (args.url, t_collect, t_report, time.time() - t0, work))


if __name__ == "__main__":
    main()
