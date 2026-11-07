# SEO agent

The SEO agent keeps track of how well easyfundraise.com targets founders' searches in each region, watches
competitors, and lists what to improve next. It runs automatically every Monday at 06:00 UTC
(`.github/workflows/seo-agent.yml`) and opens or updates one pull request, **SEO agent: weekly report**.
It never publishes changes to the site by itself.

| File | What it is |
|---|---|
| `config/easyfundraise.json` | Product, markets, competitors and publishing rules |
| `keywords/regions.json` | Target keywords, kept separately for US, UK, Europe, Asia, Middle East, Africa, Latin America, Canada, Australia & NZ and global |
| `agent/seo_agent.py` | The agent (Python standard library; Anthropic SDK optional) |
| `reports/latest.md` | The newest report; dated copies sit next to it |
| `state/coverage_history.json` | Coverage score per region for every run, so each report shows the change since the last one |
| `state/keyword_coverage.json` | Every keyword with its status (covered, partly, gap) and the page that covers it |
| `state/competitors/*.json` | Last sitemap URL list per competitor (URLs only) |

## What each run does

1. Lists our pages from the repo and from the live sitemap (including the `/investors/...` country and sector lists).
2. Audits live pages: status code, title and description length, one H1, canonical, noindex.
3. Scores every regional keyword as covered, partly covered or a gap.
4. Reads competitor sitemaps (robots.txt respected, 2 seconds between requests) and reports new and removed pages
   and the regions they have pages for. Competitor page text is never fetched or copied.
5. Writes the report with prioritised next actions. If the repository secret `ANTHROPIC_API_KEY` is set, Claude
   writes a short action plan from the findings as well.

## Changing it

- **Keywords:** edit `keywords/regions.json`. Country names must match the investor database so they line up with
  the `/investors` pages. Don't add search volumes unless they come from Search Console or Keyword Planner.
- **Competitors:** edit `competitors` in `config/easyfundraise.json`.
- **Run it now:** Actions → SEO agent → Run workflow, or locally `python seo/agent/seo_agent.py` (`--offline` skips
  the network, `--dry-run` prints instead of writing).
- **Tests:** `python -m unittest discover -s seo/agent`.

For the PR step to work, allow GitHub Actions to create pull requests (Settings → Actions → General → Workflow
permissions). Without that, the report is still in each run's summary.
