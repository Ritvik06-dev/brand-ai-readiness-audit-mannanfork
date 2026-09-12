# False-positive register

Traps an unguarded AI-readiness audit fires on, and is wrong. Each row names the
guard in this marketplace that stops it. **A check without a guard is not
finished** — if you add a check, add its row here and its negative control to the
catalog entry and the owning SKILL.md.

Rows 1–10 come from a 16-site field panel (the sibling `brand-ai-readiness-audit`
marketplace's research). Rows 11–12 were earned the hard way in this repo: both
were live false positives produced by this code against bbc.com, and both are now
fixed and locked by a regression test.

| # | Trap | Why firing on it is wrong | Guard here |
|---|---|---|---|
| 1 | Low text/HTML ratio | Two heavily-cited panel sites sit at ratios of 0.005–0.007 | `REP-EXTRACTION-LOSS` gates on an absolute displacement bar (median unique-content offset), never a ratio |
| 2 | Multiple `<h1>` | Valid HTML5; three strong panel sites ship two | No check counts `<h1>`s. Deliberate omission — do not add one |
| 3 | Bulk missing `alt` | 43/51 and 52/58 on strong sites; nearly all decorative | `REP-NON-TEXT-LOCKIN` weighs empty-alt images *against visible word count*, so a media-rich page with real text passes |
| 4 | No JSON-LD at all | Two of the most-cited panel sites ship none | `ENT-JSONLD-INVALID` fires on blocks that fail to parse, never on absence |
| 5 | Missing canonical | Fine when there is no duplicate-URL surface | `ACC-CANONICAL-CONFLICT` needs an actual conflict, not an absence |
| 6 | "Blocked in robots.txt" | Search, cart and session paths *should* be blocked | `ACC-ROBOTS-ROLE` only considers important page classes actually sampled |
| 7 | "AI blocked" as a boolean | Blocking is per-agent; one panel site blocks 5 of 14 | `ACC-ROBOTS-ROLE` resolves per token and treats training-crawler blocks as policy, never an outage |
| 8 | Missing `hreflang` | Meaningless on a single-locale site | `ACC-HREFLANG-INCONSISTENT` requires pages that already declare locales |
| 9 | One slow sample | Outliers are normal on any site | `ACC-FETCH-LATENCY` takes the median, never the max, and needs ≥3 timed successes |
| 10 | Missing Open Graph tags | Redundant when a description and JSON-LD carry the same facts | No standalone OG check. Deliberate omission |
| 11 | A 4xx on one redirect variant read as a dropped path | A WAF challenge to the audit UA is not the site breaking its redirects | `path_preserved` now answers only "did the path survive"; `variant_ok` carries status separately, and `redirect_relay()` excludes unreadable variants and names their status |
| 12 | End-to-end fetch time labelled "TTFB" | `timing_ms` covers connect + redirect hops + body read, so sub-second TTFB bars would over-fire by 3–5× | `ACC-FETCH-LATENCY` states the metric in its own evidence and sets bars for what is actually measured (2500/5000 ms) |

## The two traps this repo fell into

Both were found by auditing bbc.com and reading the evidence rather than the verdict.

**Row 11 — the expensive one.** `path_preserved` was computed as
`final_path == parts.path and status < 400`, collapsing two unrelated questions
into one boolean, and the `status` that drove it was never recorded. When BBC's
WAF answered 403 to the audit UA on the plain-http variant, the audit reported
*"1 redirect variant(s) dropped the deep path"* as a **high**-severity finding —
against a site whose http redirect resolves 200 with the path fully intact.

It survived because the stored evidence contradicted the stored verdict and there
was no way to tell which was right: `final_path` was byte-identical to the
requested path, yet `path_preserved` said `false`. One reader trusted the verdict
and filed the finding; another spotted the contradiction and filed
`not_evaluated`. The second reader was right.

The lesson generalises beyond this bug: **a verdict whose inputs are not recorded
cannot be audited, and an unauditable verdict eventually becomes a false
positive.** If a gate depends on a value, store the value.

**Row 12 — the quiet one.** The sibling marketplace reports a "Median TTFB" and
flags anything over 1500 ms. Its measurement, like this repo's `timing_ms`, is
actually a full response cycle. Ported naively, that check flags healthy sites at
around 1.6 s. Relabelled and rebarred, bbc.com's 1648 ms median correctly passes.
