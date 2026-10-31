# ADR-002: Postgres for rate limits, counters and the reminder queue (no Redis yet)

**Status:** accepted · 2026-10-31

Usage counters (searches, reveals), fixed-window rate limits (ASP-02) and the reminder → notification
job (TZ-04) use Postgres tables plus a small polling worker (`python -m app.worker`). This keeps the
first deploy to two moving parts (Postgres + app). Move rate limits and the send queue to Redis/BullMQ
when outreach sending ships (MAIL-05/TZ-03), where per-second pacing matters.
