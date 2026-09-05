#!/usr/bin/env python3
"""collect_snapshot.py - build the shared evidence snapshot for one audit.

The ONLY component in the marketplace that performs network I/O. Reads: one URL
(or, in --passages mode, an existing snapshot plus audit/passages.json). Writes: audit/snapshot.json, audit/excerpts/<skill>.json,
and (passages mode) audit/passages_checked.json. Prints a small summary;
never dumps page content to stdout.

Safety: GET/HEAD only, no credentials, no forms, scheme http/https only, ports
80/443 unless --allow-private (for local test fixtures), private/loopback/
link-local destinations rejected unless --allow-private, per-request timeout,
bounded response bytes, one global deadline, serial requests (concurrency 1 <=
cap 3). Robots-aware UA probes: homepage only, only when the probed token is
allowed there.

Stdlib only (Python 3.9+). Self-validates its output against
references/snapshot_schema.json using the vendored validator from build_report.
"""

import argparse
import datetime
import gzip
import zlib
import ipaddress
import json
import os
import re
import socket
import sys
import time
import uuid
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin, urlparse, urlunparse
from urllib.request import Request, build_opener, HTTPRedirectHandler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_report import validate as validate_schema  # same-skill import

MAX_HOPS = 5
PAGE_BYTES = 2 * 1024 * 1024
SMALL_BYTES = 1024 * 1024
TINY_BYTES = 512 * 1024
AUDITOR_UA = "BrandRetrievalReadinessAudit/1.0 (recommend-only audit; respects robots.txt)"
STATE_IDS = {"__NEXT_DATA__", "__NUXT__", "__APOLLO_STATE__", "__INITIAL_STATE__",
             "__NEXT_DATA_JSON__", "REDUX_STATE"}
BLOCK_TAGS = {"p", "div", "li", "ul", "ol", "tr", "td", "th", "section", "article",
              "header", "footer", "nav", "aside", "blockquote", "pre", "dt", "dd",
              "main", "figure", "figcaption", "h1", "h2", "h3", "h4", "h5", "h6",
              "table", "form", "label", "button"}
HEADINGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}
OVERLAY_RE = re.compile(r"cookie|consent|gdpr|paywall|interstitial|onetrust|osano"
                        r"|cookiebot|subscribe-modal|signup-modal", re.I)
ACCORDION_RE = re.compile(r"accordion|collapse|expander|toggle-content", re.I)

PRICE_RE = re.compile(r"(?:[$\u20ac\u00a3\u20b9]\s?\d[\d,.]*)|(?:\b\d[\d,.]*\s?(?:USD|EUR|GBP|INR)\b)")
DATE_RE = re.compile(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s?(?:19|20)\d{2}\b|\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(?:19|20)\d{2}\b|\b(?:19|20)\d{2}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}/(?:19|20)\d{2}\b|(?:(?:updated|modified|published|revised|last\s+(?:updated|modified|reviewed)|copyright|\u00a9|as\s+of)[^.\n]{0,40}?\b(?:19|20)\d{2}\b)", re.I)
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
COUNT_RE = re.compile(r"\b\d[\d,.]*\+?\s+(?:customers|users|teams|companies|developers|downloads|installs|packages|modules|plugins|extensions|themes|pages|articles|posts|members|countries|enterprises|stars|reviews|questions|students|patients|locations|stores|recipes|episodes|issues|projects|skills)\b", re.I)
PLAN_RE = re.compile(r"\b(?:Free|Starter|Basic|Standard|Pro|Professional|Premium|Team|Business|Enterprise|Growth|Scale|Plus|Advanced)\b(?!(?:\s+(?:deviation|library|error|form)))(?:\s+plan)?")
VERSION_RE = re.compile(r"\bv(?:ersion\s*)?\d+\.\d+(?:\.\d+)?\b|\b\d+\.\d+\.\d+\b", re.I)
HOURS_RE = re.compile(r"\b\d{1,2}(?::\d{2})?\s?(?:am|pm)\s?(?:[-\u2013]\s?\d{1,2}(?::\d{2})?\s?(?:am|pm))?", re.I)
PHONE_RE = re.compile(r"(?:\+\d{1,2}\s?)?(?:\(\d{3}\)|\d{3})[\s.-]\d{3}[\s.-]\d{4}\b")
ADDRESS_RE = re.compile(r"\b\d{1,5}\s+[A-Z][A-Za-z]+(?:\s[A-Za-z]+)*\s+"
                        r"(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Suite|Ste|Floor|Way)\b\.?")
ELIGIBILITY_RE = re.compile(r"\b(?:eligib\w*|eligibility)\b[^.\n]{0,120}", re.I)
DEADLINE_RE = re.compile(r"\b(?:deadline|apply by|applies? (?:by|until)|closes? on|ends? on|due (?:by|on)|registration closes)\b[^.\n]{0,80}", re.I)
STOCK_RE = re.compile(r"\b(?:in stock|out of stock|sold out|back-?order|pre-?order|discontinued|no longer available|available again)\b[^.\n]{0,60}", re.I)
SHIPPING_RE = re.compile(r"\b(?:free shipping|ships? (?:in|within)|delivery (?:in|within)|same-day delivery)\b[^.\n]{0,60}", re.I)
CREDENTIAL_RE = re.compile(r"\b(?:ISO\s?\d{4,5}|SOC\s?2(?:\s+Type\s+I{1,2})?|GDPR[ -]compliant|HIPAA|FedRAMP|PCI[ -]DSS|certified)\b[^.\n]{0,60}", re.I)
CLAIM_PATTERNS = [("price", PRICE_RE), ("date", DATE_RE), ("count", COUNT_RE),
                  ("plan", PLAN_RE), ("version", VERSION_RE), ("hours", HOURS_RE),
                  ("phone", PHONE_RE), ("address", ADDRESS_RE),
                  ("eligibility", ELIGIBILITY_RE), ("deadline", DEADLINE_RE),
                  ("stock", STOCK_RE), ("shipping", SHIPPING_RE),
                  ("credential", CREDENTIAL_RE)]

INDEPENDENT_DOMAINS = {"wikipedia.org", "wikidata.org", "crunchbase.com",
                       "producthunt.com", "g2.com", "capterra.com", "trustpilot.com",
                       "yelp.com", "bbb.org", "news.ycombinator.com"}
OWNED_DOMAINS = {"linkedin.com", "twitter.com", "x.com", "facebook.com",
                 "instagram.com", "youtube.com", "tiktok.com", "medium.com",
                 "substack.com", "discord.com"}
REGISTRY_DOMAINS = {"github.com", "npmjs.com", "pypi.org", "gitlab.com"}


class DeadlineHit(Exception):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # raise HTTPError so the fetch loop controls every hop


_OPENER = build_opener(NoRedirect)

SAFE_URL_CHARS = ":/?#[]@!$&'()*+,;=%~-._"


def pct_encode_url(u):
    """Percent-encode non-ASCII in URLs (raw Unicode in a Location header or an
    href crashes urllib on re-request - the vernacular-web bug). Recovers the
    original bytes from latin-1-decoded headers, then encodes byte-wise; existing
    %XX stays intact."""
    if not u:
        return u
    try:
        b = u.encode("latin-1")
    except UnicodeEncodeError:
        b = u.encode("utf-8")
    out = quote(b, safe=SAFE_URL_CHARS)
    # normalize percent-hex to uppercase (%e0 vs %E0 hit different cache keys
    # on some strict origins) - deterministic probe URLs
    return re.sub(r"%[0-9a-f]{2}", lambda m: m.group(0).upper(), out)


class Fetcher:
    def __init__(self, deadline_ts, allow_private, per_request_timeout=8.0):
        self.deadline_ts = deadline_ts
        self.allow_private = allow_private
        self.timeout = per_request_timeout
        self.requests = 0
        self._ok_hosts = {}

    def remaining(self):
        return self.deadline_ts - time.time()

    def _check_host(self, host, port):
        key = (host, port)
        if key in self._ok_hosts:
            return
        if self.allow_private:
            self._ok_hosts[key] = True
            return
        try:
            infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
        except OSError as e:
            raise ValueError("dns failure for %s: %s" % (host, e))
        for info in infos:
            ip = ipaddress.ip_address(info[4][0])
            if (ip.is_private or ip.is_loopback or ip.is_link_local
                    or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
                raise ValueError("refusing non-public destination %s (%s)" % (host, ip))
        self._ok_hosts[key] = True

    def fetch(self, url, ua=AUDITOR_UA, method="GET", max_bytes=PAGE_BYTES):
        """One logical fetch following <=MAX_HOPS hops manually. Never raises
        for network conditions; returns a result dict."""
        url = pct_encode_url(url)
        chain = [url]
        current = url
        started = time.time()
        for hop in range(MAX_HOPS + 1):
            if self.remaining() < 2.0:
                return {"error": "deadline reached before request", "status": None,
                        "redirect_chain": chain, "timing_ms": 0}
            parts = urlparse(current)
            if parts.scheme not in ("http", "https"):
                return {"error": "non-http(s) URL: %s" % parts.scheme, "status": None,
                        "redirect_chain": chain, "timing_ms": 0}
            if parts.username or parts.password:
                return {"error": "credentials in URL", "status": None,
                        "redirect_chain": chain, "timing_ms": 0}
            port = parts.port or (443 if parts.scheme == "https" else 80)
            if port not in (80, 443) and not self.allow_private:
                return {"error": "non-standard port refused (use --allow-private for fixtures)",
                        "status": None, "redirect_chain": chain, "timing_ms": 0}
            try:
                self._check_host(parts.hostname, port)
            except ValueError as e:
                return {"error": str(e), "status": None, "redirect_chain": chain,
                        "timing_ms": 0}
            req = Request(current, method=method if hop == 0 else "GET", headers={
                "User-Agent": ua,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.5",
                "Accept-Encoding": "gzip",
            })
            self.requests += 1
            try:
                resp = _OPENER.open(req, timeout=self.timeout)
                status = resp.status
                headers = {k.lower(): v for k, v in resp.headers.items()}
                raw = resp.read(max_bytes + 1)
            except HTTPError as e:
                status = e.code
                headers = {k.lower(): v for k, v in (e.headers or {}).items()}
                try:
                    raw = e.read(max_bytes + 1)
                except Exception:
                    raw = b""
            except (URLError, OSError, socket.timeout) as e:
                return {"error": str(e), "status": None, "redirect_chain": chain,
                        "timing_ms": int((time.time() - started) * 1000)}
            if len(raw) > max_bytes:
                raw = raw[:max_bytes]
            if headers.get("content-encoding", "").lower() == "gzip":
                try:
                    raw = gzip.decompress(raw)
                except (OSError, EOFError, zlib.error, ValueError):
                    try:
                        # truncated stream: salvage what decompresses
                        partial = zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(raw)
                        if partial:
                            raw = partial
                    except (OSError, EOFError, zlib.error, ValueError):
                        pass  # keep raw bytes; extraction degrades to partial
            if status in (301, 302, 303, 307, 308):
                loc = headers.get("location")
                if not loc:
                    break
                nxt = pct_encode_url(urljoin(current, loc))
                chain.append(nxt)
                current = nxt
                continue
            return {"status": status, "headers": headers, "body": raw,
                    "final_url": current, "redirect_chain": chain,
                    "timing_ms": int((time.time() - started) * 1000), "error": None}
        return {"error": "too many redirects", "status": None, "redirect_chain": chain,
                "timing_ms": int((time.time() - started) * 1000)}


class PageExtractor(HTMLParser):
    """One pass over raw HTML: text blocks/sections, metadata, links, JSON-LD,
    structure signals. CSS is invisible to it; all layout signals are heuristic
    and only ever feed observations, not findings."""

    def __init__(self, base_url):
        super().__init__(convert_charrefs=True)
        self.base = base_url
        self.blocks = []
        self.sections = []
        self.cur_section = {"heading": None, "heading_level": 0, "heading_id": None,
                            "parts": [], "char_offset": 0}
        self.cur_block = []
        self._text_len = 0
        self.skip_depth = 0
        self.title = None
        self._in_title = False
        self._title_buf = []
        self.metas = {}
        self.canonical = None
        self.hreflang = []
        self.robots_meta = None
        self.lang = None
        self.headings = []
        self._heading = None
        self.links = []
        self._a_href = None
        self._a_text = []
        self._a_rel = None
        self.images = []
        self.jsonld_raw = []
        self._jsonld_buf = None
        self._state_buf = None
        self._state_key = None
        self._state_payloads = []
        self.canvas = 0
        self.svg_open = 0
        self.svg_text = 0
        self.video = 0
        self.video_transcript = 0
        self._in_video = 0
        self.tables = 0
        self.details = 0
        self.dialog = 0
        self.accordion_signals = 0
        self.overlay_signal = None
        self.grid_cols = 0
        self.microdata_types = []
        self.time_datetimes = []
        self.code_depth = 0
        self.claims_parts = []
        self.open_graph = {}

    # -- helpers ------------------------------------------------------------
    def _flush_block(self):
        text = " ".join(" ".join(self.cur_block).split())
        self.cur_block = []
        if text:
            self.blocks.append(text)
            self._text_len += len(text) + 1
            if self.cur_section is not None:
                self.cur_section["parts"].append(text)

    def _close_section(self):
        self._flush_block()
        sec = self.cur_section
        if sec is not None:
            text = "\n".join(sec["parts"])[:3000]
            if text or sec["heading"]:
                self.sections.append({
                    "heading": sec["heading"], "heading_level": sec["heading_level"],
                    "heading_id": sec["heading_id"], "text": text,
                    "char_offset": sec["char_offset"]})
        self.cur_section = None

    def _scan_class_id(self, attrs):
        blob = " ".join(v for k, v in attrs if k in ("class", "id") and v)
        return blob

    # -- parser hooks ---------------------------------------------------------
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "html" and a.get("lang"):
            self.lang = a["lang"]
        if tag == "img":
            alt = a.get("alt")
            self.images.append({"src": urljoin(self.base, a.get("src") or ""),
                                "alt": alt, "alt_empty": not (alt and alt.strip()),
                                "width": a.get("width"), "height": a.get("height")})
        if tag in ("script", "style", "noscript", "template"):
            self.skip_depth += 1
            if tag == "script":
                stype = (a.get("type") or "").lower()
                if stype == "application/ld+json":
                    self._jsonld_buf = []
                elif a.get("id") in STATE_IDS or (stype == "application/json"
                                                  and a.get("id") in STATE_IDS):
                    self._state_buf = []
                    self._state_key = a.get("id")
            return
        if self.skip_depth:
            return
        if tag == "meta":
            name = (a.get("name") or a.get("property") or "").lower()
            content = a.get("content")
            if name and content is not None:
                self.metas[name] = content
                if name == "robots":
                    self.robots_meta = content
                if name.startswith("og:"):
                    self.open_graph[name] = content
        elif tag == "title":
            self._in_title = True
        elif tag == "link":
            rel = (a.get("rel") or "").lower()
            if "canonical" in rel and a.get("href"):
                self.canonical = urljoin(self.base, a["href"])
            elif "alternate" in rel and a.get("hreflang") and a.get("href"):
                self.hreflang.append({"lang": a["hreflang"], "href": urljoin(self.base, a["href"])})
        elif tag in HEADINGS:
            self._close_section()
            self.cur_section = {"heading": None, "heading_level": HEADINGS[tag],
                                "heading_id": a.get("id"), "parts": [],
                                "char_offset": self._text_len}
            self._heading = {"level": HEADINGS[tag], "text": [], "id": a.get("id")}
        elif tag in BLOCK_TAGS:
            self._flush_block()
        elif tag == "a":
            self._a_href = urljoin(self.base, a["href"]) if a.get("href") else None
            self._a_rel = a.get("rel")
            self._a_text = []
        elif tag == "img":
            pass  # captured at starttag
        elif tag == "table":
            self.tables += 1
        elif tag == "details":
            self.details += 1
        elif tag == "dialog" or a.get("role") == "dialog":
            self.dialog += 1
        elif tag == "canvas":
            self.canvas += 1
        elif tag == "svg":
            self.svg_open += 1
        elif tag == "text" and self.svg_open:
            self.svg_text += 1
        elif tag == "video":
            self.video += 1
            self._in_video += 1
        elif tag == "track" and self._in_video and (a.get("kind") in ("captions", "subtitles")):
            self.video_transcript += 1
        elif tag == "time" and a.get("datetime"):
            self.time_datetimes.append(a["datetime"])
        if tag in ("pre", "code", "kbd", "samp", "tt"):
            self.code_depth += 1
        blob = self._scan_class_id(attrs)
        if blob:
            if OVERLAY_RE.search(blob) and self.overlay_signal is None:
                self.overlay_signal = True
            if ACCORDION_RE.search(blob):
                self.accordion_signals += 1
            if tag == "div" and re.search(r"\bcol(?:-\w+)?\b|\bcolumn\b", blob, re.I):
                self.grid_cols += 1
        if a.get("itemscope") is not None and a.get("itemtype"):
            self.microdata_types.append(a["itemtype"].rsplit("/", 1)[-1])

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "template"):
            if tag == "script":
                if self._jsonld_buf is not None:
                    raw = "".join(self._jsonld_buf)
                    ok, parsed = False, None
                    try:
                        parsed = json.loads(raw)
                        ok = True
                    except ValueError:
                        pass
                    self.jsonld_raw.append({"raw": raw[:20000], "parse_ok": ok,
                                            "parsed": parsed if ok else None})
                    self._jsonld_buf = None
                if self._state_buf is not None:
                    self._state_payloads.append((self._state_key or "inline",
                                                 "".join(self._state_buf)))
                    self._state_buf = None
                    self._state_key = None
            if self.skip_depth:
                self.skip_depth -= 1
            return
        if self.skip_depth:
            return
        if tag == "title":
            self._in_title = False
            self.title = " ".join("".join(self._title_buf).split()) or None
        elif tag in HEADINGS:
            if self._heading is not None:
                text = " ".join("".join(self._heading["text"]).split())
                self.headings.append({"level": self._heading["level"], "text": text,
                                      "id": self._heading["id"]})
                if self.cur_section is not None and not self.cur_section["heading"]:
                    self.cur_section["heading"] = text
            self._heading = None
        elif tag == "a":
            if self._a_href is not None:
                text = " ".join("".join(self._a_text).split())[:200] or None
                self.links.append({"href": self._a_href, "anchor_text": text,
                                   "rel": self._a_rel})
            self._a_href = None
        elif tag == "svg" and self.svg_open:
            self.svg_open -= 1
        elif tag == "video" and self._in_video:
            self._in_video -= 1
        elif tag in ("pre", "code", "kbd", "samp", "tt") and self.code_depth:
            self.code_depth -= 1
        elif tag in BLOCK_TAGS:
            self._flush_block()

    def handle_data(self, data):
        if self._in_title:
            self._title_buf.append(data)
            return
        if self._heading is not None:
            self._heading["text"].append(data)
            if self.cur_section is not None and not self.cur_section["heading"]:
                pass  # section heading set at close
            return
        if self._a_href is not None:
            self._a_text.append(data)
            return
        if self._jsonld_buf is not None:
            self._jsonld_buf.append(data)
            return
        if self._state_buf is not None:
            self._state_buf.append(data)
            return
        if self.skip_depth or self.svg_open:
            return
        text = data.strip()
        if text:
            self.cur_block.append(text)
            if not self.code_depth:
                self.claims_parts.append(text)

    def finalize(self):
        self._close_section()
        return self


def extract_claims(text, url, cap=30):
    claims, seen = [], set()
    lines = text.split("\n")
    for ctype, rx in CLAIM_PATTERNS:
        for m in rx.finditer(text):
            value = m.group(0)
            if ctype == "count" and "." in value:
                continue  # dotted numbers are section headings ('3.17. Users'), not counts
            key = (ctype, value)
            if key in seen:
                continue
            seen.add(key)
            line = next((ln for ln in lines if value in ln), value)
            claims.append({"type": ctype, "value": value,
                           "quote": line.strip()[:160], "location": url})
            if len(claims) >= cap:
                return claims
    return claims


def walk_state_strings(node, out, depth=0):
    if depth > 8 or len(out) >= 60:
        return
    if isinstance(node, str):
        if 10 <= len(node) <= 300 and not node.startswith(("http://", "https://", "/", "#")):
            out.append(node)
    elif isinstance(node, dict):
        for v in node.values():
            walk_state_strings(v, out, depth + 1)
    elif isinstance(node, list):
        for v in node[:50]:
            walk_state_strings(v, out, depth + 1)


def capture_page(res, url, extractor, sitemap_lastmod):
    heads = res["headers"]
    headers = {"server": heads.get("server"), "cf_ray": heads.get("cf-ray"),
               "cf_mitigated": heads.get("cf-mitigated"),
               "last_modified": heads.get("last-modified"),
               "cache_control": heads.get("cache-control"),
               "content_language": heads.get("content-language"),
               "link": heads.get("link")}
    visible = "\n".join(extractor.blocks)
    state_payloads = []
    for key, buf in extractor._state_payloads:
        try:
            parsed_state = json.loads(buf)
        except ValueError:
            m = re.search(r"\{.*\}", buf, re.S)
            try:
                parsed_state = json.loads(m.group(0)) if m else None
            except ValueError:
                parsed_state = None
        state_payloads.append((key, parsed_state))
    contrast = []
    payload_keys = []
    for key, parsed in state_payloads:
        payload_keys.append(key)
        if parsed is None:
            continue
        strings = []
        walk_state_strings(parsed, strings)
        for s in strings:
            if s not in visible and s not in contrast:
                contrast.append(s)
            if len(contrast) >= 40:
                break
    structured_dates = list(extractor.time_datetimes)
    for block in extractor.jsonld_raw:
        if block["parse_ok"] and isinstance(block["parsed"], dict):
            for k in ("dateModified", "datePublished"):
                if k in block["parsed"]:
                    structured_dates.append(str(block["parsed"][k]))
    if extractor.metas.get("article:modified_time"):
        structured_dates.append(extractor.metas["article:modified_time"])
    return {
        "requested_url": url,
        "final_url": res.get("final_url") or url,
        "status": res.get("status") if res.get("status") is not None else 0,
        "redirect_chain": res.get("redirect_chain") or [url],
        "content_type": heads.get("content-type"),
        "bytes": len(res.get("body") or b""),
        "timing_ms": res.get("timing_ms"),
        "raw_html": (res.get("body") or b"").decode("utf-8", "replace"),
        "visible_text": visible[:200000],
        "title": extractor.title,
        "meta_description": extractor.metas.get("description"),
        "canonical": extractor.canonical,
        "lang": extractor.lang,
        "hreflang": extractor.hreflang[:20],
        "robots_meta": extractor.robots_meta,
        "x_robots_tag": heads.get("x-robots-tag"),
        "headers": headers,
        "sitemap_lastmod": sitemap_lastmod,
        "headings": extractor.headings[:100],
        "links": extractor.links[:400],
        "jsonld": extractor.jsonld_raw[:20],
        "microdata_types": list(dict.fromkeys(extractor.microdata_types))[:20],
        "open_graph": extractor.open_graph,
        "images": extractor.images[:100],
        "tables": {"semantic_count": extractor.tables,
                   "div_grid_candidates": extractor.grid_cols // 3},
        "interactive": {"accordions": extractor.accordion_signals,
                        "dialogs": extractor.dialog,
                        "details_elements": extractor.details,
                        "overlay_in_raw_html": extractor.overlay_signal},
        "non_text": {"canvas": extractor.canvas,
                     "svg_without_text": max(0, extractor.svg_open - (1 if extractor.svg_text else 0)),
                     "video_without_transcript": max(0, extractor.video - extractor.video_transcript)},
        "inline_state": {"payload_keys": payload_keys, "contrast_strings": contrast[:40]},
        "claim_index": extract_claims("\n".join(extractor.claims_parts), url),
        "_structured_dates": structured_dates[:10],
    }


def parse_robots(text):
    groups, sitemaps = [], []
    cur = {"agents": [], "allow": [], "disallow": []}
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        k, v = line.split(":", 1)
        k, v = k.strip().lower(), v.strip()
        if k == "user-agent":
            if cur["allow"] or cur["disallow"]:
                groups.append(cur)
                cur = {"agents": [], "allow": [], "disallow": []}
            cur["agents"].append(v.lower())
        elif k in ("allow", "disallow") and cur["agents"]:
            if v:
                cur[k].append(v)
        elif k == "sitemap" and v:
            sitemaps.append(v)
    if cur["agents"]:
        groups.append(cur)
    return groups, sitemaps


def rules_for(rows, token):
    specific = [r for r in rows if r["token"] == token.lower()]
    wildcard = [r for r in rows if r["token"] == "*"]
    chosen = specific or wildcard
    disallow, allow = [], []
    for r in chosen:
        disallow.extend(r["disallowed_paths"])
        allow.extend(r["allow_paths"])
    return disallow, allow


def expand_robot_rows(groups, role_by_token):
    """One row per (group, agent) so co-grouped tokens (e.g. GPTBot and
    OAI-SearchBot sharing one rule block) each keep their rules."""
    rows = []
    for g in groups:
        for agent in g["agents"]:
            rows.append({"token": agent,
                         "role": role_by_token.get(
                             agent, "wildcard" if agent == "*" else "unknown"),
                         "disallowed_paths": g["disallow"][:50],
                         "allow_paths": g["allow"][:50],
                         "catch_all_disallow": "/" in g["disallow"] if agent == "*" else None})
    return rows


def allowed(groups, token, path):
    disallow, allow = rules_for(groups, token)
    if not disallow:
        return True

    def norm(p):
        p = p.split("$")[0].rstrip("*")
        return p

    best = None
    for rule, kind in [(d, "disallow") for d in disallow] + [(a, "allow") for a in allow]:
        n = norm(rule)
        if path.startswith(n):
            if best is None or len(n) > best[0]:
                best = (len(n), kind)
    return best is None or best[1] == "allow"


def fetch_sitemap(fetcher, sitemap_url):
    res = fetcher.fetch(sitemap_url, max_bytes=SMALL_BYTES)
    if res.get("error") or (res.get("status") or 500) >= 400:
        return None
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(res["body"].decode("utf-8", "replace"))
    except ET.ParseError:
        return {"url": sitemap_url, "http_status": res["status"], "parse_ok": False,
                "entries_count": None, "lastmod_present_count": None,
                "lastmod_distinct_count": None, "lastmod_sample": []}
    ns = root.tag.split("}")[0].strip("{") if "}" in root.tag else ""
    tag = lambda t: "%s%s" % (("{%s}" % ns) if ns else "", t)
    if root.tag == tag("sitemapindex"):
        child = root.find(tag("sitemap") + "/" + tag("loc"))
        if child is not None and child.text:
            inner = fetcher.fetch(child.text.strip(), max_bytes=SMALL_BYTES)
            if not inner.get("error") and (inner.get("status") or 500) < 400:
                try:
                    root = ET.fromstring(inner["body"].decode("utf-8", "replace"))
                    sitemap_url = child.text.strip()
                except ET.ParseError:
                    return {"url": sitemap_url, "http_status": res["status"],
                            "parse_ok": False, "entries_count": None,
                            "lastmod_present_count": None,
                            "lastmod_distinct_count": None, "lastmod_sample": []}
            else:
                return {"url": sitemap_url, "http_status": res["status"],
                        "parse_ok": True, "entries_count": 0,
                        "lastmod_present_count": 0, "lastmod_distinct_count": 0,
                        "lastmod_sample": []}
    entries = []
    for sm in root.findall(tag("url")):
        loc = sm.findtext(tag("loc"))
        lastmod = sm.findtext(tag("lastmod"))
        if loc:
            entries.append((loc.strip(), (lastmod or "").strip()))
    lastmods = [lm for _, lm in entries if lm]
    return {"url": sitemap_url, "http_status": res["status"], "parse_ok": True,
            "entries_count": len(entries),
            "lastmod_present_count": len(lastmods),
            "lastmod_distinct_count": len(set(lastmods)),
            "lastmod_sample": [{"url": u, "lastmod": lm} for u, lm in entries[:50]]}


def select_pages(candidate_urls, max_pages):
    """Stratified, template-clustered selection of 6-8 representative pages.
    Returns (urls, labels, cluster_rows); labels map url -> page_class."""
    prio = [
        (r"price|pricing|plan|plans|cost", "decision"),
        (r"doc|docs|help|faq|support|guide|tutorial|manual", "docs"),
        (r"blog|news|article|post|release|changelog|update", "recent"),
        (r"about|contact|team|location|store|hours|company", "about"),
        (r"product|shop|item|service|solution|feature", "product"),
        (r"security|legal|privacy|terms|status", "trust"),
    ]
    clusters = {}
    # Auth-shaped slugs are never decision content; sample them only if slots remain.
    auth_re = re.compile(r"login|log-in|signin|sign-in|signup|sign-up|register|dashboard|settings|account|forgot|password|checkout|cart", re.I)
    deferred = []

    def cluster_key(u):
        path = urlparse(u).path.rstrip("/")
        segs = [s for s in path.split("/") if s]
        shaped = [re.sub(r"\d+", "{d}", s) for s in segs[:2]]
        return "/" + "/".join(shaped) if shaped else "/"

    for u in candidate_urls:
        clusters.setdefault(cluster_key(u), []).append(u)
    picked, labels = [], {}
    home = next((u for u in candidate_urls if urlparse(u).path in ("", "/")), None)
    if home:
        picked.append(home)
        labels[home] = "homepage"
    cluster_rows = sorted(clusters.items(), key=lambda kv: -len(kv[1]))
    for pattern, label in prio:
        for key, urls in cluster_rows:
            if len(picked) >= max_pages:
                break
            if re.search(pattern, key, re.I) or any(re.search(pattern, u, re.I) for u in urls[:3]):
                rep = urls[0]
                if rep not in labels:
                    if auth_re.search(key or "") or auth_re.search(rep):
                        deferred.append((rep, label))
                        continue
                    picked.append(rep)
                    labels[rep] = label
    for key, urls in cluster_rows:
        if len(picked) >= max_pages:
            break
        if urls[0] not in labels:
            if auth_re.search(key or "") or auth_re.search(urls[0]):
                deferred.append((urls[0], "other"))
                continue
            picked.append(urls[0])
            labels[urls[0]] = "other"
    for rep, label in deferred:
        if len(picked) >= max_pages:
            break
        if rep not in labels:
            picked.append(rep)
            labels[rep] = label
    out, seen = [], set()
    for u in picked:
        if u not in seen:
            out.append(u)
            seen.add(u)
    return out[:max_pages], labels, [{"pattern": k, "count": len(v)} for k, v in cluster_rows[:15]]


def probe_soft_404(fetcher, base):
    path = "/" + uuid.uuid4().hex
    res = fetcher.fetch(urljoin(base, path), max_bytes=SMALL_BYTES)
    if res.get("error") or res.get("status") is None:
        return None
    status = res["status"]
    body = res.get("body", b"").decode("utf-8", "replace")
    low = body.lower()
    return {
        "probe_path": path,
        "status": status,
        "is_soft_404": status == 200,
        "body_quality": {
            "has_search": "search" in low,
            "has_navigation": low.count("<a ") >= 3 or low.count("href=") >= 3,
            "has_suggestions": bool(re.search(r"popular|recent|related|did you mean|maybe you", low)),
        },
    }


def probe_redirects(fetcher, deep_path):
    """deep_path: path portion of an important page, e.g. /pricing."""
    out = []
    parts = urlparse(deep_path)
    host = parts.hostname or ""
    variants = [("http", urlunparse(("http", parts.netloc, parts.path, "", "", "")))]
    if host.startswith("www."):
        variants.append(("apex", urlunparse(("https", host[4:], parts.path, "", "", ""))))
    else:
        variants.append(("www", urlunparse(("https", "www." + host, parts.path, "", "", ""))))
    for variant, url in variants:
        res = fetcher.fetch(url, max_bytes=TINY_BYTES)
        if res.get("error") or res.get("status") is None:
            out.append({"variant": variant, "requested": url,
                        "final_path": None, "path_preserved": None})
            continue
        final_path = urlparse(res["final_url"]).path
        out.append({"variant": variant, "requested": url, "final_path": final_path,
                    "path_preserved": final_path == parts.path
                    and (res["status"] or 500) < 400})
    return out


def probe_ua(fetcher, homepage_url, robots_groups, robots_status, browser_status):
    out = []
    for token in ("OAI-SearchBot", "GPTBot", "PerplexityBot"):
        if robots_status == "present" and robots_groups is not None:
            allowed_here = allowed(robots_groups, token, "/")
        elif robots_status == "not_found":
            allowed_here = True
        else:
            allowed_here = None
        if allowed_here is False:
            out.append({"token": token, "requested_path": homepage_url,
                        "robots_allows": False, "status": None, "content_type": None,
                        "cf_mitigated": None, "differential": None,
                        "probe_robots_meta": None, "probe_x_robots_tag": None,
                        "headers": {"server": None, "cf_ray": None, "cf_mitigated": None},
                        "note": "probe skipped: robots disallows this token on / "
                                "- the rule itself is the finding"})
            continue
        res = fetcher.fetch(homepage_url, ua=token, max_bytes=TINY_BYTES)
        headers = res.get("headers") or {}
        status = res.get("status")
        # what directives does the BOT-UA tier actually see? (bot-tier-serve
        # cross-check: a noindex shown only to the auditor's UA is not an
        # index-control defect for retrieval surfaces)
        probe_body = (res.get("body") or b"").decode("utf-8", "replace")
        m_rm = re.search(r'<meta[^>]+name=["\']robots["\'][^>]+content=["\']([^"\']*)',
                         probe_body, re.I)
        probe_robots_meta = m_rm.group(1) if m_rm else None
        probe_xrobots = headers.get("x-robots-tag")
        diff = None
        if (status is not None and browser_status is not None
                and status != browser_status and status in (401, 403, 429, 503)):
            diff = "browser %s / bot-UA %s (suspected edge discrimination, medium confidence cap)" % (
                browser_status, status)
        out.append({"token": token, "requested_path": homepage_url,
                    "robots_allows": allowed_here, "status": status,
                    "content_type": headers.get("content-type"),
                    "cf_mitigated": True if headers.get("cf-mitigated") else None,
                    "differential": diff,
                    "probe_robots_meta": probe_robots_meta,
                    "probe_x_robots_tag": probe_xrobots,
                    "headers": {"server": headers.get("server"),
                                "cf_ray": headers.get("cf-ray"),
                                "cf_mitigated": headers.get("cf-mitigated")}})
    return out


EXTERNAL_LINK_RE = re.compile(r"^(https?://)?(www\.)?([a-z0-9.-]+)", re.I)
# Social/registry surfaces reject non-browser user agents; a browser-like UA with the
# audit token appended resolves their status for the <=12 presence HEAD/GETs.
EXTERNAL_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
               "Chrome/126.0.0.0 Safari/537.36 BrandRetrievalReadinessAudit/1.0")


def resolve_external_presence(fetcher, pages, site_host):
    """Declared external presence: JSON-LD sameAs + footer links. Timeouts never
    become findings - the entity skill interprets; the collector only records."""
    candidates = {}
    for page in pages:
        for block in page["jsonld"]:
            if not block["parse_ok"] or not isinstance(block["parsed"], dict):
                continue
            for sa in block["parsed"].get("sameAs", []) or []:
                if isinstance(sa, str) and sa.startswith("http"):
                    candidates.setdefault(urlparse(sa).netloc.lower().removeprefix("www."), sa)
        for link in page["links"]:
            netloc = urlparse(link["href"]).netloc.lower()
            if not netloc or netloc.endswith(site_host):
                continue
            base = netloc.removeprefix("www.")
            if base in INDEPENDENT_DOMAINS or base in OWNED_DOMAINS or base in REGISTRY_DOMAINS:
                candidates.setdefault(base, link["href"])
    brand = ""
    for page in pages:
        for block in page["jsonld"]:
            if block["parse_ok"] and isinstance(block["parsed"], dict):
                name = block["parsed"].get("name")
                if isinstance(name, str) and name:
                    brand = name
                    break
        if brand:
            break
    if not brand and pages and pages[0].get("title"):
        brand = pages[0]["title"].split("|")[0].strip()
    brand_token = re.split(r"[^a-z0-9]+", brand.lower())[0] if brand else ""

    out = []
    for base, url in list(candidates.items())[:12]:
        declared_in = "jsonld sameAs or footer"
        klass = ("independent" if base in INDEPENDENT_DOMAINS
                 else "owned" if base in OWNED_DOMAINS
                 else "unknown")
        res = fetcher.fetch(url, method="HEAD", ua=EXTERNAL_UA, max_bytes=0)
        status = res.get("status")
        if status in (403, 405, 429, 501) or (res.get("error") and status is None):
            # HEAD unsupported or the surface rejects bots - fall back to a small GET
            res = fetcher.fetch(url, ua=EXTERNAL_UA, max_bytes=TINY_BYTES)
            status = res.get("status")
        match = None
        if (status and 200 <= status < 400 and klass in ("independent", "unknown")
                and brand_token and len([o for o in out if o["brand_name_match"] is not None]) < 6):
            body = fetcher.fetch(url, ua=EXTERNAL_UA, max_bytes=TINY_BYTES)
            if not body.get("error") and body.get("body"):
                m = re.search(r"<title[^>]*>(.*?)</title>", body["body"].decode("utf-8", "replace"),
                              re.I | re.S)
                if m:
                    match = brand_token in m.group(1).lower()
        out.append({"url": url, "declared_in": declared_in, "http_status": status,
                    "owned_vs_independent": klass, "brand_name_match": match,
                    "heuristic": "domain table classification; refine in entity skill"})
    return out


FRAGMENT_SHAPE = {
    "required_top_level": ["skill_id", "mode", "results"],
    "mode_enum": ["snapshot", "url"],
    "mode_note": "composed runs use mode snapshot; standalone URL-mode runs use url",
    "result_required": ["check_id", "gate"],
    "result_keys": ["check_id", "gate", "urls", "observations", "evidence_quality",
                    "candidate_finding"],
    "urls_note": ("result-level 'urls' is the array of page URLs this result aggregates; "
                  "the report renames it affected_urls - never write affected_urls in a fragment"),
    "observations_rule": "observations is an object of measured values, or omit the key; never null",
    "evidence_quality_enum": ["direct-measurement", "direct-representation-comparison",
                              "indirect-corroborated", "semantic-judgment", "hypothesis"],
    "candidate_finding_required": ["title", "severity", "confidence",
                                   "evidence", "suggested_action"],
    "candidate_finding_keys": ["title", "severity", "confidence", "evidence",
                               "why_it_matters", "affected_surfaces", "suggested_action"],
    "suggested_action_required": ["summary", "priority"],
    "suggested_action_keys": ["summary", "priority", "effort", "owner", "acceptance_test"],
    "sampling_gap": ("expected page unsampled, or question unanswerable from sampled pages: "
                     "not_evaluated with reason 'sampling limitation: ...', never a finding; "
                     "market-derived gaps with no answering page go to opportunities[], not findings"),
    "note": ("candidate_finding is required only when gate == 'finding'; "
               "gate is one of finding, pass, not_evaluated"),
}


def _load_catalog():
    try:
        return load_json(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                      "..", "references", "check_catalog.json"))
    except (OSError, ValueError):
        return None


def checks_for(catalog, skill_id):
    """Project this skill's check templates from the catalog (single source -
    generated here, never copied into docs)."""
    if not catalog:
        return []
    return [{"check_id": c["check_id"],
             "pattern_template": c.get("pattern_template"),
             "evidence_template": c.get("evidence_template"),
             "severity_band": c.get("severity_band"),
             "negative_control": c.get("negative_control")}
            for c in catalog.get("checks", [])
            if c.get("skill_id") == skill_id]


def cap_claims(claims):
    """Collapse runs of identical (type, value) claims (e.g. a date strip)
    into one row with a count; keep the first quote plus sample locations."""
    grouped, order = {}, []
    for c in claims or []:
        key = (c.get("type"), c.get("value"))
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(c)
    out = []
    for key in order:
        rows = grouped[key]
        if len(rows) > 5:
            first = dict(rows[0])
            first["count"] = len(rows)
            locs = [r.get("location") for r in rows[1:4] if r.get("location")]
            if locs:
                first["sample_locations"] = locs
            out.append(first)
        else:
            out.extend(rows)
    return out


def build_excerpts(pages, sitemap_summary, probes, catalog=None, corroboration=None):
    budgets = {"answer-coverage-audit": 24000, "freshness-consistency-audit": 16000,
               "referral-experience-audit": 6000}
    ans_pages, frs_pages, ref_pages, empty_urls = [], [], [], []
    screen_windows = []
    totals = {"answer-coverage-audit": 0, "freshness-consistency-audit": 0,
              "referral-experience-audit": 0}

    def bounded(locs, skill_id):
        total = totals[skill_id]
        out = []
        for loc in locs:
            if totals[skill_id] + len(loc["text"]) > budgets[skill_id]:
                break
            out.append(loc)
            totals[skill_id] += len(loc["text"])
        return out

    for p in pages:
        heading_tree = [{"level": h["level"], "text": h["text"], "id": h["id"]}
                        for h in p["headings"]][:40]
        sections = json.loads(json.dumps(p["_sections"])) if p.get("_sections") else []
        excerpt_locs = [{"char_offset": s["char_offset"], "text": s["text"][:1500],
                         "location": ("under %s" % s["heading"]) if s["heading"] else "top of page"}
                        for s in sections if s["text"]][:6]
        claims = p["claim_index"]
        if not excerpt_locs and not claims and not heading_tree:
            empty_urls.append(p["requested_url"])
            continue
        capped = cap_claims(claims)
        tables = p.get("tables") or {}
        inter = p.get("interactive") or {}
        page_stats = {
            "visible_chars": len(p.get("visible_text") or ""),
            "heading_count": len(p.get("headings") or []),
            "image_count": len(p.get("images") or []),
            "table_semantic_count": tables.get("semantic_count", 0) or 0,
            "div_grid_candidates": tables.get("div_grid_candidates", 0) or 0,
            "accordions": inter.get("accordions", 0) or 0,
            "details_elements": inter.get("details_elements", 0) or 0,
            "dialogs": inter.get("dialogs", 0) or 0,
        }
        ans_pages.append({"url": p["requested_url"], "page_class": p.get("page_class"), "title": p["title"],
                          "heading_tree": heading_tree,
                          "main_content_excerpts": bounded(excerpt_locs, "answer-coverage-audit"),
                          "claim_index_subset": capped,
                          "page_stats": page_stats})
        frs_pages.append({"url": p["requested_url"], "page_class": p.get("page_class"), "title": p["title"],
                          "heading_tree": heading_tree[:24],
                          "main_content_excerpts": bounded(excerpt_locs[:1], "freshness-consistency-audit"),
                          "claim_index_subset": capped,
                          "page_stats": page_stats})
        first = sorted(excerpt_locs, key=lambda l: l["char_offset"])[:1]
        h1 = next((h["text"] for h in heading_tree if h["level"] == 1), None)
        overlay = bool((p.get("interactive") or {}).get("overlay_in_raw_html"))
        if first:
            screen_windows.append({"url": p["requested_url"],
                                   "window_offset": first[0]["char_offset"],
                                   "headline": h1, "overlay_present": overlay})
        else:
            screen_windows.append({"url": p["requested_url"], "window_offset": None,
                                   "headline": h1, "overlay_present": overlay})
        first = [{"char_offset": l["char_offset"], "text": l["text"][:600],
                  "location": l.get("location")} for l in first]
        ref_pages.append({"url": p["requested_url"], "page_class": p.get("page_class"), "title": p["title"],
                          "heading_tree": heading_tree,
                          "main_content_excerpts": bounded(first, "referral-experience-audit"),
                          "claim_index_subset": [],
                          "page_stats": page_stats})
    appendix_heads, appendix_nav, seen_nav, topic_counts = [], [], set(), {}
    for p in pages:
        for h in (p.get("headings") or []):
            if h.get("level") in (1, 2) and h.get("text") and len(appendix_heads) < 30:
                appendix_heads.append(h["text"])
        for link in (p.get("links") or []):
            t = (link.get("anchor_text") or "").strip()
            if t and t not in seen_nav and len(appendix_nav) < 20:
                seen_nav.add(t)
                appendix_nav.append(t)
        for c in (p.get("claim_index") or []):
            topic_counts[c.get("type", "?")] = topic_counts.get(c.get("type", "?"), 0) + 1
    coverage_appendix = {"headings": appendix_heads, "nav_labels": appendix_nav,
                         "claim_topics": topic_counts}
    matrix = {}
    for p in pages:
        for c in (p.get("claim_index") or []):
            e = {"value": c.get("value"), "quote": (c.get("quote") or "")[:200],
                 "url": p["requested_url"], "location": c.get("location")}
            if c.get("count"):
                e["occurrences"] = c["count"]
            matrix.setdefault(c.get("type", "?"), []).append(e)
    claim_matrix = []
    for t in sorted(matrix):
        if len(json.dumps(claim_matrix)) > 8000:
            break
        claim_matrix.append({"type": t, "entries": matrix[t][:8]})
    ans = {"kind": "excerpt", "skill_id": "answer-coverage-audit", "budget_chars": 24000,
           "generated_at": _now(), "pages": ans_pages,
           "pages_without_content": empty_urls,
           "extras": {"checks": checks_for(catalog, "answer-coverage-audit"),
                      "fragment_shape": FRAGMENT_SHAPE,
                      "corroboration": corroboration or {"independent_resolving": 0,
                                                          "brand_matched": 0},
                      "coverage_appendix": coverage_appendix}}
    frs = {"kind": "excerpt", "skill_id": "freshness-consistency-audit",
           "budget_chars": 16000, "generated_at": _now(), "pages": frs_pages,
           "pages_without_content": empty_urls,
           "extras": {"sitemap": sitemap_summary,
                      "page_dates": [{"url": p["requested_url"],
                                      "structured": p.get("_structured_dates", []),
                                      "visible_dates": [c["value"] for c in p["claim_index"]
                                                        if c["type"] == "date"][:5]}
                                     for p in pages],
                      "checks": checks_for(catalog, "freshness-consistency-audit"),
                      "fragment_shape": FRAGMENT_SHAPE,
                      "corroboration": corroboration or {"independent_resolving": 0,
                                                          "brand_matched": 0},
                      "claim_matrix": claim_matrix}}
    ref = {"kind": "excerpt", "skill_id": "referral-experience-audit",
           "budget_chars": 6000, "generated_at": _now(), "pages": ref_pages,
           "pages_without_content": empty_urls,
           "extras": {"checks": checks_for(catalog, "referral-experience-audit"),
                      "fragment_shape": FRAGMENT_SHAPE,
                      "screen_windows": screen_windows,
                      "pages_signals": [
               {"url": p["requested_url"],
                "overlay_in_raw_html": p["interactive"]["overlay_in_raw_html"],
                "accordions": p["interactive"]["accordions"],
                "details_elements": p["interactive"]["details_elements"],
                "dialogs": p["interactive"]["dialogs"]} for p in pages],
               "soft_404": probes.get("soft_404"),
               "redirect_path_preservation": probes.get("redirect_path_preservation", []),
               "note": "passages_checked.json arrives after the --passages post-step;"
                       " REF-SOFT-404 / REF-404-DEAD-END / REF-PATH-DROP-REDIRECT read"
                       " the probe results here"}}
    return ans, frs, ref


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def discover_candidates(homepage_res, extractor, sitemap_urls, fetcher, base):
    candidates = []
    for sm_url in sitemap_urls[:2]:
        sm = fetch_sitemap(fetcher, urljoin(base, sm_url))
        if sm and sm.get("parse_ok") and sm.get("entries_count"):
            candidates = [e["url"] for e in sm["lastmod_sample"]]  # sample only; full list too big
            break
    seen = set()
    for link in extractor.links:
        href = link["href"]
        p = urlparse(href)
        if p.scheme not in ("http", "https") or p.netloc != urlparse(base).netloc:
            continue
        if p.path in ("", "/") or p.path in seen:
            continue
        if re.search(r"\.(pdf|jpg|jpeg|png|gif|svg|zip|css|js|ico|xml|mp4|webp)$", p.path, re.I):
            continue
        if any(frag in p.path.lower() for frag in ("wp-content", "wp-json", "feed", "tag/", "author/")):
            continue
        seen.add(p.path)
        candidates.append(urlunparse((p.scheme, p.netloc, p.path, "", "", "")))
        if len(seen) >= 400:
            break
    return candidates


def _blank_page(url, page_class, timing_ms, content_type=None):
    """Page record for a fetch with nothing parsable (non-HTML, exhausted chain).

    Specialists see an uncaptured page with its content type; nothing enters
    the claim index."""
    return {
        "requested_url": url, "final_url": url,
        "status": 0, "redirect_chain": [],
        "content_type": content_type, "bytes": 0, "timing_ms": timing_ms,
        "raw_html": "", "visible_text": "", "title": None,
        "meta_description": None, "canonical": None, "lang": None,
        "hreflang": [], "robots_meta": None, "x_robots_tag": None,
        "headers": {}, "sitemap_lastmod": None, "page_class": page_class,
        "headings": [], "links": [], "jsonld": [], "microdata_types": [],
        "open_graph": {}, "images": [],
        "tables": {"semantic_count": 0, "div_grid_candidates": 0},
        "interactive": {"accordions": 0, "dialogs": 0, "details_elements": 0,
                        "overlay_in_raw_html": None},
        "non_text": {"canvas": 0, "svg_without_text": 0,
                     "video_without_transcript": 0},
        "inline_state": {"payload_keys": [], "contrast_strings": []},
        "claim_index": [], "_structured_dates": [], "_sections": []}


def probe_link_rot(fetcher, pages, selected_urls, robot_rows, site_host):
    """Sample <=5 unfetched same-origin links (rot hides off the crawled set).

    Bounded and deadline-aware; the caller skips when remaining() is low.
    410 Gone is correct removal and never rot - only 404/5xx count downstream.
    Timeouts/unresolved never become findings (recorded without status)."""
    if fetcher.remaining() < 15.0:
        return []
    seen, rows = set(), []
    fetched = {u.rstrip("/") for u in selected_urls}
    for p in pages:
        if len(rows) >= 5:
            break
        for link in (p.get("links") or []):
            if len(rows) >= 5:
                break
            href = link.get("href") or ""
            parts = urlparse(href)
            if parts.scheme not in ("http", "https"):
                continue
            if parts.netloc != site_host and not parts.netloc.endswith("." + site_host):
                continue
            norm = href.rstrip("/")
            if norm in seen or norm in fetched:
                continue
            try:
                if robot_rows is not None and not allowed(
                        robot_rows, "*", parts.path or "/"):
                    continue
            except Exception:
                pass
            seen.add(norm)
            res = fetcher.fetch(href, max_bytes=TINY_BYTES)
            rows.append({"url": href, "status": res.get("status"),
                         "error": str(res.get("error") or "")[:120] or None,
                         "source_url": p["requested_url"],
                         "source_class": p.get("page_class")})
    return rows


def run_collect(args):
    started = time.time()
    marks = [("start", started)]
    deadline_ts = started + args.deadline
    url = args.url
    parts = urlparse(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        fail("URL must be absolute http(s): %s" % url)
    if parts.username or parts.password:
        fail("refusing URL with credentials")
    # declared facts, probed never: site_type is the agent's classification
    notes = []
    valid_site_types = {"saas", "ecommerce", "local-business", "docs-developer",
                        "publisher", "gov-edu", "marketplace-platform", "org-portfolio"}
    site_types = [s.strip() for s in args.site_type.split(",") if s.strip()]
    bad_types = [s for s in site_types if s not in valid_site_types]
    if bad_types or len(site_types) > 3:
        fail("invalid --site-type %s (valid: %s; max 3)" % (bad_types, sorted(valid_site_types)), [])
    declared_caps = {c.strip() for c in args.capabilities.split(",") if c.strip()}
    bad_caps = declared_caps - {"web_fetch", "web_search", "browser", "subagents"}
    if bad_caps:
        fail("invalid --capabilities values: %s" % sorted(bad_caps), [])
    if "browser" in declared_caps:
        notes.append("browser capability declared; representation checks may upgrade confidence")
    else:
        notes.append("no browser: render checks run no-browser at limited confidence")

    base = urlunparse((parts.scheme, parts.netloc, "/", "", "", ""))
    fetcher = Fetcher(deadline_ts, args.allow_private)

    # robots -----------------------------------------------------------------
    robots_attempts = 1
    robots_res = fetcher.fetch(urljoin(base, "/robots.txt"), max_bytes=SMALL_BYTES)
    if (not robots_res.get("error")) and (robots_res.get("status") or 0) >= 500:
        # one retry for transient safe failures - ACC-ROBOTS-UNAVAILABLE's
        # two-consecutive-5xx rule needs recorded attempts
        robots_attempts = 2
        robots_res = fetcher.fetch(urljoin(base, "/robots.txt"), max_bytes=SMALL_BYTES)
    robots_groups, sitemap_urls = [], []
    r_status, r_http = "error", None
    if not robots_res.get("error"):
        r_http = robots_res["status"]
        if r_http == 404:
            r_status = "not_found"
        elif r_http and r_http < 400:
            r_status = "present"
            robots_groups, sitemap_urls = parse_robots(
                robots_res["body"].decode("utf-8", "replace"))
        else:
            r_status = "error"
            notes.append("robots.txt returned %s - crawl-delays condition (see ACC-ROBOTS-UNAVAILABLE)" % r_http)
    else:
        notes.append("robots.txt unreachable: %s" % robots_res["error"])
    robot_rows = expand_robot_rows(robots_groups, ROLE_BY_TOKEN)

    marks.append(("robots", time.time()))
    # homepage + discovery ----------------------------------------------------
    home_res = fetcher.fetch(base)
    home_redirect_record = None
    if home_res.get("error") or home_res.get("status") is None:
        chain = res_chain = home_res.get("redirect_chain") or []
        if len(chain) >= 3:
            # a homepage-level redirect loop is exactly what ACC-REDIRECT-LOOP
            # must see - record the chain and keep building the snapshot
            home_redirect_record = chain
            notes.append("homepage redirect chain exhausted (%d hops)" % len(chain))
        else:
            print("collect_snapshot: FATAL - homepage unreachable: %s" % home_res.get("error"))
            print(json.dumps({"snapshot_written": False, "error": home_res.get("error")}))
            sys.exit(1)
        home_res = {"status": None, "headers": {}, "body": b"",
                    "final_url": chain[-1] if chain else base,
                    "redirect_chain": chain, "timing_ms": 0, "error": None}
    home_ex = PageExtractor(base)
    home_ex.feed(home_res["body"].decode("utf-8", "replace"))
    home_ex.close()
    home_ex.finalize()

    candidates = discover_candidates(home_res, home_ex, sitemap_urls, fetcher, base)
    selected, labels, cluster_rows = select_pages([base] + candidates, args.max_pages)
    sitemap_summary = None
    if sitemap_urls:
        sitemap_summary = fetch_sitemap(fetcher, urljoin(base, sitemap_urls[0]))
    lastmod_by_url = {}
    if sitemap_summary and sitemap_summary.get("parse_ok"):
        for e in sitemap_summary.get("lastmod_sample", []):
            lastmod_by_url[e["url"].rstrip("/")] = e["lastmod"]

    marks.append(("discovery", time.time()))
    # per-page capture --------------------------------------------------------
    pages = []
    if home_redirect_record:
        pages.append({
            "requested_url": base, "final_url": home_redirect_record[-1],
            "status": 0, "redirect_chain": home_redirect_record,
            "content_type": None, "bytes": 0, "timing_ms": 0,
            "raw_html": "", "visible_text": "", "title": None,
            "meta_description": None, "canonical": None, "lang": None,
            "hreflang": [], "robots_meta": None, "x_robots_tag": None,
            "headers": {}, "sitemap_lastmod": None, "page_class": "homepage",
            "headings": [], "links": [], "jsonld": [], "microdata_types": [],
            "open_graph": {}, "images": [],
            "tables": {"semantic_count": 0, "div_grid_candidates": 0},
            "interactive": {"accordions": 0, "dialogs": 0, "details_elements": 0,
                            "overlay_in_raw_html": None},
            "non_text": {"canvas": 0, "svg_without_text": 0,
                         "video_without_transcript": 0},
            "inline_state": {"payload_keys": [], "contrast_strings": []},
            "claim_index": [], "_structured_dates": [], "_sections": []})
    for u in selected:
        if fetcher.remaining() < 3.0:
            notes.append("deadline: stopped page capture early")
            break
        res = fetcher.fetch(u)
        if (res.get("error") or res.get("status") is None
                or (res.get("status") or 500) >= 400):
            # a redirect-exhausted chain is ACC-REDIRECT-LOOP evidence - record
            # the chain instead of dropping the fetch entirely
            if len(res.get("redirect_chain") or []) >= 3:
                notes.append("page redirect chain exhausted: %s" % u)
                pages.append({
                    "requested_url": u,
                    "final_url": (res.get("redirect_chain") or [u])[-1],
                    "status": 0,
                    "redirect_chain": res.get("redirect_chain") or [u],
                    "content_type": None, "bytes": 0, "timing_ms": res.get("timing_ms"),
                    "raw_html": "", "visible_text": "", "title": None,
                    "meta_description": None, "canonical": None, "lang": None,
                    "hreflang": [], "robots_meta": None, "x_robots_tag": None,
                    "headers": {}, "sitemap_lastmod": None, "page_class": labels.get(u, "other"),
                    "headings": [], "links": [], "jsonld": [], "microdata_types": [],
                    "open_graph": {}, "images": [],
                    "tables": {"semantic_count": 0, "div_grid_candidates": 0},
                    "interactive": {"accordions": 0, "dialogs": 0, "details_elements": 0,
                                    "overlay_in_raw_html": None},
                    "non_text": {"canvas": 0, "svg_without_text": 0,
                                 "video_without_transcript": 0},
                    "inline_state": {"payload_keys": [], "contrast_strings": []},
                    "claim_index": [], "_structured_dates": [], "_sections": []})
            else:
                notes.append("page fetch failed: %s (%s)" % (u, res.get("error") or res.get("status")))
            continue
        ctype = ((res.get("headers") or {}).get("content-type") or "")
        if ctype and "html" not in ctype.lower() and "xml" not in ctype.lower():
            # binary or foreign content (PDF, images, downloads): decoding it
            # feeds garbage claims into the index. Record the fetch, skip the
            # parse - specialists see an uncaptured page with its content type.
            notes.append("non-HTML content skipped: %s (%s)" % (u, ctype.split(";")[0]))
            pages.append(_blank_page(u, labels.get(u, "other"), res.get("timing_ms"),
                                      content_type=ctype.split(";")[0]))
            continue
        ex = PageExtractor(u)
        ex.feed(res["body"].decode("utf-8", "replace"))
        ex.close()
        ex.finalize()
        page = capture_page(res, u, ex, lastmod_by_url.get(u.rstrip("/")))
        page["_sections"] = ex.sections
        page["page_class"] = labels.get(u, "other")
        pages.append(page)

    marks.append(("capture", time.time()))
    # probes ------------------------------------------------------------------
    soft = probe_soft_404(fetcher, base)
    llms_res = fetcher.fetch(urljoin(base, "/llms.txt"), max_bytes=TINY_BYTES)
    llms_txt = None
    if not llms_res.get("error") and llms_res.get("status") is not None:
        llms_txt = {"http_status": llms_res["status"],
                    "content_type": (llms_res.get("headers") or {}).get("content-type"),
                    "format": "llms-txt" if llms_res["status"] == 200 else "none"}
    deep = next((urlparse(p["requested_url"]).path for p in pages
                 if urlparse(p["requested_url"]).path not in ("", "/")), "/pricing")
    redirects = probe_redirects(fetcher, urlunparse((parts.scheme, parts.netloc, deep, "", "", "")))
    ua_probes = probe_ua(fetcher, base, robot_rows, r_status,
                         home_res.get("status"))
    link_rot = probe_link_rot(fetcher, pages, [p["requested_url"] for p in pages],
                              robot_rows, parts.netloc)
    external = resolve_external_presence(fetcher, pages, parts.netloc)

    marks.append(("probes", time.time()))
    # excerpts ----------------------------------------------------------------
    catalog = _load_catalog()
    ans, frs, ref = build_excerpts(pages, sitemap_summary, {"soft_404": soft,
                                                            "redirect_path_preservation": redirects},
                                   catalog=catalog,
                                   corroboration={
                                       "independent_resolving": sum(
                                           1 for e in external
                                           if e.get("owned_vs_independent") == "independent"
                                           and isinstance(e.get("http_status"), int)
                                           and 200 <= e["http_status"] < 400),
                                       "brand_matched": sum(
                                           1 for e in external if e.get("brand_name_match") is True)})

    snapshot = {
        "snapshot_version": 1,
        "requested_url": url,
        "audited_at": _now(),
        "network_deadline_seconds": args.deadline,
        "capabilities": {"web_fetch": True,
                         "web_search": "web_search" in declared_caps,
                         "browser": "browser" in declared_caps,
                         "subagents": "subagents" in declared_caps,
                         "notes": notes},
        "robots": {"status": r_status, "http_status": r_http,
                   "attempts": robots_attempts,
                   "groups": robot_rows,
                   "sitemaps_declared": sitemap_urls[:10],
                   "content_type": robots_res.get("headers", {}).get("content-type")},
        "sitemap": sitemap_summary,
        "discovery": {"method": "sitemap sample + crawlable same-origin links,"
                                " template-clustered stratified pick",
                      "sitemap_urls_count": len(sitemap_urls),
                      "candidates_count": len(candidates) + 1,
                      "selected": [p["requested_url"] for p in pages],
                      "clusters": cluster_rows},
        "external_presence": external,
        "pages": [{k: v for k, v in p.items() if not k.startswith("_")} for p in pages],
        "probes": {"soft_404": soft, "redirect_path_preservation": redirects,
                   "ua_probes": ua_probes, "llms_txt": llms_txt,
                   "internal_link_rot": link_rot},
        "excerpts_manifest": [],
    }

    errs = validate_schema(snapshot, SNAPSHOT_SCHEMA)
    if errs:
        fail("snapshot does not validate against snapshot_schema.json", errs)
    if site_types:
        snapshot["site_type"] = site_types
        errs = validate_schema(snapshot, SNAPSHOT_SCHEMA)
        if errs:
            fail("snapshot (site_type) does not validate", errs)

    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    exc_dir = os.path.join(out_dir, "excerpts")
    os.makedirs(exc_dir, exist_ok=True)
    manifest = []
    for exc in (ans, frs, ref):
        path = os.path.join(exc_dir, "%s.json" % exc["skill_id"])
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(exc, fh, indent=2, ensure_ascii=False)
        manifest.append({"skill_id": exc["skill_id"], "path": os.path.abspath(path),
                         "note": "single prepared input; one read + one judgment + one write"})
    snapshot["excerpts_manifest"] = manifest
    errs = validate_schema(snapshot, SNAPSHOT_SCHEMA)
    if errs:
        fail("snapshot (with manifest) does not validate", errs)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(snapshot, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    elapsed = int(time.time() - started)
    print("collect_snapshot: %s" % args.out)
    print("  robots: %s (http %s) | sitemap entries: %s | candidates: %d | selected: %d"
          % (r_status, r_http,
             (sitemap_summary or {}).get("entries_count") if sitemap_summary else None,
             len(candidates) + 1, len(pages)))
    print("  soft-404 probe: %s | redirect variants: %d | UA probes: %d | external: %d"
          % ((soft or {}).get("status"), len(redirects), len(ua_probes), len(external)))
    print("  requests: %d | wall-clock: %ds of %ds deadline | deadline_hit: %s"
          % (fetcher.requests, elapsed, args.deadline, elapsed >= args.deadline - 2))
    marks.append(("excerpts_write", time.time()))
    print("  phases: %s" % " | ".join(
        "%s=%ds" % (marks[i + 1][0], int(marks[i + 1][1] - marks[i][1]))
        for i in range(len(marks) - 1)))
    print("  excerpts: %s" % ", ".join(m["path"] for m in manifest))
    if notes:
        print("  notes: %s" % " | ".join(notes[:5]))
    return snapshot


def _fold_confusables(s):
    """Fold common punctuation confusables before text comparison.

    A model quoting a passage retypes what it saw: en/em dashes become
    hyphens, curly quotes straighten, nbsp becomes a space. Browsers match
    scroll-to-text fragments on narrower terms, so a folded match is NOT a
    contiguity verdict - it only earns a distinct note naming quoting
    fidelity instead of blaming the page."""
    table = dict((ord(c), r) for c, r in [
        ("\u2010", "-"), ("\u2011", "-"), ("\u2012", "-"),
        ("\u2013", "-"), ("\u2014", "-"), ("\u2212", "-"),
        ("\u2018", "'"), ("\u2019", "'"), ("\u201a", "'"),
        ("\u201b", "'"), ("\u201c", '"'), ("\u201d", '"'),
        ("\u201e", '"'), ("\u201f", '"'), ("\u00a0", " "),
    ])
    return " ".join((s or "").translate(table).split())


def run_passages(args):
    snapshot = load_json(args.snapshot)
    passages = load_json(args.passages)
    if passages.get("kind") != "passages":
        fail("--passages file must be a passages file (kind=passages)", [])
    if not isinstance(passages.get("questions"), list) or not passages["questions"]:
        fail("--passages file has no questions[]: answer-coverage wrote no prompt set "
             "(expected key 'questions', not 'passages'); fix passages.json and re-run", [])
    by_url = {p["requested_url"]: p for p in snapshot["pages"]}

    def _norm_key(u):
        try:
            parts = urlparse(u or "")
            host = (parts.netloc or "").lower()
            if host.startswith("www."):
                host = host[4:]
            path = parts.path.rstrip("/") or "/"
            return host + path
        except Exception:
            return u or ""
    by_norm = {}
    for p in snapshot["pages"]:
        by_norm.setdefault(_norm_key(p["requested_url"]), p)
    results = []
    for q in passages.get("questions", []):
        if not q.get("candidate_passage"):
            # unanswered question: the entry is kept (it still feeds the
            # offsite prompt set) with no passage key. Never a crash, never
            # a contiguity verdict - referral reads this note, not a finding.
            results.append({"question_id": q.get("question_id"), "page_url": q.get("expected_page"),
                            "contiguous": False, "quote": None,
                            "note": "no candidate passage recorded (unanswered question)"})
            continue
        want_url = q.get("expected_page")
        page = by_url.get(want_url) or by_norm.get(_norm_key(want_url))
        contiguous, note = False, None
        if page is None:
            close = [u for u in by_url
                     if _norm_key(u) == _norm_key(want_url) or u.rstrip("/") == (want_url or "").rstrip("/")][:3]
            if not close:
                same_host = [u for u in by_url if urlparse(u).netloc.lower().lstrip("www.") == urlparse(want_url or "").netloc.lower().lstrip("www.")][:3]
                close = same_host
            note = ("expected_page not in snapshot: got %s%s" %
                    (want_url, "; close matches: " + ", ".join(close) if close else "; no close match"))
        else:
            ex = PageExtractor(q["expected_page"])
            ex.feed(page["raw_html"])
            ex.close()
            ex.finalize()
            want = " ".join((q.get("candidate_passage") or "").split())
            blocks = [" ".join(b.split()) for b in ex.blocks]
            # headings and link anchors never enter blocks (handle_data routes
            # them aside), but each is a single rendered run - checkable here.
            head_runs = [" ".join(h.get("text", "").split()) for h in (ex.headings or [])]
            head_runs += [" ".join((a.get("anchor_text") or "").split())
                          for a in (ex.links or [])]
            head_runs = [t for t in head_runs if t]
            contiguous = any(want and want in b for b in blocks)
            if not contiguous and want:
                # scroll-to-text range fragments match across consecutive block
                # boundaries; a two-adjacent-block span still highlights
                contiguous = any(want in (blocks[i] + " " + blocks[i + 1])
                                 for i in range(len(blocks) - 1))
                if contiguous:
                    note = "passage spans two adjacent blocks (still fragment-highlightable)"
            if not contiguous:
                full = " ".join(blocks)
                if want and want in full:
                    note = ("passage text is present on the page but split across blocks "
                            "or interleaved - not one contiguous run")
                elif want and any(want in t for t in head_runs):
                    contiguous = True
                    note = ("passage matches a heading or link run - "
                            "a single highlightable run")
                elif want and ex.title and want == " ".join(ex.title.split()):
                    note = ("passage matches the document title, which is not "
                            "a highlightable body run - quote body text instead")
                elif want and _fold_confusables(want) in _fold_confusables(full):
                    note = ("passage matches page text up to punctuation/whitespace variants "
                            "(e.g. dashes or quotes) - likely quoting fidelity, not a site defect; "
                            "verify the exact substring before citing")
                else:
                    note = ("passage text not found anywhere on the page - the "
                            "expected_page may be wrong or the passage paraphrased")
        results.append({"question_id": q["question_id"], "page_url": q.get("expected_page"),
                        "contiguous": contiguous, "quote": ((q.get("candidate_passage") or "")[:200]
                        if contiguous else None), "note": note})
    out = {"kind": "passages_checked", "generated_at": _now(), "results": results}
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    n_ok = sum(1 for r in results if r["contiguous"])
    n_split = sum(1 for r in results if not r["contiguous"] and r["note"]
                  and r["note"].startswith("passage text is present"))
    n_missing = len(results) - n_ok - n_split
    print("collect_snapshot --passages: %d/%d passages contiguous "
          "(split-across-blocks: %d, not-on-page: %d) -> %s"
          % (n_ok, len(results), n_split, n_missing, args.out))

    # offsite prompt-set excerpt: the questions (with their source) plus the
    # snapshot's external presence; written here because the prompt set only
    # exists after answer-coverage runs.
    exc_dir = os.path.join(os.path.dirname(os.path.abspath(args.out)), "excerpts")
    os.makedirs(exc_dir, exist_ok=True)
    offsite = {
        "kind": "excerpt", "skill_id": "offsite-visibility-audit", "budget_chars": 8000,
        "generated_at": _now(),
        "pages": [{"url": q.get("expected_page"), "page_class": None, "title": None,
                   "heading_tree": [], "main_content_excerpts": [],
                   "claim_index_subset": []}
                  for q in passages.get("questions", [])][:8],
        "extras": {"prompt_set": [{"question_id": q["question_id"],
                                    "question": q["question"],
                                    "source": q.get("source", "site-derived")}
                                   for q in passages.get("questions", [])],
                   "external_presence": snapshot.get("external_presence", []),
                   "search_declared": snapshot.get("capabilities", {}).get("web_search", False),
                   "note": "live probes only when search_declared; sheds first at the "
                           "deadline; without search, snapshot-only reasoning over "
                           "external_presence and never invented probe results",
                   "checks": checks_for(_load_catalog(), "offsite-visibility-audit"),
                   "fragment_shape": FRAGMENT_SHAPE},
    }
    offsite_path = os.path.join(exc_dir, "offsite-visibility-audit.json")
    with open(offsite_path, "w", encoding="utf-8") as fh:
        json.dump(offsite, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print("  offsite prompt-set excerpt -> %s (%d prompts, search_declared=%s)"
          % (offsite_path, len(offsite["extras"]["prompt_set"]),
             offsite["extras"]["search_declared"]))


SNAPSHOT_SCHEMA = None  # loaded in main()
ROLE_BY_TOKEN = {}  # agent token -> registry role; loaded in main()


def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def fail(what, errs):
    sys.stderr.write("collect_snapshot: FAIL - %s\n" % what)
    for e in errs or []:
        sys.stderr.write("  - %s\n" % e)
    sys.exit(1)


def main():
    global SNAPSHOT_SCHEMA, ROLE_BY_TOKEN
    here = os.path.dirname(os.path.abspath(__file__))
    refs = os.path.normpath(os.path.join(here, "..", "references"))
    SNAPSHOT_SCHEMA = load_json(os.path.join(refs, "snapshot_schema.json"))
    registry = load_json(os.path.join(refs, "provider_registry.json"))
    ROLE_BY_TOKEN = {r["agent"].lower(): r["role"] for r in registry["crawler_roles"]}

    ap = argparse.ArgumentParser(description="Build the shared audit evidence snapshot.")
    ap.add_argument("--url", help="public http(s) URL to audit")
    ap.add_argument("--out", default="audit/snapshot.json", help="snapshot output path")
    ap.add_argument("--snapshot", help="existing snapshot (for --passages mode)")
    ap.add_argument("--passages", help="audit/passages.json (answer-coverage-audit output)")
    ap.add_argument("--allow-private", action="store_true",
                    help="permit private/loopback hosts and non-standard ports "
                         "(local test fixtures only)")
    ap.add_argument("--site-type", default="",
                    help="the agent's conservative classification, comma-separated "
                         "(max 3): saas,ecommerce,local-business,docs-developer,"
                         "publisher,gov-edu,marketplace-platform,org-portfolio")
    ap.add_argument("--capabilities", default="",
                    help="declared capabilities, comma-separated: "
                         "web_fetch,web_search,browser,subagents")
    ap.add_argument("--max-pages", type=int, default=8)
    ap.add_argument("--deadline", type=int, default=120, help="network deadline seconds")
    args = ap.parse_args()

    if args.passages:
        if not args.snapshot:
            fail("--passages mode requires --snapshot", [])
        run_passages(args)
    elif args.url:
        run_collect(args)
    else:
        fail("either --url or (--passages with --snapshot) is required", [])


if __name__ == "__main__":
    main()
