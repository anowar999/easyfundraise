"""EasyFundraise SEO agent (spec §20). Runs on a schedule (.github/workflows/seo-agent.yml) and by hand:

    python seo/agent/seo_agent.py                 # full run: site, regional keywords, competitors, report
    python seo/agent/seo_agent.py --offline       # repo only: no network (used by tests and local checks)

Each run:
1. Builds an inventory of our pages: the Next.js pages and blog posts in this repo, plus the live sitemap when the
   site is reachable (which adds the /investors/... country and sector lists).
2. Audits the live pages: status, title and description length, one H1, canonical, noindex.
3. Checks every keyword in seo/keywords/regions.json against those pages, separately for each region
   (US, UK, Europe, Asia, Middle East, ...), and keeps the coverage history so each run shows what improved.
4. Watches competitors (seo/config: competitors): robots.txt-respecting sitemap fetch, new and removed URLs since
   the last run, and which regions they have pages for that we don't. Only URLs and topics from URL slugs are
   stored. Competitor page content is never fetched or copied.
5. Writes seo/reports/latest.md (and a dated copy) with prioritised next actions. With ANTHROPIC_API_KEY set, Claude
   turns the findings into a short action plan; without it the report lists the same actions from rules.

Standard library only (plus the optional anthropic package), so the workflow needs no install step.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import urllib.robotparser
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "seo/config/easyfundraise.json"
REGIONS = ROOT / "seo/keywords/regions.json"
STATE = ROOT / "seo/state"
REPORTS = ROOT / "seo/reports"
WEB_APP = ROOT / "apps/web/src/app"
BLOG = ROOT / "apps/web/content/blog"
HISTORY_KEEP = 104  # two years of weekly runs
MAX_AUDIT = 300

UA = "EasyFundraiseSEOAgent/1.0 (+https://easyfundraise.com/llms.txt)"

# --------------------------------------------------------------------------------------------------- text matching

STOP = {"a", "an", "and", "the", "for", "in", "of", "to", "with", "on", "how", "who", "your", "you", "my", "best", "list",
        "vs", "what", "is", "are", "from", "by", "at", "do", "does", "can", "get", "find", "free"}
PHRASES = [  # normalised before tokenising, so "UK" matches "united kingdom" and "VC" matches "venture capital"
    (r"\bunited kingdom\b", "uk"), (r"\bunited states\b", "us"), (r"\busa\b", "us"), (r"\bu\.s\.?\b", "us"),
    (r"\bunited arab emirates\b", "uae"), (r"\bventure capital(ists?)?\b", "vc"), (r"\bvcs\b", "vc"),
    (r"\bpre[- ]?seed\b", "preseed"), (r"\bbusiness angels?\b", "angel"), (r"\bstart[- ]ups?\b", "startup"),
    (r"\bfund ?raising\b", "fundraising"), (r"\bseries a\b", "seriesa"), (r"&", " and "),
]


def norm(text: str) -> str:
    t = text.lower().replace("-", " ").replace("_", " ").replace("/", " ")
    for pat, rep in PHRASES:
        t = re.sub(pat, rep, t)
    return t


def stem(w: str) -> str:
    for suf in ("ies", "es", "s"):
        if w.endswith(suf) and len(w) > len(suf) + 2:
            return w[: -len(suf)] + ("y" if suf == "ies" else "")
    return w


def tokens(text: str) -> set[str]:
    return {stem(w) for w in re.findall(r"[a-z0-9$£€]+", norm(text)) if w not in STOP}


def slugify(s: str) -> str:
    return re.sub(r"^-|-$", "", re.sub(r"[^a-z0-9]+", "-", s.lower().replace("&", "and")))


# --------------------------------------------------------------------------------------------------- pages

@dataclass
class Page:
    url: str
    title: str = ""
    description: str = ""
    h1: str = ""
    source: str = "repo"  # repo | live
    issues: list[str] = field(default_factory=list)

    @property
    def strong(self) -> set[str]:
        return tokens(f"{urlparse(self.url).path} {self.title} {self.h1}")

    @property
    def weak(self) -> set[str]:
        return self.strong | tokens(self.description)


def _str_after(src: str, key: str) -> str:
    m = re.search(key + r"""\s*:\s*(?:\{\s*absolute\s*:\s*)?(["'`])(.+?)\1""", src, re.S)
    return re.sub(r"\s+", " ", m.group(2)).strip() if m else ""


def _front(head: str, key: str) -> str:
    m = re.search(rf"^{key}:\s*(.+)$", head, re.M)
    return m.group(1).strip().strip("\"'") if m else ""


PRIVATE = {"app", "admin", "login", "onboarding", "invite", "welcome", "r"}


def repo_pages(site: str) -> list[Page]:
    """Static pages (title and description from each page.tsx metadata) and blog posts (front matter)."""
    out: list[Page] = []
    for f in sorted(WEB_APP.rglob("page.tsx")):
        rel = f.parent.relative_to(WEB_APP).as_posix()
        if rel.split("/")[0] in PRIVATE or "[" in rel:
            continue  # signed-in app pages are not indexed; dynamic routes come from the live sitemap
        src = f.read_text(encoding="utf-8")
        meta = src[src.find("metadata"):] if "metadata" in src else ""
        h1 = re.search(r"<h1[^>]*>(.*?)</h1>", src, re.S)
        out.append(Page(url=site if rel == "." else f"{site}/{rel}", title=_str_after(meta, "title"),
                        description=_str_after(meta, "description"),
                        h1=re.sub(r"<[^>]+>|\{[^}]*\}|\s+", " ", h1.group(1)).strip() if h1 else ""))
    if BLOG.exists():
        for f in sorted(BLOG.glob("*.md")):
            fm = f.read_text(encoding="utf-8").split("---")
            head = fm[1] if len(fm) > 2 else ""
            title, desc = _front(head, "title"), _front(head, "description")
            out.append(Page(url=f"{site}/blog/{f.stem}", title=title, description=desc, h1=title))
    return out


class _Head(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title, self.description, self.canonical, self.robots = "", "", "", ""
        self.h1s: list[str] = []
        self._in: str | None = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "title":
            self._in = "title"
        elif tag == "h1":
            self._in = "h1"
            self.h1s.append("")
        elif tag == "meta" and (a.get("name") or "").lower() == "description":
            self.description = a.get("content") or ""
        elif tag == "meta" and (a.get("name") or "").lower() == "robots":
            self.robots = (a.get("content") or "").lower()
        elif tag == "link" and (a.get("rel") or "").lower() == "canonical":
            self.canonical = a.get("href") or ""

    def handle_endtag(self, tag):
        if tag in ("title", "h1"):
            self._in = None

    def handle_data(self, data):
        if self._in == "title":
            self.title += data
        elif self._in == "h1":
            self.h1s[-1] += data


def audit(url: str, status: int, html: str) -> Page:
    p = _Head()
    try:
        p.feed(html)
    except Exception:  # broken markup still yields what was parsed
        pass
    page = Page(url=url, title=p.title.strip(), description=p.description.strip(),
                h1=(p.h1s[0].strip() if p.h1s else ""), source="live")
    if status != 200:
        page.issues.append(f"returns HTTP {status}")
    if not page.title:
        page.issues.append("missing <title>")
    elif len(page.title) > 65:
        page.issues.append(f"title is {len(page.title)} characters (aim for 65 or fewer)")
    if not page.description:
        page.issues.append("missing meta description")
    elif not 70 <= len(page.description) <= 165:
        page.issues.append(f"meta description is {len(page.description)} characters (aim for 70-165)")
    if len(p.h1s) != 1:
        page.issues.append(f"has {len(p.h1s)} H1 headings (should be 1)")
    if not p.canonical:
        page.issues.append("missing canonical link")
    if "noindex" in p.robots:
        page.issues.append("is noindex but listed in the sitemap")
    return page


# --------------------------------------------------------------------------------------------------- network

class Fetcher:
    """Polite HTTP: one user agent, a delay per host, robots.txt respected for every non-own host."""

    def __init__(self, delay: float = 2.0, own_hosts: tuple[str, ...] = ()):
        self.delay, self.own = delay, own_hosts
        self._last: dict[str, float] = {}
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}

    def raw(self, url: str, timeout: int = 25) -> tuple[int, bytes]:
        host = urlparse(url).netloc
        wait = self._last.get(host, 0) + self.delay - time.time()
        if wait > 0:
            time.sleep(wait)
        self._last[host] = time.time()
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read(20_000_000)
                if r.headers.get("Content-Encoding") == "gzip" or url.endswith(".gz"):
                    body = gzip.decompress(body)
                return r.status, body
        except urllib.error.HTTPError as e:
            return e.code, b""
        except (urllib.error.URLError, TimeoutError, OSError, EOFError, gzip.BadGzipFile):
            return 0, b""

    def robots(self, base: str) -> urllib.robotparser.RobotFileParser | None:
        if base not in self._robots:
            status, body = self.raw(f"{base}/robots.txt")
            rp = None
            if status == 200:
                rp = urllib.robotparser.RobotFileParser()
                rp.parse(body.decode("utf-8", "replace").splitlines())
            self._robots[base] = rp
        return self._robots[base]

    def allowed(self, url: str) -> bool:
        u = urlparse(url)
        if u.netloc in self.own:
            return True
        rp = self.robots(f"{u.scheme}://{u.netloc}")
        return rp is None or rp.can_fetch(UA, url)

    def get(self, url: str) -> tuple[int, str]:
        u = urlparse(url)
        if u.scheme not in ("http", "https") or not u.netloc:
            return 0, ""  # a malformed URL from someone's sitemap must not stop the run
        if not self.allowed(url):
            return -1, ""
        status, body = self.raw(url)
        return status, body.decode("utf-8", "replace")


def sitemap_urls(f: Fetcher, base: str, cap: int = 5000) -> tuple[list[str], str]:
    """All page URLs from a site's sitemaps (robots.txt Sitemap lines, else /sitemap.xml), following indexes."""
    rp = f.robots(base)
    queue = list(rp.site_maps() or []) if rp else []
    queue = queue or [f"{base}/sitemap.xml"]
    seen, urls, note = set(), [], ""
    host = urlparse(base).netloc.removeprefix("www.")
    while queue and len(seen) < 40 and len(urls) < cap:
        sm = queue.pop(0)
        if sm in seen:
            continue
        seen.add(sm)
        status, text = f.get(sm)
        if status == -1:
            note = "sitemap disallowed by robots.txt"
            continue
        if status != 200 or not text.strip():
            note = note or f"sitemap {sm} returned {status or 'no response'}"
            continue
        try:
            root = ElementTree.fromstring(text.encode("utf-8"))
        except ElementTree.ParseError:
            note = f"sitemap {sm} is not valid XML"
            continue
        # relative or blank <loc> entries are resolved against the sitemap's own URL, anything else is dropped
        locs = [urljoin(sm, e.text.strip()) for e in root.iter() if e.tag.endswith("loc") and (e.text or "").strip()]
        locs = [u for u in locs if urlparse(u).scheme in ("http", "https") and urlparse(u).netloc]
        if root.tag.endswith("sitemapindex"):
            queue += locs
        else:
            urls += [u for u in locs if urlparse(u).netloc.removeprefix("www.") == host]
    return sorted(set(urls))[:cap], note


# --------------------------------------------------------------------------------------------------- analysis

def coverage(regions: dict, pages: list[Page]) -> dict:
    """For every region and keyword: the best page and whether it is covered, partly covered, or a gap."""
    out = {}
    strong = [(p, p.strong) for p in pages]
    weak = [(p, p.weak) for p in pages]
    for key, r in regions.items():
        rows = []
        for group, kws in r["keywords"].items():
            for kw in kws:
                want = tokens(kw)
                if not want:
                    continue
                best, best_s = None, 0.0
                for p, toks in strong:
                    s = len(want & toks) / len(want)
                    if s > best_s:
                        best, best_s = p, s
                status = "covered" if best_s >= 0.99 else None
                if status is None:
                    for p, toks in weak:
                        s = len(want & toks) / len(want)
                        if s > best_s:
                            best, best_s = p, s
                    status = "partial" if best_s >= 0.6 else "gap"
                rows.append({"keyword": kw, "group": group, "status": status, "score": round(best_s, 2),
                             "page": best.url if best and best_s >= 0.6 else ""})
        n = len(rows)
        cov = sum(1 for x in rows if x["status"] == "covered")
        part = sum(1 for x in rows if x["status"] == "partial")
        out[key] = {"name": r["name"], "countries": r.get("countries", []), "total": n, "covered": cov, "partial": part, "gap": n - cov - part,
                    "score": round((cov + 0.5 * part) / n * 100) if n else 0, "keywords": rows}
    return out


def regional_pages(regions: dict, urls: list[str]) -> dict[str, dict]:
    """How many of a site's URLs mention each region's countries or cities in the slug."""
    out = {}
    for key, r in regions.items():
        terms = {slugify(x) for x in r.get("countries", []) + r.get("cities", [])}
        terms |= {"uk"} if key == "uk" else set()
        terms |= {"uae", "dubai", "mena", "gcc"} if key == "middle_east" else set()
        hits = []
        for u in urls:
            path = "-" + slugify(urlparse(u).path) + "-"
            if any(f"-{t}-" in path for t in terms if t):
                hits.append(u)
        if hits:
            out[key] = {"count": len(hits), "sample": hits[:8]}
    return out


def slug_topics(urls: list[str], top: int = 25) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for u in urls:
        for t in tokens(urlparse(u).path):
            if not t.isdigit() and len(t) > 2:
                counts[t] = counts.get(t, 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:top]


def competitor_watch(f: Fetcher | None, competitors: list[dict], regions: dict, state_dir: Path) -> list[dict]:
    out = []
    for c in competitors:
        domain = c["domain"]
        path = state_dir / "competitors" / f"{domain}.json"
        prev = json.loads(path.read_text()) if path.exists() else {}
        entry = {"domain": domain, "url": c.get("url", f"https://{domain}/"), "markets": c.get("markets", []),
                 "fetched": False, "note": "", "url_count": prev.get("url_count", 0), "new": [], "removed": []}
        urls = prev.get("urls", [])
        if f is not None:
            base = c.get("url", f"https://{domain}").rstrip("/")
            fresh, note = sitemap_urls(f, base)
            entry["note"] = note
            if fresh:
                old = set(urls)
                entry.update(fetched=True, url_count=len(fresh),
                             new=sorted(set(fresh) - old) if old else [], removed=sorted(old - set(fresh)) if old else [])
                urls = fresh
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps({"domain": domain, "fetched_at": now_iso(), "url_count": len(fresh),
                                            "urls": fresh}, indent=1) + "\n")
        else:
            entry["note"] = "offline run: using the last saved sitemap" if urls else "offline run: no saved sitemap yet"
        entry["regions"] = regional_pages(regions, urls)
        entry["topics"] = slug_topics(urls)
        out.append(entry)
    return out


def regions_have_countries(r: dict) -> bool:
    return bool(r.get("countries"))


def actions(cov: dict, comps: list[dict], ours_regional: dict, issues: list[Page]) -> list[dict]:
    """Rule-based next actions, highest priority first."""
    acts = []
    for key, r in sorted(cov.items(), key=lambda kv: kv[1]["score"]):
        gaps = [k for k in r["keywords"] if k["status"] == "gap" and k["group"] in ("transactional", "commercial")]
        if gaps:
            comp = sum(c["regions"].get(key, {}).get("count", 0) for c in comps)
            pri = 3 if comp else 2
            if key in ("us", "uk", "europe", "asia", "middle_east"):
                pri += 1
            acts.append({"priority": pri, "region": r["name"],
                         "action": f"{r['name']}: no page targets {len(gaps)} high-intent keywords, e.g. "
                                   + ", ".join(f"\"{g['keyword']}\"" for g in gaps[:4])
                                   + (". Competitors have " + str(comp) + " pages for this region." if comp else ".")
                                   + (" Check the /investors country pages for this region reach the 30-investor threshold, "
                                      "and plan one regional guide (one page per intent, no doorway pages)."
                                      if regions_have_countries(r) else " Cover them on a product or feature page.")})
        info = [k for k in r["keywords"] if k["status"] == "gap" and k["group"] == "informational"]
        if info:
            acts.append({"priority": 1, "region": r["name"],
                         "action": f"{r['name']}: write or extend a guide for \"{info[0]['keyword']}\""
                                   + (f" and {len(info) - 1} related question{'s' if len(info) > 2 else ''}" if len(info) > 1 else "") + "."})
    for c in comps:
        if c["new"]:
            acts.append({"priority": 2, "region": "All", "action": f"{c['domain']} published {len(c['new'])} new pages since "
                                                                   "the last run. Review the topics (not the text) for gaps."})
        for key, rp in c["regions"].items():
            if key not in ours_regional and key in cov:
                acts.append({"priority": 2, "region": cov[key]["name"],
                             "action": f"{c['domain']} has {rp['count']} pages for {cov[key]['name']}; we have none in our sitemap."})
    if issues:
        acts.append({"priority": 3, "region": "All", "action": f"Fix {sum(len(p.issues) for p in issues)} technical issues "
                                                               f"on {len(issues)} live pages (see Technical SEO)."})
    return sorted(acts, key=lambda a: -a["priority"])


# --------------------------------------------------------------------------------------------------- report

def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def ai_plan(summary: dict) -> str:
    """Optional: Claude writes the action plan from the structured findings (no competitor text is sent)."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return ""
    try:
        import anthropic
    except ImportError:
        return ""
    system = ("You are the SEO lead for EasyFundraise, an investor database, cold email outreach and fundraising CRM "
              "for founders. Using only the JSON findings, write the 5 most valuable next actions for the coming week "
              "as a Markdown numbered list. Each item: the action, the region it serves, the target keyword(s), the "
              "page to create or change, and why it matters. Never invent search volumes, rankings or statistics. "
              "Never suggest copying competitor content, doorway pages, keyword stuffing or buying links.")
    try:
        resp = anthropic.Anthropic().beta.messages.create(
            model=os.environ.get("EF_SEO_MODEL", "claude-opus-5-5"), max_tokens=16000,
            output_config={"effort": "medium"}, betas=["server-side-fallback-2026-07-01"], fallbacks="default",
            system=system, messages=[{"role": "user", "content": json.dumps(summary)[:150_000]}])
    except Exception as e:  # the report still ships with the rule-based actions
        print(f"AI plan skipped: {e}", file=sys.stderr)
        return ""
    if resp.stop_reason in ("refusal", "max_tokens"):
        return ""
    return "".join(b.text for b in resp.content if b.type == "text").strip()


def render(run: dict) -> str:
    L = [f"# SEO agent report: {run['date']}", ""]
    L += [f"Mode: {'live (site and competitors fetched)' if run['live'] else 'offline (repo only)'}. "
          f"Pages checked: {run['pages']} ({run['live_pages']} from the live sitemap).", ""]
    L += ["## Regional keyword coverage", "",
          "Score = covered + half of partly covered keywords. Change is since the previous run.", "",
          "| Region | Keywords | Covered | Partly | Gaps | Score | Change |", "|---|---:|---:|---:|---:|---:|---:|"]
    for key, r in run["coverage"].items():
        d = run["delta"].get(key)
        L.append(f"| {r['name']} | {r['total']} | {r['covered']} | {r['partial']} | {r['gap']} | {r['score']}% | "
                 f"{'' if d is None else f'{d:+d}'} |")
    L += ["", "## Next actions", ""]
    if run["ai_plan"]:
        L += [run["ai_plan"], "", "<details><summary>Rule-based actions</summary>", ""]
    for i, a in enumerate(run["actions"][:15], 1):
        L.append(f"{i}. **[{['low', 'low', 'medium', 'high', 'high'][min(a['priority'], 4)]}]** {a['action']}")
    if run["ai_plan"]:
        L += ["", "</details>"]
    L += ["", "## Competitors", ""]
    for c in run["competitors"]:
        L.append(f"### {c['domain']}")
        L.append(f"- Sitemap URLs: {c['url_count']}" + (f" ({c['note']})" if c["note"] else ""))
        if c["new"]:
            L.append(f"- New since last run ({len(c['new'])}): " + ", ".join(c["new"][:15]))
        if c["removed"]:
            L.append(f"- Removed since last run: {len(c['removed'])}")
        if c["regions"]:
            L.append("- Regional pages: " + ", ".join(f"{run['coverage'][k]['name'] if k in run['coverage'] else k} {v['count']}"
                                                     for k, v in c["regions"].items()))
        if c["topics"]:
            L.append("- Top URL topics: " + ", ".join(f"{t} ({n})" for t, n in c["topics"][:15]))
        L.append("")
    L += ["## Technical SEO", ""]
    if run["issues"]:
        for p in run["issues"][:40]:
            L.append(f"- {p['url']}: " + "; ".join(p["issues"]))
    else:
        L.append("- No issues found." if run["live"] else "- Skipped: the live site was not fetched.")
    L += ["", "## Gaps by region", ""]
    for r in run["coverage"].values():
        gaps = [k["keyword"] for k in r["keywords"] if k["status"] == "gap"]
        if gaps:
            L.append(f"- **{r['name']}**: " + "; ".join(gaps))
    L += ["", "_Generated by seo/agent/seo_agent.py. Keywords live in seo/keywords/regions.json; competitors in "
          "seo/config/easyfundraise.json. No search volumes or rankings are estimated: connect Search Console for those._", ""]
    return "\n".join(L)


def run(offline: bool, site: str | None = None, fetcher: Fetcher | None = None, state_dir: Path = STATE,
        reports_dir: Path = REPORTS, write: bool = True) -> dict:
    cfg = json.loads(CONFIG.read_text())
    regions = json.loads(REGIONS.read_text())["regions"]
    site = (site or os.environ.get("EF_SEO_SITE") or cfg["environments"]["prod"]).rstrip("/")
    pages = repo_pages(site)
    f = None if offline else (fetcher or Fetcher(delay=cfg.get("competitor_rules", {}).get("min_seconds_between_requests", 2),
                                                 own_hosts=(urlparse(site).netloc,)))
    live: list[Page] = []
    if f is not None:
        urls, _ = sitemap_urls(f, site)
        for u in urls[:MAX_AUDIT]:
            status, html = f.get(u)
            live.append(audit(u, status, html))
        if live:  # live pages replace the repo copy of the same URL
            known = {p.url for p in live}
            pages = live + [p for p in pages if p.url not in known]
    cov = coverage(regions, pages)
    comps = competitor_watch(f, [c for c in cfg.get("competitors", []) if isinstance(c, dict)], regions, state_dir)
    ours = regional_pages(regions, [p.url for p in pages])
    issues = [p for p in live if p.issues]

    hist_path = state_dir / "coverage_history.json"
    hist = json.loads(hist_path.read_text()) if hist_path.exists() else []
    # compare like with like: a live run against the last live run, an offline run against the last offline run
    same = [h for h in hist if h.get("live") == bool(live) and h["date"] != datetime.now(UTC).strftime("%Y-%m-%d")]
    prev = same[-1]["regions"] if same else {}
    delta = {k: r["score"] - prev[k]["score"] for k, r in cov.items() if k in prev}
    date = datetime.now(UTC).strftime("%Y-%m-%d")
    result = {"date": date, "live": bool(live), "pages": len(pages), "live_pages": len(live), "coverage": cov,
              "delta": delta, "competitors": comps, "issues": [{"url": p.url, "issues": p.issues} for p in issues],
              "actions": actions(cov, comps, ours, issues), "ai_plan": ""}
    if not offline:
        result["ai_plan"] = ai_plan({k: v for k, v in result.items() if k not in ("ai_plan",)})
    if write:
        state_dir.mkdir(parents=True, exist_ok=True)
        reports_dir.mkdir(parents=True, exist_ok=True)
        snap = {"date": date, "live": bool(live),
                "regions": {k: {x: r[x] for x in ("total", "covered", "partial", "gap", "score")} for k, r in cov.items()}}
        hist = [h for h in hist if h["date"] != date] + [snap]
        hist_path.write_text(json.dumps(hist[-HISTORY_KEEP:], indent=1) + "\n")
        (state_dir / "keyword_coverage.json").write_text(json.dumps(cov, indent=1, ensure_ascii=False) + "\n")
        md = render(result)
        (reports_dir / "latest.md").write_text(md)
        (reports_dir / f"{date}.md").write_text(md)
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--offline", action="store_true", help="repo only, no network")
    ap.add_argument("--site", help="site to audit (default: EF_SEO_SITE or the prod URL in the config)")
    ap.add_argument("--dry-run", action="store_true", help="print the report instead of writing files")
    a = ap.parse_args(argv)
    res = run(offline=a.offline, site=a.site, write=not a.dry_run)
    if a.dry_run:
        print(render(res))
    else:
        print(f"SEO agent: {res['pages']} pages, live={res['live']}; "
              + ", ".join(f"{r['name']} {r['score']}%" for r in res["coverage"].values()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
