#!/usr/bin/env python3
"""analyze_representation.py - representation-parity specialist (read stage).

Snapshot-only reader: this script performs NO network I/O. It reads the shared
snapshot produced by collect_snapshot.py and writes one finding fragment shaped
by the orchestrator's references/finding_fragment.json.

Default path assumes no browser. REP-KEY-FACT-LOSS is emitted only when multiple
independent shell indicators coexist on a page (indirect, medium confidence);
otherwise it is reported as not_evaluated: "no browser: render gap unconfirmed".
A declared browser capability upgrades confidence but is not required.

Checks (see check_catalog.json): REP-KEY-FACT-LOSS, REP-STATE-ONLY-FACT,
REP-METADATA-CONTRAST, REP-EXTRACTION-LOSS, REP-NON-TEXT-LOCKIN,
REP-TABLE-SEMANTICS, REP-LINKS-SCRIPT-ONLY, REP-HIDDEN-TEXT-SUSPECT.

Stdlib only (Python 3.9+). Reads the snapshot from disk; prints a small summary;
never dumps page content to stdout beyond short quoted samples.
"""

import argparse
import datetime
import json
import os
import re
import sys
from statistics import median
from urllib.parse import urlparse

CHECK_IDS = [
    "REP-KEY-FACT-LOSS", "REP-STATE-ONLY-FACT", "REP-METADATA-CONTRAST",
    "REP-EXTRACTION-LOSS", "REP-NON-TEXT-LOCKIN", "REP-TABLE-SEMANTICS",
    "REP-LINKS-SCRIPT-ONLY", "REP-HIDDEN-TEXT-SUSPECT",
]
KEY_FACT_SURFACES = ["chatgpt_search", "perplexity_retrieval", "claude_search"]
NOSCRIPT_RE = re.compile(r"<noscript[^>]*>[^<]*(enable javascript|javascript (?:is|must be) "
                         r"(?:enabled|required)|you need to enable)", re.I)
EMPTY_ROOT_RE = re.compile(r"<div[^>]*\bid=[\"'](root|app|__next|__nuxt|q-app)[\"'][^>]*>"
                           r"\s*</div>", re.I)
HIDE_STYLE_RE = re.compile(
    r"<[a-z]+[^>]*\bstyle=\"[^\"]*(?:display\s*:\s*none|visibility\s*:\s*hidden"
    r"|font-size\s*:\s*0(?:\.0+)?\s*(?:px|em|pt)?\s*[;\"]|left\s*:\s*-\d{3,}px"
    r"|text-indent\s*:\s*-\d{3,}px)[^\"]*\"[^>]*>", re.I)
ALLOWLIST_RE = re.compile(r"class=\"[^\"]*(?:sr-only|visually-hidden|skip-link|show-for-sr)"
                          r"|aria-hidden=\"true\"|type=\"hidden\"", re.I)
META_TOKEN_RE = re.compile(r"[$\u20ac\u00a3\u20b9]\s?\d[\d,.]*|\b\d+(?:\.\d+)?\s?%"
                           r"|\bv?\d+\.\d+(?:\.\d+)?\b|\b(?:Free|Starter|Basic|Pro|Premium"
                           r"|Enterprise|Business|Team)\b")
FACT_STRING_RE = re.compile(r"^[^h/]")

def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def fail(what, errs):
    sys.stderr.write("analyze_representation: FAIL - %s\n" % what)
    for e in errs:
        sys.stderr.write("  - %s\n" % e)
    sys.exit(1)


def norm(s):
    return " ".join((s or "").split())


def fact_like(s):
    """A payload-only string that reads like content, not internal machinery
    (props, ids, routes, hashes)."""
    s = norm(s)
    if len(s) < 25 or len(s.split()) < 5:
        return False
    if s.startswith(("http", "/", "#", "{", "fn:", "urn:")):
        return False
    return not re.match(r"^[A-Za-z0-9_/.:,@%+=-]+$", s)


def shell_indicators(page):
    raw = page.get("raw_html", "") or ""
    words = len((page.get("visible_text") or "").split())
    ind = []
    if NOSCRIPT_RE.search(raw):
        ind.append("noscript-enable-js")
    if words < 120 and len(raw) > 20000:
        ind.append("tiny-visible-vs-raw (%d words, %d bytes)" % (words, len(raw)))
    title = (page.get("title") or "").strip().lower()
    if title in ("", "loading", "loading...", "..."):
        ind.append("loading-or-empty-title")
    if EMPTY_ROOT_RE.search(raw):
        ind.append("empty-root-container")
    return ind


def state_fact_count(page):
    return sum(1 for s in (page.get("inline_state") or {}).get("contrast_strings", [])
               if fact_like(s))


def analyze(pages):
    results = []
    not_evaluated = []
    urls = [p.get("requested_url", "") for p in pages]

    # --- REP-KEY-FACT-LOSS -------------------------------------------------
    shell_pages = []
    for p in pages:
        ind = shell_indicators(p)
        if len(ind) >= 2 and state_fact_count(p) < 3:
            shell_pages.append((p, ind))
    if shell_pages:
        k = len(shell_pages)
        ex = shell_pages[0]
        urls_hit = [p["requested_url"] for p, _ in shell_pages[:8]]
        ev = ("Sampled %d pages; %d client-rendered shell%s whose main content is absent "
              "from the raw response (indicators on %s: %s; %d visible words vs %d raw bytes)."
              % (len(pages), k, "" if k == 1 else "s",
                 ex[0]["requested_url"], "; ".join(ex[1]),
                 len((ex[0].get("visible_text") or "").split()),
                 len(ex[0].get("raw_html") or "")))
        results.append({
            "check_id": "REP-KEY-FACT-LOSS", "gate": "finding", "urls": urls_hit,
            "observations": {"pages_sampled": len(pages), "shell_pages": k,
                             "indicators": ex[1], "browser_available":
                                 False},
            "evidence_quality": "indirect-corroborated",
            "candidate_finding": {
                "title": "Main content on %s pages is absent from the raw server response"
                         % (ex[0].get("page_class") or "site"),
                "severity": "high", "confidence": "medium",
                "evidence": ev,
                "why_it_matters": "Non-rendering retrieval bots (GPTBot, ClaudeBot, "
                                  "PerplexityBot measured; OAI-SearchBot per third-party "
                                  "tests) read the raw response, so this content is "
                                  "unretrievable there; rendering crawlers (Google, Copilot) "
                                  "still see it - a partial outage.",
                "affected_surfaces": list(KEY_FACT_SURFACES),
                "suggested_action": {
                    "summary": "Server-render or prerender the shell pages so the main "
                               "content is present in the raw response.",
                    "priority": "high", "effort": "medium", "owner": "web-platform",
                    "acceptance_test": "A no-JavaScript fetch of %s returns the page's main "
                                       "content in visible text." % urls_hit[0]}}})
    else:
        not_evaluated.append({
            "check_id": "REP-KEY-FACT-LOSS",
            "reason": "no browser: render gap unconfirmed (%d pages sampled; shell "
                      "indicators counted, none combined >=2 with an empty state payload)"
                      % len(pages)})

    # --- REP-STATE-ONLY-FACT ----------------------------------------------
    state_pages = [(p, [s for s in (p.get("inline_state") or {}).get("contrast_strings", [])
                        if fact_like(s)])
                   for p in pages]
    state_hits = [(p, ss) for p, ss in state_pages
                  if ss and len((p.get("visible_text") or "").split()) < 250]
    if state_hits:
        p, ss = state_hits[0]
        results.append({
            "check_id": "REP-STATE-ONLY-FACT", "gate": "finding",
            "urls": [q["requested_url"] for q, _ in state_hits[:8]],
            "observations": {"pages_with_contrast": len(state_pages),
                             "fact_like_payload_strings": {p["requested_url"]: len(ss)
                                                           for p, ss in state_hits[:8]}},
            "evidence_quality": "direct-representation-comparison",
            "candidate_finding": {
                "title": "Content-like strings appear only inside inline state payloads, "
                         "not in visible text",
                "severity": "medium", "confidence": "medium",
                "evidence": "On %s, %d payload-only content-like strings live in %s and are "
                            "absent from the %d-word visible text; sample: \"%s\". The page "
                            "is partially readable to crawlers that index initial-HTML JSON, "
                            "not fully retrievable."
                            % (p["requested_url"], len(ss),
                               ", ".join((p.get("inline_state") or {}).get("payload_keys", []))
                               or "inline payloads",
                               len((p.get("visible_text") or "").split()),
                               norm(ss[0])[:200]),
                "why_it_matters": "AI crawlers may index initial-HTML JSON, so payload facts "
                                  "are partially readable - degraded retrieval, not loss.",
                "suggested_action": {
                    "summary": "Server-render the payload-only facts into visible DOM text.",
                    "priority": "medium", "effort": "medium",
                    "acceptance_test": "The quoted strings appear in the visible raw text of "
                                       "%s, not only in an inline script." % p["requested_url"]}}})
    else:
        results.append({
            "check_id": "REP-STATE-ONLY-FACT", "gate": "pass", "urls": urls[:8],
            "observations": {
                "pages_with_contrast_strings":
                    sum(1 for _, ss in state_pages if ss),
                "ssr_negative_control": "SSR pages whose payload strings also appear in "
                                        "visible text pass; contrast-only machinery strings "
                                        "on full-content pages are not facts",
                "max_fact_like_payload_strings":
                    max([len(ss) for _, ss in state_pages] or [0])},
            "evidence_quality": "direct-representation-comparison"})

    # --- REP-METADATA-CONTRAST ---------------------------------------------
    meta_hits = []
    for p in pages:
        desc = norm((p.get("open_graph") or {}).get("og:description")
                    or p.get("meta_description") or "")
        vis = norm(p.get("visible_text") or "")
        if not desc:
            continue
        tokens = [t for t in META_TOKEN_RE.findall(desc) if t.lower() not in vis.lower()]
        if tokens:
            meta_hits.append((p, desc, tokens))
    if len(meta_hits) >= 2:
        p, desc, tokens = meta_hits[0]
        results.append({
            "check_id": "REP-METADATA-CONTRAST", "gate": "finding",
            "urls": [q["requested_url"] for q, _, _ in meta_hits[:8]],
            "observations": {"pages_with_metadata_contrast": len(meta_hits),
                             "contrast_tokens": tokens[:10]},
            "evidence_quality": "direct-representation-comparison",
            "candidate_finding": {
                "title": "Facts are stated in metadata that never appear in the pages' "
                         "visible text",
                "severity": "medium", "confidence": "medium",
                "evidence": "%d/%d pages state fact tokens (%s) in og:description/meta "
                            "description that never appear in their visible text; on %s the "
                            "metadata reads: \"%s\"."
                            % (len(meta_hits), len(pages), ", ".join(tokens[:6]),
                               p["requested_url"], desc[:200]),
                "why_it_matters": "Retrieval surfaces quote metadata as a fact the page does "
                                  "not visibly state - an inconsistent extractable claim.",
                "suggested_action": {
                    "summary": "State the metadata facts in the visible page content (or "
                               "align the metadata with what the page shows).",
                    "priority": "medium", "effort": "small",
                    "acceptance_test": "Every fact token in the sampled pages' descriptions "
                                       "also appears in that page's visible text."}}})
    else:
        results.append({
            "check_id": "REP-METADATA-CONTRAST", "gate": "pass", "urls": urls[:8],
            "observations": {"pages_with_metadata_contrast": len(meta_hits),
                             "note": "metadata mirroring or summarizing visible text is "
                                     "normal and never flagged"},
            "evidence_quality": "direct-representation-comparison"})

    # --- REP-EXTRACTION-LOSS ------------------------------------------------
    preambles = {}
    for p in pages:
        first = next((norm(ln) for ln in (p.get("visible_text") or "").splitlines()
                      if norm(ln)), "")
        if len(first) >= 80:
            preambles.setdefault(first, []).append(p)
    shared = {t: ps for t, ps in preambles.items() if len(ps) >= max(2, len(pages) // 2)}
    if shared:
        shared_lines = set(shared)
        offsets = []
        for p in pages:
            off, seen_unique = 0, False
            for ln in (p.get("visible_text") or "").splitlines():
                n = norm(ln)
                if n and n not in shared_lines:
                    seen_unique = True
                    break
                off += len(ln) + 1
            if seen_unique:
                offsets.append(off)
        med = int(median(offsets)) if offsets else 0
    else:
        med = 0
    if shared and med > 1500:
        t, ps = max(shared.items(), key=lambda kv: len(kv[1]))
        results.append({
            "check_id": "REP-EXTRACTION-LOSS", "gate": "finding",
            "urls": [q["requested_url"] for q in ps[:8]],
            "observations": {"pages_sharing_preamble": len(ps), "preamble_chars": len(t),
                             "median_unique_content_offset": med},
            "evidence_quality": "direct-representation-comparison",
            "candidate_finding": {
                "title": "Repeated boilerplate displaces page-unique content in text "
                         "extraction",
                "severity": "medium", "confidence": "medium",
                "evidence": "%d/%d pages share an identical %d-char preamble and their "
                            "page-unique content starts at a median offset of %d characters "
                            "into the extraction; preamble: \"%s\"."
                            % (len(ps), len(pages), len(t), med, t[:200]),
                "why_it_matters": "Extraction-first retrieval reads the same boilerplate "
                                  "before any page-specific answer, so answer-bearing content "
                                  "is displaced deep into the extracted text.",
                "suggested_action": {
                    "summary": "Move the repeated preamble into landmark elements and lead "
                               "each page's extraction with page-unique content.",
                    "priority": "medium", "effort": "small",
                    "acceptance_test": "Unique content starts within the first 300 extracted "
                                       "characters on the sampled pages."}}})
    else:
        results.append({
            "check_id": "REP-EXTRACTION-LOSS", "gate": "pass", "urls": urls[:8],
            "observations": {"pages_sharing_long_preamble":
                             sum(len(ps) for ps in shared.values()) if shared else 0,
                             "median_unique_content_offset": med,
                             "note": "flag threshold: shared >=80-char preamble on half the "
                                     "pages AND median unique-content offset > 1500 chars"},
            "evidence_quality": "direct-representation-comparison"})

    # --- REP-NON-TEXT-LOCKIN -------------------------------------------------
    dominant = []
    for p in pages:
        words = len((p.get("visible_text") or "").split())
        empty_alt = sum(1 for im in p.get("images", []) if im.get("alt_empty"))
        nt = p.get("non_text") or {}
        media = nt.get("canvas", 0) + nt.get("svg_without_text", 0) \
            + nt.get("video_without_transcript", 0)
        if (empty_alt >= 5 and words < 300) or media >= 3:
            dominant.append((p, empty_alt, media, words))
    if dominant:
        p, empty_alt, media, words = dominant[0]
        sev = "high" if words < 80 else "medium"
        results.append({
            "check_id": "REP-NON-TEXT-LOCKIN", "gate": "finding",
            "urls": [q["requested_url"] for q, _, _, _ in dominant[:8]],
            "observations": {"pages_image_or_media_dominant": len(dominant),
                             "empty_alt_images": empty_alt, "non_text_media": media,
                             "visible_words": words},
            "evidence_quality": "direct-measurement",
            "candidate_finding": {
                "title": "Decision content is carried by media without text equivalents",
                "severity": sev, "confidence": "medium",
                "evidence": "%s carries %d empty-alt images and %d text-free media elements "
                            "against %d visible words - the page's substance is not "
                            "extractable as text." % (p["requested_url"], empty_alt, media,
                                                      words),
                "why_it_matters": "Text extraction recovers almost nothing from these pages; "
                                  "facts locked in media are invisible to retrieval systems.",
                "suggested_action": {
                    "summary": "Provide text equivalents (alt text, captions, transcripts) "
                               "for the facts carried by images and media.",
                    "priority": "medium", "effort": "medium",
                    "acceptance_test": "No text-bearing image or media element without a "
                                       "text equivalent remains on %s." % p["requested_url"]}}})
    else:
        results.append({
            "check_id": "REP-NON-TEXT-LOCKIN", "gate": "pass", "urls": urls[:8],
            "observations": {"empty_alt_images_total":
                             sum(1 for p in pages for im in p.get("images", [])
                                 if im.get("alt_empty")),
                             "media_elements_total":
                             sum((p.get("non_text") or {}).get("canvas", 0)
                                 + (p.get("non_text") or {}).get("svg_without_text", 0)
                                 + (p.get("non_text") or {}).get("video_without_transcript", 0)
                                 for p in pages)},
            "evidence_quality": "direct-measurement"})

    # --- REP-TABLE-SEMANTICS -------------------------------------------------
    table_hits = []
    for p in pages:
        t = p.get("tables") or {}
        pricing_context = bool(re.search(r"price|pricing|plan|cost|billing",
                                         ((p.get("title") or "") + " "
                                          + urlparse(p.get("requested_url", "")).path),
                                         re.I))
        distinct_prices = len({c.get("value") for c in p.get("claim_index", [])
                               if c.get("type") == "price"})
        comparison_content = (p.get("page_class") in ("decision", "product")
                              or (pricing_context and distinct_prices >= 2))
        if (t.get("div_grid_candidates", 0) >= 2 and t.get("semantic_count", 0) == 0
                and comparison_content):
            table_hits.append(p)
    if table_hits:
        p = table_hits[0]
        results.append({
            "check_id": "REP-TABLE-SEMANTICS", "gate": "finding",
            "urls": [q["requested_url"] for q in table_hits[:8]],
            "observations": {"pages_with_grids_no_table": len(table_hits)},
            "evidence_quality": "direct-measurement",
            "candidate_finding": {
                "title": "Comparison data is laid out in non-semantic grids",
                "severity": "medium", "confidence": "medium",
                "evidence": "%d grid(s) of >=3 aligned columns carry comparison content with "
                            "no <table> on %s (page_class=%s, %d distinct price claims, "
                            "pricing context=%s); row-column pairing does not survive "
                            "extraction."
                            % ((p.get("tables") or {}).get("div_grid_candidates", 0),
                               p["requested_url"], p.get("page_class"), distinct_prices,
                               pricing_context),
                "why_it_matters": "Extracted alone, grid cells lose their plan/value pairing, "
                                  "so 'which plan includes X' questions extract wrongly.",
                "suggested_action": {
                    "summary": "Use semantic <table> markup (or labeled definition lists) for "
                               "the comparison data.",
                    "priority": "medium", "effort": "medium",
                    "acceptance_test": "The comparison page contains a <table> whose headers "
                                       "label the extracted values."}}})
    else:
        results.append({
            "check_id": "REP-TABLE-SEMANTICS", "gate": "pass", "urls": urls[:8],
            "observations": {"pages_with_grids_no_table": len(table_hits),
                             "note": "grids without comparison content are not flagged"},
            "evidence_quality": "direct-measurement"})

    # --- REP-LINKS-SCRIPT-ONLY ------------------------------------------------
    link_hits = []
    for p in pages:
        raw = p.get("raw_html", "") or ""
        handlers = set(re.findall(r"(?:onclick|router\.push|navigate(?:To)?|history\.push)"
                                  r"\s*\(\s*[\"'](/[^\"']{1,80})", raw))
        link_paths = {urlparse(l.get("href", "")).path for l in p.get("links", [])}
        missing = sorted(h for h in handlers if h not in link_paths)
        if len(missing) >= 5:
            link_hits.append((p, missing))
    if link_hits:
        p, missing = link_hits[0]
        results.append({
            "check_id": "REP-LINKS-SCRIPT-ONLY", "gate": "finding",
            "urls": [q["requested_url"] for q, _ in link_hits[:8]],
            "observations": {"pages_with_script_only_destinations": len(link_hits),
                             "sample_missing_paths": missing[:10]},
            "evidence_quality": "direct-measurement",
            "candidate_finding": {
                "title": "Section destinations are reachable only through script handlers",
                "severity": "medium", "confidence": "medium",
                "evidence": "%d destinations on %s are referenced only by script handlers "
                            "with no crawlable <a href> equivalent (%s)."
                            % (len(missing), p["requested_url"], ", ".join(missing[:5])),
                "why_it_matters": "Non-rendering fetchers cannot follow script-only "
                                  "navigation, so those sections are undiscoverable to them.",
                "suggested_action": {
                    "summary": "Emit crawlable <a href> links for the handler-navigated "
                               "destinations.",
                    "priority": "medium", "effort": "small",
                    "acceptance_test": "Every quoted destination appears in an <a href> on "
                                       "the page."}},
        })
    else:
        results.append({
            "check_id": "REP-LINKS-SCRIPT-ONLY", "gate": "pass", "urls": urls[:8],
            "observations": {"pages_with_script_only_destinations": len(link_hits)},
            "evidence_quality": "direct-measurement"})

    # --- REP-HIDDEN-TEXT-SUSPECT ----------------------------------------------
    hidden_pages = []
    total_instances = 0
    for p in pages:
        raw = p.get("raw_html", "") or ""
        instances = 0
        for m in HIDE_STYLE_RE.finditer(raw):
            tag = m.group(0)
            if ALLOWLIST_RE.search(tag):
                continue
            instances += 1
        if instances >= 2:
            hidden_pages.append((p, instances))
        total_instances += instances
    if hidden_pages and len(hidden_pages) >= 2:
        p, instances = hidden_pages[0]
        results.append({
            "check_id": "REP-HIDDEN-TEXT-SUSPECT", "gate": "finding",
            "urls": [q["requested_url"] for q, _ in hidden_pages[:8]],
            "observations": {"pages_with_hidden_text": len(hidden_pages),
                             "total_instances": total_instances},
            "evidence_quality": "direct-measurement",
            "candidate_finding": {
                "title": "Hidden text beyond accessibility patterns is present on multiple "
                         "pages",
                "severity": "medium", "confidence": "medium",
                "evidence": "%d hidden-text instances (inline display:none / visibility:"
                            "hidden / font-size:0 / off-screen positioning) on %d pages "
                            "after allowlisting sr-only, visually-hidden, skip-link, "
                            "aria-hidden decorative, and hidden-input patterns; %s carries "
                            "%d." % (total_instances, len(hidden_pages),
                                     p["requested_url"], instances),
                "why_it_matters": "Non-accessibility hidden text can carry content or "
                                  "instructions shown to some readers and not others.",
                "suggested_action": {
                    "summary": "Remove the non-accessibility hidden text or replace it with "
                               "visibly stated content.",
                    "priority": "medium", "effort": "small",
                    "acceptance_test": "No non-allowlisted hidden text remains in the raw "
                                       "HTML of the sampled pages."}},
        })
    else:
        results.append({
            "check_id": "REP-HIDDEN-TEXT-SUSPECT", "gate": "pass", "urls": urls[:8],
            "observations": {"total_instances": total_instances,
                             "allowlist": "sr-only, visually-hidden, skip-link, "
                                          "aria-hidden decorative, type=hidden inputs"},
            "evidence_quality": "direct-measurement"})

    return results, not_evaluated


def resolve_fragment_schema():
    d = os.path.dirname(os.path.abspath(__file__))
    while True:
        if os.path.exists(os.path.join(d, "marketplace.json")):
            cand = os.path.join(d, "skills", "audit-orchestrator", "references",
                                "finding_fragment.json")
            return cand if os.path.exists(cand) else None
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def main():
    ap = argparse.ArgumentParser(
        description="Representation-parity specialist: detect content that does not survive "
                    "into the raw response's visible text (snapshot-only; no network I/O).")
    ap.add_argument("--snapshot", required=True,
                    help="path to the shared snapshot.json from collect_snapshot.py")
    ap.add_argument("--out", required=True, help="output finding-fragment path")
    ap.add_argument("--fragment-schema", default=None,
                    help="path to finding_fragment.json (default: resolved from the "
                         "marketplace root; self-validation is skipped when unresolvable)")
    args = ap.parse_args()

    snap = load_json(args.snapshot)
    pages = snap.get("pages", [])
    if not pages:
        frag = {"skill_id": "representation-parity-audit", "mode": "snapshot",
                "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"),
                "results": [], "not_evaluated": [
                    {"check_id": cid, "reason": "no pages captured in snapshot"
                     } for cid in CHECK_IDS]}
    else:
        results, not_evaluated = analyze(pages)
        frag = {"skill_id": "representation-parity-audit", "mode": "snapshot",
                "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"),
                "results": results, "not_evaluated": not_evaluated}

    schema_path = args.fragment_schema or resolve_fragment_schema()
    if schema_path and os.path.exists(schema_path):
        sys.path.insert(0, os.path.dirname(os.path.abspath(schema_path)).replace(
            os.sep + "references", os.sep + "scripts"))
        try:
            from build_report import validate
            errs = validate(frag, load_json(schema_path))
            if errs:
                fail("fragment does not validate against finding_fragment.json", errs)
        except ImportError:
            print("note: build_report.validate unavailable - self-validation skipped")
    else:
        print("note: finding_fragment.json unresolvable - self-validation skipped")

    out_dir = os.path.dirname(os.path.abspath(args.out))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(frag, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    findings = [r["check_id"] for r in frag["results"] if r["gate"] == "finding"]
    print("analyze_representation: %s" % args.out)
    print("  pages: %d | findings: %s | passes: %d | not_evaluated: %d"
          % (len(pages), ", ".join(findings) if findings else "none",
             sum(1 for r in frag["results"] if r["gate"] == "pass"),
             len(frag["not_evaluated"])))


if __name__ == "__main__":
    main()
