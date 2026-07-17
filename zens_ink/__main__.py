#!/usr/bin/env python3
"""CLI dispatcher for zens.ink SEO toolkit."""

import sys

TOOLS = {
    "keyword_research":   "Discover keywords via Google Autocomplete",
    "keyword_volume":     "Check real search volume via Bing API",
    "kd":                 "Keyword Difficulty score via SERP structure analysis",
    "brave_volume":       "Estimate search demand via Brave SERP signals",
    "search_performance": "Your site's Google search data (GSC)",
    "competitor_gap":     "Analyze competitor content via sitemaps",
    "site_audit":         "Technical SEO audit (orphan pages, broken links, missing tags)",
    "setup_gsc":          "One-time OAuth setup for Search Console",
}


def show_help():
    print(f"\nzens.ink CLI v1.1.0 — Free SEO toolkit for indie builders\n")
    print("Usage: zens-ink <tool> [options]")
    print("   or: python3 -m zens_ink.<tool> [options]\n")
    print("Tools:")
    for name, desc in TOOLS.items():
        print(f"  {name:25s}  {desc}")
    print(f"\nDocs: https://github.com/respectevery01/zens-ink-seo-package\n")


def main():
    # Entry point mode: zens-ink <tool> [args...]
    # sys.argv[0] = script path, sys.argv[1] = tool name (or --help)
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
    mod.main()


if __name__ == "__main__":
    main()
