# Field Study — human workstream (BUILD_PLAN §2)

Failure-first protocol (INDEPENDENT_REVIEW §8.2). Start Day 3: pick 10 sites where you
personally know a specific ground-truth fact (a price, an SSO tier, a limit, opening hours,
a return window). Run 8 question-pairs × 2 engines (Perplexity + ChatGPT-search or Google
AI Mode) × 2 repeats ≈ 32 queries.

Outcome classes per query:
`official-cited` / `third-party-cited` / `brand-mentioned-no-citation` / `brand-absent` /
`wrong-entity` / `fact-stated-wrongly` (the money case) / `unhelpful-landing`

Log every run in `query_ledger.csv`; per-site pipeline signals go in `site_ledger.csv`.
Earn-a-check rule: a signal becomes a check only if it repeatedly separates cited from
uncited or explains a misrepresentation.
