# Question archetypes — what customers ask, by site type

Answer-coverage generates its question set from these archetypes. Two rules govern
applicability: generate questions an actual customer in the site's category would ask, and do
not force an archetype onto a site type where it has no decision meaning (the negative control
for ANS-QUESTION-UNANSWERED).

## The eight archetypes

| Archetype | The customer's question shape | Example |
|---|---|---|
| identity | What is this, and who is it for? | "What does Acme do?" |
| capability | Does it support / provide / handle X? | "Does Acme support SAML?" |
| transaction | What does it cost, and what are the constraints? | "How much is the Pro plan?" |
| procedure | How do I do X with it? | "How do I migrate to Acme?" |
| temporal | What is the current version / status / policy? | "Is v2 still supported?" |
| comparison | How does it differ from the alternative? | "Acme vs Beta for small teams?" |
| trust | What evidence backs this claim? | "Is Acme SOC 2 certified?" |
| local | Where, when, how do I visit / contact / book? | "Is the clinic open Saturday?" |

## Applicability by site type

Site types come from the snapshot's `site_type` (multiple allowed). "core" archetypes must be
answered by the site's own pages for the category to be competitive; "often" archetypes apply
when the site's content implies them; "rare" archetypes are skipped unless the site clearly
targets them.

| Site type | core | often | rare |
|---|---|---|---|
| saas | identity, capability, transaction, procedure | temporal, comparison, trust | local |
| ecommerce | identity, transaction (price/stock/shipping), local (returns) | capability (specs), comparison, temporal | procedure, trust |
| local-business | local (hours, location, booking), identity, transaction | capability (services), trust (credentials) | comparison, procedure, temporal |
| docs-developer | identity, procedure, temporal (versions) | capability (limits/prereqs), comparison | transaction, local, trust |
| publisher | identity, temporal (currency) | trust (sourcing), local (editions) | capability, transaction, procedure, comparison |
| gov-edu | identity, temporal (deadlines/status), local | procedure, transaction (fees), trust | comparison |
| marketplace-platform | identity, transaction, comparison | capability, temporal, trust | procedure, local |
| org-portfolio | identity, capability (services/work) | local (contact), trust | comparison, temporal, procedure |

## What "answered" means (the gate for ANS-\*)

A question is **answered** when a sampled page contains a candidate passage that states the
subject explicitly, carries the operative claim with its units/timeframe, and keeps its
qualifier attached (the `qualifier_present` field). "Answered by a third party instead" is not
answered — that is ANS-QUESTION-UNANSWERED's finding, with the third-party gap as the
mechanism. "Answered for one plan/tier only" is ANS-QUALIFIER-DETACHED when the qualifier
lives elsewhere.

## Sizing

4–6 questions per audit, spread across the applicable core archetypes, weighted toward core.
At least two must be **market-derived** (asked the way a customer would phrase it, not the way
the site's nav labels it) — they are the prompt set offsite-visibility probes and the source
of `opportunities[]` when no page answers them. Prefer the questions that map to *sampled*
pages: a question whose expected page was not sampled can only end in `not_evaluated`.
One question per archetype; take a second archetype only when the site type's core row has
fewer than four applicable archetypes.

Default transaction and trust ON for every site type unless the coverage appendix shows
neither fees nor credentials anywhere. Include a comparison question only when the excerpt
shows a competing-option surface (tier grid, vs-page, plan grid) — never invent a competitor.
