# Investor Intelligence App — Build Brief & Data Handoff

_Prepared 2026-10-30. Hand this file, plus the three data files listed in §3, to the build agent._

## 1. What we're building

A better version of Round Funded: a web app that helps a founder raise money by (a) finding the investors that fit their startup, (b) understanding what each investor actually brings, and (c) letting AI draft a highly personalized cold-outreach sequence (email 1 / 2 / 3) per investor.

Target capabilities the data is designed to support:
1. **Browse & search** a directory of ~15k investors with filters: sector/industry, stage, check size, geography, contactability (email/LinkedIn), and an **"active in last 12 months"** flag.
2. **Deck → matching investors.** Founder uploads a deck; app extracts sector/stage/geo/check need and ranks investors by fit (use `focus_sectors`, `focus_stages`, `geography_focus`, `typical_check_size`, `industries`).
3. **Similar investors.** On an investor profile, show others like them (same sector practice / stage / thesis). Precompute similarity from `focus_sectors` + `industries` + `firm_type` + `focus_stages`.
4. **AI outreach generator.** For a chosen investor, generate email 1/2/3 from `personalization_hooks`, `best_email_angle`, `investment_thesis`, `recent_news`, `notable_portfolio`, and the founder's deck. The enrichment schema was built specifically to feed this.
5. **Value-add & decision signals.** Surface `value_add`, `decision_speed`, `investments_per_year_estimate`, `instrument_preference` (SAFE vs priced equity), `leads_rounds` so a founder knows what an investor offers and how they operate.

## 2. Two datasets (join them)

There are two layers. **Join key: `linkedin` URL** (present on 100% of directory rows and copied into enrichment via `wid`). Fallback join: normalized `name` + `email`.

### 2a. Directory (scraped) — `ALL_investors_merged.csv`
- **14,853 unique investors** (one row each; `industries` is comma-separated because an investor appears under multiple industries). 14,374 have an email, 14,853 a LinkedIn, 10,353 a photo.
- This is the breadth layer: contact + social + basic classification for the whole base.
- NOTE: the scrape is still running (~31 of 46 industries done); this file grows. Treat it as a refreshable snapshot.

Columns: `name, title, company, industries, industry_count, stages, location, email, linkedin, x, facebook, portfolio_sample, more_portfolio, check_size, photo_url`

### 2b. Enrichment (web-researched) — `Investor_enrichment.csv` + `enriched_master.jsonl`
- **394 investors enriched so far**, growing in waves toward ~1,833 (prioritized: healthcare, digital health, biotech/medtech, AI, wellness first). The `.jsonl` is the durable source of truth (one JSON object per line); the `.csv` is a flattened view (list/dict fields joined with `;` or ` || `).
- This is the depth layer: the research that powers matching, similarity, and AI email generation.
- Of the 394: identity_confidence high 354 / medium 30 / low 10; active_last_12mo yes 41 / no 11 / unknown 342.

Columns (29): `wid, name, identity_confidence, current_firm, firm_website, firm_type, role_at_firm, about, investment_thesis, focus_sectors, focus_stages, geography_focus, typical_check_size, fund_size_or_aum, leads_rounds, instrument_preference, investments_per_year_estimate, decision_speed, notable_portfolio, recent_investments_12mo, last_known_investment_date, active_last_12mo, value_add, recent_news, public_content, personalization_hooks, best_email_angle, sources, notes`

Field notes for the build agent:
- `recent_investments_12mo` — list of `{company, date, round, role, source_url}` (in JSONL; ` || `-joined JSON in CSV).
- `recent_news`, `public_content` — lists of `{headline/title, date, source, url, summary/key_point}`.
- `personalization_hooks` — array of short factual hooks → the primary raw material for email personalization.
- `active_last_12mo` — `"yes"` only when a dated deal within 12 months was verified; `"unknown"` is common and does NOT mean inactive (see §4).
- `sources` — URLs actually used; keep for citation/verification in the UI.

## 3. Files in this handoff
1. `BUILD_BRIEF.md` (this file)
2. `ALL_investors_merged.csv` — directory, 14,853 rows
3. `Investor_enrichment.csv` — enrichment flat view, 394 rows (growing)
4. `enriched_master.jsonl` — enrichment source of truth (nested fields intact)
5. `schema.json` — machine-readable field dictionary for both datasets

## 4. Data-quality findings the app MUST handle

These came up in nearly every enrichment batch and directly affect product correctness:

- **Round Funded's own stage/check/sector tags are frequently wrong.** Many investors tagged "Seed / $500K–$2M" are actually large-cap PE / buyout / growth-equity firms (e.g. Leonard Green, Stone Point, TSG, Francisco Partners), or non-investing roles (CFOs, Heads of IR/Talent, board members, wealth-manager RIAs, family offices). **Do not trust the directory's `stages`/`check_size` for fit matching.** Prefer the enrichment `firm_type`, `focus_stages`, `typical_check_size`. The `notes` field flags each mismatch.
- **Recommend a "seed_fit" / investor-type filter.** Before showing an investor as a seed/pre-seed match, check `firm_type` (angel / operator-angel / seed VC vs PE/buyout/growth/CVC/family-office/wealth-manager) and `role_at_firm` (decision-making partner vs operations/finance/IR). The pilot used a `seed_fit` flag; reintroduce it as a computed column.
- **`active_last_12mo = unknown` is the norm, not "inactive."** Individual dated deals are rarely public. Use it as a positive signal when `yes`; don't filter out `unknown`.
- **Identity confidence varies.** Respect `identity_confidence`; show a "needs verification" badge for `medium`/`low`, and never present `low`/stub rows as researched.
- **Company vs real vehicle.** The directory `company`/email domain often differs from the actual investing vehicle (`current_firm`). Email domains frequently reveal the real fund — useful, but reconcile against `current_firm`.
- **Photos:** `photo_url` present for ~70%; company-logo placeholders were already stripped (blank when not a real headshot).
- **Dedup:** done on `linkedin` (fallback name+email). Keep that key in the app DB.

## 5. Suggested data model (starting point)
- `investors` (one row per person, PK = `investor_id`; store `linkedin` as unique key): all directory fields + a `enriched` boolean.
- `investor_enrichment` (1:1 with investors, FK `investor_id`): the 29 enrichment fields; nested fields (`recent_investments_12mo`, `recent_news`, `public_content`, `personalization_hooks`, `sources`) as JSON columns.
- `investor_industries` (many-to-many) for fast sector filtering (split the comma-separated `industries`).
- Computed/derived: `seed_fit` (bool), `investor_type` (normalized from `firm_type`), `similarity_vector` (from sectors+stage+thesis embeddings).
- Ingestion: load `enriched_master.jsonl` (authoritative) for enriched rows; `ALL_investors_merged.csv` for the rest. Re-ingest periodically — both files are still growing.

## 6. Current status (as of handoff)
- Directory scrape: 14,853 unique across 31/46 industries; still running (remaining incl. FoodTech, Food & Beverage, AgTech, Gaming, Media, Sports, Marketplace, Marketing, HR, Travel, Social, Impact, GovTech, LegalTech, Telecom). Final count will be higher.
- Enrichment: 394/1,833 done, running in waves, healthcare/digital-health/AI/wellness prioritized. Expect the enrichment file to keep growing — build ingestion to be re-runnable.

## 7. Guardrails to carry into the app
- Enrichment is professional/investing info only (no personal-life data); keep it that way in any further scraping/enrichment.
- Every deal/news item is sourced (`sources`); never let the AI generator invent deals, dates, or quotes — ground email claims in the stored fields only.
- Contact data is for the founder's own outreach; don't expose bulk contact export in ways that violate the source platform's terms.
