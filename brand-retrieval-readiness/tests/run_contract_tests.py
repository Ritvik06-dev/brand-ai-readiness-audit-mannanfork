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


PAGE_HTML = """<html><head><title>%s</title></head><body><main>
<h1>%s</h1>
<p>Hurry! Order in to get delivery by Friday.</p>
<p>The Pro tee is Rs. 999.00 including tax.</p>
<p>Rs. 999.00</p>
<p>Made from 240 GSM bio-washed fabric, sourced in India.</p>
<p>Free shipping over Rs. 2,000.</p>
<p>Free shipping over Rs. 2,000.</p>
</main></body></html>"""


def excerpt_loc(text):
    return {"location": "main", "char_offset": 0, "text_offset": 0, "text": text}


def check_build_passages(exc_schema):
    """Regressions in the anchor->passage builder, all four found in live runs."""
    tmp = tempfile.mkdtemp()
    urls = ["https://ex.test/p/one", "https://ex.test/p/two"]
    body = ("Hurry! Order in to get delivery by Friday. "
            "The Pro tee is Rs. 999.00 including tax. Rs. 999.00 "
            "Made from 240 GSM bio-washed fabric, sourced in India.")
    snapshot = {"pages": [{"requested_url": u, "raw_html": PAGE_HTML % (u, u)} for u in urls]}
    # excerpt text is CAPPED (as the real builder caps it) and stops before the
    # last sentence: the builder must still resolve an anchor from that sentence
    excerpt = {"kind": "excerpt", "skill_id": "answer-coverage-audit",
               "pages": [{"url": u, "main_content_excerpts": [excerpt_loc(body[:90])]}
                         for u in urls]}
    draft = {"questions": [
        # repeated verbatim on BOTH pages: templating, not ambiguity - must resolve
        {"question_id": "Q1", "question": "When does it arrive?", "source": "market-derived",
         "expected_page": urls[0], "anchor": "Hurry! Order in to get delivery by"},
        # anchor carries sentence punctuation ("Rs. ") - must not be truncated
        {"question_id": "Q-002", "question": "What does it cost?", "source": "market-derived",
         "expected_page": urls[0], "anchor": "The Pro tee is Rs. 999.00 including tax"},
        # genuinely ambiguous WITHIN its own page - must fail, with locations
        {"question_id": "Q-003", "question": "Price?", "source": "market-derived",
         "expected_page": urls[0], "anchor": "Rs. 999.00"},
        # no anchor at all: deliberately unanswered, never conflated with a failure
        {"question_id": "Q-004", "question": "Returns?", "source": "market-derived",
         "expected_page": urls[0]},
        # present in the page's runs but NOT in the capped excerpt text: the
        # builder indexes the page, so anchorable_runs can never advertise a run
        # the builder cannot match
        {"question_id": "Q-005", "question": "Where is it made?", "source": "site-derived",
         "expected_page": urls[0], "anchor": "sourced in India"},
        # the SAME run twice on one page: every occurrence yields the identical
        # passage, so this is templating to report, not ambiguity to reject
        {"question_id": "Q-006", "question": "Shipping cost?", "source": "market-derived",
         "expected_page": urls[0], "anchor": "Free shipping over Rs. 2,000"}]}
    paths = {}
    for name, obj in (("draft", draft), ("excerpt", excerpt), ("snapshot", snapshot)):
        paths[name] = os.path.join(tmp, name + ".json")
        with open(paths[name], "w", encoding="utf-8") as fh:
            json.dump(obj, fh)
    out = os.path.join(tmp, "passages.json")
    proc = subprocess.run(
        [sys.executable, os.path.join(ORCH, "scripts", "build_passages.py"),
         "--draft", paths["draft"], "--excerpt", paths["excerpt"],
         "--snapshot", paths["snapshot"], "--out", out], capture_output=True, text=True)
    assert proc.returncode == 0, "builder must write a partial set, not abort:\n" + proc.stderr
    assert os.path.exists(out), "resolved questions must be written even when one fails"
    passages = load(out)
    jsonschema.Draft7Validator(
        {"$ref": "#/definitions/passages_file", "definitions": exc_schema["definitions"]}
    ).validate(passages)
    by_id = {q["question_id"]: q for q in passages["questions"]}
    assert by_id["Q-001"]["anchor_status"] == "resolved", \
        "an anchor repeated across sibling pages is templating, not ambiguity"
    assert "Hurry!" in by_id["Q-001"]["candidate_passage"], \
        "sentence punctuation inside the anchor must not chop its head off"
    assert "Rs. 999.00" in by_id["Q-002"]["candidate_passage"], \
        "a price anchor must survive sentence-boundary expansion"
    assert by_id["Q-003"]["anchor_status"] == "unresolved" \
        and "candidate_passage" not in by_id["Q-003"], \
        "a same-page duplicate anchor is genuinely ambiguous and must not resolve"
    assert by_id["Q-004"]["anchor_status"] == "unanswered", \
        "unresolved (quoting failed) must never be recorded as unanswered (site gap)"
    assert by_id["Q-005"]["anchor_status"] == "resolved", \
        "a run the excerpt advertises must be matchable even when the excerpt text is capped"
    assert "appears in 2 different runs" in proc.stdout, \
        "ambiguity must name how many DIFFERENT runs, and quote them"
    assert by_id["Q-006"]["anchor_status"] == "resolved", \
        "an identical run repeated on one page must resolve, not be called ambiguous"
    assert "stated 2 times identically" in proc.stdout, \
        "an identical run repeated on the page resolves, and the repeat is reported"
    print("build_passages: cross-page repeats, punctuation anchors, partial write: OK")


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

    check_build_passages(exc_schema)
    print("G1: PASS")


if __name__ == "__main__":
    main()
