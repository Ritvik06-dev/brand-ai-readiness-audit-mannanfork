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


def check_verdicts_mode(frag_schema):
    """write_fragment --verdicts: flat lines in, schema-shaped fragment out."""
    tmp = tempfile.mkdtemp()
    excerpt = {"kind": "excerpt", "skill_id": "referral-experience-audit", "pages": [],
               "extras": {"measured": {
                   "REF-SOFT-404": {"candidate_gate": "pass",
                                    "evidence": "A nonexistent path returned HTTP 404."},
                   "REF-PERF-RISK": {"observations": {"images_without_dimensions": 65,
                                                      "images_total": 164}}}}}
    verdicts = {"skill_id": "referral-experience-audit", "verdicts": [
        {"check": "REF-SOFT-404", "gate": "pass"},
        {"check": "REF-PERF-RISK", "gate": "finding", "severity": "low",
         "confidence": "medium", "title": "Undimensioned media on product pages",
         "evidence": "65 of 164 images carry no width/height.",
         "fix": "Set width and height on every image.",
         "verify": "No <img> lacks dimensions on a product page.",
         "urls": ["https://ex.test/p/1"]},
        {"check": "REF-OVERLAY-BLOCK", "gate": "not_evaluated", "reason": "no observation"}]}
    paths = {}
    for name, obj in (("verdicts", verdicts), ("excerpt", excerpt)):
        paths[name] = os.path.join(tmp, name + ".json")
        with open(paths[name], "w", encoding="utf-8") as fh:
            json.dump(obj, fh)
    out = os.path.join(tmp, "frag.json")
    proc = subprocess.run(
        [sys.executable, os.path.join(ORCH, "scripts", "write_fragment.py"),
         "--verdicts", "--in", paths["verdicts"], "--excerpt", paths["excerpt"],
         "--out", out], capture_output=True, text=True)
    assert proc.returncode == 0, "verdicts assembly must produce a valid fragment:\n" + proc.stdout + proc.stderr
    frag = load(out)
    jsonschema.Draft7Validator(frag_schema).validate(frag)
    by = {r["check_id"]: r for r in frag["results"]}
    assert by["REF-SOFT-404"]["gate"] == "pass"
    assert by["REF-SOFT-404"]["observations"]["measured"].startswith("A nonexistent path"), \
        "the collector's measured evidence line must ride along, not be retyped"
    assert by["REF-SOFT-404"]["evidence_quality"] == "direct-measurement", \
        "evidence_quality comes from the catalog, never from the author"
    perf = by["REF-PERF-RISK"]
    assert perf["observations"]["images_without_dimensions"] == 65, \
        "measured observations must be merged into the result"
    assert perf["candidate_finding"]["suggested_action"]["acceptance_test"], \
        "verify -> acceptance_test"
    assert perf["urls"] == ["https://ex.test/p/1"]
    assert "affected_surfaces" not in perf["candidate_finding"], \
        "REF-PERF-RISK declares no catalog surface default; none must be invented"
    ne = {n["check_id"] for n in frag.get("not_evaluated", [])}
    assert "REF-OVERLAY-BLOCK" in ne, "an explicit not_evaluated verdict is honoured"
    assert "REF-ANSWER-NOT-CONFIRMED" in ne, \
        "a catalog check with no verdict must be not_evaluated - silence is never a pass"
    # a check that DOES declare surfaces gets them filled in from the catalog
    v2 = {"skill_id": "representation-parity-audit", "verdicts": [
        {"check": "REP-KEY-FACT-LOSS", "gate": "finding", "severity": "high",
         "confidence": "high", "title": "Key facts absent from the raw response",
         "evidence": "0/8 pages state the price in the raw HTML.",
         "fix": "Server-render the price.", "verify": "curl shows the price."}]}
    p2 = os.path.join(tmp, "v2.json")
    with open(p2, "w", encoding="utf-8") as fh:
        json.dump(v2, fh)
    out2 = os.path.join(tmp, "frag2.json")
    proc2 = subprocess.run(
        [sys.executable, os.path.join(ORCH, "scripts", "write_fragment.py"),
         "--verdicts", "--in", p2, "--out", out2], capture_output=True, text=True)
    assert proc2.returncode == 0, proc2.stdout + proc2.stderr
    f2 = load(out2)
    jsonschema.Draft7Validator(frag_schema).validate(f2)
    kfl = next(r for r in f2["results"] if r["check_id"] == "REP-KEY-FACT-LOSS")
    assert kfl["candidate_finding"]["affected_surfaces"] == [
        "chatgpt_search", "perplexity_retrieval", "claude_search"], \
        "affected_surfaces defaults from the catalog when the check declares them"
    print("write_fragment --verdicts: assembly, catalog defaults, silence-is-not-a-pass: OK")


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
    check_verdicts_mode(frag_schema)
    print("G1: PASS")


if __name__ == "__main__":
    main()
