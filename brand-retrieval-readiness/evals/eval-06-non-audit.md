# Eval 06 — non-audit prompt, no activation

## Prompt

> Write me a haiku about robots.txt.

## Expected behavior

No activation. The entrypoint's description scopes it to audits and diagnoses;
an unrelated creative request gets a normal response with no audit artifacts,
no snapshot, no report.

## Pass criteria

- No `audit/` directory created, no network probes run.
- The response does not mention findings, severities, or the pipeline.
