# EasyFundraise — Product & Engineering Specification

**Domain:** easyfundraise.com (prod) · uat.easyfundraise.com · dev.easyfundraise.com
**Document purpose:** Single source of truth for an AI engineering team to build, test, ship and operate the EasyFundraise SaaS platform end-to-end. Written to be uploaded into Claude (or any coding agent) as the master build brief.
**Version:** 1.0 · 2026-10-30
**Companion data handoff:** `BUILD_BRIEF.md`, `schema.json`, `ALL_investors_merged.csv`, `Investor_enrichment.csv`, `enriched_master.jsonl` (see §22).

---

## 0. How to use this document

1. Read §1–§4 first (vision, principles, stack, architecture). Everything else depends on them.
2. The build is executed by role-specific AI agents (§17). Each agent reads its own operating manual plus the sections it owns.
3. Every requirement has an ID (e.g. `AUTH-03`). Tasks, tests and PRs must reference IDs.
4. Where this document says **MUST**, it is a hard requirement. **SHOULD** is strongly preferred. **MAY** is optional.
5. Anything not specified: choose the simplest option that satisfies the Ponytail ladder (§3.2) and record the decision in `docs/decisions/ADR-nnn.md`.

---

## 1. Product vision

### 1.1 One-line
**EasyFundraise is the agentic workspace for raising capital: find the right investors, reach them with precise personalised emails, track every conversation in a fundraising-native CRM, and let a personal AI agent run the process with you.**

### 1.2 What we are replacing
- **Round Funded** (investor database + outreach) — we are a strict superset with better data quality, a real CRM, per-user learning agents, and an investor-relations layer.
- **Notion / Excel / Airtable trackers** — founders today track investors in spreadsheets. We give them a purpose-built, drag-and-drop fundraising funnel that the AI keeps updated.
- **Generic cold-email tools** — we are not mass mail. We send ≤20 precise, individually personalised emails per user per day, from the founder's own Gmail, threaded correctly, with learning.

### 1.3 Positioning rules (must be reflected in UI copy, SEO and onboarding)
- Never describe the product as "an investor database" or "email automation". It is *everything a founder needs to find investors, contact them, manage relationships and raise capital, powered by AI.*
- The product should **feel agentic**: the founder has a named personal agent that proposes, drafts, researches, reminds and learns. The UI surfaces the agent's reasoning and next-best-actions, not just forms.
- Precision over volume. Short emails. Momentum and FOMO mechanics (§9.8) are first-class.

### 1.4 Target users
- **Primary:** Founders raising angel / pre-seed / seed rounds ($100K–$5M), solo or small teams, non-technical to technical, global (US, UK, EU, India, SEA first).
- **Secondary:** Fractional CFOs / fundraising consultants managing several founders (multi-workspace, Pro+).
- **Admin:** EasyFundraise operators (product owner, support) using the Admin Portal (§15) and the Agent Task Dashboard (§16).

### 1.5 Success metrics (instrumented from day one)
| Metric | Definition | Target (90 days post-launch) |
|---|---|---|
| Activation | User uploads deck AND sends first email within 48h of signup | ≥ 40% |
| Weekly return | Users with ≥1 session/week after week 1 | ≥ 55% |
| Open rate | Pixel-tracked opens / delivered | ≥ 45% (vs industry ~25%) |
| Reply rate | Detected replies / delivered | ≥ 8% |
| Positive reply rate | Replies classified positive / delivered | ≥ 3% |
| Trial → paid | Paid within 14 days of trial start | ≥ 6% |
| Spam complaint rate | Complaints / delivered | < 0.1% |
| Agent token cost / active user / month | All LLM spend attributable | Basic ≤ $0.40 · Pro ≤ $2.50 · Top ≤ $8 |

---

## 2. Brand

### 2.1 Name & domain
EasyFundraise · easyfundraise.com. Brand voice: direct, confident, founder-to-founder, zero fluff. We speak like an operator who has raised before.

### 2.2 Logo
A simple, scalable wordmark + mark is provided as `brand/easyfundraise-logo.svg` (and `-mark.svg` for favicon/app icon). Concept: an upward "raise" arrow formed by three stacked chevrons (the three-email sequence / funnel stages) inside a rounded square; wordmark in a geometric sans (Inter / Geist). Primary colour **#0F62FE** (signal blue), accent **#16A34A** (committed green), ink **#0B1220**, surface **#F6F8FB**. Dark mode: surface **#0B1220**, ink **#E6EAF2**. The mark must work at 16px (favicon) and as a monochrome glyph.

### 2.3 Design system (frontend agent owns)
- Tokens: colour (above), 4px spacing grid, radius 8/12/16, Inter (UI) + JetBrains Mono (data), shadows soft, 200ms ease motion.
- Components: shadcn/ui on Tailwind v4 + Radix primitives; icons: Lucide. Kanban via `@dnd-kit`. Tables via TanStack Table. Charts via Recharts (dashboard) — all accessible (WCAG 2.2 AA), keyboard-operable, reduced-motion aware.
- Every screen has: loading skeleton, empty state with a next action, error state with a retry and a "report" link (§18), and a "what the agent is doing" strip where relevant.

---

## 3. Engineering principles

### 3.1 Non-negotiables
- **Security, privacy, compliance, scalability, robustness** are designed in, not bolted on (§19).
- **Latest, fast, easy to manage stack** (§4). Everything runs in Docker locally and in all environments.
- **Everything configurable by admin** (§15): tiers, limits, prompts, feature flags, schedules, copy, models.
- **Minimal token usage**: lower tiers run on our own deterministic engine + small models; LLM calls are cached, batched and templated (§13).
- **Automated tests for everything** (§18.2): unit, integration, e2e, contract, prompt-regression.
- **Errors are first-class data**: every error becomes an admin-visible event and, when actionable, an auto-created engineering task (§18.3).

### 3.2 Ponytail discipline (all engineering agents MUST install and follow)
Install the Ponytail skill (github.com/dietrichgebert/ponytail) in every coding agent at `full` intensity. Its core rule — *write as little code as the task needs* — is enforced via the ladder on every change:
1. Does this code need to exist? (Is there a library, a config, a platform feature, or an existing function?)
2. Read the relevant existing code before writing.
3. Can the change be smaller? Remove abstraction that serves one caller.
4. Write the minimum that works and is correct.
5. **Never cut:** validation at trust boundaries, data-loss handling, security controls, accessibility.
6. Add small tests for anything with branches, loops, parsers, money, dates/timezones, or security.
Run `/ponytail-review` on every PR diff and `/ponytail-audit` weekly; `/ponytail-debt` output feeds the Agent Task Dashboard as tech-debt tasks (§16). Mark deliberate shortcuts with `// shortcut: <reason>` so they are collected.

### 3.3 Definition of Done (every task)
- Requirement IDs referenced · tests added and green · lint/typecheck green · a11y check green on UI · no new `shortcut:` without a linked task · docs/ADR updated if behaviour changed · feature flag if user-visible · deployed to dev, verified by QA agent on uat (§16).

---

## 4. Tech stack & architecture

### 4.1 Stack (chosen for speed, maintainability and AI-agent friendliness)
| Layer | Choice | Notes |
|---|---|---|
| Frontend | **Next.js 15 (App Router, React 19, TypeScript)**, Tailwind v4, shadcn/ui, TanStack Query/Table, `@dnd-kit`, Zod | SSR for marketing/SEO pages; client app for dashboard. |
| Backend API | **Node 22 + TypeScript, Hono** (or NestJS if the team prefers structure) with **tRPC** for typed app APIs and **REST/OpenAPI** for public/admin/webhooks | One codebase, monorepo (Turborepo + pnpm). |
| AI service | **Python 3.12, FastAPI** — agent runtime, embeddings, deck parsing, scoring, learning jobs | Separate service so model/tooling iterate independently. |
| Database | **PostgreSQL 16 + pgvector** (primary), **Redis 7** (cache, rate limits, queues) | Row-Level Security for multi-tenancy. |
| Jobs / scheduling | **BullMQ** (Redis) for app jobs; **Temporal** optional for long-running agent workflows (if adopted, document why) | Timezone-aware schedulers (§9.6). |
| Search | Postgres full-text + pgvector for semantic; **Meilisearch** optional for faceted investor search | Start with Postgres; add Meili only if p95 > 300ms. |
| Email | **Gmail API (OAuth)** for sending/reading in the user's own mailbox; transactional via **Resend** | No shared sending domain for outreach — deliverability lives with the founder's Gmail. |
| Storage | **S3-compatible (Cloudflare R2 / MinIO in dev)** for decks, data-room assets, images | Signed URLs, virus scan on upload. |
| Auth | **Google OAuth (Sign in with Google)** only, via Auth.js v5; sessions in Postgres | Email is the identity; Gmail scopes requested progressively (§5). |
| Observability | OpenTelemetry → **Grafana/Tempo/Loki/Prometheus**; **Sentry** for errors | All errors mirror into Admin Error Center (§18.3). |
| Infra | **Docker Compose** (dev), **Kubernetes (k3s/EKS)** or Fly.io/Railway (prod) via Terraform; **Cloudflare** DNS/WAF/Turnstile | Three envs: dev, uat, prod. |
| CI/CD | **GitHub Actions**: lint → typecheck → unit → integration → e2e (Playwright) → build images → deploy dev → QA agent gate → promote uat → manual approve → prod | Preview envs per PR. |
| LLMs | Provider-agnostic gateway (`ai-gateway` module) supporting Anthropic Claude (Haiku/Sonnet/Opus tiers), OpenAI, and local/open models via vLLM for the "own engine" tier | Model routing per tier (§13). |

### 4.2 Monorepo layout
```
easyfundraise/
  apps/web            # Next.js app (marketing + dashboard + admin)
  apps/api            # Hono/tRPC API
  apps/ai             # FastAPI agent runtime
  apps/worker         # BullMQ workers (email send, tracking, scoring, SEO jobs)
  packages/db         # Drizzle ORM schema, migrations, RLS policies
  packages/ui         # shared components/tokens
  packages/contracts  # Zod schemas / OpenAPI / shared types
  packages/config     # feature flags, tier config loader
  infra/              # docker-compose.*.yml, k8s/, terraform/
  docs/               # ADRs, runbooks, this spec, legal drafts
  brand/              # logo SVGs, tokens
  seo/                # SEO engine config + content store adapters
```

### 4.3 Environments & domains
| Env | URL | Data | Purpose |
|---|---|---|---|
| dev | dev.easyfundraise.com | synthetic + anonymised sample | engineers/agents; auto-deploy on merge to `main` |
| uat | uat.easyfundraise.com | masked prod snapshot | QA agent + product owner acceptance; `robots: noindex`, basic-auth/IP allowlist |
| prod | easyfundraise.com | real | customers |
Each env has isolated DB, Redis, buckets, OAuth client IDs, Gmail API project, and secrets (Doppler/1Password/SOPS). Non-prod sends email only to allowlisted addresses (MailHog in dev).

### 4.4 High-level architecture
```
[Browser/PWA] ──HTTPS/CF WAF──▶ [Next.js web] ──tRPC──▶ [API (Hono)] ──▶ [Postgres/pgvector]
                                              │                    ├──▶ [Redis: cache, ratelimit, BullMQ]
                                              │                    └──▶ [S3/R2]
                                              └──REST──▶ [AI service (FastAPI)] ──▶ [LLM gateway → Claude/OpenAI/vLLM]
[Worker] ◀── BullMQ jobs: send email (Gmail API), poll replies (Gmail watch/pubsub), tracking ingest,
             scoring, learning, scheduler, SEO engine, newsletter, reminders
[Admin Portal] (same Next app, /admin, RBAC) ──▶ config, tiers, users, reports, errors, agent tasks
[Agent Task Dashboard] ──▶ Idea→Validate→Approve→Engineer→QA→CI/CD pipeline (§16)
```
Multi-tenancy: every table has `workspace_id`; Postgres RLS enforces it; API sets `SET app.workspace_id` per request. Admin bypass is explicit and audited.

---

## 5. Authentication, identity & Gmail integration

### 5.1 Requirements
- **AUTH-01** Sign-in is **Google OAuth only**. The Google account email is the user identity and the sending mailbox. No password auth.
- **AUTH-02** Progressive consent: at signup request only `openid email profile`. Request Gmail scopes (`gmail.send`, `gmail.readonly` or `gmail.modify`, `gmail.metadata`) **only when the user first tries to send or enable reply tracking**, with a clear explainer of what we do and don't do (we never read unrelated mail; we only read threads we started or that reply to them).
- **AUTH-03** Store refresh tokens encrypted (AES-256-GCM, key in KMS/secret manager), never in logs. Token revocation handling: if Google revokes, pause all sends, notify the user, show a reconnect banner.
- **AUTH-04** Google verification: app must pass Google OAuth verification for restricted Gmail scopes (privacy policy, limited-use disclosure, security assessment if required). Build with the "Limited Use" policy in mind: Gmail data is used only to provide user-facing features.
- **AUTH-05** Signature: on first send, prompt the user to **set a signature** (import from Gmail settings if available, or compose). Signature is appended to every outreach email unless the user disables per-sequence. Ask again if empty at each new campaign (dismissible with "don't ask again").
- **AUTH-06** Workspaces: one user → N workspaces (one per raise/company). Invite collaborators (owner/editor/viewer). Consultants get multi-workspace switching on Pro+.
- **AUTH-07** Sessions: secure, httpOnly, SameSite=Lax; 30-day rolling; device list with revoke in Settings.
- **AUTH-08** Admin users: separate role, MFA required (TOTP/WebAuthn), IP allowlist optional, all actions audited (§15.7).

### 5.2 Gmail sending & threading
- **MAIL-01** All outreach is sent **from the user's Gmail via Gmail API** (`users.messages.send`) so it lands in Sent, inherits SPF/DKIM/DMARC of their domain, and replies come to their inbox.
- **MAIL-02** Follow-ups and replies **MUST thread from the original sent message**: reuse `threadId`, set `In-Reply-To` and `References` headers to the original `Message-ID`, and quote nothing (short follow-ups only). Never start a new thread for email 2/3.
- **MAIL-03** Reply detection via Gmail **watch + Pub/Sub** (preferred) with polling fallback (`history.list`). A reply is any message in a tracked thread not from the user. Classify (positive / neutral / negative / auto-reply / bounce) with the small model; positive replies auto-create/advance a funnel card (§10.6).
- **MAIL-04** Bounce handling: parse DSNs; mark investor email invalid in the workspace; suppress further sends; feed a global "email health" score (admin-visible, never exposed per-user beyond "invalid").
- **MAIL-05** Daily send cap **default 20/user/day** (admin-configurable per tier and per user), enforced server-side with Redis token bucket in the **user's timezone** day boundary. Soft warnings at 80%. Sequences automatically spread across days.
- **MAIL-06** Sends are paced (random 45–180s gaps), never bursts; no sends outside the user's configured send window (default 08:00–18:00 **recipient** local time, §9.6).
- **MAIL-07** Unsubscribe/opt-out: every email carries a plain-text opt-out line ("If this isn't relevant, reply 'no' and I won't follow up"); detected opt-outs suppress globally for that workspace and add to the exclusion list. List-Unsubscribe headers are added for any newsletter-type sends (§12).

---

## 6. Subscription tiers, pricing & trial (all admin-configurable)

### 6.1 Principles
- Tiers, prices, limits, features, model routing and copy live in a **`tier_config` table** editable in Admin → Packages (§15.3), versioned, with effective dates. No tier logic hardcoded.
- Payments: **Stripe** integration is stubbed behind a `BillingProvider` interface; v1 ships with manual/admin-granted plans and a "Request upgrade" flow. Stripe Checkout/Customer Portal wiring is a later task (`BILL-*`), but the data model (plans, subscriptions, invoices, entitlements) is built now.
- Entitlements are evaluated server-side via `can(workspace, feature)` and `limit(workspace, metric)`; UI reads the same evaluation to render locks.

### 6.2 Default tiers (seed values — admin can change)
| | **Free Trial** | **Starter** | **Pro** | **Investor Relations (Top)** |
|---|---|---|---|---|
| Price | $0 (14 days, no card) | $39/mo · $390/yr | $99/mo · $990/yr | $249/mo · $2,490/yr |
| Investor searches | **3 searches** total; results show name/firm/thesis summary; **emails & LinkedIn locked** (blurred with lock icon) | 300/mo | Unlimited (fair use) | Unlimited |
| Contact reveals | 0 (locked) | 150/mo | 600/mo | 1,500/mo |
| Outreach emails/day | 0 (can draft 3 sample emails, cannot send) | 20 | 20 (admin may raise to 30) | 20 (+ newsletter channel) |
| AI engine | Own engine (templates + small model) | Own engine + small model | Frontier model for drafting & agent | Frontier model + deep research |
| Deck analysis | 1 (summary only) | Full | Full + re-analysis on edits | Full + investor-fit narrative |
| Personal Super Agent | Read-only suggestions | Basic (daily digest, reminders) | Full (instructions, proactive research, dynamic similar investors) | Full + IR agent |
| Funnel/CRM | Full (manual entries) | Full | Full + automations | Full + automations |
| Data room page | — | 1 | 3 | 10 + custom domain |
| Investor newsletter & update tracking | — | — | — | ✔ (§12) |
| Workspaces | 1 | 1 | 3 | 10 |
| Seats | 1 | 1 | 3 | 10 |
| Support | Community | Email | Priority | Priority + onboarding call |

Rules:
- **TIER-01** Trial converts to a read-only "Expired" state (data retained 90 days) — never delete the funnel.
- **TIER-02** Locked content is **rendered server-side as locked** (no real email in the DOM/HTML). Blur is cosmetic; the data never leaves the server.
- **TIER-03** Upgrade prompts are contextual (e.g. clicking a locked email) — never modal-spam. Max one upsell nudge per session.
- **TIER-04** Annual = 2 months free. Coupons/discounts admin-managed. Founder-friendly "pause subscription" option.
- **TIER-05** Fair-use on "unlimited": soft cap 5,000 searches/mo, then rate-limited, admin alerted.

---

## 7. Anti-scraping, anti-bot & data protection

The investor database is our core asset. Design assumes adversarial users and bots.

- **ASP-01 Server-side gating.** Contact fields (email, phone, LinkedIn) are never included in list/search responses. They are fetched one-at-a-time via `POST /investors/:id/reveal`, which checks entitlement, decrements credits, logs the reveal, and returns the value. Revealed values are cached per-workspace (re-reveal is free) but still never in list payloads.
- **ASP-02 Rate limits (Redis, sliding window):** search 60/min & 600/hr per user; reveal 30/min & tier monthly cap; profile view 120/min; API-wide 1,000/min per IP; anomaly → step-up (Turnstile) → temporary lock → admin alert.
- **ASP-03 Pagination limits:** max page size 25; no "export all"; CSV export only of the user's **own funnel** (their data), never of search results. Watermark exports with workspace id.
- **ASP-04 Bot detection:** Cloudflare WAF + Bot Management/Turnstile on auth and search; device fingerprint (FingerprintJS open source) + behavioural signals (no mouse/keyboard events, linear scroll, constant inter-request timing, headless UA). Score stored per session; high score → shadow-limited results (same shape, randomised subset) + admin alert.
- **ASP-05 Honeypots:** hidden investor records with unique synthetic emails per workspace. Any email sent to a honeypot or any reveal of one proves scraping → immediate suspension + evidence log.
- **ASP-06 Per-user data fingerprinting:** micro-variations in non-essential display fields (e.g. ordering of portfolio sample, whitespace in thesis summary) per workspace so leaked dumps are attributable.
- **ASP-07 No public investor contact pages.** SEO investor pages (§20) show only firm-level, non-contact information.
- **ASP-08 Copy protection UX (soft):** disable text selection on contact cells, no right-click on data tables, `Cmd+A` guard — acknowledged as friction, not security; the real control is ASP-01/02.
- **ASP-09 Account hygiene:** one trial per Google identity + fingerprint + payment instrument; disposable-domain blocklist; suspicious signups flagged in Admin.
- **ASP-10 Audit:** every reveal/search/export is an immutable event (`data_access_events`) used for reports and abuse detection. Admin can see "top revealers" and velocity graphs.

---

## 8. Investor data layer

### 8.1 Sources & lineage
- Seed dataset: public-web scraped directory (~15k investors at handoff, 46 industries, dedup on LinkedIn) + web-researched enrichment (29 fields) — see `BUILD_BRIEF.md` / `schema.json` for exact schemas. Every record carries `source`, `source_url(s)`, `collected_at`, `enriched_at`, `identity_confidence`.
- Ongoing enrichment jobs (Pro/Top triggered or nightly for hot investors) write to `investor_enrichment_versions` — never overwrite; latest version is materialised.
- **DATA-01** Directory `stages` / `check_size` from the source are **unreliable**; the app MUST prefer enrichment `firm_type`, `focus_stages`, `typical_check_size`. Compute and store `seed_fit` (bool), `investor_type` (normalised), `is_decision_maker` (bool: partner/GP/angel vs CFO/IR/ops).
- **DATA-02** `active_last_12mo = unknown` must never be rendered as "inactive"; UI shows "Activity: verified recent deal" only when `yes`.
- **DATA-03** Identity confidence badge on profile; `low` records are hidden from recommendations unless the user searches explicitly.
- **DATA-04** Right-to-removal: public "Investor? Update or remove your profile" page; requests go to Admin queue; removal propagates in ≤72h and adds to a global suppression list (also blocks re-ingestion).
- **DATA-05** Every investor has an **internal engagement score** (§11.4) and derived flags (`responsive`, `ghosting_prone`, `fast_decider`), computed only from aggregated, anonymised cross-workspace signals — never exposing which founder contacted whom.

### 8.2 Investor profile (UI)
Header: photo (if real headshot), name, role, firm (+ real vehicle if differs), location, type badges (Angel / VC Partner / GP / Principal / Family Office / CVC / PE — flagged if not early-stage), activity badge, identity confidence, engagement score (Pro+).
Tabs: **Fit** (why/why-not for *this* workspace: sectors, stage, geography, check size, lead?, instrument) · **Thesis & Portfolio** · **Recent news & content** · **How to pitch** (personalisation hooks, best angle, decision speed, value-add) · **Similar investors** · **Activity in my funnel**.
Actions: Reveal contact (credits) · Add to funnel · Draft sequence · Ask agent about this investor · Report data issue (creates Admin task).

### 8.3 Search & discovery
- **SRCH-01** Filters: sector(s), stage, geography, check size, firm type, decision-maker only, active-only, leads rounds, instrument, has email/LinkedIn, engagement score band, "not yet contacted by me", "in my funnel".
- **SRCH-02** Semantic search over thesis/about/hooks via pgvector ("investors who like vertical SaaS for clinics in Europe").
- **SRCH-03** **Company lookup:** "Find all investors who invested in `<company name or URL>`" → resolves company (name normalisation + domain), searches `notable_portfolio`/`recent_investments` + a live web-check for Pro+, returns investors with the matching deal and **then** a "Similar investors ideal for you" panel (§11.3). Example: 5 investors found for *Company X* → each shows the deal evidence/source → similar-investor carousel ranked for the user's deck.
- **SRCH-04** Saved searches with alerts ("new investor matching this appears / becomes active").
- **SRCH-05** Trial: 3 searches lifetime; counter visible; results limited to 10 with locked contacts.

---

## 9. AI layer — the Personal Super Agent, deck intelligence & outreach engine

### 9.1 The Personal Super Agent (one per workspace)
Every workspace gets a named agent (user can rename; default "Raise"). It is the product's spine: proactive, instructable, learning, and scoped to the workspace's data.

- **AGT-01 Account-level instructions.** Settings → Agent → "Instructions for my agent": free text (e.g. "Only target US/UK, never pitch PE, mention our FDA clearance, keep emails under 90 words, don't contact anyone at Sequoia"). Stored as versioned `agent_instructions`; injected into every agent prompt as the top-priority system block after safety rules. Agent confirms understanding in a short summary and flags conflicts with tier limits.
- **AGT-02 Daily brief** (in-app + optional email, user TZ, default 08:00): replies to handle, follow-ups due today, investors going cold, new matches, learning insights ("Emails mentioning your pilot with X get 2.1× replies"), and 3 suggested actions with one-click execute.
- **AGT-03 Proactive suggestions** appear as cards on the Home and Funnel views: "Investor A opened 3× but didn't reply → send the WhatsApp nudge?", "4 investors similar to the ones replying — add them?", "You have a call with B tomorrow — here's a research brief."
- **AGT-04 Meeting prep research.** When a funnel card has a call date (stage 04+) or the user types "I'm meeting Jane from Firm on Thursday", the agent produces a **Meeting Brief**: who they are, thesis, recent deals/news, portfolio overlaps with the founder, likely questions, suggested asks, red flags, and talking points mapped to the deck. Pro+: live web research; Starter: from stored enrichment only.
- **AGT-05 Chat.** A side-panel chat with tools: search investors, company lookup, explain fit, draft/rewrite email, move/annotate funnel cards, schedule follow-ups, summarise a thread, create reminders, run a FOMO round-update (§9.8). Every tool action is previewed and requires a click to apply (no silent writes), except reminders.
- **AGT-06 Reacts to notes.** Any note on a funnel card is parsed: dates → reminders; "asked for deck" → stage 05 suggestion; "intro via Sam" → referrer field; "not now, Q2" → snooze + re-engage date; "ghosting" → status + scoring signal (§11.4).
- **AGT-07 Memory.** Per-workspace memory store (facts about the company, raise terms, investor preferences, what worked) — summarised, not raw transcripts; user can view/delete ("Agent memory" page).
- **AGT-08 Guardrails.** Never invents investors, deals, quotes or metrics; cites sources for research; never sends without the user's configured consent level (default: auto-send approved sequences, ask before new recipients); respects exclusions, daily caps, quiet hours and opt-outs; no personal-life data about investors.
- **AGT-09 Ryan-Breslow-style persona (configurable).** Default outreach persona models the high-velocity, momentum-driven founder playbook: run a **parallel process**, set **real deadlines**, lead with **traction and specifics**, keep messages **short and confident**, signal **scarcity truthfully** (allocation, closing date, committed names with permission), ask for a **clear next step**, follow up **relentlessly but gracefully**. Encode as a persona config (`persona: "momentum"`), with alternatives `warm-intro`, `technical-founder`, `humble-expert`. Persona affects tone, structure and hooks; never factual claims. (Do not attribute fabricated quotes to any real person; the style is described, not quoted.)

### 9.2 Deck & data-room intelligence
- **DECK-01** Upload PDF/PPTX/Google Slides export (≤50MB). Pipeline: virus scan → text + layout extraction (PyMuPDF / python-pptx) → slide classification (problem, solution, market, traction, team, ask, etc.) → structured **Company Profile** (sector tags, sub-sector, stage, geography, business model, traction metrics, round size, instrument, use of funds, team signals, defensibility) with confidence per field. User reviews/edits the profile; edits are learning signals.
- **DECK-02** Recommendations from the profile: (a) **Investors** ranked by fit score (§11.2) with reasons; (b) **Sector/stage positioning** advice ("Your deck reads as pre-seed health-AI; 62% of matched investors want ≥$10K MRR — consider leading with pilot LOIs"); (c) **Ticket guidance** (typical check sizes among matches, suggested round structure, lead vs follower mix); (d) **Gaps** in the deck vs what matched investors ask for.
- **DECK-03** Re-analysis on new upload; diff view ("what changed and how matches shifted").
- **DECK-04** Deck privacy: decks are private by default; the agent only shares facts from the deck in emails that the user has approved in the Company Profile ("shareable facts" toggle per field).

### 9.3 Outreach sequences (3 emails, precise and short)
- **SEQ-01** A sequence = 3 emails per investor: **E1 (hook)**, **E2 (new angle)**, **E3 (last touch)**. Each MUST be different in hook and content; E2/E3 are not "just checking in". Defaults: E1 day 0, E2 day 4, E3 day 10 (admin/user configurable; recommended range E2: 3–5 days, E3: 6–8 days after E2). Stops immediately on any reply.
- **SEQ-02** Length limits (enforced): E1 ≤ 120 words, E2 ≤ 80, E3 ≤ 60. Subject ≤ 7 words, no clickbait, no ALL CAPS, no emoji by default.
- **SEQ-03** Personalisation requirements per email (the engine must satisfy ≥2 for E1, ≥1 for E2/E3): a specific portfolio company or thesis line; a recent deal/news/content item (dated, sourced); a reason *this* investor fits *this* company (sector/stage/geo/check); a mutual signal (same accelerator, city, school) when verified; the investor's own language from `personalization_hooks`. Fallback to firm-level facts if person-level is thin; never fabricate.
- **SEQ-04** Hook library (E1/E2/E3 use different families): traction-first, insight-first ("one thing we learned…"), portfolio-adjacent, thesis-echo, social-proof (with permission), deadline/allocation, ask-for-advice (E3 only), breakup (E3 variant). The learning loop (§11.1) weights families per user.
- **SEQ-05** Draft → review flow: user sees all 3 drafts with highlighted personalisation facts and their sources; can **edit/overwrite any email**, regenerate with a different hook, change tone, or lock a sentence. "Approve & schedule" queues them under the cap and send window. **Default settings** (persona, timing, length, signature, send window, auto-approve) live in Settings → Outreach and can be changed anytime; per-sequence overrides allowed.
- **SEQ-06** Exclusions: Settings → Exclusion list (emails, domains, firm names, LinkedIn URLs; CSV import). The agent never drafts or sends to excluded targets and shows "excluded" on profiles. Also excludes anyone who opted out, bounced, or is marked Rejection.
- **SEQ-07** WhatsApp/SMS/LinkedIn follow-ups: for any funnel card, "Short message" generates a ≤40-word WhatsApp-style nudge (and a LinkedIn DM variant) for the founder to copy-send (we do not send WhatsApp). Logged as a contact event when the user marks "sent".
- **SEQ-08** Spam-free rules (enforced by a pre-send linter): no spam-trigger phrases, no link shorteners, max 1 link (data room or calendar), plain-text-first with light HTML, consistent From name, signature present, opt-out line, no attachments (link to data room), no identical bodies across recipients (similarity check < 0.75 cosine), no sends to role addresses (info@, press@) unless explicitly chosen, per-domain cap (≤3 recipients/firm/day), warm-up ramp for new Gmail accounts (5/day → 20/day over 10 days).

### 9.4 Email tracking
- **TRK-01 Open pixel:** 1×1 transparent GIF at `https://t.easyfundraise.com/o/<token>.gif` (dedicated tracking subdomain; signed, single-use-per-email tokens; no PII in URL). Ignore opens from the sender's own IP/UA and known proxy prefetchers (Apple MPP, Gmail image proxy counted once). Store first open, open count, approximate geo/time. Users can disable tracking per workspace (some jurisdictions/preferences).
- **TRK-02 Link tracking:** optional per-link wrap via `t.easyfundraise.com/c/<token>`; default off for outreach (deliverability), on for newsletters.
- **TRK-03 Reply tracking:** via Gmail thread monitoring (MAIL-03). Reply rate, time-to-reply, sentiment classification, and extraction of concrete signals (asked for deck / call / passed / referral / timing).
- **TRK-04 Dashboard:** per sequence/email/hook/persona/investor-type: delivered, opened, open rate, replied, reply rate, positive rate, meeting rate; cohort by day sent and send hour. Benchmarks shown as platform medians (anonymised).

### 9.5 Round updates & FOMO engine
- **FOMO-01** "Round update" composer: founder states commitments (amount, named leads with permission, % allocated, closing date), picks audience (all previously contacted / in-funnel at stages 02–07 / specific filter), **excludes named investors (a, b, c)**, and the agent drafts a short update per investor (personalised reference to their prior interaction: "You asked about enterprise pilots in April — we've since signed two"). Truthfulness check: amounts/names must come from funnel data flagged `shareable`.
- **FOMO-02** Sequencing: send to warmest first; stagger over the day; follow the daily cap; optional 1 follow-up.
- **FOMO-03** Templates: "First close done", "Lead secured", "Oversubscribed — final allocation", "Closing Friday". Persona `momentum` by default.

### 9.6 Scheduling & timezones
- **TZ-01** User timezone from browser on signup (editable). Daily caps, briefs, reminders and reports use the user TZ.
- **TZ-02** Investor timezone inferred from location (city/country → IANA tz) and stored on the investor; sends are scheduled into the **investor's** local send window (default Tue–Thu 08:30–11:30 and 13:30–16:30; Mon/Fri allowed with lower priority; never weekends unless user overrides).
- **TZ-03** Scheduler is a BullMQ delayed-job queue with per-user and per-domain pacing; jobs are idempotent and re-checked at send time (cap, opt-out, reply, exclusion, token validity).
- **TZ-04** Reminders/next-contact dates create notifications at 09:00 user TZ on the day, with "Do it now" (opens draft) / "Snooze".

### 9.7 Investor Relations tier features (Top)
See §12.

### 9.8 Agent transparency
Every agent-authored artefact (email, brief, suggestion) shows "Why I wrote this" (facts used + sources) and "Change the approach" (hook/persona/length). Users can rate 👍/👎 with reasons; these are learning signals.

---

## 10. Investor Tracker (fundraising-native CRM / funnel)

A Notion-quality tracker, purpose-built for raising. Works standalone (manual entries) and is auto-populated by the email engine.

### 10.1 Views
- **Board (Kanban)** by Stage with drag-and-drop between columns (`@dnd-kit`), multi-select drag, keyboard moves. Swimlanes optional (by Priority or Type).
- **Table** (TanStack): all fields, inline edit, sort/filter/group, column visibility, saved views, CSV export (own data only).
- **Timeline/Calendar**: next-contact dates, calls, closing dates.
- **Investor page**: full profile + interaction timeline (emails with open/reply status, notes, calls, files) + agent panel.

### 10.2 Card fields (all optional except name)
Name · Firm · **Investor type** (Angel, VC Partner, General Partner, Principal/Associate, Family Office, Corporate VC, PE/Growth, Junior/Analyst, Other) · **Priority** (P1–P4) · **Status** (Active, Inactive, Rejection, Ghosting) · **Stage** (01 Not started, 02 Intro requested, 03 In contact, 04 First call arranged → *prompts for call date/time*, 05 Deck requested, 06 Deep dive / DD, 07 Term sheet / Offer, 08 Signed, 09 Payment received) · **Can lead?** (Yes/No/Maybe) · **Ticket size** (expected) · **Agreed size** · **Instrument** (SAFE/Note/Equity) · **Contact method** (Email/LinkedIn/WhatsApp/SMS/Intro/In person) · **Referrer / who is introducing** · **Last contacted** (auto from events) · **Next contact date** (→ reminder) · **Investor timezone** · **Source** (Database / Manual / Import) · **Notes** (rich text, @mentions, timestamps) · **Tags** · **Files** · **Shareable** flags (for FOMO updates).

### 10.3 Status & colour semantics
- Status colours: Active = blue, Inactive = grey, Rejection = red, Ghosting = amber. Heat overlay: **Hot** (opened ≥2 or replied positive in 7d) = orange flame, **Warm**, **Cold** (no activity 14d) — filterable.
- Filters: status, stage, type, priority, heat, can-lead, referrer, tag, contact method, next-contact due, "needs action".

### 10.4 Automations (agent-driven; user can toggle each)
- Positive reply → create card if missing; move to **03 In contact** (or 05 if deck requested); set Last contacted; notify.
- No reply after E3 + 7 days → suggest **Ghosting** (user confirms) → scoring signal; optional re-engage in 30 days.
- Reply contains "pass/not a fit" → suggest **Rejection** with reason extracted.
- Call date set → calendar event (Google Calendar optional scope), meeting brief 24h before (AGT-04), post-call note prompt.
- Stage 07+ → prompts for terms; stage 09 → marks committed amount for FOMO updates.
- Next contact date passed with no action → "overdue" badge + daily brief item.

### 10.5 Notifications & reminders
In-app (bell + inbox), email digest (user TZ), optional browser push. Types: reply received, investor opened (hot), follow-up due, next-contact due/overdue, call tomorrow (brief ready), ghosting suggestion, new similar investors, daily cap reached, Gmail disconnected, sequence completed. All user-configurable; quiet hours respected.

### 10.6 Import & migration
CSV/Excel import with column mapping (we publish a template matching the "Excel tracker" most founders use); duplicate detection by email/LinkedIn; link imported rows to database investors when matched (enriching the card).

---

## 11. Learning, scoring & recommendations

### 11.1 Per-user learning loop (the agent gets better for *this* founder)
- Signals: opens, replies, reply sentiment, meeting booked, stage advances, user edits to drafts (diff features: shortened? removed hook? added metric?), 👍/👎, hook family, persona, subject style, send hour/day, investor type, sector match score, email length.
- Model: per-workspace **contextual bandit** (Thompson sampling) over hook family × persona × length bucket × send-slot, with platform-level priors (anonymised, aggregated) for cold start. Updated nightly and on each reply. Explanations surfaced in the daily brief.
- Draft generation conditions on the current best arm; exploration rate 15% (configurable). Never changes factual content, only strategy.

### 11.2 Investor fit score (per workspace)
`fit = w1·sector_match + w2·stage_match + w3·geo_match + w4·check_match + w5·thesis_similarity(embedding) + w6·decision_maker + w7·active_recent + w8·engagement_score − penalties(non_early_stage, low_identity_confidence, excluded)`; weights admin-tunable and learned per workspace from outcomes. Shown as 0–100 with top 3 reasons.

### 11.3 Similar investors (dynamic)
- Static similarity: embedding of (thesis + sectors + stage + geography + firm type) → nearest neighbours.
- **Dynamic**: as replies arrive, build a "responders profile" (centroid of investors who opened/replied/advanced) and re-rank similar investors toward it; surface "Investors like the ones responding to you" on Home and in the funnel sidebar. Also powers SRCH-03's "similar to those who invested in Company X".

### 11.4 Internal investor engagement score (platform-wide, anonymised)
For database investors, aggregate across workspaces: open rate, reply rate, positive-reply rate, time-to-reply, % reaching stage ≥04, ghosting rate (marked Ghosting after replying), rejection rate, and recency. Produce `engagement_score` (0–100) and flags. Used to recommend investors to other founders ("responsive to pre-seed health founders") and to de-prioritise chronic ghosters. **Privacy:** minimum n≥5 workspaces before any score is displayed; never show which founders contacted an investor; never expose to investors themselves beyond their own removal rights.

---

## 12. Investor Relations tier (newsletter & updates)
- **IR-01** Investor update composer (monthly/quarterly templates: metrics, wins, asks, hiring, runway) with the agent drafting from funnel + Company Profile + a short Q&A with the founder.
- **IR-02** Audiences: committed investors, pipeline, advisors, custom lists; per-recipient personalised intro line.
- **IR-03** Sending via Gmail (≤ cap) for small lists, or via Resend with the user's verified subdomain for larger lists (DKIM/SPF setup wizard); List-Unsubscribe; tracking (opens/clicks/replies).
- **IR-04** Tracking dashboard: who opened/clicked, questions received, engagement trend per investor, "investors going quiet".
- **IR-05** Update archive page in the data room (optional, access-controlled).

---

## 13. Token & cost optimisation (critical)
- **COST-01 Model routing by tier & task:** Trial/Starter: deterministic template engine (slot-filling from enrichment fields) + small model (Claude Haiku-class or an open 7–8B model on vLLM) for polishing/classification. Pro/Top: frontier model for E1 drafting, meeting briefs and chat; small model for E2/E3 polishing, classification, extraction.
- **COST-02 Caching:** investor "pitch dossier" (facts + hooks + sources) computed once per investor per 30 days and shared across workspaces; prompt caching for static system blocks; embedding cache; dedupe identical requests.
- **COST-03 Budgets:** per-workspace monthly token budget per tier with soft/hard limits; admin dashboard of spend by feature; alerts at 80%.
- **COST-04 Batching:** nightly jobs batch classification/scoring; drafts for a sequence generated in one call (3 emails) with structured output.
- **COST-05 Prompt hygiene:** short system prompts, structured JSON outputs, max_tokens caps, no chain-of-thought dumps stored, stop sequences, retries with backoff only on transient errors.
- **COST-06 Evaluation:** a prompt-regression suite (golden investors × decks) run in CI; quality gates (personalisation facts present, length limits, no fabrication detector pass) before any prompt change ships.

---

## 14. Data room (one-page "great deck" site)
- **DR-01** Each workspace can publish a data room at `easyfundraise.com/r/<slug>` (custom domain on Top). It is a single, beautiful, responsive page generated from the Company Profile + uploaded assets: hero (one-liner, round, ask), problem/solution, product (screenshots/video), traction (charts from entered metrics), market, team, use of funds, FAQs, documents (deck PDF, financial model, cap table — each individually gated), investor updates archive (IR tier), contact/calendar CTA.
- **DR-02** Access modes: public link, password, email-gated (viewer enters email → we log the view and match to funnel investors), or per-investor magic links (default for outreach). Expiry and revoke.
- **DR-03** Analytics: per-viewer views, time per section, document downloads → surfaced on the funnel card and in the daily brief ("Investor X spent 6 min on your financials").
- **DR-04** Editing: block editor (Notion-like) with templates; AI "polish this section"; version history.
- **DR-05** SEO: data rooms are `noindex` by default (private); public ones are indexable only if the user opts in.

---

## 15. Admin Portal (`/admin`, RBAC: owner, admin, support, analyst, finance)

Everything the product does is configurable here; no deploy needed to change business rules.

### 15.1 Users & workspaces
Search/filter users; view workspace(s), tier, usage (searches, reveals, sends, tokens), Gmail connection health, risk score; actions: grant/extend trial, change tier, add credits, suspend/unsuspend (with reason), impersonate (read-only, audited, user-notified), export user data (GDPR), delete (GDPR, with retention rules).

### 15.2 Pricing & packages
CRUD tiers (name, price monthly/annual, currency, limits, features, model routing, trial length, trial search count, visibility), coupons, grandfathering, effective-dated versions, A/B price tests (flag), tier comparison preview as users see it.

### 15.3 Platform configuration
Daily send cap defaults, pacing, send windows, sequence timings/length limits, hook library, personas, prompt templates (versioned, with diff & rollback), model routing table, feature flags (per tier/user/percentage), notification defaults, anti-abuse thresholds, SEO engine config (§20), legal document versions (§19.5), copy strings.

### 15.4 Reports
MRR/ARR (once billing live), signups, activation, retention cohorts, usage by feature, email performance (platform medians), investor data quality (coverage %, identity confidence, removal requests), abuse/anomalies, token cost by feature/tier/user, SEO report (§20.18), support SLAs. Export CSV; scheduled email reports.

### 15.5 Investor data admin
Browse/edit investor records, merge duplicates, process removal/update requests, run/queue enrichment, view engagement scores, manage honeypots, suppression lists, import new scrapes (with diff & approval).

### 15.6 Error Center (see §18.3)
Live feed of errors grouped by fingerprint, affected users, env; status (new → triaged → task created → fixed → verified); one-click "create engineering task"; auto-created tasks shown with their pipeline state.

### 15.7 Audit log
Immutable log of all admin actions and sensitive user actions (reveals, exports, impersonations, config changes) with actor, IP, before/after. Searchable; exportable; retained ≥ 2 years.

---

## 16. Agent Task Dashboard (the engineering operating system)

A custom admin dashboard (`/admin/engineering`) where AI agents and humans run the product's development lifecycle. Built on the same stack; tasks stored in Postgres; agents interact via an authenticated internal API + webhooks (GitHub).

### 16.1 Roles (AI agents) and their manuals
| Agent | Responsibility | Inputs | Outputs |
|---|---|---|---|
| **Idea Agent** | Continuously proposes features/improvements from: user feedback, support tickets, usage analytics, error patterns, SEO/competitor intel, this spec's backlog | analytics, feedback, error center, SEO reports | Idea tasks (problem, hypothesis, evidence, proposed solution, effort guess, metric to move) |
| **Validation Agent** | Validates ideas against market demand, user needs, competitor landscape, strategy fit and cost; scores and ranks | Idea tasks, web research, internal data | Validation report (score 0–100, risks, evidence links, recommend/decline) |
| **Human approval gate** | Admin approves/declines validated ideas and new features; sets priority | Validation reports | Approved tasks |
| **Engineer Agents** (Frontend, Backend, AI/Data, DevOps — separate agents) | Implement approved tasks following Ponytail; open PRs; write tests; update docs | Approved tasks, repo | PRs with tests, ADRs, migration notes |
| **QA Agent** | Reviews PRs, runs/extends test suites, exploratory testing on dev/uat (Playwright), a11y and perf checks, verifies acceptance criteria; approves or returns with defects | PRs, deployed dev/uat | QA report; defects as tasks |
| **DevOps Agent** | Owns CI/CD, environments, secrets rotation, backups, observability, cost; promotes builds | QA approvals | Deployments, runbooks, alerts |
| **SEO Agent** | §20 | config, analytics | content, technical fixes (as PRs or CMS writes) |

### 16.2 Pipeline & states
`Idea → Validated → Awaiting approval → Approved/Backlog → In development → In review (QA) → Ready for uat → UAT verified → Ready for prod → Released → Monitoring (7d) → Done` plus `Declined`, `Blocked`, `Reopened`. Bugs enter at **Approved** automatically when created from the Error Center with severity ≥ medium (admin can veto within 1h for high-risk areas: auth, billing, data access).

### 16.3 Initial build mode vs steady state
- **Phase A — Initial build (fully automated until launch):** this spec is decomposed into epics/tasks by the Engineer agents (one planning pass, human reviews the plan once). Agents execute end-to-end: dev → QA → uat → prod, with the only human gates being (1) plan approval, (2) prod promotion of auth/billing/data-access changes, (3) legal docs.
- **Phase B — Steady state (post-launch):** Idea → Validation → **manual approval** → Engineer → QA → CI/CD as above. Bugs bypass Idea/Validation.

### 16.4 Dashboard views
Kanban by state (drag to override), per-agent queues, SLA timers, cycle-time charts, PR links, test results, deployment status per env, token/cost per task, "needs human" inbox (approvals, blockers, risky changes), weekly engineering report auto-generated.

### 16.5 Task schema
`id, type (feature|improvement|bug|debt|seo|ops), title, description, requirement_ids[], source (idea|error|user|admin|ponytail-debt), severity, priority, validation_score, approvals[], assignee_agent, pr_urls[], env_status{dev,uat,prod}, acceptance_criteria[], test_evidence[], cost_tokens, timestamps`.

### 16.6 Guardrails for autonomous engineering
- Agents never merge to `main` without green CI and QA approval; prod deploys of sensitive areas need a human click.
- Secrets never in prompts/logs; agents use scoped tokens; every agent action is in the audit log.
- Rollback: every deploy is reversible in < 5 min (blue/green or versioned images + DB migrations that are backward compatible for one release).
- Budget caps per task and per day for agent tokens; exceeded → task paused + admin alert.

---

## 17. Engineering agents — operating manuals (short)

**All agents:** read §3, §4, your section(s), and the task; install Ponytail (`full`); work on a branch `task/<id>-<slug>`; small PRs (< 400 lines net where possible); conventional commits; reference requirement IDs; update tests/docs; never fabricate test results; ask for human input only when blocked by a decision with irreversible consequences.

**Frontend agent:** owns `apps/web`, `packages/ui`; implements screens from §8–§14 with the design system (§2.3); a11y + perf budgets (LCP < 2.5s, INP < 200ms, CLS < 0.1); Storybook for components; Playwright e2e for critical flows (signup→connect Gmail→deck→draft→schedule; funnel drag; admin tier edit).

**Backend agent:** owns `apps/api`, `packages/db`, `packages/contracts`; RLS multi-tenancy; entitlements; rate limiting; Gmail integration; scheduler; tracking endpoints; webhooks; OpenAPI; integration tests with Testcontainers (Postgres/Redis).

**AI/Data agent:** owns `apps/ai`, enrichment/scoring/learning jobs, prompt templates & evals, deck parsing, embeddings, token budgets; maintains the prompt-regression suite; documents model routing.

**DevOps agent:** owns `infra/`, CI/CD, environments, secrets, backups (daily PITR, tested restores monthly), observability, cost dashboards, WAF rules, DR runbook (RPO 15 min, RTO 2 h).

**QA agent:** owns test strategy; gates every PR; maintains e2e suites, contract tests, load tests (k6: 500 concurrent users, p95 API < 300ms), security tests (ZAP baseline, dependency audit), a11y (axe); verifies acceptance criteria on uat; files defects with repro steps.

---

## 18. Quality: error handling, testing, observability

### 18.1 Error handling standards
- API: RFC 9457 problem+json; stable error codes (`EF-AUTH-001`…); user-safe messages; correlation id in every response and UI error toast ("Something went wrong · ref 8f3a…").
- UI: error boundaries per route segment; retry with backoff; offline banner; optimistic updates with rollback; never lose user-typed content (drafts autosave every 5s to IndexedDB + server).
- Jobs: idempotent, retried with exponential backoff (max 5), dead-letter queue visible in Admin; partial-failure reports.
- External APIs (Gmail, LLM, Stripe): circuit breakers; graceful degradation (e.g. LLM down → template engine; Gmail down → queue and notify).
- Data: migrations backward-compatible; soft deletes; PITR backups.

### 18.2 Automated testing (mandatory)
Unit (Vitest/pytest, ≥ 85% on domain logic), integration (API + DB via Testcontainers), contract (Zod/OpenAPI), e2e (Playwright, critical paths + visual snapshots), prompt-regression (golden set), load (k6), security (ZAP, `pnpm audit`, Trivy on images), a11y (axe in e2e), migration tests. CI blocks merge on any failure. Flaky-test quarantine with auto-task.

### 18.3 Error → Admin → Agent pipeline
Sentry/OTel error (prod/uat) → `errors` table (fingerprint, count, users affected, first/last seen, env, stack, breadcrumbs) → Admin Error Center (§15.6). Rules engine: new fingerprint with ≥ 3 users or any severity=high → auto-create **bug task** (§16) with repro context → Engineer agent picks up → QA verifies on uat with a regression test → DevOps deploys → Error Center auto-marks "fixed, monitoring" and reopens if it recurs within 7 days. Admin can mute/merge fingerprints.

### 18.4 Observability
Traces for every request/job; RED metrics per endpoint; business metrics (sends, opens, replies, reveals) as Prometheus counters; dashboards per env; alerts: error rate, p95 latency, queue depth, Gmail token failures, send cap anomalies, LLM spend spikes, scraping anomalies.

---

## 19. Security, privacy, compliance

### 19.1 Security controls
OWASP ASVS L2 baseline; TLS 1.2+ everywhere; HSTS; CSP (nonce-based); SameSite cookies; CSRF on state-changing REST; input validation (Zod) at every boundary; output encoding; SSRF-safe fetchers (allowlist for research fetches); file upload scanning (ClamAV) + type sniffing + size limits; secrets in a manager, rotated quarterly; least-privilege DB roles; RLS; encrypted at rest (DB, buckets, backups) and field-level encryption for OAuth tokens and revealed contacts cache; dependency scanning; container hardening (non-root, read-only FS); WAF/rate limiting; admin MFA; security headers tested in CI; quarterly pentest task auto-scheduled; incident response runbook.

### 19.2 Privacy & data protection (GDPR/UK GDPR/CCPA-ready)
Lawful basis: legitimate interests for processing publicly available professional investor data (documented LIA), consent for user Gmail access, contract for service delivery. Data map & records of processing; DPA with sub-processors (Google, Anthropic/OpenAI, Cloudflare, Resend, hosting); data minimisation (professional info only, no personal-life data); retention schedule (tracking events 24 months, Gmail message bodies not stored beyond what's needed — store IDs + extracted signals + user-visible thread snapshot the user can purge); DSAR tooling (export/delete) for users **and** for investors (removal/update page, §8.1 DATA-04); cookie consent (essential-only by default for app; marketing consent for site analytics); children: 18+ only.

### 19.3 Email compliance
CAN-SPAM / PECR / GDPR for B2B outreach: identify sender, accurate subject, physical address in signature (user's), opt-out honoured within 24h, no deception; Gmail/Google API Limited Use compliance; newsletters require prior relationship/consent and List-Unsubscribe.

### 19.4 Scalability & robustness
Stateless API/web pods behind LB; horizontal autoscale; Postgres primary + read replica, pgbouncer; Redis cluster; queues with concurrency controls; CDN for static/public pages; p95 API < 300 ms, search < 500 ms at 10k investors × 50k users; backups + tested restores; chaos test on uat quarterly; feature flags for kill-switches (sending, tracking, agent).

### 19.5 Legal documents (drafts in `docs/legal/`; admin-versioned; shown at signup and changes)
Provide **Privacy Policy** and **Terms & Conditions** comparable in scope to Round Funded's, plus a **Data Sources & Investor Rights** page. They MUST state clearly:
- The investor directory is compiled from **publicly available professional sources** (firm websites, press, public profiles) and web research; we do not scrape private or logged-in data; investors may request update or removal at any time via a public form; we respond within 72 hours.
- What we access in the user's Google account (scopes), why, how long we keep it, and that we comply with the Google API Services User Data Policy, including Limited Use.
- Tracking pixels: what is collected, that users can disable it, and recipients' rights.
- Acceptable use: no spam, no bulk extraction, no reselling data; daily caps; account suspension for abuse; anti-scraping measures and honeypots disclosed generically.
- Subscriptions, trials, refunds, cancellations, pausing; data retention after cancellation (90 days export window); sub-processors list; international transfers (SCCs); governing law (configurable); contact for privacy requests; cookie policy.
Drafts are provided as starting points and MUST be reviewed by counsel before prod (human gate).

---

## 20. Autonomous SEO & Growth Agent (full specification)

This section incorporates the "EasyFundraise: Autonomous SEO & Growth Agent — Master System Instructions" in full and extends it with implementation requirements. The SEO engine is **multi-domain and configuration-driven**: EasyFundraise is the first tenant, not the identity of the engine (§20.19).

### 20.0 Role and mission
You are an autonomous, senior-level SEO strategist, technical SEO engineer, content researcher, editorial director, competitor-intelligence analyst and growth-optimisation agent responsible for continuously improving the organic presence of easyfundraise.com across Google, Bing and AI-powered discovery (ChatGPT, Perplexity, Gemini, Google AI Overviews, Copilot). Mission: make EasyFundraise the leading destination for founders who need to find angel/pre-seed/seed investors, contact them with personalised cold email, manage fundraising pipelines, automate follow-ups, prepare for investor meetings and manage investor relationships — and convert that visibility into paying customers. Operate autonomously for routine work; use approval gates for high-impact changes. Traffic alone is not success.

### 20.1 Understand the business
Core capabilities to reflect (never describe us as "just a database" or "email automation"): 12,000+ verified investor contacts; investor discovery/filtering; angel/pre-seed/seed targeting; investor research and thesis analysis; individualised AI-generated investor emails; automated campaigns and intelligent follow-ups; investor CRM/pipeline; reply and engagement tracking; notifications/alerts; a personal autonomous fundraising agent (Pro/Top). Value proposition: *everything founders need to find investors, contact them, manage relationships and raise capital, powered by AI.*

### 20.2 Objectives & KPIs
Rank for high-intent investor-discovery, angel/pre-seed/seed fundraising, and investor cold-email/outreach searches; build fundraising topical authority; attract founders actively preparing to raise; convert visitors to registrations and paid; grow AI-answer visibility; build a scalable organic engine. Measure: organic clicks, impressions, rankings, non-branded traffic, organic registrations, trial→paid, organic CAC, organic-attributed revenue, relevant backlinks, AI referral traffic.

### 20.3 Keyword research agent
Maintain a structured keyword database (table `seo_keywords`, per domain) from GSC, Keyword Planner, Trends, Bing WMT, Ahrefs/Semrush (if connected), autocomplete/related/PAA, competitor sites, Reddit/founder communities, SERPs and AI query patterns. Categories: commercial (investor database, fundraising software, investor CRM software, AI fundraising platform, investor outreach software…), transactional (find angel/pre-seed/seed investors, contact VC firms…), informational (how to raise…, how to cold email investors, how to get a VC meeting, follow up with investors…), long-tail (find investors for a pre-revenue startup / without connections, raise your first $500k, best cold email subject lines for VCs, how long to wait before following up…). For each keyword record: keyword, intent, est. volume, difficulty, geo relevance, commercial intent, competition, ranking opportunity, related keywords, recommended format, existing URL, priority score. **Never fabricate volume/difficulty/rank data.** Avoid multiple pages for identical intent.

### 20.4 Competitor intelligence
Monitor Round Funded and ≥5 other investor databases / fundraising tools / investor CRMs / fundraising resources: positioning, landing pages, blog, top topics, ranking keywords, clusters, internal linking, free tools/lead magnets, backlink opportunities, content gaps, weak/outdated pages, new content, positioning vs us. Maintain `seo_competitor_opportunities` with: what they rank for, why it matters, what they fail to explain, how we do better, target keyword/intent, which product feature/CTA to include. Never copy competitor content.

### 20.5 Content strategy & editorial calendar
Clusters: A Finding startup investors · B Angel fundraising · C Pre-seed · D Seed · E Cold emailing investors · F Outreach & follow-ups · G Investor CRM/pipeline · H Pitch decks & preparation · I Valuation & financial prep · J VC/angel research · K Fundraising automation & AI tools · L Founder mistakes & challenges. Each pillar has a comprehensive main resource plus supporting articles. Calendar driven by keyword opportunity, each item with: primary/secondary keywords, intent, audience, format, proposed URL, cluster, internal-link opportunities, product relevance, CTA, priority, status.

### 20.6 Article requirements
Genuinely useful, original, accurate, written for founders, demonstrating expertise. Structure: SEO title; compelling intro; the founder's problem; step-by-step guidance; examples; actionable recommendations; common mistakes; data/research; resources; FAQs; internal links; contextual product integration; clear CTA. One H1; logical H2/H3; descriptive URLs; natural keywords + semantic terms; short paragraphs; tables/bullets where useful; images/diagrams with alt text. Length follows intent — no padding. Before writing: review SERPs, read primary sources, review competitor coverage, find unanswered questions, verify stats, record source URLs/dates. **Never invent** fundraising statistics, investor activity, amounts, volumes, success stories, testimonials, product capabilities or investor relationships. Distinguish facts, estimates, opinions. "Human feeling": vary sentence rhythm, use first-person operator voice where appropriate, concrete examples, no filler phrases; run an AI-tell linter (banned phrases list, repetition check) before publishing.

### 20.7 Investor database SEO
Landing pages such as angel/pre-seed/seed investors in USA/UK/Europe; healthcare, AI, SaaS, fintech, climate investors; female-led-startup investors; emerging-market investors — **only** where data is accurate, current, useful and legally appropriate. Each indexable page must add meaningful original value (market context, how to approach, what these investors look for, firm-level highlights). **Never expose private records, personal contact details or subscription-only data.** Prevent thin/duplicated programmatic pages.

### 20.8 Programmatic SEO
Templates with structured data for `/investors/`, `/investors/angel-investors/`, `/investors/pre-seed-investors/`, `/investors/seed-investors/`, `/investors/ai-investors/`, `/investors/saas-investors/`, `/investors/healthcare-investors/`, `/resources/…`, `/tools/…`. Each page targets a distinct intent; no city/industry find-and-replace clones.

### 20.9 Free acquisition tools
Prioritise by demand, competition, effort and conversion: investor email generator; investor match finder; fundraising readiness assessment; fundraising target calculator; valuation calculator; runway calculator; investor outreach tracker; follow-up email generator; pitch deck checklist; investor CRM spreadsheet template. Tools are React islands on marketing pages, gated lightly (email for export), instrumented for conversion.

### 20.10 Technical SEO
Maintain `/robots.txt` (allow public crawling, reference sitemap, disallow `/app`, `/admin`, `/api`, auth routes — not as a security control), `/sitemap.xml` (+ index; canonical, indexable, 200-only URLs; auto-updated on publish/update/remove), `/llms.txt` (concise, AI-readable description of EasyFundraise, purpose, features, audience, key pages, resources, docs — optional aid, no ranking promise), canonicals, JSON-LD (Organization, WebSite, SoftwareApplication, Article/BlogPosting, BreadcrumbList, Person where appropriate, FAQPage only when eligible), breadcrumbs, OG/Twitter cards, descriptive URLs, correct status codes, mobile rendering, image optimisation, speed, Core Web Vitals (LCP/INP/CLS), internal link/redirect integrity, indexability/crawlability, i18n where relevant. Never add irrelevant schema or mark up invisible content. Usability over SEO text.

### 20.11 AI search optimisation
Content that answers questions directly, with descriptive headings, clear explanations, reliable citations, original research, examples, concise definitions, structured info and real product expertise. Consistent brand facts across channels. Monitor AI referrals/mentions where measurable. No promises of citations.

### 20.12 Internal linking agent
For each new article: link to relevant existing articles, pillars and product pages; find older articles that should link to it; natural anchors (no exact-match stuffing); detect orphans and irrelevant over-linking; build a connected path from problem → understanding → product.

### 20.13 Conversion optimisation
Every page has a relevant next step (find investors / explore 12,000+ contacts / generate your first investor email / manage your pipeline / automate follow-ups / discover best-fit investors). Match CTA to intent; no aggressive pop-ups; track organic visitors through registration, activation and paid per keyword cluster.

### 20.14 Autonomous publishing
CMS: headless content store in Postgres (`seo_pages`, `seo_articles`, versions, assets) rendered by Next.js ISR; publishing API (create/edit/metadata/internal links/images/dates/categories/tags/sitemap/verification). Quality gate before publish: originality & usefulness validated; facts/citations checked; intent matched; no duplicate targeting; metadata complete; headings valid; internal links checked; schema valid; product claims verified; technically accessible. **Auto-publish** routine, high-confidence educational content. **Human approval** for: legal/regulatory/financial claims, sensitive fundraising advice, investor endorsements, unverified statistics, public investor data changes, major architecture changes, risky redirects/indexing changes. Never publish fabricated claims.

### 20.15 Performance monitoring & learning engine
Integrate GSC + GA4 (+ Bing WMT, SEO data providers where available). Track rankings, impressions, clicks, CTR, position, indexed pages, queries, landing pages, registrations, conversion rates, backlinks, referrals, AI referrals. Persistent knowledge base (per domain): keyword history, competitor research, published articles, performance, experiments (success/failure), technical issues, conversion data, historical recommendations. Weekly analysis and reprioritisation (e.g. high impressions/low CTR → test title/description; positions 5–20 → assess intent/depth/links; traffic up/registrations flat → CTA/landing; cannibalisation → consolidate). Every automated content change keeps the previous version with rollback.

### 20.16 Notifications & reporting
Notify owner (Admin → SEO inbox + email) on: important ranking changes, significant traffic drops, deindexed key pages, critical technical issues, significant competitor content, new high-value opportunities, material conversion changes, high performers losing traffic, experiment results. Each notification: what happened, why it matters, data, recommended action, priority, intervention needed? Weekly SEO report and monthly growth report (format §20.18).

### 20.17 Autonomy & execution rules
Operate continuously; no permission needed for research, analysis, drafting, internal linking, low-risk optimisation; approval gates for high-impact changes. **Never:** buy or spam backlinks, keyword-stuff, cloak, create doorway pages, mass-produce low-value pages, copy competitors, invent stats/references, change URLs without redirect planning, delete indexed pages without impact analysis, expose private product/investor data. Follow search-engine spam policies; optimise for long-term trust. Backlinks: earn them via original research/data reports (e.g. anonymised "State of pre-seed outreach" from platform aggregates with n-thresholds), free tools, digital PR, expert quotes, partnerships, guest content where editorially appropriate; track outreach in a `seo_link_prospects` table; never automate paid placements.

### 20.18 Weekly report format
Executive summary (performance, major changes, wins, problems) · Keyword performance (gaining/losing, new opportunities, high-intent) · Content performance (best/under-performing, new, recommended updates) · Competitor intelligence · Technical SEO (issues, indexing health, performance) · Business performance (organic registrations, paid conversions, best converting pages, attributable revenue) · Next actions (top 5 with expected impact, priority, status).

### 20.19 Configurable multi-domain architecture
Core engine modules (reusable, no hardcoded fundraising terms/URLs): orchestrator, keyword research, competitor intelligence, content planning, content generation, technical SEO, internal linking, programmatic SEO, AI-search optimisation, analytics, notifications, learning/memory, CMS publishing. Per-domain configuration (`seo_domains`): domain, company, description, industry, products, audience, markets, languages, brand voice, primary keywords, competitors, conversion objectives, CTA preferences, CMS integration, analytics integrations, publishing permissions, quality rules. Strict per-domain isolation of content, keywords, analytics, competitor intel, learning history, permissions, settings.

### 20.20 First execution plan
Phase 1 Website audit (crawl, structure, indexable pages, technical SEO, robots/sitemap, metadata/canonicals, schema gaps, mobile, thin/duplicate pages → audit report). Phase 2 Market & competitor research (Round Funded + ≥5 others → opportunity report). Phase 3 Keyword research (≥500 opportunities clustered, intent, competition, prioritised, mapped; no cannibalisation; 500 is a research target not a page count). Phase 4 SEO architecture (hierarchy, missing landing pages, pillar strategy, blog architecture, internal linking, schema/technical standards, sitemap/robots/llms.txt). Phase 5 Content production (homepage, core product pages, investor landing pages, discovery content, cold-email guides, pre-seed/seed guides, software comparisons, free tools; first 10 priority articles). Phase 6 Autonomous operation (daily monitoring, keyword discovery, competitor intel, research, approved auto-publishing, weekly optimisation, notifications, learning).

### 20.21 Implementation requirements (engineering)
- `apps/worker` SEO jobs: daily crawl/audit (Lighthouse CI, link checker), GSC/GA4 sync, ranking fetch (via connected provider or GSC positions only — no scraping of Google), competitor watch (RSS/sitemap diffs), content pipeline (research → outline → draft → lint → quality gate → publish), internal-link suggestions, report generation.
- Marketing site in Next.js with ISR; blog at `/blog`, resources at `/resources`, tools at `/tools`, investors at `/investors`; `noindex` on app/admin/uat; per-env robots.
- Admin → SEO: domain config, keyword DB, calendar, approvals inbox, experiments, reports, rollback.
- Every published page records author ("EasyFundraise Team" + reviewer), sources, last-reviewed date; visible "Last updated".

---

## 21. Data model (core tables — Drizzle schema to mirror)
`users` · `workspaces` · `workspace_members` · `oauth_tokens` (encrypted) · `tiers` / `tier_versions` · `subscriptions` · `entitlements_cache` · `investors` · `investor_enrichment_versions` · `investor_contacts` (encrypted, reveal-gated) · `investor_scores` · `investor_removal_requests` · `honeypots` · `company_profiles` · `decks` / `deck_versions` · `data_rooms` / `data_room_blocks` / `data_room_views` · `funnel_cards` · `card_events` (notes, calls, stage changes) · `reminders` · `sequences` · `emails` (draft/scheduled/sent, thread ids, message ids) · `email_events` (open/click/reply/bounce/opt-out) · `exclusions` · `agent_instructions` · `agent_memory` · `agent_suggestions` · `learning_arms` / `learning_observations` · `newsletters` / `newsletter_recipients` / `newsletter_events` · `notifications` · `data_access_events` · `audit_log` · `errors` · `eng_tasks` / `eng_task_events` · `seo_domains` / `seo_keywords` / `seo_competitor_opportunities` / `seo_articles` / `seo_article_versions` / `seo_experiments` / `seo_reports` / `seo_link_prospects` · `feature_flags` · `config_kv` (versioned) · `legal_documents` / `legal_acceptances`.
All tenant tables carry `workspace_id` + RLS; all tables carry `created_at/updated_at/deleted_at`.

## 22. Seed data & migration
Load `enriched_master.jsonl` (authoritative) and `ALL_investors_merged.csv` via an idempotent importer (`pnpm db:seed:investors`) that: normalises fields, computes `seed_fit`/`investor_type`/`is_decision_maker`, infers timezone from location, creates embeddings, assigns honeypots, and records lineage. Re-runnable as the datasets grow (both are still being produced; see `BUILD_BRIEF.md`).

## 23. Build phases & milestones (initial automated build)
1. **Foundation (wk 1–2):** monorepo, Docker Compose, CI, envs, auth (Google), workspaces, RLS, design system, Admin shell, Error Center, Agent Task Dashboard MVP, investor import, basic search with locked contacts, tiers config, trial logic.
2. **Outreach core (wk 3–4):** Gmail connect + signature, deck upload & Company Profile, fit scoring, sequences (3 emails, template engine + model routing), exclusions, scheduler/timezones, send caps, tracking (pixel + replies), funnel with automations, notifications.
3. **Agent (wk 5–6):** Super Agent chat + instructions + daily brief + meeting briefs + company lookup/similar investors + learning loop + investor engagement scoring + FOMO updates + WhatsApp nudges.
4. **Data room, IR tier, Admin reports, legal pages, SEO engine Phases 1–4 (wk 7–8).**
5. **Hardening & launch (wk 9):** load/security/a11y tests, DR drill, docs, uat sign-off, prod launch; SEO Phase 5–6 begins; Phase B steady-state agent pipeline switches on.
Each milestone has acceptance criteria tied to requirement IDs and must pass the QA agent on uat.

## 24. Acceptance criteria (launch gate — all MUST be true)
Google-only signup works; Gmail connect with progressive scopes; signature prompt; trial = 3 searches with server-locked contacts; deck upload → Company Profile → ranked investors with reasons; 3-email personalised sequence drafted in < 60 s (Pro) / < 20 s (Starter template engine), editable, scheduled in investor TZ within caps; emails thread correctly from Sent; pixel opens and replies tracked; positive reply auto-creates/advances funnel card; funnel drag-and-drop with all fields, statuses, stages, colours, filters, reminders; exclusion list honoured; FOMO update with exclusions; company lookup → investors → similar; WhatsApp nudge; daily brief; agent instructions respected; meeting brief; anti-scraping limits/honeypots active; Admin can change tiers/limits/prompts without deploy; errors flow to Error Center and auto-create tasks; all tests green in CI; p95 targets met under load; legal pages live (counsel-reviewed); SEO technical files live; dev/uat/prod on Docker/K8s with rollback.

## 25. Appendix — companion files
`brand/easyfundraise-logo.svg`, `brand/easyfundraise-mark.svg` · `BUILD_BRIEF.md`, `schema.json`, data CSV/JSONL (investor datasets) · `docs/legal/privacy-policy.md`, `docs/legal/terms.md`, `docs/legal/data-sources-and-investor-rights.md` (drafts) · `seo/config/easyfundraise.json` (domain config seed).
