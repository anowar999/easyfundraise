# ADR-001: Python (FastAPI) backend instead of Node/Hono

**Status:** accepted · 2026-10-31

The spec (§4.1) proposes a Node/Hono API plus a separate Python AI service. The product owner asked for
PostgreSQL + Python, so v1 is a single **FastAPI** service (`apps/api`) that owns the app API, admin API,
entitlements and the deterministic "own engine" (fit scoring, note parsing, template outreach). When LLM
features land they live in the same codebase behind a provider-agnostic gateway module; split into a
separate service only if deploy cadence or scaling demands it.

Consequences: one language for data, scoring and API; SQLAlchemy 2 + Alembic replace Drizzle; Zod
contracts are replaced by Pydantic models (OpenAPI at `/docs` in non-prod).
