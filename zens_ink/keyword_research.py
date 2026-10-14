#!/usr/bin/env python3
"""
Keyword Discovery — Google Autocomplete long-tail mining.

Free, no API key needed. Uses Google's public autocomplete endpoint
to discover what people actually type into search.

Usage:
  python3 -m zens_ink.keyword_research "tarot meaning" --lang en
  python3 -m zens_ink.keyword_research "八字排盘" --lang zh
  python3 -m zens_ink.keyword_research "dream about snakes" --expand

Add  --json  for machine-readable output.
"""

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request


def get_autocomplete(keyword: str, hl: str = "en") -> list[str]:
    """Fetch Google Autocomplete suggestions for a keyword."""
    q = urllib.parse.quote(keyword)
    url = f"https://suggestqueries.google.com/complete/search?client=firefox&q={q}&hl={hl}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read().decode())
        s = data[1] if len(data) > 1 else []
        return s if isinstance(s, list) else []
    except Exception as e:
        print(f"  [warn] autocomplete failed for '{keyword}': {e}", file=sys.stderr)
        return []


def expand_keyword(keyword: str, hl: str = "en") -> list[str]:
    """Expand by appending a-z to discover long-tail variants."""
    results = set()
    for ch in "abcdefghijklmnopqrstuvwxyz":
        time.sleep(0.15)
        suggestions = get_autocomplete(f"{keyword} {ch}", hl)
        for s in suggestions:
            if s.lower().startswith(keyword.lower()):
                results.add(s)
    return sorted(results)


def research(keyword: str, lang: str = "en", expand: bool = False) -> dict:
    """Full keyword research report."""
    hl = "zh-CN" if lang == "zh" else "en"
    suggestions = get_autocomplete(keyword, hl)
    in_suggest = keyword.lower() in [a.lower() for a in suggestions]

    if len(suggestions) >= 8:
        level = "high-activity"
    elif len(suggestions) >= 4:
        level = "medium-activity"
    else:
        level = "low-activity"

    result = {
        "keyword": keyword,
        "lang": lang,
        "in_autocomplete": in_suggest,
        "activity_level": level,
        "suggestion_count": len(suggestions),
        "suggestions": suggestions,
    }

    if expand:
        result["long_tail"] = expand_keyword(keyword, hl)

    return result


def _print_report(r: dict, expand: bool):
    kw = r["keyword"]
    print(f"\n{'='*60}")
    print(f"  Keyword: {kw}  ({r['lang']})")
    print(f"{'='*60}\n")
    print(f"  In autocomplete : {'YES' if r['in_autocomplete'] else 'NO'}")
    print(f"  Activity level  : {r['activity_level']} ({r['suggestion_count']} variants)")
    print(f"\n  Suggestions:")
    for s in r["suggestions"]:
        print(f"    {s}")
    if expand and r.get("long_tail"):
        print(f"\n  Long-tail expansion ({len(r['long_tail'])} keywords):")
        for lt in r["long_tail"][:30]:
            print(f"    {lt}")


def main():
    parser = argparse.ArgumentParser(description="Keyword discovery via Google Autocomplete")
    parser.add_argument("keyword", help="Seed keyword")
    parser.add_argument("--lang", "-l", default="en", choices=["en", "zh"])
    parser.add_argument("--expand", "-e", action="store_true",
                        help="Expand with a-z long-tail discovery (slower)")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    r = research(args.keyword, args.lang, args.expand)

    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        _print_report(r, args.expand)


if __name__ == "__main__":
    main()
