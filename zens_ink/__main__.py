#!/usr/bin/env python3
"""CLI dispatcher for zens.ink SEO toolkit."""

import sys

TOOLS = {
    # Discovery
    "keyword_research":   "Discover keywords via Google Autocomplete",
    "keyword_cluster":    "Group raw keywords into semantic topic clusters",
    # Difficulty
    "kd":                 "Keyword Difficulty score via SERP structure analysis",
    "kgr_auto":           "Automated opportunity scoring (KGR: competition vs volume)",
    # Volume
    "keyword_volume":     "Check real search volume via Bing API",
    "brave_volume":       "Estimate search demand via Brave SERP signals",
    # Off-page authority
    "domain_rating":      "Real Ahrefs Domain Rating via free public API",
    # Intent & Strategy
    "search_intent":      "Classify keywords by search intent (info/commercial/transactional/navigational)",
    "serp_intent":        "SERP-based intent analysis (reverse-engineer Google's actual ranking behavior)",
    "content_matrix":     "Generate prioritized content opportunity matrix",
    "geo_fanout":         "Query Fan-out content planning (GEO/AI search)",
    "reddit_blueocean":   "Reddit blue-ocean keyword mining via Autocomplete",
    # Competitive
    "competitor_gap":     "Analyze competitor content via sitemaps",
    # Technical Audit
    "site_audit":         "Technical SEO audit (orphan pages, broken links, missing tags)",
    "onpage_audit":       "On-page quality scoring (7 dimensions, 0-100 per page)",
    "ai_crawler_audit":   "robots.txt AI-crawler policy + llms.txt layer audit (AI-readiness score)",
    # GSC
    "setup_gsc":          "One-time OAuth setup for Search Console",
    "search_performance": "Your site's Google search data (GSC)",
    # Tracking
    "rank_tracker":       "SQLite-backed keyword position history",
    # MCP server
    "mcp":               "Run as MCP stdio server (DSH / Claude / Codex integration)",
}


def show_help():
    from zens_ink import __version__
    print(f"\nzens.ink CLI v{__version__} — Free SEO toolkit for indie builders\n")
    print("Usage: zens-ink <tool> [options]")
    print("   or: python3 -m zens_ink.<tool> [options]\n")
    print("Tools:")
    for name, desc in TOOLS.items():
        print(f"  {name:25s}  {desc}")
    print(f"\n  {len(TOOLS)} tools — all pure stdlib, zero pip dependencies")
    print(f"\nDocs: https://github.com/ZensInk/zens-ink-seo-package\n")


def main():
    args = sys.argv[1:]

    if not args or args[0] in ("-h", "--help", "help"):
        show_help()
        return

    tool = args[0]
    if tool not in TOOLS:
        print(f"Unknown tool: {tool}\n")
        show_help()
        sys.exit(1)

    # Import and run the tool's main() with remaining args
    mod = __import__(f"zens_ink.{tool}", fromlist=["main"])
    sys.argv = [tool] + args[1:]
    if tool == "mcp":
        mod.serve()  # MCP stdio server loop
        return
    mod.main()


if __name__ == "__main__":
    main()
