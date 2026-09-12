#!/usr/bin/env python3
"""check_entities.py - entity-consistency-audit: analyze entity identity and
structured-data consistency from a snapshot.

Snapshot-only reader: this script performs NO network I/O. All network work
(fetches, external-presence resolution) belongs to collect_snapshot.py, which
produces the snapshot this script reads from disk.

Reads: one snapshot JSON (see the orchestrator's references/snapshot_schema.json).
Writes: one finding fragment JSON (see references/finding_fragment.json) covering
the ENT-* checks in check_catalog.json. Titles follow each check's
pattern_template and evidence follows its evidence_template, filled from real
observations: site- or template-level patterns with counts and denominators,
never one visitor's incident.

Exit codes: 0 = fragment written and valid; 1 = fragment validation failed;
2 = could not analyze (a fragment with not_evaluated entries is still written).
Stdout is a small summary; quoted evidence never exceeds 200 characters.
"""

import argparse
import datetime
import json
import os
import re
import sys
import time
from urllib.parse import urlparse

CHECK_IDS = [
    "ENT-JSONLD-INVALID", "ENT-STRUCTURED-VISIBLE-CONFLICT",
    "ENT-NAME-INCONSISTENT", "ENT-AMBIGUOUS-NAME", "ENT-CORROBORATION-ABSENT",
]

MAX_QUOTE = 200

# Types whose machine-readable identity requires a human-readable name.
NAME_REQUIRED_TYPES = {"Organization", "LocalBusiness", "Product", "Brand"}
# Types that name the site's main entity (identity blocks).
IDENTITY_TYPES = {"Organization", "LocalBusiness", "Product", "Brand", "WebSite"}
NAME_TYPE_RE = re.compile(
    r'"@type"\s*:\s*"(Organization|LocalBusiness|Product|Brand|WebSite)"')

TITLE_SEP_RE = re.compile(r"\s+[|\u2013\u2014\u00b7:\u00bb\u00ab]\s+")
FOOTER_RE = re.compile(
    r"(?i:copyright|©|\(c\)|&copy;).{0,120}?((?:[A-Z][\w&.'\-]*\s?){1,6}"
    r"[A-Z][\w&.'\-]*\.?)", re.S)
FOOTER_NOISE = {"all", "rights", "reserved", "legal", "statements", "privacy",
                "terms", "notice", "the"}
LEGAL_TOKENS = {"inc", "llc", "ltd", "gmbh", "corp", "corporation", "co",
                "company", "limited", "llp", "bv", "ag", "sa", "sas", "pty",
                "foundation", "nonprofit"}
STOP_TOKENS = {"the", "and", "of", "a", "an", "to", "for"}
# A category word next to the brand name is what separates it from namesakes.
# The list was tech/services-only, so an apparel or food brand whose title reads
# "Oversized Streetwear & Urban Fashion" scored in_title: false and the model had
# to overrule the boolean from the raw title - exactly the re-derivation the
# scripts-own-the-exact split exists to prevent. Kept deliberately broad and
# category-neutral; it is a presence hint, never the verdict.
QUALIFIER_WORDS = {
    # software / services
    "documentation", "software", "library", "framework", "platform", "agency",
    "studio", "consultancy", "tools", "developer", "hosting", "marketplace",
    "app", "api", "saas", "analytics", "cloud",
    # institutions
    "foundation", "nonprofit", "open", "source", "university", "institute",
    "college", "school", "council", "ministry", "department", "government",
    # local / physical services
    "clinic", "dental", "dentist", "medical", "hospital", "restaurant", "cafe",
    "hotel", "salon", "garage", "bakery",
    # retail / goods
    "clothing", "apparel", "streetwear", "fashion", "wear", "shop", "store",
    "brand", "label", "boutique", "jewellery", "jewelry", "furniture",
    "cosmetics", "beauty", "skincare", "footwear", "outfitters",
    # media
    "news", "magazine", "journal", "media", "publisher", "review",
}
CITATION_SURFACES = ["google_ai_overviews_ai_mode", "bing_copilot",
                     "chatgpt_search", "perplexity_retrieval", "claude_search"]


# --- small helpers ---------------------------------------------------------


def short(text, limit=MAX_QUOTE):
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit - 1] + "\u2026"


def result(check_id, gate, urls=None, observations=None, candidate=None,
           evidence_quality="direct-measurement"):
    out = {"check_id": check_id, "gate": gate, "observations": observations or {}}
    if urls:
        out["urls"] = urls
    out["evidence_quality"] = evidence_quality
    if gate == "finding":
        out["candidate_finding"] = candidate
    return out


def candidate(title, severity, confidence, evidence, why, action_summary,
              priority, surfaces=None, effort=None, owner=None,
              acceptance=None):
    out = {
        "title": title,
        "severity": severity,
        "confidence": confidence,
        "evidence": evidence,
        "suggested_action": {"summary": action_summary, "priority": priority},
    }
    if why:
        out["why_it_matters"] = why
    if surfaces:
        out["affected_surfaces"] = surfaces
    if effort:
        out["suggested_action"]["effort"] = effort
    if owner:
        out["suggested_action"]["owner"] = owner
    if acceptance:
        out["suggested_action"]["acceptance_test"] = acceptance
    return out


def page_class(page):
    return page.get("page_class") or "page"


def is_homepage(page):
    if page.get("page_class") == "homepage":
        return True
    return urlparse(page.get("requested_url") or "").path in ("", "/")


def jsonld_blocks(page):
    return page.get("jsonld") or []


def graph_entries(node):
    """Yield the entity nodes to validate: the object itself, or the members
    of its @graph when present (the @context/@graph wrapper is never itself a
    typed node). @graph is never required - only traversed when present."""
    if isinstance(node, dict):
        g = node.get("@graph")
        if isinstance(g, list):
            for entry in g:
                if isinstance(entry, dict):
                    yield entry
        elif isinstance(g, dict):
            yield g
        else:
            yield node
    elif isinstance(node, list):
        for entry in node:
            if isinstance(entry, dict):
                yield entry


def type_names(node):
    t = node.get("@type")
    if isinstance(t, list):
        return {str(x) for x in t}
    if isinstance(t, str):
        return {t}
    return set()


def parse_number(text):
    m = re.search(r"\d[\d,]*(?:\.\d+)?", str(text or ""))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def schema_offer_prices(node):
    """Numeric offer prices declared by one JSON-LD node (never ranges)."""
    vals = []
    if node.get("price") is not None:
        vals.append(str(node["price"]))
    offers = node.get("offers")
    if isinstance(offers, dict):
        offers = [offers]
    if isinstance(offers, list):
        for o in offers:
            if isinstance(o, dict) and o.get("price") is not None:
                vals.append(str(o["price"]))
    return vals


def schema_availabilities(node):
    out = []
    offers = node.get("offers")
    if isinstance(offers, dict):
        offers = [offers]
    if isinstance(offers, list):
        for o in offers:
            if isinstance(o, dict) and isinstance(o.get("availability"), str):
                out.append(o["availability"])
    return out


def schema_identity_names(node):
    if type_names(node) & IDENTITY_TYPES and isinstance(node.get("name"), str) \
            and node["name"].strip():
        return [node["name"].strip()]
    return []


def norm_tokens(name):
    words = re.findall(r"[a-z0-9]+", (name or "").lower())
    return {w for w in words if w not in STOP_TOKENS and w not in LEGAL_TOKENS}


def subset_match(a, b):
    return bool(a) and bool(b) and (a <= b or b <= a)


def shares_token(a, b):
    """Version-stamped or page-scope titles share a significant word with the
    entity name (e.g. '3.14.7 Documentation' vs 'Python documentation') - such
    titles name pages, not a different entity, and never form a new variant."""
    sig = lambda t: {w for w in t if len(w) >= 3 and not w.isdigit()}
    return bool(sig(a) & sig(b))


def title_segments(title):
    parts = [p.strip() for p in TITLE_SEP_RE.split(title or "") if p.strip()]
    return parts if parts else ([title.strip()] if (title or "").strip() else [])


LEGAL_MARKER_RE = re.compile(r"\u00a9|copyright|\binc\b|\bltd\b|\bllc\b|\bgmbh\b"
                             r"|\blimited\b|\bcorp(?:oration)?\b|\bvof\b|\bsl\b", re.I)


def footer_names(raw_html):
    # inline scripts contain copyright markers and identifiers - strip them
    html = re.sub(r"<script\b.*?</script>", " ", raw_html or "", flags=re.S | re.I)
    out = []
    for m in FOOTER_RE.finditer(html):
        # a footer legal name carries a legal marker; class hashes and UI
        # strings (e.g. 'V1DKq_socials', 'Claims Subject') are not names
        if not LEGAL_MARKER_RE.search(m.group(1) + " " + m.group(0)[:20]):
            continue
        words = m.group(1).split()
        while words and words[-1].lower().strip(".,").rstrip(".") in FOOTER_NOISE:
            words = words[:-1]
        name = " ".join(words).strip(" .,")
        if len(name) >= 3:
            out.append(name)
    return out[-1:]  # last match = footer region


class NameGroups:
    """Groups name variants by token-subset equivalence; records anchors."""

    def __init__(self):
        self.groups = []  # each: {"reps": [(surface, value)], "tokens": set}

    def matches_existing(self, value):
        tokens = norm_tokens(value)
        return any(subset_match(g["tokens"], tokens) or shares_token(g["tokens"], tokens)
                   for g in self.groups)

    def add(self, surface, value, anchor=False):
        tokens = norm_tokens(value)
        if not tokens:
            return None
        for g in self.groups:
            if subset_match(g["tokens"], tokens) or shares_token(g["tokens"], tokens):
                g["reps"].append((surface, value))
                if anchor:
                    g["anchored"] = True
                return g
        g = {"reps": [(surface, value)], "tokens": tokens, "anchored": anchor}
        self.groups.append(g)
        return g


# --- checks ----------------------------------------------------------------


def check_jsonld_invalid(snap, pages):
    """ENT-JSONLD-INVALID: parse failures + missing type-required properties."""
    parse_fail, missing_type, missing_name = [], [], []
    n_blocks = 0
    identity_ok_elsewhere = False
    homepage_identity_fail = False
    product_org_fail = False
    for page in pages:
        url = page.get("requested_url") or ""
        for i, block in enumerate(jsonld_blocks(page)):
            n_blocks += 1
            if not block.get("parse_ok", False):
                raw = block.get("raw") or ""
                looks_identity = bool(NAME_TYPE_RE.search(raw))
                parse_fail.append({"url": url, "block": i,
                                   "snippet": short(raw, 160)})
                if looks_identity:
                    if is_homepage(page):
                        homepage_identity_fail = True
                    product_org_fail = True
                continue
            for node in graph_entries(block.get("parsed")):
                types = type_names(node)
                if not types:
                    missing_type.append({"url": url, "block": i})
                    continue
                name = node.get("name")
                has_name = isinstance(name, str) and name.strip()
                if types & NAME_REQUIRED_TYPES and not has_name:
                    missing_name.append({"url": url, "block": i,
                                         "types": sorted(types & NAME_REQUIRED_TYPES)})
                if types & IDENTITY_TYPES and has_name:
                    identity_ok_elsewhere = True
    main_identity_fail = (homepage_identity_fail or
                          (product_org_fail and not identity_ok_elsewhere))
    if not parse_fail and not missing_type and not missing_name:
        obs = {"blocks_checked": n_blocks}
        if n_blocks == 0:
            obs["reason"] = ("no JSON-LD blocks present on sampled pages; "
                             "missing optional markup is never a finding")
        return result("ENT-JSONLD-INVALID", "pass", observations=obs)
    classes = sorted({page_class(p) for p in pages if jsonld_blocks(p)})
    severity = "high" if main_identity_fail else "medium"
    examples = []
    for f in parse_fail[:2]:
        examples.append("unparseable block on %s" % f["url"])
    for m in missing_name[:2]:
        examples.append("%s block without name on %s" % ("/".join(m["types"]), m["url"]))
    for m in missing_type[:2]:
        examples.append("block without @type on %s" % m["url"])
    k = len(parse_fail)
    m_count = len(missing_type) + len(missing_name)
    title = ("Structured data on %s pages fails to parse or omits "
             "type-required properties" % (", ".join(classes) or "page"))
    evidence = ("%d/%d JSON-LD blocks fail parsing; %d omit type-required "
                "properties (%s)."
                % (k, n_blocks, m_count, "; ".join(examples) or "none"))
    return result(
        "ENT-JSONLD-INVALID", "finding",
        urls=sorted({e["url"] for e in parse_fail + missing_type + missing_name}),
        observations={"blocks_checked": n_blocks,
                      "parse_failures": parse_fail[:5],
                      "missing_type": missing_type[:5],
                      "missing_name": missing_name[:5],
                      "main_identity_block_affected": main_identity_fail},
        candidate=candidate(
            title, severity, "high", short(evidence),
            "JSON-LD blocks that fail to parse or omit type-required properties "
            "deny systems a machine-readable entity description.",
            "Repair or complete the failing JSON-LD blocks so every "
            "Organization/Product block declares @type and a name.",
            severity, surfaces=CITATION_SURFACES,
            effort="small", owner="web-platform",
            acceptance="Re-run collect_snapshot.py on the site; every JSON-LD "
                       "block parses and each Organization/Product block "
                       "carries @type and name."))


def check_structured_visible(snap, pages, name_groups):
    """ENT-STRUCTURED-VISIBLE-CONFLICT: JSON-LD offer data vs visible claims.

    Price is the deterministic gate. Name contradictions across identity
    surfaces are adjudicated under ENT-NAME-INCONSISTENT (one mechanism, one
    finding) whenever >=3 variants exist; they gate here only when the name
    variant count is <= 2, so the two checks never double-flag one mechanism.
    Availability is recorded as an observation - the claim_index carries no
    availability facts, so no deterministic comparison is possible.
    """
    conflicts, availability_obs, name_obs = [], [], []
    for page in pages:
        url = page.get("requested_url") or ""
        s_prices, s_avail, s_names = [], [], []
        for block in jsonld_blocks(page):
            if not block.get("parse_ok", False):
                continue
            for node in graph_entries(block.get("parsed")):
                s_prices.extend(schema_offer_prices(node))
                s_avail.extend(schema_availabilities(node))
                s_names.extend(schema_identity_names(node))
        claims = [c for c in (page.get("claim_index") or []) if c.get("type") == "price"]
        vis = {}
        for c in claims:
            num = parse_number(c.get("value"))
            if num is not None:
                vis[num] = c
        s_nums = {}
        for v in s_prices:
            num = parse_number(v)
            if num is not None:
                s_nums[num] = v
        if len(s_nums) == 1 and len(vis) == 1:
            s_num, s_raw = next(iter(s_nums.items()))
            v_num, claim = next(iter(vis.items()))
            if s_num != v_num:
                conflicts.append({
                    "url": url, "fact_type": "price",
                    "schema_value": s_raw, "visible_value": claim.get("value"),
                    "schema_quote": short(s_raw),
                    "visible_quote": short(claim.get("quote")),
                })
        if s_avail:
            availability_obs.append({"url": url, "availability": s_avail[:4],
                                     "visible_price_claims": len(claims)})
        if s_names:
            title = page.get("title") or ""
            og_name = (page.get("open_graph") or {}).get("og:site_name") or ""
            name_obs.append({"url": url, "schema_name": s_names[0],
                             "title": short(title, 80),
                             "og_site_name": short(og_name, 80)})
    # name portion: only when the name-variant count is <= 2 (see docstring)
    name_conflicts = []
    if len(name_groups.groups) <= 2:
        schema_name = next((v for g in name_groups.groups
                              for s, v in g["reps"] if s == "schema"), None)
        if schema_name:
            visible_names = [v for g in name_groups.groups
                             for s, v in g["reps"] if s in ("title", "og")]
            schema_g = name_groups.groups[
                next(i for i, g in enumerate(name_groups.groups)
                     for s, v in g["reps"] if s == "schema")]
            if visible_names and not any(subset_match(schema_g["tokens"],
                                                      norm_tokens(v))
                                         for v in visible_names):
                name_conflicts.append({
                    "url": pages[0].get("requested_url") if pages else "",
                    "fact_type": "name", "schema_value": schema_name,
                    "visible_value": visible_names[0],
                    "schema_quote": short(schema_name),
                    "visible_quote": short(visible_names[0]),
                })
    all_conflicts = conflicts + name_conflicts
    if not all_conflicts:
        return result("ENT-STRUCTURED-VISIBLE-CONFLICT", "pass", observations={
            "pages_with_schema_prices": sum(1 for p in pages if any(
                schema_offer_prices(n) for b in jsonld_blocks(p)
                if b.get("parse_ok", False) for n in graph_entries(b.get("parsed")))),
            "name_schema_vs_title_og": name_obs[:5],
            "availability_observations": availability_obs[:5],
            "reason": "no structured-vs-visible contradiction measured; matching "
                      "or differently-scoped offers are never flagged",
        })
    k = len(all_conflicts)
    c0 = all_conflicts[0]
    title = "Structured data contradicts visible content on %s" % c0["fact_type"]
    evidence = "%d conflicts: schema says %s, page shows %s (%s)." % (
        k, c0["schema_value"], c0["visible_value"],
        ", ".join(c["url"] for c in all_conflicts[:3]))
    return result(
        "ENT-STRUCTURED-VISIBLE-CONFLICT", "finding",
        urls=sorted({c["url"] for c in all_conflicts}),
        observations={"conflicts": all_conflicts[:5],
                      "name_schema_vs_title_og": name_obs[:5],
                      "availability_observations": availability_obs[:5]},
        candidate=candidate(
            title, "high", "high", short(evidence),
            "Structured data contradicting visible content (price, availability, "
            "name) is worse than missing markup - it actively supplies a wrong "
            "quotable fact.",
            "Correct the structured data (or the visible claim) so the machine-"
            "readable and human-visible values agree on every sampled page.",
            "high", surfaces=CITATION_SURFACES,
            effort="small", owner="web-platform",
            acceptance="Re-run collect_snapshot.py; on %s the JSON-LD offer "
                       "values equal the visible claim values." % c0["url"]))


def collect_name_evidence(pages):
    """Gather identity-surface name values and group them into variants."""
    groups = NameGroups()
    og_site, schema_names = [], []
    footer = []
    homepage_title_segs, homepage_h1s = [], []
    n_pages = 0
    for page in pages:
        n_pages += 1
        og = (page.get("open_graph") or {}).get("og:site_name")
        if og:
            og_site.append(og)
            groups.add("og", og, anchor=True)
        for block in jsonld_blocks(page):
            if not block.get("parse_ok", False):
                continue
            for node in graph_entries(block.get("parsed")):
                for name in schema_identity_names(node):
                    schema_names.append(name)
                    groups.add("schema", name, anchor=True)
        fn = footer_names(page.get("raw_html") or "")
        if fn:
            footer.append(fn[0])
            groups.add("footer", fn[0], anchor=True)
        if is_homepage(page):
            for seg in title_segments(page.get("title") or ""):
                homepage_title_segs.append(seg)
                groups.add("title", seg)
            for h in (page.get("headings") or []):
                if h.get("level") == 1 and h.get("text", "").strip():
                    homepage_h1s.append(h["text"].strip())
                    # an H1 that shares no token with the name groups is a
                    # tagline, not a name variant - excluded from the gate
                    if groups.matches_existing(h["text"].strip()):
                        groups.add("h1", h["text"].strip())
    return {
        "groups": groups, "n_pages": n_pages,
        "title_value": homepage_title_segs[0] if homepage_title_segs else "(absent)",
        "og_value": og_site[0] if og_site else "(absent)",
        "h1_value": homepage_h1s[0] if homepage_h1s else "(absent)",
        "schema_value": schema_names[0] if schema_names else "(absent)",
        "footer_value": footer[0] if footer else "(absent)",
    }


def check_name_inconsistent(pages, ne):
    """ENT-NAME-INCONSISTENT: org name stated materially different ways."""
    distinct = len(ne["groups"].groups)
    anchored = sum(1 for g in ne["groups"].groups if g.get("anchored"))
    variants = []
    for g in ne["groups"].groups:
        rep = g["reps"][0]
        variants.append({"variant": rep[1], "surfaces": sorted({s for s, _ in g["reps"]}),
                         "mentions": len(g["reps"])})
    obs = {"pages_examined": ne["n_pages"], "distinct_variants": distinct,
           "anchored_variants": anchored, "variants": variants[:6],
           "title": ne["title_value"], "og": ne["og_value"], "h1": ne["h1_value"],
           "schema": ne["schema_value"], "footer": ne["footer_value"]}
    negative = ("intentional brand/product hierarchies with a consistent legal "
                "entity name, and title/H1-only page-scope naming, are never "
                "flagged")
    # Gate is a MODEL judgment (corpus: 2/6 known-good brands flagged by the
    # deterministic version - product-vs-publisher schema names, taglines, and
    # page-scope titles are not identity conflicts). The script prepares the
    # variant table; the orchestrator's model completes the gate per the
    # entity SKILL.md, pairing with ENT-AMBIGUOUS-NAME.
    obs["prepared_gate"] = ("model judgment: does any NAME-BEARING surface (og:site_name, "
                            "Organization schema name, footer legal name) carry a materially "
                            "different entity name than the dominant brand token? Product vs "
                            "publisher naming, taglines, and page-scope titles are not conflicts.")
    return result("ENT-NAME-INCONSISTENT", "pass", evidence_quality="semantic-judgment",
                  observations=obs)
    return result("ENT-NAME-INCONSISTENT", "pass", observations=obs)


def check_ambiguous_name(pages, ne):
    """ENT-AMBIGUOUS-NAME: semantic judgment - the script only prepares
    observations; the orchestrator's model completes the gate per SKILL.md."""
    name = None
    name_source = None
    for surface in ("schema", "og", "title"):
        val = ne[{"schema": "schema_value", "og": "og_value",
                  "title": "title_value"}[surface]]
        if val and val != "(absent)":
            name = val
            name_source = surface
            break
    if not name:
        return result("ENT-AMBIGUOUS-NAME", "not_evaluated",
                      observations={"reason": "no organization name found in "
                                              "schema, og:site_name, or homepage title"})
    qualifiers = {"in_title": False, "in_h1": False, "in_schema": False,
                  "in_about": False}
    # The FULL homepage <title>, not the name representative. The representative
    # is the brand-name portion split off at the separator ("WHAT THE FIT"), so
    # it can never contain a category qualifier - the qualifier is exactly what
    # lives in the tail that was dropped ("- Oversized Streetwear & Urban
    # Fashion"). Testing the representative made in_title structurally always
    # false and forced the model to overrule the boolean from the raw title.
    title = " ".join(filter(None, [
        next((p.get("title") for p in pages if p.get("page_class") == "homepage"), None)
        or (pages[0].get("title") if pages else ""),
        next(((p.get("open_graph") or {}).get("og:title")
              for p in pages if p.get("page_class") == "homepage"), None),
        next(((p.get("metas") or {}).get("description")
              for p in pages if p.get("page_class") == "homepage"), None),
    ]))
    h1s = [v for g in ne["groups"].groups for s, v in g["reps"] if s == "h1"]

    def has_qualifier(text):
        toks = set(re.findall(r"[a-z]+", (text or "").lower()))
        return bool(toks & QUALIFIER_WORDS) or \
            bool(toks & {t for t in LEGAL_TOKENS if t not in ("foundation",)})

    if has_qualifier(title):
        qualifiers["in_title"] = True
    if any(has_qualifier(h) for h in h1s):
        qualifiers["in_h1"] = True
    for page in pages:
        for block in jsonld_blocks(page):
            if not block.get("parse_ok", False):
                continue
            for node in graph_entries(block.get("parsed")):
                if type_names(node) & IDENTITY_TYPES:
                    for k in ("description", "disambiguatingDescription",
                              "alternateName", "slogan"):
                        if has_qualifier(str(node.get(k) or "")):
                            qualifiers["in_schema"] = True
        if page.get("page_class") in ("about", "homepage"):
            if has_qualifier(page.get("visible_text") or ""):
                qualifiers["in_about"] = True
    return result(
        "ENT-AMBIGUOUS-NAME", "pass", evidence_quality="semantic-judgment",
        urls=[p.get("requested_url") for p in pages
              if p.get("page_class") in ("homepage", "about")][:3],
        observations={
            "candidate_name": name, "name_source": name_source,
            "name_variants": [g["reps"][0][1] for g in ne["groups"].groups][:6],
            "qualifier_presence": qualifiers,
            "qualifier_words_checked": sorted(QUALIFIER_WORDS)[:15],
            # The orchestrator procedure names this as the one gate the model must
            # finish; every other semantic-judgment pass is a prepared pass to be
            # left alone. Saying so in the data means the runner can label it
            # instead of the reader inferring it from prose.
            "requires_completion": True,
            "prepared_gate": (
                "MODEL JUDGMENT - complete here, do not open a SKILL.md for it. "
                "Ask: could a retrieval system confuse this brand with a different "
                "entity sharing the name? A shared name alone is NEVER a finding "
                "when a distinguishing qualifier exists anywhere name-bearing "
                "(title, og:site_name, H1, schema description, about page). "
                "qualifier_words_checked is a keyword hint, not the verdict: read "
                "candidate_name and the page title yourself before trusting a "
                "false. To finish, either leave gate 'pass' or set it to 'finding', "
                "and in EITHER case add observations.model_completion: 1-3 "
                "sentences naming the namesake risk and the qualifier that does or "
                "does not resolve it."),
        })


def check_corroboration(snap):
    """ENT-CORROBORATION-ABSENT: declared external presence vs corroboration."""
    ext = snap.get("external_presence")
    if ext is None or len(ext) == 0:
        return result("ENT-CORROBORATION-ABSENT", "not_evaluated",
                      observations={"reason": "no declared external-presence "
                                              "links recorded in the snapshot"})

    def resolved(e):
        s = e.get("http_status")
        return isinstance(s, int) and 200 <= s < 400

    n = len(ext)
    indep_resolved = [e for e in ext
                      if e.get("owned_vs_independent") == "independent" and resolved(e)]
    owned_resolved = [e for e in ext
                      if e.get("owned_vs_independent") == "owned" and resolved(e)]
    unknown_resolved = [e for e in ext
                        if e.get("owned_vs_independent") == "unknown" and resolved(e)]
    indep_errors = [e for e in ext if e.get("owned_vs_independent") == "independent"
                    and isinstance(e.get("http_status"), int)
                    and e["http_status"] >= 400]
    timeouts = [e for e in ext if e.get("http_status") is None]  # never findings
    matches = [e for e in indep_resolved if e.get("brand_name_match") is True]
    obs = {"declared_links": n, "resolved_links": len(indep_resolved) +
           len(owned_resolved) + len(unknown_resolved),
           "independent_resolved": len(indep_resolved),
           "owned_resolved": len(owned_resolved),
           "unknown_resolved": len(unknown_resolved),
           "independent_http_errors": len(indep_errors),
           "unresolved_timeouts": len(timeouts),
           "independent_brand_matches": len(matches)}
    if matches:
        return result("ENT-CORROBORATION-ABSENT", "pass", observations=obs)
    # brand_name_match may be unrecorded (collector fetch budget) - never punish
    if indep_resolved and all(e.get("brand_name_match") is None
                              for e in indep_resolved):
        obs["reason"] = ("independent surfaces resolve but brand match was not "
                         "verified by the collector; cannot establish absence")
        return result("ENT-CORROBORATION-ABSENT", "pass", observations=obs)
    if timeouts and not indep_resolved:
        # absence would rest on timeouts - timeouts never become findings
        obs["reason"] = ("independent destination(s) unresolved (timeout); "
                         "timeouts never become findings")
        return result("ENT-CORROBORATION-ABSENT", "pass", observations=obs)
    if indep_errors and not indep_resolved:
        # the site DECLARES independent corroboration and every such link is
        # broken - a real deterministic finding (dead sameAs targets)
        sample = indep_errors[0].get("url", "")
        evidence = ("%d declared independent corroboration link(s) all fail to resolve "
                    "(e.g. %s); %d owned links resolve."
                    % (len(indep_errors), sample, len(owned_resolved)))
        return result(
            "ENT-CORROBORATION-ABSENT", "finding",
            urls=[e.get("url") for e in indep_errors[:3]],
            observations=obs,
            candidate=candidate(
                "Declared independent corroboration links fail to resolve",
                "medium", "high", short(evidence),
                "The site points at independent surfaces (a directory, registry, or "
                "review profile) and they are dead - the declared corroboration is "
                "broken, so nothing independent vouches for the entity.",
                "Fix or remove the dead independent links (sameAs/footer).",
                "medium", effort="small", owner="web-platform",
                acceptance="All declared independent links return 2xx/3xx."))
    if owned_resolved and not indep_resolved:
        # every resolving declared link is owned. Zero DECLARED independent links
        # is common on well-run brands and only meaningful when the entity name is
        # ambiguous - model judgment, paired with ENT-AMBIGUOUS-NAME (never
        # auto-flagged; the corpus showed this firing on 4/6 known-good sites).
        sample = owned_resolved[0].get("url", "")
        obs["note"] = ("all resolving declared links are owned (e.g. %s); zero declared "
                       "independent corroboration is common on healthy brands and only "
                       "meaningful when the ENT-AMBIGUOUS-NAME judgment finds the name "
                       "ambiguous - complete the gate there, citing these numbers" % sample)
        obs["prepared_for"] = "ENT-AMBIGUOUS-NAME pairing (model judgment)"
        return result("ENT-CORROBORATION-ABSENT", "pass",
                      evidence_quality="semantic-judgment", observations=obs)
    obs["reason"] = ("declared surfaces resolved but none classified 'independent'; "
                     "owned surfaces never count as corroboration and 'unknown' "
                     "classifications cannot establish corroboration absence")
    return result("ENT-CORROBORATION-ABSENT", "pass", observations=obs)


# --- driver ----------------------------------------------------------------


def resolve_marketplace_root(start_dir):
    node = os.path.abspath(start_dir)
    while True:
        if os.path.exists(os.path.join(node, "marketplace.json")):
            return node
        parent = os.path.dirname(node)
        if parent == node:
            return None
        node = parent


def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def not_evaluated_fragment(reason):
    return {"skill_id": "entity-consistency-audit", "mode": "snapshot",
            "generated_at": datetime.datetime.now(
                datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "results": [],
            "not_evaluated": [{"check_id": cid, "reason": reason}
                              for cid in CHECK_IDS]}


def write_fragment(fragment, out_path):
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(fragment, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def summarize(results):
    findings = [r for r in results if r["gate"] == "finding"]
    passes = [r for r in results if r["gate"] == "pass"]
    skipped = [r for r in results if r["gate"] == "not_evaluated"]
    lines = ["check_entities: %d finding(s), %d pass, %d not_evaluated"
             % (len(findings), len(passes), len(skipped))]
    for r in findings:
        c = r["candidate_finding"]
        lines.append("  [%s/%s] %s (%s)" % (c["severity"], c["confidence"],
                                            c["title"],
                                            ", ".join(r.get("urls", []))[:100]))
    for r in results:
        if r.get("check_id") == "ENT-AMBIGUOUS-NAME":
            obs = r.get("observations", {}) or {}
            lines.append("  ambiguous-name prepared: candidate=%r variants=%d "
                         "(gate=%s; orchestrator completes per SKILL.md)"
                         % (obs.get("candidate_name"),
                            len(obs.get("name_variants", [])), r.get("gate")))
    return "\n".join(lines)


def analyze(snap, notes):
    pages = snap.get("pages") or []
    if not pages:
        raise ValueError("snapshot contains no pages")
    ne = collect_name_evidence(pages)
    results = [
        check_jsonld_invalid(snap, pages),
        check_structured_visible(snap, pages, ne["groups"]),
        check_name_inconsistent(pages, ne),
        check_ambiguous_name(pages, ne),
        check_corroboration(snap),
    ]
    return results


def main():
    ap = argparse.ArgumentParser(
        description="entity-consistency-audit: analyze entity identity and "
                    "structured-data consistency (JSON-LD validity, "
                    "structured-vs-visible conflicts, name consistency, "
                    "corroboration, ambiguity observations) from a snapshot. "
                    "Snapshot-only reader; performs no network I/O.")
    ap.add_argument("--snapshot", required=True,
                    help="path to snapshot.json written by collect_snapshot.py")
    ap.add_argument("--out", required=True,
                    help="path for the finding fragment JSON to write")
    ap.add_argument("--fragment-schema", default=None,
                    help="optional explicit path to finding_fragment.json "
                         "(default: <marketplace root>/skills/audit-orchestrator/"
                         "references/finding_fragment.json, resolved by walking "
                         "up from this script to marketplace.json; self-"
                         "validation is skipped with a printed note when "
                         "unresolvable)")
    args = ap.parse_args()

    notes = []
    try:
        snap = load_json(args.snapshot)
        try:
            _t0 = datetime.datetime.fromisoformat(
                snap["audited_at"].replace("Z", "+00:00")).timestamp()
            print("audit elapsed since snapshot: %ds (budget 300s; timeboxes apply)"
                  % max(0, int(time.time() - _t0)))
        except (KeyError, ValueError, AttributeError, OSError):
            pass
    except (OSError, ValueError) as e:
        fragment = not_evaluated_fragment("snapshot unreadable: %s" % e)
        soft_validate(fragment, args.fragment_schema or default_schema_path(), notes)
        write_fragment(fragment, args.out)
        print("check_entities: could not read snapshot; not_evaluated fragment "
              "-> %s" % args.out)
        for note in notes:
            print("  note: %s" % note)
        sys.exit(2)

    try:
        results = analyze(snap, notes)
    except ValueError as e:
        fragment = not_evaluated_fragment("could not analyze snapshot: %s" % e)
        soft_validate(fragment, args.fragment_schema or default_schema_path(), notes)
        write_fragment(fragment, args.out)
        print("check_entities: %s; not_evaluated fragment -> %s"
              % (e, args.out))
        for note in notes:
            print("  note: %s" % note)
        sys.exit(2)

    fragment = {
        "skill_id": "entity-consistency-audit",
        "mode": "snapshot",
        "generated_at": datetime.datetime.now(
            datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "results": results,
        "not_evaluated": [],
    }
    errs = soft_validate(fragment, args.fragment_schema or default_schema_path(),
                         notes)
    if errs:
        sys.stderr.write("check_entities: FAIL - fragment does not validate "
                         "against finding_fragment.json\n")
        for e in errs:
            sys.stderr.write("  - %s\n" % e)
        write_fragment(fragment, args.out)
        sys.exit(1)
    write_fragment(fragment, args.out)
    print(summarize(results))
    for note in notes:
        print("  note: %s" % note)
    sys.exit(0)


def default_schema_path():
    root = resolve_marketplace_root(os.path.dirname(os.path.abspath(__file__)))
    if not root:
        return None
    return os.path.join(root, "skills", "audit-orchestrator", "references",
                        "finding_fragment.json")


def soft_validate(fragment, schema_path, notes):
    """Soft self-validation: on any gap print one note and skip."""
    if not schema_path or not os.path.exists(schema_path):
        notes.append("fragment schema not found; self-validation skipped")
        return None
    root = resolve_marketplace_root(os.path.dirname(os.path.abspath(__file__)))
    if root:
        sys.path.insert(0, os.path.join(root, "skills", "audit-orchestrator",
                                        "scripts"))
    try:
        from build_report import validate  # the one sanctioned soft import
    except ImportError:
        notes.append("build_report.validate unavailable; self-validation skipped")
        return None
    return validate(fragment, load_json(schema_path))


if __name__ == "__main__":
    main()
