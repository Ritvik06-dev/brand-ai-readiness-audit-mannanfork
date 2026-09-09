#!/usr/bin/env python3
"""Passage builder for answer-coverage-audit: anchors in, exact passages out.

The model drafts questions with a SHORT verbatim anchor (<~20 words) quoted from
the prepared excerpt. This script owns the mechanics it used to hand-roll (and
debug, across 7 tool turns in traced runs):

  - locate the anchor inside the expected page's own extraction runs - the same
    index the excerpt's `anchorable_runs` is built from, so anything that array
    advertises can actually be matched (whitespace-fold fallback)
  - reject an anchor only when it appears in two runs whose TEXT DIFFERS. The
    same run repeated on the page, or on sibling pages, is templating rather
    than ambiguity: every occurrence yields the identical passage, so the choice
    cannot be wrong, and the question already names its page. (Rejecting those
    made every shared answer on a templated storefront or docs set unanchorable,
    which is exactly the text a model most wants to quote.)
  - expand to sentence-bounded text <=600 chars WITHIN that single run, so the
    downstream contiguity check passes by construction
  - write audit/passages.json (kind/skill_id/questions; `source` preserved for
    the offsite prompt set)
  - print one line per question: OK + first 120 chars, or FAIL + what would work

Draft schema (this is the whole contract - do not read the source for it):

  {"questions": [
    {"question_id": "Q-001",              # Q-000 pattern; loose ids are normalized
     "question": "How much does the Pro plan cost?",
     "source": "market-derived",          # site-derived | market-derived
     "intent": "transaction",             # identity|capability|transaction|procedure|
                                          # temporal|comparison|trust|local
     "expected_page": "https://example.com/pricing",   # must be a sampled page URL
     "anchor": "Pro is $29 per user per month",        # <=~20 words, VERBATIM from
                                          # the excerpt; omit the key entirely when
                                          # the question is genuinely unanswered
     "qualifier_present": false}
  ]}

Every question keeps an `anchor_status`: resolved (a passage was extracted),
unanswered (no anchor was drafted - the site does not answer it), or unresolved
(an anchor was drafted but could not be pinned). Unresolved is never the same as
unanswered: it means the quote failed, or the fact exists only in fragments.

Exit 0 = passages.json written. Resolved questions are always written even when
others fail, so a repair pass re-anchors only the FAIL lines.
Exit 1 = the draft itself was unusable (no questions[], unreadable inputs).
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


def find_all_anchors(raw_text, anchor, cap=5):
    """Every offset of anchor in raw_text (whitespace-folded), not just the first.
    Repeats WITHIN one page location are real ambiguity and must be counted."""
    hits, start = [], 0
    while len(hits) < cap:
        i = find_anchor(raw_text[start:], anchor)
        if i is None:
            break
        hits.append(start + i)
        start += i + max(1, len(anchor))
        if start >= len(raw_text):
            break
    return hits


def normalize_qid(qid, n):
    """Coerce a draft id to the schema pattern Q-000 (excerpts_schema question)."""
    m = re.search(r"(\d+)", str(qid or ""))
    return "Q-%03d" % int(m.group(1)) if m else "Q-%03d" % n


def _quote(s, limit=180):
    s = " ".join((s or "").split())
    return "«%s»" % (s[:limit] + ("…" if len(s) > limit else ""))


def _nearest_blocks(blocks, anchor, k=2):
    """Blocks sharing the most words with the anchor - the re-anchor candidates."""
    words = set(fold(anchor).lower().split())
    scored = sorted(((len(words & set(b.lower().split())), b) for b in blocks),
                    key=lambda t: -t[0])
    return [b for score, b in scored[:k] if score]


_RUNS_CACHE = {}


def page_runs(cs, url, page):
    """(blocks, heading/link runs) for a page, whitespace-folded. Cached: the
    extractor is re-run once per page, not once per question."""
    if url in _RUNS_CACHE:
        return _RUNS_CACHE[url]
    ex = cs.PageExtractor(url)
    ex.feed(page.get("raw_html") or "")
    ex.close()
    ex.finalize()
    blocks = [" ".join(b.split()) for b in ex.blocks]
    runs = [" ".join(h.get("text", "").split()) for h in (ex.headings or [])]
    runs += [" ".join((a.get("anchor_text") or "").split()) for a in (ex.links or [])]
    _RUNS_CACHE[url] = (blocks, [t for t in runs if t])
    return _RUNS_CACHE[url]


def _suggest_from_page(page_locs, anchor):
    """When the anchor is absent, point at the page text that is closest to it."""
    blocks = [loc["text"] for loc in page_locs]
    near = _nearest_blocks(blocks, anchor, k=1)
    if near:
        return "closest text on that page: %s" % _quote(near[0])
    return "that page's excerpt carries no text resembling the anchor"


def sentence_bounds(text, lo, hi):
    """Expand [lo, hi) outward to sentence boundaries, clipping to <=600 chars.

    Boundary search stops at `lo`, never `hi`: sentence punctuation INSIDE the
    anchor ("Hurry!", "Rs. 999.00", "v3.2") must not chop the anchor's own head
    off. `start` is therefore always <= lo, and the anchor always survives.
    """
    start = 0
    m = None
    for m in SENT_END.finditer(text, 0, lo):
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
        for m4 in SENT_END.finditer(text, 0, min(start, lo)):
            pass
        start = m4.end() if m4 else 0
    return start, min(max(end, hi), len(text))


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
    for qn, q in enumerate(questions, 1):
        qid = normalize_qid(q.get("question_id"), qn)
        if qid != q.get("question_id"):
            print("NOTE %-6s question_id normalized from %r (schema pattern is Q-000)"
                  % (qid, q.get("question_id")))
        q = dict(q, question_id=qid)
        anchor = (q.get("anchor") or "").strip()
        if not anchor:
            # deliberately unanswered: kept, no candidate (run_passages semantics)
            entry = {k: q[k] for k in q if k != "anchor"}
            entry["anchor_status"] = "unanswered"
            out_questions.append(entry)
            print("OK   %-6s unanswered (no anchor) - entry kept without candidate" % qid)
            continue
        want_url = q.get("expected_page")
        page = by_url.get(want_url)
        if page is None:
            near = sorted(by_url)[:3]
            failures.append((qid, q, "expected_page %s was not sampled; sampled pages include "
                                     "%s" % (want_url, ", ".join(near) or "none")))
            continue
        # Index the PAGE'S OWN RUNS, which is what anchorable_runs is built from
        # and what a passage must be cut from. Searching the capped excerpt text
        # instead made the builder unable to find runs the excerpt itself
        # advertised, and reported them as "anchor not found".
        blocks, head_runs = page_runs(cs, want_url, page)
        runs = blocks + head_runs
        hits = [r for r in runs if fold(anchor) in r]
        elsewhere = 0
        for u, pg in by_url.items():
            if u == want_url:
                continue
            b2, h2 = page_runs(cs, u, pg)
            if any(fold(anchor) in r for r in b2 + h2):
                elsewhere += 1
        if not hits:
            failures.append((qid, q, "anchor is not inside any single run on %s - the page "
                                     "states it in fragments, which is itself REP/ANS evidence "
                                     "(leave it unresolved and say so). Nearest runs: %s"
                             % (want_url,
                                "; ".join(_quote(b) for b in _nearest_blocks(runs, anchor))
                                or "none")))
            continue
        # Identical run text repeated on the page is not ambiguity: every
        # occurrence yields the same passage, so the choice cannot be wrong.
        # Only genuinely DIFFERENT surrounding runs are unresolvable.
        distinct = list(dict.fromkeys(hits))
        if len(distinct) > 1:
            failures.append((qid, q, "anchor appears in %d different runs on %s - lengthen it "
                                     "with words unique to the one you mean: %s"
                             % (len(distinct), want_url,
                                " | ".join(_quote(r, 90) for r in distinct[:3]))))
            continue
        holder = distinct[0]
        where = "block" if holder in blocks else "heading/link run"
        j = find_anchor(holder, anchor) or 0
        lo, hi = sentence_bounds(holder, j, j + len(anchor))
        passage = holder[lo:hi].strip()
        if fold(anchor) not in fold(passage):
            failures.append((qid, q, "the anchor's run is longer than the 600-char passage cap; "
                                     "anchor a shorter, more specific phrase inside %s"
                             % _quote(holder)))
            continue
        entry = {k: q[k] for k in q if k != "anchor"}
        entry["candidate_passage"] = passage
        entry["anchor_status"] = "resolved"
        loc = next((c for c in corpus
                    if c["url"] == want_url and find_anchor(c["text"], anchor) is not None), None)
        entry["source_location"] = "%s | %s" % (
            want_url, (loc or {}).get("heading") or where)
        out_questions.append(entry)
        rep = ""
        if len(hits) > 1:
            rep += " [stated %d times identically on this page]" % len(hits)
        if elsewhere:
            rep += " [same run on %d other page(s) - templated boilerplate]" % elsewhere
        print("OK   %-6s %3d chars (%s) \u00ab%s\u00bb%s"
              % (qid, len(passage), where, passage[:120], rep))

    # Partial write: resolved questions are kept, unresolved ones stay in the set
    # marked anchor_status=unresolved so the post-step never calls them
    # "unanswered". One repair pass over the FAIL lines, never a rebuild.
    for qid, q, why in failures:
        entry = {k: q[k] for k in q if k != "anchor"}
        entry.pop("candidate_passage", None)
        entry["anchor_status"] = "unresolved"
        out_questions.append(entry)
        print("FAIL %-6s %s" % (qid, why))

    out_questions.sort(key=lambda q: q.get("question_id", ""))
    out = {"kind": "passages", "skill_id": "answer-coverage-audit", "questions": out_questions}
    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    n_res = sum(1 for q in out_questions if q.get("candidate_passage"))
    print("wrote %s (%d questions, %d resolved, %d unresolved, %d unanswered)"
          % (args.out, len(out_questions), n_res, len(failures),
             len(out_questions) - n_res - len(failures)))
    if failures:
        print("Re-anchor ONLY the FAIL lines above and re-run this one command; "
              "resolved questions are already written and must not be redrafted. "
              "If a fact is genuinely stated in fragments, leave it unresolved: that is "
              "site evidence (pair with REP-*), not a quoting error to fix.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
