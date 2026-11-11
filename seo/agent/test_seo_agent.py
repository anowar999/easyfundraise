"""Tests for the SEO agent, with a fake fetcher (no network). Run: python -m unittest discover -s seo/agent"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import seo_agent as sa  # noqa: E402

SITE = "https://easyfundraise.com"
PAGE = ("<html><head><title>Angel investors in the United Kingdom | EasyFundraise</title>"
        "<meta name='description' content='{}'><link rel='canonical' href='x'></head>"
        "<body><h1>Angel investors in the United Kingdom</h1></body></html>").format("d" * 120)


class FakeFetcher(sa.Fetcher):
    def __init__(self, pages: dict[str, tuple[int, str]]):
        super().__init__(delay=0, own_hosts=("easyfundraise.com",))
        self.pages, self.calls = pages, []

    def raw(self, url, timeout=25):
        self.calls.append(url)
        status, body = self.pages.get(url, (404, ""))
        return status, body.encode()


def urlset(*urls):
    return "<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>" + "".join(f"<url><loc>{u}</loc></url>" for u in urls) + "</urlset>"


class Matching(unittest.TestCase):
    def test_synonyms_match(self):
        self.assertLessEqual(sa.tokens("angel investors UK"), sa.tokens("/investors/angel-investors-in-the-united-kingdom"))
        self.assertIn("vc", sa.tokens("Venture capital firms"))
        self.assertIn("preseed", sa.tokens("pre-seed investors"))

    def test_regions_file_has_requested_regions(self):
        regions = json.loads(sa.REGIONS.read_text())["regions"]
        for key in ("us", "uk", "europe", "asia", "middle_east"):
            self.assertIn(key, regions)
            self.assertGreaterEqual(sum(len(v) for v in regions[key]["keywords"].values()), 15)

    def test_coverage_per_region(self):
        regions = {"uk": {"name": "UK", "countries": ["United Kingdom"], "keywords": {"transactional": ["angel investors UK", "SEIS investors"]}}}
        pages = [sa.Page(url=f"{SITE}/investors/angel-investors-in-the-united-kingdom", title="Angel investors in the United Kingdom")]
        cov = sa.coverage(regions, pages)["uk"]
        self.assertEqual((cov["covered"], cov["gap"]), (1, 1))
        self.assertEqual(cov["score"], 50)


class Audit(unittest.TestCase):
    def test_clean_page(self):
        self.assertEqual(sa.audit("u", 200, PAGE).issues, [])

    def test_problems_are_reported(self):
        issues = sa.audit("u", 500, "<html><h1>a</h1><h1>b</h1><meta name='robots' content='noindex'></html>").issues
        text = " ".join(issues)
        for s in ("HTTP 500", "missing <title>", "2 H1", "canonical", "noindex"):
            self.assertIn(s, text)


class Competitors(unittest.TestCase):
    def test_robots_respected_and_diff(self):
        comp = "https://www.rival.example"
        f = FakeFetcher({
            f"{comp}/robots.txt": (200, f"User-agent: *\nDisallow: /private\nSitemap: {comp}/sitemap.xml\n"),
            f"{comp}/sitemap.xml": (200, urlset(f"{comp}/angel-investors-dubai", f"{comp}/blog/seis-guide", "https://other.example/x")),
        })
        regions = json.loads(sa.REGIONS.read_text())["regions"]
        with tempfile.TemporaryDirectory() as d:
            state = Path(d)
            (state / "competitors").mkdir()
            (state / "competitors/rival.example.json").write_text(json.dumps({"urls": [f"{comp}/blog/seis-guide", f"{comp}/old"]}))
            out = sa.competitor_watch(f, [{"domain": "rival.example", "url": comp}], regions, state)[0]
            saved = json.loads((state / "competitors/rival.example.json").read_text())
        self.assertEqual(out["new"], [f"{comp}/angel-investors-dubai"])
        self.assertEqual(out["removed"], [f"{comp}/old"])
        self.assertIn("middle_east", out["regions"])
        self.assertEqual(saved["url_count"], 2)  # other hosts are dropped
        self.assertFalse(any("/private" in c for c in f.calls))
        self.assertTrue(set(saved) <= {"domain", "fetched_at", "url_count", "urls"})  # URLs only, no page content

    def test_disallowed_sitemap_is_not_fetched(self):
        comp = "https://www.closed.example"
        f = FakeFetcher({f"{comp}/robots.txt": (200, "User-agent: *\nDisallow: /\n")})
        urls, note = sa.sitemap_urls(f, comp)
        self.assertEqual(urls, [])
        self.assertIn("robots", note)
        self.assertEqual(f.calls, [f"{comp}/robots.txt"])


    def test_relative_and_bad_sitemap_entries_do_not_crash(self):
        comp = "https://www.rival.example"
        index = ("<sitemapindex xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'><sitemap><loc>/pages.xml</loc></sitemap>"
                 "<sitemap><loc>/</loc></sitemap><sitemap><loc> </loc></sitemap><sitemap><loc>mailto:x</loc></sitemap></sitemapindex>")
        f = FakeFetcher({f"{comp}/robots.txt": (200, f"Sitemap: {comp}/sitemap.xml\n"),
                         f"{comp}/sitemap.xml": (200, index),
                         f"{comp}/pages.xml": (200, urlset("/angel-investors-london", f"{comp}/about"))})
        urls, _ = sa.sitemap_urls(f, comp)
        self.assertEqual(urls, [f"{comp}/about", f"{comp}/angel-investors-london"])
        self.assertEqual(f.get("/no-host"), (0, ""))


class FullRun(unittest.TestCase):
    def test_offline_run_writes_report_and_history(self):
        with tempfile.TemporaryDirectory() as d:
            res = sa.run(offline=True, state_dir=Path(d) / "state", reports_dir=Path(d) / "reports")
            sa.run(offline=True, state_dir=Path(d) / "state", reports_dir=Path(d) / "reports")
            md = (Path(d) / "reports/latest.md").read_text()
            hist = json.loads((Path(d) / "state/coverage_history.json").read_text())
        self.assertGreater(res["pages"], 3)
        self.assertIn("Middle East", md)
        self.assertIn("## Next actions", md)
        self.assertEqual(len(hist), 1)  # same day replaces, so reruns don't skew the trend

    def test_live_run_with_fake_site(self):
        f = FakeFetcher({
            f"{SITE}/robots.txt": (200, f"Sitemap: {SITE}/sitemap.xml\n"),
            f"{SITE}/sitemap.xml": (200, urlset(f"{SITE}/investors/angel-investors-in-the-united-kingdom", f"{SITE}/broken")),
            f"{SITE}/investors/angel-investors-in-the-united-kingdom": (200, PAGE),
        })
        with tempfile.TemporaryDirectory() as d:
            res = sa.run(offline=False, site=SITE, fetcher=f, state_dir=Path(d) / "s", reports_dir=Path(d) / "r")
        self.assertTrue(res["live"])
        self.assertEqual([i["url"] for i in res["issues"]], [f"{SITE}/broken"])
        uk = {k["keyword"]: k["status"] for k in res["coverage"]["uk"]["keywords"]}
        self.assertEqual(uk["find angel investors UK"], "covered")


if __name__ == "__main__":
    unittest.main()
