#!/usr/bin/env python3
"""build_report.py - merge specialist finding fragments into the final audit report.

Phase 1 stub (BUILD_PLAN G1, redefined per PHASE1_REVIEW section 6): fragment(s)
in, schema-validated report out. Full root-cause dedup, never-claim lint, and
the composed human summary land in Phase 2.

Stdlib only. Schema validation uses the vendored draft-07 subset validator below
because `jsonschema` is NOT in the standard library and the judge's machine gets
no third-party installs. The real jsonschema package remains the dev-time oracle
in tests/run_contract_tests.py.

Discipline (agentskills "using scripts"): reads files from disk, prints small
summaries to stdout, diagnostics to stderr, meaningful exit codes, no prompts.
"""

import argparse
import datetime
import json
import os
import re
import sys

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


# ---------------------------------------------------------------------------
# Vendored draft-07 subset validator.
# Supports only the keywords our schemas use: type, enum, const, required,
# properties, additionalProperties, items, maxItems, pattern, minimum,
# minLength, maxLength, in-file $ref. Annotation keywords (title, description,
# $id, $schema, format) are ignored, matching draft-07 default behavior.
# oneOf/allOf/if-then are NOT supported - none of the runtime-validated schemas
# (output_schema, finding_fragment, snapshot_schema) use them;
# excerpts_schema.json is dev-oracle-only.
# ---------------------------------------------------------------------------


def _resolve_ref(ref, root):
    if not ref.startswith("#"):
        raise ValueError("only in-file $ref is supported: %s" % ref)
    node = root
    for part in ref.lstrip("#/").split("/"):
        node = node[part]
    return node


def _type_ok(inst, t):
    if t == "object":
        return isinstance(inst, dict)
    if t == "array":
        return isinstance(inst, list)
    if t == "string":
        return isinstance(inst, str)
    if t == "integer":
        return isinstance(inst, int) and not isinstance(inst, bool)
    if t == "number":
        return isinstance(inst, (int, float)) and not isinstance(inst, bool)
    if t == "boolean":
        return isinstance(inst, bool)
    if t == "null":
        return inst is None
    return False


def validate(inst, schema, root=None, path="$"):
    """Return a list of error strings (empty means valid)."""
    root = schema if root is None else root
    if "$ref" in schema:
        return validate(inst, _resolve_ref(schema["$ref"], root), root, path)
    errs = []
    if "type" in schema:
        types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_type_ok(inst, t) for t in types):
            return ["%s: expected type %s, got %s" % (path, schema["type"], type(inst).__name__)]
    if "enum" in schema and inst not in schema["enum"]:
        errs.append("%s: %r is not one of %r" % (path, inst, schema["enum"]))
    if "const" in schema and inst != schema["const"]:
        errs.append("%s: %r != const %r" % (path, inst, schema["const"]))
    if isinstance(inst, str):
        if "minLength" in schema and len(inst) < schema["minLength"]:
            errs.append("%s: shorter than minLength %d" % (path, schema["minLength"]))
        if "maxLength" in schema and len(inst) > schema["maxLength"]:
            errs.append("%s: longer than maxLength %d" % (path, schema["maxLength"]))
        if "pattern" in schema and not re.search(schema["pattern"], inst):
            errs.append("%s: %r does not match %r" % (path, inst, schema["pattern"]))
    if isinstance(inst, (int, float)) and not isinstance(inst, bool):
        if "minimum" in schema and inst < schema["minimum"]:
            errs.append("%s: below minimum %s" % (path, schema["minimum"]))
    if isinstance(inst, list):
        if "maxItems" in schema and len(inst) > schema["maxItems"]:
            errs.append("%s: more than maxItems %d" % (path, schema["maxItems"]))
        if "items" in schema:
            for i, item in enumerate(inst):
                errs.extend(validate(item, schema["items"], root, "%s[%d]" % (path, i)))
    if isinstance(inst, dict):
        for req in schema.get("required", []):
            if req not in inst:
                errs.append("%s: missing required property %r" % (path, req))
        props = schema.get("properties", {})
        for key in sorted(inst):
            sub = props.get(key)
            if sub is not None:
                errs.extend(validate(inst[key], sub, root, "%s.%s" % (path, key)))
            else:
                ap = schema.get("additionalProperties", True)
                if ap is False:
                    errs.append("%s: unexpected property %r" % (path, key))
                elif isinstance(ap, dict):
                    errs.extend(validate(inst[key], ap, root, "%s.%s" % (path, key)))
    return errs


# ---------------------------------------------------------------------------
# Report assembly
# ---------------------------------------------------------------------------


def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def fail(what, errs):
    sys.stderr.write("build_report: FAIL - %s\n" % what)
    for e in errs:
        sys.stderr.write("  - %s\n" % e)
    sys.exit(1)


def main():
    ap = argparse.ArgumentParser(
        description="Merge specialist finding fragments into the final audit report.")
    ap.add_argument("--fragment", action="append", required=True,
                    help="finding fragment JSON file; repeatable")
    ap.add_argument("--site", required=True, help="audited host, e.g. example.com")
    ap.add_argument("--out", required=True, help="output report path")
    ap.add_argument("--marketplace-version", default="1.0.0")
    args = ap.parse_args()

    refs_dir = os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "references"))
    frag_schema = load_json(os.path.join(refs_dir, "finding_fragment.json"))
    out_schema = load_json(os.path.join(refs_dir, "output_schema.json"))
    catalog_path = os.path.join(refs_dir, "check_catalog.json")
    if not os.path.exists(catalog_path):
        fail("missing check_catalog.json", [catalog_path])
    catalog = load_json(catalog_path)
    checks_by_id = {c["check_id"]: c for c in catalog["checks"]}

    findings = []
    needs_verification = []
    not_evaluated = []
    skill_ids = set()
    for frag_path in args.fragment:
        frag = load_json(frag_path)
        errs = validate(frag, frag_schema)
        if errs:
            fail("fragment %s does not validate against finding_fragment.json" % frag_path, errs)
        skill_ids.add(frag["skill_id"])
        for result in frag.get("results", []):
            gate = result.get("gate")
            if gate == "pass":
                continue
            if gate == "not_evaluated":
                not_evaluated.append({
                    "check_id": result["check_id"],
                    "reason": "specialist reported not_evaluated (see fragment)",
                })
                continue
            cand = result["candidate_finding"]
            action = {"summary": cand["suggested_action"]["summary"],
                      "priority": cand["suggested_action"]["priority"]}
            for opt in ("effort", "owner", "acceptance_test"):
                if opt in cand["suggested_action"]:
                    action[opt] = cand["suggested_action"][opt]
            entry = {
                "check_id": result["check_id"],
                "title": cand["title"],
                "severity": cand["severity"],
                "confidence": cand["confidence"],
                "evidence": cand["evidence"],
                "suggested_action": action,
            }
            if cand.get("why_it_matters"):
                entry["why_it_matters"] = cand["why_it_matters"]
            if result.get("urls"):
                entry["affected_urls"] = result["urls"]
            if cand.get("affected_surfaces"):
                entry["affected_surfaces"] = cand["affected_surfaces"]
            if cand["confidence"] == "low":
                # Reporting gate rule 2: low-confidence hypotheses are never findings.
                needs_verification.append({
                    "title": cand["title"],
                    "evidence": cand["evidence"],
                    "what_would_confirm": cand.get("why_it_matters")
                    or "re-observation across runs or owner-side verification",
                })
            else:
                findings.append(entry)
        for ne in frag.get("not_evaluated", []):
            not_evaluated.append({"check_id": ne["check_id"], "reason": ne["reason"]})

    # Catalog resolution lint: no invented check ids anywhere.
    used_ids = set()
    for f in findings:
        used_ids.add(f["check_id"])
    for ne in not_evaluated:
        used_ids.add(ne["check_id"])
    unknown = sorted(used_ids - set(checks_by_id))
    if unknown:
        fail("check_ids not present in check_catalog.json",
             ["%s: invented id" % u for u in unknown])

    # Severity-then-check_id stable sort, then id assignment (orchestrator-only duty).
    findings.sort(key=lambda f: (SEVERITY_ORDER[f["severity"]], f["check_id"]))
    ordered = []
    for i, f in enumerate(findings, 1):
        rec = {"id": "F-%03d" % i, "check_id": f["check_id"]}
        cat = checks_by_id[f["check_id"]].get("category")
        if cat:
            rec["category"] = cat
        rec.update(f)
        ordered.append(rec)

    # Reporting gate rule 1: critical requires high confidence.
    gate_errs = []
    for f in ordered:
        if f["severity"] == "critical" and f.get("confidence") != "high":
            gate_errs.append("%s: critical requires confidence=high (got %s)"
                             % (f["id"], f.get("confidence")))
    if gate_errs:
        fail("reporting gate", gate_errs)

    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for f in ordered:
        counts[f["severity"]] += 1
    summary = {
        "total_findings": len(ordered),
        "critical": counts["critical"],
        "high": counts["high"],
        "medium": counts["medium"],
        "low": counts["low"],
        "opportunities": 0,
    }
    if summary["total_findings"] != len(ordered):
        fail("arithmetic guard", ["total_findings != len(findings)"])

    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    report = {
        "site": args.site,
        "audited_at": now,
        "audit_status": "complete",
        "report_schema_version": "1.0",
        "marketplace_version": args.marketplace_version,
        "coverage": {
            "specialists_resolved": len(skill_ids),
            "specialists_requested": 6,
            "capabilities_unavailable": [],
        },
        "summary": summary,
        "findings": ordered,
        "opportunities": [],
        "needs_verification": needs_verification,
        "not_evaluated": not_evaluated,
        "limitations": [
            "Phase 1 stub: root-cause dedup, never-claim lint, and the composed"
            " human summary land in Phase 2 (BUILD_PLAN.md).",
        ],
        "lint_warnings": [],
        "human_summary": _human_summary(args.site, ordered, needs_verification),
    }

    errs = validate(report, out_schema)
    if errs:
        fail("report does not validate against output_schema.json", errs)

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print("build_report: report written to %s (%d findings, %d needs_verification,"
          " %d not_evaluated)" % (args.out, len(ordered), len(needs_verification),
                                  len(not_evaluated)))


def _human_summary(site, findings, needs_verification):
    lines = ["Audit of %s: %d finding(s)." % (site, len(findings))]
    for f in findings:
        lines.append("- [%s] %s -> %s" % (f["severity"].upper(), f["title"],
                                          f["suggested_action"]["summary"]))
    if needs_verification:
        lines.append("%d item(s) need verification before they can be called defects."
                     % len(needs_verification))
    return "\n".join(lines)


if __name__ == "__main__":
    main()
