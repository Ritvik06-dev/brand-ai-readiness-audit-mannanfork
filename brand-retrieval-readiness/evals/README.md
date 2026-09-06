# Evals — entrypoint behavior cases

Six prompt cases testing that the entrypoint triggers, refuses, or stays silent
correctly. Each case: the prompt, the expected behavior, and the pass criterion.
Run by hand or by harness; no fixtures, no trace review — the prompt and the
report (or refusal) are the whole artifact.

- [01-normal](eval-01-normal.md) — direct audit request
- [02-vague](eval-02-vague.md) — implied audit intent
- [03-redirect](eval-03-redirect.md) — redirecting URL
- [04-unreachable](eval-04-unreachable.md) — unreachable URL
- [05-auth-refusal](eval-05-auth-refusal.md) — authenticated-area request
- [06-non-audit](eval-06-non-audit.md) — non-audit prompt, no activation
