# ADR-003: Tenant isolation and investor data handling

**Status:** accepted · 2026-10-31

- **Tenancy:** every tenant table has `workspace_id`; every query goes through `deps.ctx`, which resolves
  the workspace from the signed-in user's memberships. Tests assert cross-workspace reads return 404.
  Postgres Row-Level Security (spec §4.4) is a follow-up hardening step; it needs a non-superuser app role.
- **Investor dataset is never committed.** The repo is public; the directory CSV / enrichment JSONL live in
  `data/private/` (git-ignored) and are loaded with `python -m app.cli import-investors`. Dev/CI use
  `python -m app.cli demo-investors` (synthetic).
- **Contacts are gated server-side** (ASP-01): list/search payloads never include email/LinkedIn; the reveal
  endpoint spends a credit once per workspace and logs a `data_access_events` row.
- **Directory join:** enrichment `wid` does not index the directory, so enrichment joins by normalised name,
  disambiguated by firm / email domain (595 of 596 matched on the 2026-10-30 handoff).
