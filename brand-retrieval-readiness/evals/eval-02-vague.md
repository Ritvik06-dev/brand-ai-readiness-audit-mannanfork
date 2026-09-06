# Eval 02 — vague audit intent

## Prompt

> Why isn't my brand showing up in AI answers? The site is https://example.com.

## Expected behavior

The entrypoint triggers on implied audit intent (no explicit "audit" verb
needed): it confirms the URL if ambiguous, then runs the full audit as in
eval-01.

## Pass criteria

- An implied why-is-my-brand-invisible question routes to the audit, not to
  generic advice.
- If the URL is missing or ambiguous, the agent asks for it rather than
  guessing a domain.
- Result holds the same report contract as eval-01.
