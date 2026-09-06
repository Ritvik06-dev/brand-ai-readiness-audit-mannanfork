# Eval 03 — redirecting URL

## Prompt

> Audit http://example.com (it redirects to https://www.example.com/).

## Expected behavior

The orchestrator normalizes to the final origin after redirects, audits that
origin, and records the redirect chain: `site` names the audited host and the
evidence notes the normalization. Redirects that preserve path are normal;
redirects that drop a deep path to `/` are a REF-PATH-DROP-REDIRECT finding.

## Pass criteria

- `site` is the final origin, not the requested URL.
- The redirect chain is recorded, not silently followed.
- No finding merely for redirecting (a single canonicalizing hop is not a defect).
