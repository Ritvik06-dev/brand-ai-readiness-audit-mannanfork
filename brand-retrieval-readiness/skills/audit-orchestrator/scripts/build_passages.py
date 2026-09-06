#!/usr/bin/env python3
"""Passage builder for answer-coverage-audit: anchors in, exact passages out.

The model drafts questions with a SHORT verbatim anchor (<~20 words) quoted from
the prepared excerpt. This script owns the mechanics it used to hand-roll (and
debug, across 7 tool turns in traced runs):

  - locate the anchor on the question's expected page in the excerpt
    (whitespace-fold fallback; anything more is a quoting defect and FAILs)
  - reject ambiguous anchors (count occurrences across the WHOLE excerpt)
  - expand to sentence-bounded text <=600 chars within the anchor's block
  - verify fold-containment in the page's extraction blocks (same semantics as
    the --passages contiguity check), so the downstream check passes by
    construction
  - write audit/passages.json (kind/skill_id/questions; candidate omitted for
    unanswered questions; `source` preserved for the offsite prompt set)
  - print one line per question: OK + first 120 chars, or FAIL + reason

Usage:
  python3 build_passages.py --draft draft.json \
      --excerpt audit/excerpts/answer-coverage-audit.json \
      --snapshot audit/snapshot.json --out audit/passages.json

Exit 0 = passages.json written, every anchored question resolved.
Exit 1 = failures printed; nothing written; fix the draft and re-run.
"""
import argparse
import json
import os
import re
import sys

SENT_END = re.compile(r"[.!?][\"'\u201d\u2019]?(?=\s|$)")


def fold(s):
    return " ".join((s or "").split())


def find_anchor(raw_text, anchor):
    """Return the raw offset of anchor in raw_text, else None.
    Exact first; whitespace-fold fallback mapped back to raw offsets."""
    i = raw_text.find(anchor)
    if i >= 0:
        return i
    norm, idx_map = [], []
    last_ws = True
    for pos, ch in enumerate(raw_text):
        if ch.isspace():
            if not last_ws:
                norm.append(" ")
                idx_map.append(pos)
            last_ws = True
        else:
            norm.append(ch)
            idx_map.append(pos)
            last_ws = False
    j = "".join(norm).find(fold(anchor))
    if j < 0:
        return None
    return idx_map[j] if j < len(idx_map) else None


def sentence_bounds(text, lo, hi):
    """Expand [lo, hi) outward to sentence boundaries, clipping to <=600 chars."""
    start = 0
    m = None
    for m in SENT_END.finditer(text, 0, hi):
        start = m.end()
    start = m.end() if m else 0
    end = len(text)
    m2 = SENT_END.search(text, hi)
    if m2:
        end = m2.end()
    if end - start > 600:
        # keep the anchor inside a 600-char window, clipped at sentence ends
        anchor_len = hi - lo
        end = min(len(text), hi + max(0, 600 - anchor_len))
        m3 = None
        for m3 in SENT_END.finditer(text, hi, end):
            pass
        end = m3.end() if m3 else end
        start = max(0, end - 600)
        m4 = None
        for m4 in SENT_END.finditer(text, 0, start):
            pass
        start = m4.end() if m4 else 0
    return start, end


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build passages.json from anchors.")
    ap.add_argument("--draft", required=True)
    ap.add_argument("--excerpt", required=True)
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    draft = json.load(open(args.draft, encoding="utf-8"))
    exc = json.load(open(args.excerpt, encoding="utf-8"))
    questions = draft.get("questions")
    if not isinstance(questions, list) or not questions:
        print("FAIL: draft has no questions[]")
        return 1

    # excerpt corpus: (page_url, location) with raw text
    corpus = []
    for page in exc.get("pages", []):
        for loc in page.get("main_content_excerpts", []):
            corpus.append({"url": page.get("url"), "heading": loc.get("location", ""),
                           "offset": loc.get("char_offset", 0),
                           "text_offset": loc.get("text_offset", 0),
                           "text": loc.get("text", "")})

    # page blocks for fold-containment verification (same extractor as the check)
    here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, here)
    try:
        import collect_snapshot as cs
    except Exception as e:  # noqa: BLE001
        print("FAIL: cannot import collect_snapshot (%s)" % e)
        return 1
    snap = json.load(open(args.snapshot, encoding="utf-8"))
    by_url = {p["requested_url"]: p for p in snap.get("pages", [])}

    out_questions, failures = [], []
    for q in questions:
        qid = q.get("question_id", "?")
        anchor = (q.get("anchor") or "").strip()
        if not anchor:
            # unanswered question: kept, no candidate (run_passages semantics)
            out_questions.append({k: q[k] for k in q if k != "anchor"})
            print("OK   %-6s unanswered (no anchor) - entry kept without candidate" % qid)
            continue
        want_url = q.get("expected_page")
        page_locs = [c for c in corpus if c["url"] == want_url]
        if not page_locs:
            failures.append("%s: expected_page %s has no excerpt locations" % (qid, want_url))
            continue
        # locate + count across the WHOLE excerpt corpus
        hits, page_hit = [], None
        for c in corpus:
            i = find_anchor(c["text"], anchor)
            if i is not None:
                hits.append((c, i))
                if c["url"] == want_url:
                    page_hit = (c, i)
        if page_hit is None:
            failures.append("%s: anchor not found on expected_page %s (excerpt)"
                            % (qid, want_url))
            continue
        if len(hits) > 1:
            where = "; ".join("%s under %s @%d" % (c["url"], c["heading"], c["offset"] + i)
                              for c, i in hits[:3])
            failures.append("%s: anchor matches %d locations - re-anchor: %s"
                            % (qid, len(hits), where))
            continue
        c, i = page_hit
        lo, hi = sentence_bounds(c["text"], i, i + len(anchor))
        passage = c["text"][lo:hi].strip()
        if fold(anchor) not in fold(passage):
            failures.append("%s: expansion lost the anchor (block too short?) - re-anchor" % qid)
            continue
        # verify fold-containment in the page's blocks (checker semantics)
        page = by_url.get(want_url)
        ok = False
        if page is not None:
            ex = cs.PageExtractor(want_url)
            ex.feed(page.get("raw_html") or "")
            ex.close()
            ex.finalize()
            want = fold(passage)
            blocks = [" ".join(b.split()) for b in ex.blocks]
            head_runs = [" ".join(h.get("text", "").split()) for h in (ex.headings or [])]
            head_runs += [" ".join((a.get("anchor_text") or "").split())
                          for a in (ex.links or [])]
            ok = any(want in b for b in blocks) or \
                any(want in (blocks[j] + " " + blocks[j + 1]) for j in range(len(blocks) - 1)) or \
                any(want and want in t for t in [t for t in head_runs if t])
        else:
            failures.append("%s: expected_page %s not in snapshot - cannot verify" % (qid, want_url))
            continue
        if not ok:
            failures.append("%s: passage verified in excerpt but not contiguous in page "
                            "blocks (excerpt clip boundary?) - re-anchor" % qid)
            continue
        entry = {k: q[k] for k in q if k != "anchor"}
        entry["candidate_passage"] = passage
        entry["source_location"] = {"url": c["url"], "heading_path": c["heading"],
                                    "char_offset": c["offset"] + c.get("text_offset", 0) + lo}
        out_questions.append(entry)
        print("OK   %-6s %3d chars \u00ab%s\u00bb" % (qid, len(passage), passage[:120]))

    if failures:
        print("\n%d failure(s) - fix the draft and re-run; nothing written:" % len(failures))
        for x in failures:
            print("  FAIL %s" % x)
        return 1

    out = {"kind": "passages", "skill_id": "answer-coverage-audit", "questions": out_questions}
    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print("wrote %s (%d questions, %d with candidates)"
          % (args.out, len(out_questions), sum(1 for q in out_questions if q.get("candidate_passage"))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
