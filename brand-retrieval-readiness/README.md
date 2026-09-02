# Brand Retrieval Readiness — Agent Skill Marketplace

> **Build status (Phase 0):** skeleton. This README is finalized in Phase 7 per `BUILD_PLAN.md`.

Planned opener (INDEPENDENT_REVIEW §10):

1. This marketplace audits the assistant pipeline — **reach → read → extract → identify → trust →
   land** — and reports, for each break, which stage failed, on which retrieval surfaces, with
   quoted evidence and a stated confidence.
2. Scripts own what must be exact: status codes, parses, counts, timeouts, schema validation.
   The model owns what regex cannot judge: whether a passage stands alone as an answer, whether
   two claims contradict, whether a name is ambiguous.
3. It refuses to treat training-crawler policy, a missing `llms.txt`, or a guessed Core Web Vital
   as an outage — Google's own documentation states there are no special requirements or schema
   needed to appear in AI features, and the checks here are built accordingly.

## Skills

| Skill | Role | Driven by |
|---|---|---|
| `audit-orchestrator` | **entrypoint** — snapshot, composition, correlation, report | `collect_snapshot.py`, `build_report.py` |
| `access-discovery-audit` | reach: robots roles, index controls, canonicals, challenges | `probe_access.py` |
| `representation-parity-audit` | read: raw/text/state/metadata fact parity | `analyze_representation.py` |
| `answerability-audit` | extract: question→passage completeness | judgment over bounded excerpts |
| `entity-consistency-audit` | identify: JSON-LD validity, identity matrix, ambiguity | `check_entities.py` + judgment |
| `freshness-consistency-audit` | trust: dates, versions, self-contradictions | judgment over claim index |
| `referral-experience-audit` | land: above-fold confirmation, overlays, soft 404s, fragments | judgment + snapshot probes |

## Validation

```sh
uvx --from skills-ref agentskills validate skills/<skill-name>
```

(Note: the `skills-ref` package installs a binary named `agentskills`, not `skills-ref`.)
