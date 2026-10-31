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
| **Gmail sending** from the founder's own mailbox: progressive consent, encrypted tokens, threaded follow-ups, warm-up ramp, per-domain cap, pacing, bounce/opt-out handling | GML-01..05, SEQ-09 |
| **Reply detection** and classification (positive, pass, opt-out, out-of-office, deck request) that stops the sequence and moves the card | GML-03, AGT-03 |
| Open tracking (with proxy/prefetch filtering) and an Outreach page with reply rates by email, hook and approach | TRK-01..03 |
| **Claude agent**: grounded drafting with fact ids and lint, chat that searches and proposes changes you apply with a tap, memory, meeting briefs, morning brief, positioning advice, feedback | AGT-01..08, §9.4 |
| **Data room** at `/r/<slug>`: editor, access modes (public / email / password / personal link), gated documents, per-viewer section analytics, version history, noindex by default | §14, DR-01..05 |
| **Round updates** (first close, lead secured, oversubscribed, closing Friday) naming only backers who agreed, and **investor updates** with engagement | §9.5, FOMO-01..03, §12 |
| Team invites and roles, multiple workspaces, signed-in devices, admin two-factor, Stripe Checkout / portal / webhooks | AUTH-05..08, §6.3 |

Not built yet: transactional email (invites and digests are shared as links / shown in-app), Gmail Pub/Sub push
(replies are polled every few minutes), Google Calendar, Postgres row-level security, live web research in
briefs (they use stored data), S3 for documents (stored in Postgres), SEO engine.

### Turning on the paid integrations

| Feature | Set |
|---|---|
| Claude drafting, chat, briefs | `ANTHROPIC_API_KEY` (and `EF_AI_ENABLED=true`, the default). Without it everything falls back to templates. |
| Gmail | Enable the Gmail API on the same Google OAuth client and add `<EF_WEB_ORIGIN>/api/gmail/callback` as a redirect URI. `EF_GMAIL_MODE=fake` gives a test mailbox in dev. |
| Open tracking | `EF_TRACKING_BASE_URL` (public URL of the API) |
| Token encryption | `EF_TOKEN_KEY` (32-byte base64). Required in prod. |
| Stripe | `EF_STRIPE_SECRET_KEY`, `EF_STRIPE_WEBHOOK_SECRET`, then paste price ids per plan in Admin → Packages |

## Run with Docker (easiest)

Needs only [Docker Desktop](https://www.docker.com/products/docker-desktop/).

```bash
cp apps/api/.env.example apps/api/.env      # add ANTHROPIC_API_KEY and EF_ADMIN_EMAILS=you@example.com
docker compose -f infra/docker-compose.yml up -d --build
docker compose -f infra/docker-compose.yml exec api python -m app.cli demo-investors --count 200
open http://localhost:3000                  # use "Sign in with email (dev)"
```

This starts Postgres, the API, the worker (sending, replies, reminders, briefs) and the web app. Stop with
`docker compose -f infra/docker-compose.yml down` (add `-v` to wipe the database).

## Run locally without Docker

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
python -m app.worker              # separate terminal: reminders, sending, replies, briefs

# 3. Web
cd apps/web && npm install && npm run dev   # http://localhost:3000
```

The importer is idempotent: re-run it whenever the datasets grow. Removed investors stay suppressed.

### Google sign-in and Gmail sending (use your real account)

Sign-up asks for Gmail permission on the same Google screen, so founders connect their mailbox in one step.
Nothing is sent until the founder confirms each sequence (who, from which address, and when).

1. In [Google Cloud Console](https://console.cloud.google.com/) create a project, then **APIs & Services → Library**
   and enable the **Gmail API**.
2. **OAuth consent screen**: External, app name EasyFundraise, your support email. Add the scopes
   `openid`, `email`, `profile`, `gmail.send` and `gmail.readonly`. While the app is in **Testing**, add your own
   Gmail under **Test users** (up to 100 testers work without Google's review).
3. **Credentials → Create credentials → OAuth client ID → Web application**. Add both redirect URIs, using the port
   you open the app on (for example 3001):
   - `http://localhost:3001/api/auth/google/callback`
   - `http://localhost:3001/api/gmail/callback`
4. Put the keys in `apps/api/.env` and switch Gmail from the fake mailbox to the real one:
   ```
   EF_GOOGLE_CLIENT_ID=....apps.googleusercontent.com
   EF_GOOGLE_CLIENT_SECRET=...
   EF_GMAIL_MODE=google
   ```
5. `docker compose -f infra/docker-compose.yml up -d --build`, open the app and press **Continue with Google**.

Going live for everyone: `gmail.readonly` (used only to spot investor replies) is a restricted scope, so Google
asks for app verification and an annual security assessment before you leave Testing. `gmail.send` alone is a
sensitive scope and only needs verification. Dev sign-in is always off when `EF_ENV=prod`.

### Email sign-in links

"Continue with email" sends a 15-minute magic link. Set `EF_SMTP_HOST`, `EF_SMTP_PORT`, `EF_SMTP_USER`,
`EF_SMTP_PASSWORD` and `EF_SMTP_FROM` (any SMTP provider: Postmark, Resend, SES, or Gmail with an app password).
Without SMTP, development shows the link on screen and production hides email sign-in.

Users can also add a password in Settings → Sign-in & password (Google and Gmail stay connected). After a correct
password we email a 6-digit one-time code that works once, for 10 minutes; five wrong tries burn it. The code step is on
only when `EF_ENV=prod` (it needs SMTP there); dev and UAT sign in with the password alone. `EF_PASSWORD_OTP=true|false`
forces it on or off.
## Tests

```bash
cd apps/api && createdb easyfundraise_test && pytest     # 61 tests: tiers, isolation, funnel, import, Gmail, sign-in, agent, data room, updates, billing, SEO
cd apps/web && npx tsc --noEmit && npm run build
```

CI runs both on every PR (`.github/workflows/ci.yml`).
