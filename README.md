# EasyFundraise

The agentic workspace for raising capital: find the right investors, reach them with precise personalised
emails, and track every conversation in a fundraising-native CRM. Product spec: [`docs/spec/EASYFUNDRAISE_SPEC.md`](docs/spec/EASYFUNDRAISE_SPEC.md).

```
apps/api     Python 3.12 · FastAPI · SQLAlchemy 2 · Alembic · PostgreSQL 16
apps/web     Next.js 15 · React 19 · Tailwind v4 · TanStack Query · dnd-kit (mobile-first, installable PWA)
infra/       docker-compose for the full local stack
docs/        spec, ADRs, legal drafts (counsel review required before prod)
data/private investor datasets (git-ignored, never committed)
```

## What works today

| Area | Spec refs |
|---|---|
| Sign in with Google (openid/email/profile only) + passwordless dev sign-in, 30-day rolling httpOnly sessions | AUTH-01/02/07 |
| Workspaces, roles, admin-editable tiers & limits, 14-day trial (3 searches, contacts locked server-side) | §6, TIER-01/02 |
| Investor search & filters, researched profiles, fit score with reasons, similar investors, "who invested in X" | §8, §11.2, §11.3, SRCH-01/03 |
| Contact reveal with credits, rate limits, honeypots, data-access audit trail, CSV export of own funnel only | ASP-01/02/03/05/10 |
| Investor funnel: board with drag-and-drop, mobile stage list with one-tap "Move stage" / "Contacted", table view | §10.1–10.3 |
| **Import an existing tracker (.xlsx/.csv)**: header-row detection, column auto-mapping, dedupe, links to database investors | §10.6 |
| Notes → reminders and suggested stage/status/referrer changes; call date → prep reminder | AGT-06, §10.4 |
| Notifications, reminders (09:00 user time), daily brief on Home | §10.5, AGT-02, TZ-04 |
| 3-email sequences from stored facts only, with sources, linter, signature gate, investor-timezone scheduling | §9.3, SEQ-02/05/06/08, TZ-02 |
| WhatsApp / LinkedIn nudge generator | SEQ-07 |
| Company profile + deck PDF text extraction, agent instructions, exclusion list | DECK-01, AGT-01, SEQ-06 |
| Admin: overview, users (suspend, tier, trial), packages, Error Center → tasks, task board, removal requests, audit log | §15, §16, §18.3 |
| Public: landing page, legal pages, investor removal/update form, robots.txt, sitemap.xml, llms.txt | §19.5, §20.10, DATA-04 |

Not yet built (next phases): Gmail OAuth sending and reply detection, open tracking, LLM drafting and agent
chat, learning loop, data rooms, IR newsletters, Stripe, SEO engine.

## Run locally

Prereqs: Python 3.12+, Node 22, PostgreSQL 16 (or Docker).

```bash
# 1. Database
createdb easyfundraise            # or: docker compose -f infra/docker-compose.yml up db

# 2. API
cd apps/api
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env              # set EF_ADMIN_EMAILS=you@example.com
alembic upgrade head
python -m app.cli seed
python -m app.cli import-investors --directory ../../data/private/ALL_investors_merged.csv \
                                   --enrichment ../../data/private/enriched_master.jsonl
#   (no dataset? python -m app.cli demo-investors --count 200)
uvicorn app.main:app --reload --port 8000
python -m app.worker              # separate terminal: fires reminders

# 3. Web
cd apps/web && npm install && npm run dev   # http://localhost:3000
```

Or everything in Docker: `docker compose -f infra/docker-compose.yml up --build`.

The importer is idempotent: re-run it whenever the datasets grow. Removed investors stay suppressed.

### Google sign-in

Create an OAuth client (Web) in Google Cloud, add `<EF_WEB_ORIGIN>/api/auth/google/callback` as a redirect
URI, and set `EF_GOOGLE_CLIENT_ID` / `EF_GOOGLE_CLIENT_SECRET`. Dev sign-in is always disabled when `EF_ENV=prod`.

## Tests

```bash
cd apps/api && createdb easyfundraise_test && pytest     # 32 tests: tiers, gating, isolation, funnel, import, outreach
cd apps/web && npx tsc --noEmit && npm run build
```

CI runs both on every PR (`.github/workflows/ci.yml`).
