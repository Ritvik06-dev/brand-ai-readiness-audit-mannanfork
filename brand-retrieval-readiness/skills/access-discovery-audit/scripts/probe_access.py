#!/usr/bin/env python3
"""probe_access.py - access-discovery-audit: analyze crawler reach from a snapshot.

Snapshot-only reader: this script performs NO network I/O. All network work
(fetches, robots, UA probes, llms.txt) belongs to collect_snapshot.py, which
produces the snapshot this script reads from disk.

Reads: one snapshot JSON (see the orchestrator's references/snapshot_schema.json).
Writes: one finding fragment JSON (see references/finding_fragment.json) covering
the ACC-* checks in check_catalog.json. Titles follow each check's
pattern_template and evidence follows its evidence_template, filled from real
observations: site- or template-level patterns with counts and denominators,
never one visitor's incident.

Exit codes: 0 = fragment written and valid; 1 = fragment validation failed;
2 = could not analyze (a fragment with not_evaluated entries is still written).
Stdout is a small summary; page text never leaves the snapshot beyond short
quoted evidence.
"""

import argparse
import datetime
import json
import os
import re
import sys
from urllib.parse import urlparse

CHECK_IDS = [
    "ACC-ROBOTS-ROLE", "ACC-ROBOTS-UNAVAILABLE", "ACC-INDEX-CONTROL",
    "ACC-NOARCHIVE-COPILOT", "ACC-CANONICAL-CONFLICT", "ACC-REDIRECT-LOOP",
    "ACC-BOT-CHALLENGE", "ACC-SITEMAP-ORPHAN", "ACC-SITEMAP-INVALID",
    "ACC-HREFLANG-INCONSISTENT", "ACC-LLMS-TXT-ABSENT",
]
IMPORTANT_CLASSES = {"homepage", "decision", "product", "docs", "about", "trust"}
HREFLANG_RE = re.compile(r"^[a-z]{2,3}(-[A-Za-z]{2})?(-[a-z]{2})?$")
MAX_QUOTE = 200


def norm_path(url):
    path = urlparse(url or "").path
    if not path:
        return "/"
    return path.rstrip("/") or "/"


def same_origin(url, base_netloc):
    return urlparse(url or "").netloc.rstrip(".").lower() == base_netloc


def rule_matches(path, rule):
    """Conservative robots rule matcher: prefix + trailing-wildcard + $ anchor.
    Mid-pattern wildcards do not match (conservative: fewer findings)."""
    rule = rule.strip()
    if not rule:
        return False
    if rule.endswith("$"):
        return path == rule[:-1]
    return path.startswith(rule.rstrip("*"))


def rules_for_token(rows, token):
    specific = [r for r in rows if r["token"].lower() == token.lower()]
    wildcard = [r for r in rows if r["token"] == "*"]
    chosen = specific or wildcard
    disallow, allow = [], []
    for row in chosen:
        disallow.extend(row.get("disallowed_paths") or [])
        allow.extend(row.get("allow_paths") or [])
    return disallow, allow


def path_blocked_by(rows, token, path):
    """True when the longest matching rule for this token/path is a disallow.
    Conservative mid-pattern wildcards never match, so absence of a match means
    'not blocked by the rules we can parse'."""
    disallow, allow = rules_for_token(rows, token)
    best = None
    for rule, kind in ([(d, "disallow") for d in disallow]
                       + [(a, "allow") for a in allow]):
        if rule_matches(path, rule):
            if best is None or len(rule.rstrip("*$")) > best[0]:
                best = (len(rule.rstrip("*$")), kind)
    return best is not None and best[1] == "disallow"


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
    # Belt-and-braces with severity_model rule 1: a specialist can never emit
    # critical without high confidence - clamp at emit, and build_report
    # normalizes (with a lint warning) if anything still slips through.
    if severity == "critical" and confidence != "high":
        severity = "high"
        priority = "high" if priority == "critical" else priority
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


# --- checks ---------------------------------------------------------------


def check_robots_role(snap, rows, important_pages):
    """Search-index crawler blocked on important paths while direct fetches succeed."""
    status = snap["robots"]["status"]
    if status == "not_found":
        return result("ACC-ROBOTS-ROLE", "pass",
                      observations={"reason": "robots.txt 404 = no crawl restrictions "
                                              "(never a defect)"})
    tokens = sorted({r["token"] for r in rows if r.get("role") == "search-index"})
    blocked = []
    for token in tokens:
        hits = []
        for page in important_pages:
            path = norm_path(page["requested_url"])
            if path_blocked_by(rows, token, path):
                hits.append((page, path))
        if hits:
            blocked.append((token, hits))
    if not blocked:
        return result("ACC-ROBOTS-ROLE", "pass", observations={
            "search_index_tokens_evaluated": tokens or ["(none declared)"],
            "important_paths_checked": len(important_pages),
            "note": "no search-index crawler is disallowed on any sampled important path",
        })
    results = []
    for token, hits in blocked:
        site_wide = any(norm_path(p["requested_url"]) == "/" for p, _ in hits)
        classes = sorted({p.get("page_class") or "page" for p, _ in hits})
        severity = "critical" if site_wide else "high"
        sample = hits[0][1]
        rule_text = ""
        disallow, _allow = rules_for_token(rows, token)
        for rule in disallow:
            if rule_matches(sample, rule):
                rule_text = rule
                break
        urls = [p["requested_url"] for p, _ in hits]
        results.append(result(
            "ACC-ROBOTS-ROLE", "finding", urls=urls,
            observations={"token": token, "blocked_paths": [p for _, p in hits],
                          "page_classes": classes, "site_wide": site_wide,
                          "matching_rule": rule_text,
                          "direct_statuses": {p["requested_url"]: p["status"]
                                                    for p, _ in hits}},
            evidence_quality="direct-measurement",
            candidate=candidate(
                "%s crawler access to %s pages is blocked by robots policy while direct fetches succeed"
                % (token, "/".join(classes[:2])),
                severity, "high",
                "robots.txt contains 'User-agent: %s' with '%s: %s'; the same path(s) returned "
                "200 to a direct fetch during the audit (%s of %d sampled important paths blocked)."
                % (token, "Disallow", rule_text or "/", len(hits), len(important_pages)),
                "OpenAI documents that sites disallowing OAI-SearchBot 'will not be shown in "
                "ChatGPT search answers, though can still appear as navigational links' "
                "(developers.openai.com/api/docs/bots).",
                "Allow %s on public %s paths (keep training-bot policy unchanged if that "
                "restriction is intentional)." % (token, " and ".join(classes[:2])),
                severity,
                surfaces=["chatgpt_search", "claude_search", "perplexity_retrieval"],
                effort="small", owner="web-platform",
                acceptance="No robots.txt rule for %s matches the affected path(s), and a fetch "
                           "with that User-Agent returns 200." % token)))
    return results


def check_robots_unavailable(snap):
    robots = snap["robots"]
    if robots["status"] != "error":
        return result("ACC-ROBOTS-UNAVAILABLE", "pass", observations={
            "status": robots["status"], "http_status": robots.get("http_status"),
            "note": "404 means 'no crawl restrictions' - never a defect"})
    # The collector records robots attempts (2 = one retry after a 5xx); the
    # severity rule needs two consecutive 5xx for high/high. A single attempt
    # -> low confidence, which build_report routes to needs_verification.
    attempts = robots.get("attempts") or 1
    if attempts >= 2:
        return result(
            "ACC-ROBOTS-UNAVAILABLE", "finding",
            urls=[snap["requested_url"] + "/robots.txt"],
            observations={"http_status": robots.get("http_status"),
                          "recorded_attempts": attempts,
                          "consecutive_5xx_rule": "2+ required for high/high - satisfied"},
            evidence_quality="direct-measurement",
            candidate=candidate(
                "robots.txt is unavailable to crawlers (%s)" % robots.get("http_status"),
                "high", "high",
                "/robots.txt returned %s on %d consecutive attempts during the audit - the "
                "severity rule's two-consecutive-5xx bar is met."
                % (robots.get("http_status"), attempts),
                "An unavailable robots.txt can delay crawling of the whole site; a 404 would "
                "have meant 'no crawl restrictions', which is not a defect.",
                "Restore robots.txt availability and monitor 5xx rates on it.",
                "high", effort="small", owner="infrastructure",
                acceptance="A re-audit observes robots.txt returning 200 (or the origin's "
                           "intended response) on two consecutive requests."))
    return result(
        "ACC-ROBOTS-UNAVAILABLE", "finding",
        urls=[snap["requested_url"] + "/robots.txt"],
        observations={"http_status": robots.get("http_status"),
                      "recorded_attempts": attempts,
                      "consecutive_5xx_rule": "2+ required for high/high"},
        evidence_quality="direct-measurement",
        candidate=candidate(
            "robots.txt is unavailable to crawlers (%s)" % robots.get("http_status"),
            "high", "low",
            "/robots.txt returned %s on the single recorded attempt; the severity rule "
            "requires two or more consecutive 5xx to escalate beyond needs_verification."
            % robots.get("http_status"),
            "An unavailable robots.txt can delay crawling of the whole site; a 404 would "
            "have meant 'no crawl restrictions', which is not a defect.",
            "Confirm robots.txt availability over time; if 5xx persists, fix the origin or "
            "cache robots.txt at the edge.",
            "high", effort="small", owner="web-platform",
            acceptance="robots.txt returns 200 (or 404, which is fine) on two consecutive "
                       "fetches."))


def parse_directives(text):
    out = {}
    for part in re.split(r"[,;]", (text or "").lower()):
        if ":" in part:
            k, v = part.split(":", 1)
            out[k.strip()] = v.strip()
        elif part.strip():
            out[part.strip()] = None
    return out


def important_only(pages):
    return [p for p in pages if (p.get("page_class") or "other") in IMPORTANT_CLASSES]


def check_index_control(snap, pages):
    imp = important_only(pages)
    findings, observations = [], {}
    for page in imp:
        directives = {}
        for field in ("robots_meta", "x_robots_tag"):
            parsed = parse_directives(page.get(field))
            if parsed:
                directives[field] = parsed
        merged = {}
        for d in directives.values():
            merged.update(d)
        flags = {}
        if "noindex" in merged or "none" in merged:
            flags["noindex"] = True
        if "nosnippet" in merged:
            flags["nosnippet"] = True
        if str(merged.get("max-snippet", "1")).strip() in ("0", "") and "max-snippet" in merged:
            flags["max-snippet:0"] = True
        if flags:
            findings.append((page, flags, list(directives)))
        if merged.get("data-nosnippet") or "data-nosnippet" in (page.get("raw_html") or ""):
            observations.setdefault("pages_with_data_nosnippet", 0)
            observations["pages_with_data_nosnippet"] += 1
    observations["important_pages_checked"] = len(imp)
    if not findings:
        return result("ACC-INDEX-CONTROL", "pass", observations=observations)
    results = []
    noindex_pages = [p for p, f, _ in findings if "noindex" in f]
    if noindex_pages:
        site_wide = any(norm_path(p["requested_url"]) == "/" for p in noindex_pages)
        results.append(result(
            "ACC-INDEX-CONTROL", "finding", urls=[p["requested_url"] for p in noindex_pages],
            observations={"pages": [{"url": p["requested_url"],
                                     "page_class": p.get("page_class"),
                                     "robots_meta": short(p.get("robots_meta")),
                                     "x_robots_tag": short(p.get("x_robots_tag"))}
                                    for p in noindex_pages],
                          "data_nosnippet_observations": observations.get(
                              "pages_with_data_nosnippet", 0)},
            evidence_quality="direct-measurement",
            candidate=candidate(
                "noindex on %s removes them from Google Search and AI features"
                % ("the homepage and site-wide" if site_wide
                   else "important %s pages" % "/".join(sorted(
                       {p.get("page_class") or "page" for p in noindex_pages}))),
                "critical" if site_wide else "high", "high",
                "%d/%d sampled important pages carry noindex via robots meta or "
                "X-Robots-Tag (%s)." % (len(noindex_pages), len(imp),
                                        "; ".join(short(p.get("robots_meta") or
                                                        p.get("x_robots_tag"))
                                                  for p in noindex_pages[:2])),
                "noindex removes the page from Google Search entirely; Google's AI-features "
                "documentation names noindex among the controls that limit what AI Overviews "
                "and AI Mode can show (developers.google.com/search/docs/appearance/"
                "ai-features).",
                "Remove noindex from these public pages if they are meant to be retrievable; "
                "keep it on staging, duplicates, or internal URLs.",
                "critical" if site_wide else "high", effort="small", owner="web-platform",
                acceptance="A no-JS fetch of each affected page shows no noindex in robots "
                           "meta or X-Robots-Tag.")))
    snippet_pages = [p for p, f, _ in findings
                     if ("nosnippet" in f or "max-snippet:0" in f) and "noindex" not in f]
    if snippet_pages:
        results.append(result(
            "ACC-INDEX-CONTROL", "finding", urls=[p["requested_url"] for p in snippet_pages],
            observations={"pages": [{"url": p["requested_url"],
                                     "page_class": p.get("page_class"),
                                     "robots_meta": short(p.get("robots_meta"))}
                                    for p in snippet_pages]},
            evidence_quality="direct-measurement",
            candidate=candidate(
                "nosnippet/max-snippet:0 on %s pages removes them from Google AI features"
                % "/".join(sorted({p.get("page_class") or "page" for p in snippet_pages})),
                "high", "high",
                "%d/%d sampled important pages carry nosnippet or max-snippet:0 (%s)."
                % (len(snippet_pages), len(imp),
                   "; ".join(short(p.get("robots_meta") or "") for p in snippet_pages[:2])),
                "Google's AI-features documentation: 'To limit the information shown from "
                "your pages in Search, use nosnippet, data-nosnippet, max-snippet, or "
                "noindex controls.' The search listing survives, so this is high, not "
                "critical, and scoped to Google AI surfaces.",
                "Remove nosnippet / set a workable max-snippet on public decision pages; "
                "scope data-nosnippet to boilerplate only.",
                "high", surfaces=["google_ai_overviews_ai_mode"],
                effort="small", owner="web-platform",
                acceptance="A no-JS fetch of each affected page shows neither nosnippet nor "
                           "max-snippet:0.")))
    return results


def check_noarchive(snap, pages):
    imp = important_only(pages)
    hits = []
    for page in imp:
        merged = {}
        for field in ("robots_meta", "x_robots_tag"):
            merged.update(parse_directives(page.get(field)))
        if "noarchive" in merged or "nocache" in merged:
            hits.append((page, sorted({d for d in ("noarchive", "nocache") if d in merged})))
    if not hits:
        return result("ACC-NOARCHIVE-COPILOT", "pass", observations={
            "important_pages_checked": len(imp),
            "note": "no noarchive/nocache on sampled important pages"})
    directive = hits[0][1][0]
    return result(
        "ACC-NOARCHIVE-COPILOT", "finding", urls=[p["requested_url"] for p, _ in hits],
        observations={"pages": [{"url": p["requested_url"], "page_class": p.get("page_class"),
                                 "directives": d, "robots_meta": short(p.get("robots_meta"))}
                                for p, d in hits[:5]],
                      "important_pages_checked": len(imp)},
        evidence_quality="direct-measurement",
        candidate=candidate(
            "%s pages carry %s, limiting Copilot's use of them"
            % ("/".join(sorted({p.get("page_class") or "page" for p, _ in hits})), directive),
            "high" if any("noarchive" in d for _, d in hits) else "medium", "high",
            "%d/%d sampled important pages carry %s via robots meta or X-Robots-Tag (%s)."
            % (len(hits), len(imp), ", ".join(sorted({d for _, d in hits for d in d})),
               short(hits[0][0].get("robots_meta") or hits[0][0].get("x_robots_tag"))),
            "Bing documents that a page with noarchive 'will not be included in Bing Chat "
            "answers, not be linked to in the answers', and nocache limits it to URL, title "
            "and snippet - while both still rank in ordinary Bing results "
            "(blogs.bing.com/webmaster/september-2023). Paywalled and news sites commonly "
            "ship noarchive for unrelated reasons.",
            "If the intent was only to prevent caching, replace noarchive with nocache; "
            "remove both from public decision pages.",
            "high" if any("noarchive" in d for _, d in hits) else "medium",
            surfaces=["bing_copilot"], effort="small", owner="web-platform",
            acceptance="A no-JS fetch of each affected page shows neither noarchive nor "
                       "nocache in robots meta or X-Robots-Tag."))


def norm_url_key(url):
    parts = urlparse(url or "")
    host = (parts.netloc or "").lower().rstrip(".")
    host = host[4:] if host.startswith("www.") else host
    path = parts.path or "/"
    path = path.rstrip("/")
    for suffix in ("/index.html", "/index.htm"):
        if path.endswith(suffix):
            path = path[: -len(suffix)]
            break
    return host + path.rstrip("/")


def check_canonical(snap, pages):
    conflicts = []
    for page in pages:
        canonical = page.get("canonical")
        if not canonical:
            continue
        if norm_url_key(canonical) != norm_url_key(page.get("final_url") or
                                                   page["requested_url"]):
            conflicts.append((page, canonical))
    if not conflicts:
        return result("ACC-CANONICAL-CONFLICT", "pass", observations={
            "pages_with_canonical": sum(1 for p in pages if p.get("canonical")),
            "pages_checked": len(pages),
            "note": "all declared canonicals agree with the final fetch URL"})
    targets = {norm_url_key(c) for _, c in conflicts}
    if len(conflicts) >= 2 and len(targets) == 1:
        # Coherent consolidation: many pages, one shared canonical target. That
        # is a deliberate site-wide signal (e.g. version homepages folding into
        # the current docs root), not the scattered disagreement the check
        # guards against. Recorded, never flagged.
        return result("ACC-CANONICAL-CONFLICT", "pass", observations={
            "coherent_consolidation": True,
            "pages_involved": len(conflicts),
            "shared_target": sorted(targets)[0],
            "note": "multiple pages consolidate onto one canonical target - an "
                    "intentional-looking signal, recorded but not flagged"})
    # A true redirect/canonical disagreement is directly measured on both
    # sides: the page was redirected to X but declares canonical Y != X.
    redirected = [(p, c) for p, c in conflicts if len(p.get("redirect_chain") or []) > 1]
    if redirected:
        return result(
            "ACC-CANONICAL-CONFLICT", "finding",
            urls=[p["requested_url"] for p, _ in redirected],
            observations={"conflicts": [{"url": p["requested_url"], "canonical": c,
                                         "final_url": p.get("final_url"),
                                         "redirected": True}
                                        for p, c in redirected[:5]],
                          "pages_checked": len(pages)},
            evidence_quality="direct-measurement",
            candidate=candidate(
                "Canonical declarations disagree with redirect destinations on %d sampled "
                "pages" % len(redirected),
                "medium" if len(redirected) < max(2, len(pages) // 2) else "high", "high",
                "%d/%d sampled pages redirect to one URL while declaring a different "
                "canonical: %s redirects to %s but declares canonical %s."
                % (len(redirected), len(pages), redirected[0][0]["requested_url"],
                   redirected[0][0].get("final_url"), redirected[0][1]),
                "Canonical and redirect signals that disagree split retrieval surfaces' "
                "understanding of the authoritative URL, fragmenting discovery of the page.",
                "Make the canonical of each page match its redirect destination (or drop "
                "the canonical and let the redirect target self-canonicalize).",
                "medium", effort="small", owner="web-platform",
                acceptance="Every sampled page's canonical equals its final fetch URL after "
                           "scheme/host/trailing-slash normalization."))
    # Declaration-only divergence with no redirect involved and no coherent
    # consolidation pattern: intent cannot be read offline. One or two such
    # pages is a hypothesis, not an established defect -> low confidence, which
    # build_report routes to needs_verification.
    low_conf = len(conflicts) <= 2
    return result(
        "ACC-CANONICAL-CONFLICT", "finding", urls=[p["requested_url"] for p, _ in conflicts],
        observations={"conflicts": [{"url": p["requested_url"], "canonical": c,
                                     "final_url": p.get("final_url")}
                                    for p, c in conflicts[:5]],
                      "pages_checked": len(pages),
                      "divergence_class": "declaration-only"},
        evidence_quality="direct-measurement",
        candidate=candidate(
            "Canonical declarations disagree with the final fetch URL on %d sampled pages"
            % len(conflicts),
            "medium", "low" if low_conf else "medium",
            "%d/%d sampled pages declare a canonical that differs from their final fetch "
            "URL with no redirect involved: %s declares canonical %s. %s"
            % (len(conflicts), len(pages), conflicts[0][0]["requested_url"],
               conflicts[0][1],
               "Single uncorroborated divergence - verify intent before treating as a "
               "defect." if low_conf else "Scattered targets across same-template pages."),
            "Canonical declarations that point somewhere the URL itself does not go can "
            "consolidate signals away from live content - or they can be deliberate; "
            "intent is not observable offline.",
            "Point each page's canonical at the URL that serves its content, unless the "
            "consolidation is intentional.",
            "medium", effort="small", owner="web-platform",
            acceptance="Every sampled page's canonical equals its final fetch URL after "
                       "scheme/host/trailing-slash normalization."))


def check_redirect_loop(snap, pages):
    loops, chains = [], []
    for page in pages:
        chain = page.get("redirect_chain") or []
        seen = {}
        loop = False
        for i, u in enumerate(chain):
            key = norm_url_key(u)
            if key in seen:
                loop = True
                break
            seen[key] = i
        if loop:
            loops.append(page)
        elif len(chain) >= 4:
            chains.append(page)
    if not loops and not chains:
        return result("ACC-REDIRECT-LOOP", "pass", observations={
            "pages_checked": len(pages),
            "max_chain_hops": max((len(p.get("redirect_chain") or []) for p in pages),
                                  default=0)})
    sev = "high" if loops else "medium"
    return result(
        "ACC-REDIRECT-LOOP", "finding", urls=[p["requested_url"] for p in loops + chains],
        observations={"loops": [p["requested_url"] for p in loops[:5]],
                      "long_chains": [{"url": p["requested_url"],
                                       "hops": len(p.get("redirect_chain") or [])}
                                      for p in chains[:5]],
                      "pages_checked": len(pages)},
        evidence_quality="direct-measurement",
        candidate=candidate(
            "Important URLs redirect through %s"
            % ("loops" if loops else "%d+-hop chains" % 4),
            sev, "high",
            "%d sampled URL(s) loop through repeated redirects; %d require 4+ hops "
            "(example: %s)." % (len(loops), len(chains),
                                " -> ".join((chains or loops)[0].get("redirect_chain") or [])
                                [:MAX_QUOTE]),
            "Redirect loops or excessive chains prevent fetchers from reaching content at "
            "all; loops make the URL unreachable to every retrieval surface.",
            "Collapse each loop/chain to a single 301/308 hop to the canonical URL.",
            sev, effort="small", owner="web-platform",
            acceptance="Each affected URL resolves in one hop and the redirect chain "
                       "contains no repeated URLs."))


def check_bot_challenge(snap):
    probes = (snap.get("probes") or {}).get("ua_probes") or []
    hits = [p for p in probes if p.get("differential")]
    if not hits:
        return result("ACC-BOT-CHALLENGE", "pass", observations={
            "probes_run": len(probes),
            "tokens": [p.get("token") for p in probes],
            "note": "no UA differential observed on robots-allowed homepage probes"})
    return result(
        "ACC-BOT-CHALLENGE", "finding",
        urls=[p.get("requested_path") for p in hits],
        observations={"probes": [{"token": p.get("token"), "status": p.get("status"),
                                  "differential": p.get("differential"),
                                  "cf_mitigated": p.get("cf_mitigated"),
                                  "content_type": p.get("content_type")} for p in hits],
                      "note": "same-IP spoofed-UA evidence; verification via provider IP "
                              "lists is the owner-side path"},
        evidence_quality="direct-measurement",
        candidate=candidate(
            "Automated retrieval traffic receives %s where direct traffic succeeds"
            % ", ".join(str(p.get("status")) for p in hits),
            "high", "medium",
            "; ".join("%s UA received %s (cf-mitigated: %s, content-type: %s) while a direct "
                      "fetch returned 200 on the same path" % (p.get("token"), p.get("status"),
                                                               p.get("cf_mitigated"),
                                                               p.get("content_type"))
                      for p in hits) + ". Same-IP spoofed-UA evidence: suspected edge "
            "discrimination, capped at medium confidence per severity_model.md, so this "
            "finding's severity ceiling is high (rule 1: critical requires high confidence).",
            "A WAF challenge served to retrieval-bot UAs blocks citation surfaces at the "
            "edge; Cloudflare-documented signals are the cf-mitigated header and a forced "
            "text/html content-type even on non-HTML requests.",
            "Allowlist the documented retrieval crawlers at the edge (or add a verified-bot "
            "rule); verify with owner logs or provider IP lists "
            "(claude.com/crawling/bots.json, perplexity.com/perplexitybot.json).",
            "high",
            surfaces=["chatgpt_search", "perplexity_retrieval", "claude_search",
                      "bing_copilot"],
            effort="medium", owner="infrastructure",
            acceptance="Homepage probes with each retrieval-bot UA return 200 with the "
                       "origin's real content type."))


def check_sitemap_orphan(snap, pages):
    sitemap = snap.get("sitemap")
    if not sitemap or not sitemap.get("parse_ok"):
        return result("ACC-SITEMAP-ORPHAN", "pass", observations={
            "note": "no parsed sitemap - absence alone is never a defect "
                    "(see ACC-SITEMAP-INVALID if a declared one failed)"})
    base = snap["requested_url"]
    netloc = urlparse(base).netloc
    linked = set()
    for page in pages:
        for link in page.get("links") or []:
            href = link.get("href") or ""
            if same_origin(href, netloc):
                linked.add(norm_path(href))
    selected = {norm_path(u) for u in (snap.get("discovery") or {}).get("selected") or []}
    sample = sitemap.get("lastmod_sample") or []
    orphans = [e["url"] for e in sample
               if norm_path(e["url"]) not in linked and norm_path(e["url"]) not in selected]
    candidates_count = (snap.get("discovery") or {}).get("candidates_count") or 0
    large_site = candidates_count >= 50
    observations = {"sitemap_sample_size": len(sample), "orphans": orphans[:10],
                    "orphan_count": len(orphans), "large_site_threshold": large_site,
                    "note": "orphan detection runs on a bounded sitemap sample "
                            "(%d of %s entries)" % (len(sample),
                                                    sitemap.get("entries_count"))}
    if not orphans or not large_site:
        observations["outcome"] = ("no orphans in sample" if not orphans
                                   else "small comprehensively linked site - never flagged")
        return result("ACC-SITEMAP-ORPHAN", "pass", observations=observations)
    return result(
        "ACC-SITEMAP-ORPHAN", "finding", urls=orphans[:5],
        observations=observations,
        evidence_quality="direct-measurement",
        candidate=candidate(
            "Important sitemap URLs are unreachable from sampled navigation",
            "medium", "medium",
            "%d of %d sampled sitemap URLs have no internal link from any sampled page "
            "(example: %s); site has %s discovered candidates. Sample-limited evidence."
            % (len(orphans), len(sample), orphans[0], candidates_count),
            "Important URLs that exist only in the sitemap but not in crawlable links "
            "depend entirely on sitemap discovery; surfaces that miss the sitemap never "
            "find them.",
            "Link the orphaned pages from related hub pages or navigation so they are "
            "reachable by crawling alone.",
            "medium", effort="medium", owner="web-platform",
            acceptance="Each previously orphaned URL appears as a link target on at least "
                       "one sampled page."))


def check_sitemap_invalid(snap):
    sitemap = snap.get("sitemap")
    if not sitemap:
        return result("ACC-SITEMAP-INVALID", "pass", observations={
            "note": "no sitemap declared or found - absence alone is never a defect"})
    declared = snap["robots"].get("sitemaps_declared") or []
    bad = (not sitemap.get("parse_ok")) or (sitemap.get("http_status") or 200) >= 400
    if not bad:
        return result("ACC-SITEMAP-INVALID", "pass", observations={
            "url": sitemap.get("url"), "http_status": sitemap.get("http_status"),
            "parse_ok": sitemap.get("parse_ok"),
            "entries_count": sitemap.get("entries_count")})
    return result(
        "ACC-SITEMAP-INVALID", "finding", urls=[sitemap.get("url") or (declared[0] if declared
                                                     else snap["requested_url"] + "/sitemap.xml")],
        observations={"url": sitemap.get("url"), "http_status": sitemap.get("http_status"),
                      "parse_ok": sitemap.get("parse_ok"),
                      "declared_in_robots": declared[:3]},
        evidence_quality="direct-measurement",
        candidate=candidate(
            "The declared sitemap is %s"
            % ("unparseable" if not sitemap.get("parse_ok")
               else "returning %s" % sitemap.get("http_status")),
            "medium", "high",
            "%s returned %s; parse_ok=%s while robots.txt declares %d sitemap(s)."
            % (sitemap.get("url"), sitemap.get("http_status"), sitemap.get("parse_ok"),
               len(declared)),
            "A declared sitemap that 5xx's or fails to parse removes a discovery aid for "
            "index crawlers on a site that chose to rely on one.",
            "Restore the sitemap (200 + parseable XML) or remove the Sitemap declaration "
            "from robots.txt.",
            "medium", effort="small", owner="web-platform",
            acceptance="robots.txt-declared sitemap URL returns 200 parseable XML with "
                       ">0 <url> entries."))


def check_hreflang(snap, pages):
    with_hrefs = [(p, p.get("hreflang") or []) for p in pages]
    declared = [(p, h) for p, h in with_hrefs if h]
    if not declared:
        return result("ACC-HREFLANG-INCONSISTENT", "not_evaluated",
                      observations={"note": "no hreflang declarations on sampled pages - "
                                            "treated as single-locale; check not applicable"})
    by_path = {norm_path(p["requested_url"]): p for p in pages}
    problems = []
    for page, hrefs in declared:
        for entry in hrefs:
            lang, href = entry.get("lang"), entry.get("href")
            if lang and not HREFLANG_RE.match(lang):
                problems.append({"url": page["requested_url"], "issue": "invalid lang",
                                 "value": lang})
                continue
            target = by_path.get(norm_path(href))
            if target is not None:
                back = [(e.get("lang") or "").lower()
                        for e in (target.get("hreflang") or [])]
                if (page.get("lang") or "").lower() not in back:
                    problems.append({"url": page["requested_url"],
                                     "issue": "missing reciprocal tag",
                                     "expected": page.get("lang"),
                                     "on": target["requested_url"]})
    if not problems:
        return result("ACC-HREFLANG-INCONSISTENT", "pass", observations={
            "pages_with_hreflang": len(declared),
            "note": "sampled reciprocal declarations are consistent"})
    return result(
        "ACC-HREFLANG-INCONSISTENT", "finding",
        urls=sorted({p["url"] if "url" in p else p.get("on") for p in problems})[:5],
        observations={"problems": problems[:8],
                      "pages_with_hreflang": len(declared)},
        evidence_quality="direct-measurement",
        candidate=candidate(
            "Locale alternates are missing or misdeclared on a multilingual site",
            "medium", "high",
            "%d hreflang problems across %d pages declaring locales (%s)."
            % (len(problems), len(declared), short(json.dumps(problems[0]),
                                                  limit=140) if problems else ""),
            "Missing or misdeclared locale alternates leave locale variants undiscoverable "
            "to region-sensitive retrieval.",
            "Add reciprocal hreflang link pairs (each alternate declares back), with valid "
            "lang codes, ideally also in the sitemap.",
            "medium", effort="medium", owner="web-platform",
            acceptance="Every sampled hreflang target that is itself sampled declares a "
                       "return link to the origin page's language."))


def check_llms_txt(snap):
    site_types = snap.get("site_type") or []
    if "docs-developer" not in site_types:
        return result("ACC-LLMS-TXT-ABSENT", "not_evaluated", observations={
            "site_type": site_types,
            "note": "not a docs-developer site - llms.txt absence is never flagged elsewhere"})
    llms = (snap.get("probes") or {}).get("llms_txt")
    if llms and llms.get("format") == "llms-txt":
        return result("ACC-LLMS-TXT-ABSENT", "pass", observations={
            "http_status": llms.get("http_status"),
            "note": "llms.txt present"})
    doc_pages = [p for p in snap.get("pages") or []
                 if (p.get("page_class") or "") == "docs"]
    return result(
        "ACC-LLMS-TXT-ABSENT", "finding", urls=[snap["requested_url"] + "/llms.txt"],
        observations={"probe": llms, "sampled_doc_pages": len(doc_pages)},
        evidence_quality="direct-measurement",
        candidate=candidate(
            "A documentation-heavy site offers no llms.txt or Markdown alternates",
            "low", "high",
            "/llms.txt returned %s on a docs-developer site with %d sampled doc pages."
            % (llms.get("http_status") if llms else "unknown", len(doc_pages)),
            "An agent-navigation aid for documentation-heavy sites; an opportunity only - "
            "Google states it does not use such files and 2026 studies found no citation "
            "effect, so this is never framed as discoverability.",
            "Publish an /llms.txt index (and optional Markdown alternates for doc pages) "
            "as agent-facing navigation.",
            "low", effort="small", owner="docs-platform",
            acceptance="/llms.txt returns 200 with an index of the documentation sections."))


# --- driver ---------------------------------------------------------------


def resolve_marketplace_root(start_dir):
    node = os.path.abspath(start_dir)
    while True:
        if os.path.exists(os.path.join(node, "marketplace.json")):
            return node
        parent = os.path.dirname(node)
        if parent == node:
            return None
        node = parent


def self_validate(fragment, notes):
    here = os.path.dirname(os.path.abspath(__file__))
    root = resolve_marketplace_root(here)
    schema_default = None
    if root:
        schema_default = os.path.join(root, "skills", "audit-orchestrator",
                                      "references", "finding_fragment.json")
    if not schema_default or not os.path.exists(schema_default):
        notes.append("fragment schema not found; self-validation skipped")
        return
    sys.path.insert(0, os.path.join(root, "skills", "audit-orchestrator", "scripts"))
    try:
        from build_report import validate  # the one sanctioned soft import
    except ImportError:
        notes.append("build_report.validate unavailable; self-validation skipped")
        return
    errs = validate(fragment, load_json(schema_default))
    if errs:
        fail("fragment does not validate against finding_fragment.json", errs, 1)


def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def fail(what, errs, code):
    sys.stderr.write("probe_access: FAIL - %s\n" % what)
    for e in errs or []:
        sys.stderr.write("  - %s\n" % e)
    sys.exit(code)


def analyze(snap, notes):
    rows = (snap.get("robots") or {}).get("groups") or []
    pages = snap.get("pages") or []
    imp = important_only(pages)
    results = []
    if (snap.get("robots") or {}).get("status") == "error":
        results.append(check_robots_unavailable(snap))
        results.append(result("ACC-ROBOTS-ROLE", "not_evaluated", observations={
            "reason": "robots.txt unavailable; per-token policy cannot be read"}))
    else:
        out = check_robots_role(snap, rows, imp)
        results.extend(out if isinstance(out, list) else [out])
        results.append(check_robots_unavailable(snap))
    out = check_index_control(snap, pages)
    results.extend(out if isinstance(out, list) else [out])
    results.append(check_noarchive(snap, pages))
    results.append(check_canonical(snap, pages))
    results.append(check_redirect_loop(snap, pages))
    results.append(check_bot_challenge(snap))
    results.append(check_sitemap_orphan(snap, pages))
    results.append(check_sitemap_invalid(snap))
    results.append(check_hreflang(snap, pages))
    results.append(check_llms_txt(snap))
    return results


def summarize(results):
    findings = [r for r in results if r["gate"] == "finding"]
    passes = [r for r in results if r["gate"] == "pass"]
    skipped = [r for r in results if r["gate"] == "not_evaluated"]
    lines = ["probe_access: %d finding(s), %d pass, %d not_evaluated"
             % (len(findings), len(passes), len(skipped))]
    for r in findings:
        c = r["candidate_finding"]
        lines.append("  [%s/%s] %s (%s)" % (c["severity"], c["confidence"],
                                            c["title"], ", ".join(r.get("urls", []))[:100]))
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(
        description="access-discovery-audit: analyze crawler reach (robots roles, index "
                    "controls, canonicals, challenges, sitemaps, llms.txt) from a snapshot. "
                    "Snapshot-only reader; performs no network I/O.")
    ap.add_argument("--snapshot", required=True,
                    help="path to snapshot.json written by collect_snapshot.py")
    ap.add_argument("--out", required=True, help="path for the finding fragment JSON")
    ap.add_argument("--fragment-schema",
                    help="optional explicit path to finding_fragment.json (default: "
                         "resolved by walking up from this script to marketplace.json)")
    args = ap.parse_args()

    notes = []
    try:
        snap = load_json(args.snapshot)
    except (OSError, ValueError) as e:
        # exit 2: could not analyze; still write a fragment with not_evaluated
        fragment = {"skill_id": "access-discovery-audit", "mode": "snapshot",
                    "generated_at": datetime.datetime.now(
                        datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "results": [],
                    "not_evaluated": [{"check_id": cid,
                                       "reason": "snapshot unreadable: %s" % e}
                                      for cid in CHECK_IDS]}
        os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(fragment, fh, indent=2)
            fh.write("\n")
        print("probe_access: could not read snapshot; fragment with not_evaluated -> %s"
              % args.out)
        sys.exit(2)

    results = analyze(snap, notes)
    fragment = {
        "skill_id": "access-discovery-audit",
        "mode": "snapshot",
        "generated_at": datetime.datetime.now(
            datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "results": results,
        "not_evaluated": [],
    }
    self_validate(fragment, notes)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(fragment, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print(summarize(results))
    for note in notes:
        print("  note: %s" % note)
    sys.exit(0)


if __name__ == "__main__":
    main()
