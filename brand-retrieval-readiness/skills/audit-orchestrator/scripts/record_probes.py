#!/usr/bin/env python3
"""record_probes.py - turn a compact probe log into recorded observation rows.

The off-site probes are run by the model (it holds the search capability), but
everything about *recording* them is transcription, not judgment: the query text
already exists in the prompt set, the timestamp is one batch clock, and the cited
URLs are copied straight out of the tool result. Typing all of that back out as
nested, escaped JSON is the single most expensive piece of authoring in the
audit, and none of it is a decision.

So the model writes the short form - which prompt, what outcome, what it noticed,
and the URLs - and this script joins the query text from the prompt set, stamps
the batch timestamp, checks the protocol's rules, and emits the rows.

Input format (line-oriented, '#' starts a comment):

    engine: web_search
    timestamp: 2026-09-12T07:54:16Z

    [Q-001] navigational third-party-cited
    note: brand named and described accurately; zero bbc.com cited
    https://en.wikipedia.org/wiki/BBC
    https://www.britannica.com/money/British-Broadcasting-Corporation

    [Q-004] - third-party-cited
    note: the answer came from Wikipedia, not bbc.com
    https://en.wikipedia.org/wiki/BBC_News_Online

The label slot takes `navigational` or `-`. Bare URLs belong to the probe above
them. Everything the protocol requires of a recorded probe - engine, exact query,
UTC timestamp, result - ends up in the row, so a row is either complete or the
script refuses it.

Writes: {"probes_run": N, "rows": [...]} for --observations-from in a verdicts file.
Exit 0 on success, 2 on a malformed log or a protocol violation.
"""

import argparse
import json
import re
import sys

# probe_protocol.md rule 5.
OUTCOMES = {"official-cited", "third-party-cited", "mentioned-not-cited", "absent",
            "wrong-entity", "fact-stated-wrongly", "unhelpful-landing"}
MAX_PROBES = 6          # probe_protocol.md rule 3
MAX_NAVIGATIONAL = 1    # probe_protocol.md rule 4
TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
HEAD_RE = re.compile(r"^\[([A-Za-z0-9_-]+)\]\s+(\S+)\s+(\S+)\s*$")


def fail(msg):
    sys.stderr.write("record_probes: %s\n" % msg)
    raise SystemExit(2)


def parse(text):
    engine = timestamp = None
    rows, current = [], None
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        low = line.lower()
        if low.startswith("engine:"):
            engine = line.split(":", 1)[1].strip()
            continue
        if low.startswith("timestamp:"):
            timestamp = line.split(":", 1)[1].strip()
            continue
        head = HEAD_RE.match(line)
        if head:
            qid, label, outcome = head.groups()
            if outcome not in OUTCOMES:
                fail("line %d: outcome %r is not one of: %s"
                     % (lineno, outcome, ", ".join(sorted(OUTCOMES))))
            current = {"question_id": qid, "outcome": outcome, "cited_urls": [],
                       "notes": None}
            if label != "-":
                if label != "navigational":
                    fail("line %d: label must be 'navigational' or '-', got %r"
                         % (lineno, label))
                current["label"] = label
            rows.append(current)
            continue
        if low.startswith("note:"):
            if current is None:
                fail("line %d: note before any [Q-id] header" % lineno)
            current["notes"] = line.split(":", 1)[1].strip()
            continue
        if line.startswith("http://") or line.startswith("https://"):
            if current is None:
                fail("line %d: URL before any [Q-id] header" % lineno)
            current["cited_urls"].append(line)
            continue
        fail("line %d: cannot parse %r" % (lineno, raw[:80]))
    return engine, timestamp, rows


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="inp", required=True, help="compact probe log")
    ap.add_argument("--prompt-set", required=True,
                    help="audit/excerpts/offsite-visibility-audit.json (supplies query text)")
    ap.add_argument("--out", required=True, help="observation rows JSON")
    args = ap.parse_args()

    try:
        with open(args.inp, "r", encoding="utf-8") as fh:
            engine, timestamp, rows = parse(fh.read())
    except OSError as e:
        fail("cannot read %s: %s" % (args.inp, e))

    if not engine:
        fail("missing 'engine:' line - a probe row without its engine is not a record")
    if not timestamp:
        fail("missing 'timestamp:' line - run one `date -u` before the batch and stamp "
             "every row with it (probe_protocol rule 1)")
    if not TS_RE.match(timestamp):
        fail("timestamp %r must be UTC ISO-8601 like 2026-09-12T07:54:16Z" % timestamp)
    if not rows:
        fail("no probe rows found")
    if len(rows) > MAX_PROBES:
        fail("%d probes exceeds the hard budget of %d (probe_protocol rule 3)"
             % (len(rows), MAX_PROBES))
    nav = [r for r in rows if r.get("label") == "navigational"]
    if len(nav) > MAX_NAVIGATIONAL:
        fail("%d brand-anchored probes; at most %d may be labelled navigational "
             "(probe_protocol rule 4)" % (len(nav), MAX_NAVIGATIONAL))

    try:
        with open(args.prompt_set, "r", encoding="utf-8") as fh:
            prompts = json.load(fh)
    except (OSError, ValueError) as e:
        fail("cannot read prompt set %s: %s" % (args.prompt_set, e))
    by_id = {p.get("question_id"): p
             for p in ((prompts.get("extras") or {}).get("prompt_set") or [])}
    if not by_id:
        fail("prompt set carries no extras.prompt_set")

    out = []
    seen = set()
    for r in rows:
        qid = r["question_id"]
        if qid not in by_id:
            fail("%s is not in the prompt set (have: %s)"
                 % (qid, ", ".join(sorted(by_id))))
        if qid in seen:
            fail("%s recorded twice; repeats are separate rows only when the budget "
                 "allows and they are deliberate (probe_protocol rule 7)" % qid)
        seen.add(qid)
        row = {"engine": engine, "question_id": qid,
               "query": by_id[qid].get("question"),
               "source": by_id[qid].get("source"),
               "timestamp": timestamp, "outcome": r["outcome"],
               "cited_urls": r["cited_urls"][:10]}
        if r.get("label"):
            row["label"] = r["label"]
        if r.get("notes"):
            row["notes"] = r["notes"]
        out.append(row)

    doc = {"probes_run": len(out), "rows": out,
           "note": "one run is one observation from the auditor egress at the "
                   "recorded timestamp; edge behavior varies by visitor context"}
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    print("record_probes: %d row(s) -> %s" % (len(out), args.out))
    for row in out:
        print("  %-7s %-20s %d url(s)  %s"
              % (row["question_id"], row["outcome"], len(row["cited_urls"]),
                 (row["query"] or "")[:52]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
