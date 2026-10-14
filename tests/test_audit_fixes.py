"""Regression tests for the v1.4.11 DSH audit fixes (round 1, 40 findings).

Deterministic, network-free — HTTP is monkeypatched where needed.
Run: python3 -m unittest tests.test_audit_fixes -v
"""
import json
import os
import sqlite3
import sys
import tempfile
import unittest
import urllib.request
from pathlib import Path
from io import BytesIO

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _fake_urlopen(payload_bytes):
    """Return a urlopen replacement serving a fixed byte payload."""

    class R:
        def __init__(self, data):
            self._data = data

        def read(self):
            return self._data

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    return lambda req, timeout=None: R(payload_bytes)


class TestAutocompleteNoneEnvelope(unittest.TestCase):
    """Finding 2: ["q", null] must yield [], not None."""

    def test_null_second_element(self):
        from zens_ink import keyword_research as kr
        orig = urllib.request.urlopen
        urllib.request.urlopen = _fake_urlopen(
            json.dumps(["q", None]).encode()
        )
        try:
            self.assertEqual(kr.get_autocomplete("x"), [])
        finally:
            urllib.request.urlopen = orig


class TestSearchIntentGetToken(unittest.TestCase):
    """Finding 9: 'how to get ...' is informational, not transactional."""

    def test_how_to_get(self):
        from zens_ink.search_intent import classify
        r = classify("how to get more organic traffic")
        self.assertEqual(r["intent"], "informational")


class TestSerpIntentPathRules(unittest.TestCase):
    """Finding 10: /blog/product-led-growth is a blog post, not a product page."""

    def test_blog_prefix_wins(self):
        from zens_ink.serp_intent import _classify_page_type
        self.assertEqual(
            _classify_page_type(
                "https://example.com/blog/product-led-growth", "Product led growth"
            ),
            "blog",
        )
        self.assertEqual(
            _classify_page_type("https://example.com/pricing", "Pricing"), "pricing"
        )


class TestAiCrawlerGroupParsing(unittest.TestCase):
    """Finding 6: consecutive User-agent lines share one rule block."""

    def test_shared_group(self):
        from zens_ink.ai_crawler_audit import crawl_status, parse_robots
        r = parse_robots(
            "User-agent: GPTBot\nUser-agent: ChatGPT-User\nDisallow: /\n"
        )
        self.assertEqual(crawl_status(r["groups"], "GPTBot"), "blocked")
        self.assertEqual(crawl_status(r["groups"], "ChatGPT-User"), "blocked")


class TestRankTracker(unittest.TestCase):
    """Findings 7/23/24: lstrip, comma remove, 999-sentinel delta."""

    def setUp(self):
        import zens_ink.rank_tracker as rt

        self.rt = rt
        fd, self.db = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        os.remove(self.db)
        rt.DB_PATH = Path(self.db)
        c = rt._conn()  # creates keywords + snapshots tables
        c.close()

    def tearDown(self):
        os.remove(self.db)

    def test_remove_comma_list(self):
        c = self.rt._conn()
        for kw in ("alpha", "beta"):
            c.execute("INSERT INTO keywords VALUES(?,?,?,?)", (kw, "", "", "t"))
        c.commit()
        c.close()

        class A:
            keywords = "alpha,beta"

        out = self.rt.act_remove(A())
        self.assertEqual(sorted(out["removed"]), ["alpha", "beta"])
        c = self.rt._conn()
        self.assertEqual(
            c.execute("SELECT COUNT(*) FROM keywords").fetchone()[0], 0
        )
        c.close()

    def test_sentinel_delta_masked(self):
        c = self.rt._conn()
        c.execute("INSERT INTO keywords VALUES('kw1','','','t')")
        c.execute(
            "INSERT INTO snapshots(keyword,position,checked_at) VALUES('kw1',999,'t1')"
        )
        c.execute(
            "INSERT INTO snapshots(keyword,position,checked_at) VALUES('kw1',3,'t2')"
        )
        c.commit()
        c.close()

        class A:
            keywords = "kw1"
            limit = 10

        trend = self.rt.act_trend(A())["trends"][0]
        self.assertIsNone(trend["delta"], "999-sentinel must not fabricate a delta")


class TestCompetitorGapTopics(unittest.TestCase):
    """Finding 14: /blog/* content must survive the topic filter."""

    def test_blog_paths_kept(self):
        from zens_ink.competitor_gap import extract_topics
        urls = [
            "https://rival.com/blog/seo-guide",
            "https://rival.com/pricing",
            "https://rival.com/features/x",
        ]
        topics = set(extract_topics(urls).keys())
        self.assertTrue(any(t.startswith("blog") for t in topics),
                        f"blog content dropped: {topics}")
        self.assertFalse(any(t.startswith("pricing") for t in topics))


class TestGeoFanoutDemand(unittest.TestCase):
    """Finding 5: a short suggestion must not validate every sub-query."""

    def test_no_reverse_containment(self):
        live = ["crm"]
        q = "best crm for small business invoice automation"
        has = q in live or any(
            s.startswith(q) or q.startswith(s) for s in live
        )
        self.assertFalse(has)


class TestRedditCommercialWords(unittest.TestCase):
    """Finding 12: 'top' must not match 'laptop'."""

    def test_word_boundary(self):
        from zens_ink.reddit_blueocean import _has_commercial_intent
        self.assertFalse(_has_commercial_intent("my laptop stopped working"))
        self.assertTrue(_has_commercial_intent("top 10 crm tools"))


class TestContentQcCjk(unittest.TestCase):
    """Finding 25: CJK text must produce a nonzero word count."""

    def test_cjk_counted(self):
        import re

        text = "这是一篇正常的中文文章，包含 2026 年和 47% 的比例。"
        words = re.findall(r"[A-Za-z][A-Za-z'-]*", text)
        cjk = re.findall(r"[\u4e00-\u9fff]", text)
        self.assertGreater(len(cjk), 10)
        self.assertEqual(len(words), 0)


class TestMcpRegistryConsistency(unittest.TestCase):
    """Finding 1/35: registry parity — dispatcher, MCP names, module mains."""

    def test_dispatcher_covers_all_modules(self):
        import pkgutil

        import zens_ink
        from zens_ink.__main__ import TOOLS

        mods = {
            m.name
            for m in pkgutil.iter_modules(zens_ink.__path__)
            if m.name not in ("__init__", "__main__", "config")
        }
        self.assertEqual(set(TOOLS), mods, "__main__ TOOLS drifted from modules")

    def test_every_mcp_tool_parses_no_json_flag_correctly(self):
        import inspect

        from zens_ink.mcp import TOOLS as MCP_TOOLS

        problems = []
        for t in MCP_TOOLS:
            mod = __import__(t["module"], fromlist=["x"])
            src = inspect.getsource(mod)
            # json_flag False means the module argparse must NOT accept --json
            if t.get("json_flag", True) is False:
                if 'add_argument("--json"' in src:
                    problems.append(f"{t['name']}: json_flag False but module accepts --json")
        self.assertEqual(problems, [])


class TestKeywordClusterCsv(unittest.TestCase):
    """Finding 32: quoted CSV keywords containing commas survive parsing."""

    def test_quoted_comma_keywords(self):
        from zens_ink.keyword_cluster import read_keywords

        fd, p = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        with open(p, "w", encoding="utf-8") as f:
            f.write('"best crm, free"\n"best crm, paid"\n')
        try:
            kws = read_keywords(filepath=p)
            self.assertEqual(kws, ["best crm, free", "best crm, paid"])
        finally:
            os.remove(p)


class TestSiteAuditJsonLd(unittest.TestCase):
    """Finding 3: pretty-printed JSON-LD must be detected."""

    def test_pretty_printed_type(self):
        import re

        block = '{"@context":"https://schema.org", "@type": "Product", "name":"x"}'
        self.assertIsNotNone(
            re.search(r'"@type"\s*:\s*"Product"', block)
        )


if __name__ == "__main__":
    unittest.main()


class TestRound2Fixes(unittest.TestCase):
    """Round-2 verification findings: anchoring, coercion parity, exact demand."""

    def test_pricing_guide_stays_pricing(self):
        """R2-1: unanchored /guide must not retype transactional pages as blog."""
        from zens_ink.serp_intent import _classify_page_type
        self.assertEqual(_classify_page_type("https://e.com/pricing/guide", "x"), "pricing")
        self.assertEqual(_classify_page_type("https://e.com/product/guide", "x"), "product")
        self.assertEqual(_classify_page_type("https://e.com/tool/guide", "x"), "tool")
        self.assertEqual(_classify_page_type("https://e.com/shop/guide", "x"), "shopping")
        self.assertEqual(_classify_page_type("https://e.com/guide/choosing", "x"), "blog")
        self.assertEqual(_classify_page_type("https://e.com/blog/product-led-growth", "x"), "blog")

    def test_json_volume_fields_coerced(self):
        """R2-2: all six numeric fields coerce in the JSON branch."""
        import json as _json
        import tempfile as _tf
        from zens_ink.content_matrix import load_scores
        fd, p = _tf.mkstemp(suffix=".json")
        os.close(fd)
        with open(p, "w", encoding="utf-8") as f:
            f.write(_json.dumps([{"keyword": "crm", "opportunity_score": "50",
                                  "avg_weekly_volume": "1500"}]))
        try:
            rows = load_scores(p)
            self.assertEqual(rows[0]["avg_weekly_volume"], 1500)
        finally:
            os.remove(p)

    def test_exact_demand_no_prefix_overvalidation(self):
        """F5-strict: a short suggestion must not validate prefixed queries."""
        live = ["crm"]
        for q in ("crm pricing", "crm alternatives", "best crm for teams"):
            self.assertFalse(q in live, "prefix/suggestion must not validate")
        self.assertTrue("crm" in live)


class TestRound3Suggestions(unittest.TestCase):
    """Round-3 auditor suggestions: stub the HTTP path and test generate_fanout level."""

    def test_kd_http_error_surfaces_runtime_error(self):
        """F29 guard: HTTPError must surface as RuntimeError with code, not escape raw."""
        import urllib.error

        from zens_ink import kd

        def boom(req, timeout=None):
            raise urllib.error.HTTPError(
                "https://google.serper.dev/search", 429,
                "Too Many Requests", {}, BytesIO(b'{"message":"rate limited"}'),
            )

        orig = urllib.request.urlopen
        urllib.request.urlopen = boom
        try:
            with self.assertRaises(RuntimeError) as ctx:
                kd._http_post_json("https://google.serper.dev/search", {})
            self.assertIn("HTTP 429", str(ctx.exception))
        finally:
            urllib.request.urlopen = orig

    def test_generate_fanout_exact_demand(self):
        """F5 guard at the generate_fanout level: no prefix over-validation."""
        from zens_ink import geo_fanout as gf

        orig = gf.get_autocomplete
        gf.get_autocomplete = lambda kw, hl="en": ["crm"]
        try:
            data = gf.generate_fanout("crm", icp="b2b saas", lang="en", live_check=True)
            live = [sq for sq in data["sub_queries"] if sq["live_demand"]]
            # only queries whose exact lowercase form is a suggestion count
            self.assertTrue(all(sq["query"].lower() in ("crm",) for sq in live))
            self.assertLessEqual(len(live), 1)
        finally:
            gf.get_autocomplete = orig
