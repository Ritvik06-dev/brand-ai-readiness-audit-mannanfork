#!/usr/bin/env python3
"""Aggregate question-curation data from /tmp/qcorpus runs into one JSONL.

Per run: question set (from audit/passages.json), report summary, per-check
gates, session timing (wall, thinking chars, tool calls). One line per run.
"""
import glob
import json
import os
from datetime import datetime

QROOT = "/tmp/qcorpus"
SESS = os.path.expanduser("~/.pi/agent/sessions")
OUT = "/home/zyrus/Desktop/Projects/AdobeSkilsThonR3/research/question-curation/corpus.jsonl"

rows = []
for d in sorted(glob.glob(QROOT + "/*")):
    slug = os.path.basename(d)
    audit = os.path.join(d, "audit")
    if not os.path.isdir(audit):
        continue
    row = {"slug": slug}
    # question set
    pj = os.path.join(audit, "passages.json")
    if os.path.exists(pj):
        try:
            p = json.load(open(pj))
            qs = p.get("questions", [])
            row["questions"] = [{
                "id": q.get("question_id"), "q": q.get("question"),
                "source": q.get("source"), "intent": q.get("intent"),
                "has_candidate": bool(q.get("candidate_passage")),
                "qualifier": q.get("qualifier_present")}
                for q in qs]
            row["n_questions"] = len(qs)
            row["n_market"] = sum(1 for q in qs if q.get("source") == "market-derived")
            row["n_site"] = sum(1 for q in qs if q.get("source") == "site-derived")
            row["intents"] = sorted({q.get("intent") for q in qs if q.get("intent")})
        except (OSError, ValueError):
            pass
    # report
    rj = os.path.join(audit, "report.json")
    if os.path.exists(rj):
        try:
            r = json.load(open(rj))
            row["summary"] = r.get("summary")
            row["finding_checks"] = [f.get("check_id") for f in r.get("findings", [])]
            row["ne"] = len(r.get("not_evaluated", []))
            row["nv"] = len(r.get("needs_verification", []))
            row["opps"] = len(r.get("opportunities", []))
            row["lint"] = r.get("lint_warnings")
        except (OSError, ValueError):
            pass
    # fragments: all gates
    gates = {}
    for ff in glob.glob(os.path.join(audit, "findings", "*.json")):
        try:
            f = json.load(open(ff))
            for res in f.get("results", []):
                g = res.get("gate", "?")
                gates.setdefault(g, []).append(res.get("check_id"))
        except (OSError, ValueError):
            pass
    row["gates_finding"] = gates.get("finding", [])
    row["gates_pass"] = len(gates.get("pass", []))
    row["gates_ne"] = len(gates.get("not_evaluated", []))
    # timing from session
    sess_files = glob.glob(os.path.join(SESS, "*tmp-qcorpus-%s--*" % slug, "*.jsonl"))
    if sess_files:
        f = max(sess_files, key=os.path.getmtime)
        first_u, last_a, calls, think = None, None, 0, 0
        for line in open(f):
            try:
                dd = json.loads(line)
            except ValueError:
                continue
            m = dd.get("message", {})
            if not isinstance(m, dict):
                continue
            ts = dd.get("timestamp")
            if m.get("role") == "user" and first_u is None and "audit http" in str(m.get("content")):
                first_u = ts
            if m.get("role") == "assistant":
                for part in m.get("content", []):
                    if part.get("type") == "toolCall":
                        calls += 1
                    if part.get("type") == "thinking":
                        think += len(part.get("thinking", ""))
                last_a = ts
        if first_u and last_a:
            t1 = datetime.fromisoformat(first_u.replace("Z", "+00:00"))
            t2 = datetime.fromisoformat(last_a.replace("Z", "+00:00"))
            row["wall_s"] = (t2 - t1).seconds
        row["tool_calls"] = calls
        row["think_chars"] = think
    rows.append(row)

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w") as fh:
    for r in rows:
        fh.write(json.dumps(r, ensure_ascii=False) + "\n")
print("runs:", len(rows))
for r in rows:
    print("%-26s q=%s(mkt=%s) wall=%s calls=%s think=%s findings=%s opps=%s ne=%s" % (
        r["slug"], r.get("n_questions"), r.get("n_market"), r.get("wall_s", "-"),
        r.get("tool_calls", "-"), r.get("think_chars", "-"),
        len(r.get("finding_checks") or []), r.get("opps", "-"), r.get("ne", "-")))
# corpus aggregates over runs with question sets
qruns = [r for r in rows if r.get("n_questions")]
if qruns:
    qs = [r["n_questions"] for r in qruns]
    mk = [r["n_market"] for r in qruns]
    print("\ncorpus: %d runs with question sets | questions: min %d max %d avg %.1f | market-derived: min %d max %d avg %.1f" % (
        len(qruns), min(qs), max(qs), sum(qs)/len(qs), min(mk), max(mk), sum(mk)/len(mk)))
    intents = {}
    for r in qruns:
        for i in r.get("intents", []):
            intents[i] = intents.get(i, 0) + 1
    print("intent frequency:", json.dumps(intents))
    fired = {}
    for r in qruns:
        for c in r.get("finding_checks") or []:
            fired[c] = fired.get(c, 0) + 1
    print("finding check frequency:", json.dumps(dict(sorted(fired.items(), key=lambda kv: -kv[1]))))
