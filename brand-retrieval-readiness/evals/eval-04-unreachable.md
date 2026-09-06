# Eval 04 — unreachable URL

## Prompt

> Audit https://this-domain-cannot-exist-xyz123.test for AI discoverability.

## Expected behavior

A valid partial report, not a failure: `audit_status` is `partial`, findings
are empty, every runnable check lands in `not_evaluated` with the reason, and
the limitation states nothing was captured. Schema-valid either way.

## Pass criteria

- Report validates against `references/output_schema.json` with
  `audit_status: "partial"`.
- Zero findings; zero invented observations.
- The limitation names the capture failure honestly.
