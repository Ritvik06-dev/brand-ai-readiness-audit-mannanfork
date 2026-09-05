#!/bin/sh
# Sync local test-dir installs from the source marketplace.
# Run before every local run - stale copies silently test yesterday's skills.
set -e
cd "$(dirname "$0")"
for d in local-skill-test local-skill-tes-00 local-skill-tes-01 local-skill-tes-02; do
  [ -d "$d" ] || continue
  rm -rf "$d/.agents/skills"
  mkdir -p "$d/.agents/skills"
  cp -r brand-retrieval-readiness/skills/* "$d/.agents/skills/"
  cp brand-retrieval-readiness/marketplace.json "$d/.agents/marketplace.json"
  find "$d/.agents" -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
  echo "synced $d"
done
