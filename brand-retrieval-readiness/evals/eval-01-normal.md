# Eval 01 — normal audit request

## Prompt

> Audit https://example.com for AI discoverability and engagement.

## Expected behavior

Full audit via `audit-orchestrator`: snapshot, specialists in manifest order,
single schema-valid `report.json` with the required floor (`site`,
`audited_at`, counts-by-severity summary, findings with
`id/title/severity/evidence/suggested_action`).

## Pass criteria

- Report validates against `references/output_schema.json`.
- Every finding carries evidence (URL + observation + method) and a suggested
  action with an acceptance test.
- Honest coverage: `not_evaluated` entries carry reasons; nothing silent.
