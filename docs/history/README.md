# Preserved history and owner inventory

- `2026-10-18.md` is the earlier implementation/acceptance chronology, superseded by `../current-state.md`.
- `package-manifest-legacy.json` preserves the old root package inventory. It is stale historical data, not an integrity gate; the review found 35 changed entries among its 90 files. Production packages use their own `handoff.json` instead.
- The root `bone-app-svg-collection.zip` is retained owner inventory (about 35 MB), outside SBPH runtime and example dependencies. No deletion, extraction, publication, or Git history rewrite is required for local production.

Keep current test/render results and their source revision with local run evidence; `/tmp/` is diagnostic scratch, not a durable evidence store.
