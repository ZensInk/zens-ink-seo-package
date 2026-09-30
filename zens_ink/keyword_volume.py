#!/usr/bin/env python3
"""
Keyword Volume — real search demand via Bing Webmaster API.

Returns ~25 weeks of weekly impression data per keyword: average volume,
trend direction, and demand level. Free with a Bing Webmaster API key.

Usage:
  python3 -m zens_ink.keyword_volume "塔罗牌"
  python3 -m zens_ink.keyword_volume "tarot,dream interpretation" --country us --lang en-US
  python3 -m zens_ink.keyword_volume --file keywords.txt --csv results.csv
"""

import argparse
import csv
import json
import sys
import time
import urllib.parse
import urllib.request

from zens_ink.config import BING_API_KEY

BASE = "https://ssl.bing.com/webmaster/api.svc/json"

# Bing requires full locale codes (language=en -> HTTP 400; en-US works)
_LOCALE_FIX = {"en": "en-US", "zh": "zh-CN", "ja": "ja-JP", "es": "es-ES",
              "de": "de-DE", "fr": "fr-FR", "ko": "ko-KR", "pt": "pt-BR"}


def _norm_lang(language: str) -> str:
    return _LOCALE_FIX.get(language.lower(), language)


def get_stats(keyword: str, country: str = "cn", language: str = "zh-CN") -> dict:
    """Fetch weekly impression data for a single keyword."""
    language = _norm_lang(language)
    if not BING_API_KEY:
        print("ERROR: BING_API_KEY not set. See .env.example", file=sys.stderr)
        sys.exit(1)

    q = urllib.parse.quote(keyword)
    url = f"{BASE}/GetKeywordStats?q={q}&country={country}&language={language}&apikey={BING_API_KEY}"

    for attempt in range(3):
        try:
            resp = urllib.request.urlopen(url, timeout=15)
            rows = json.loads(resp.read().decode()).get("d", [])
            if not rows:
                return {"keyword": keyword, "avg_weekly": 0, "latest_weekly": 0,
                        "trend": "no_data", "quarterly": 0, "weeks": 0}

            imps = [r.get("Impressions", 0) for r in rows]
            avg = sum(imps) // len(imps)
            latest = imps[-1]
            trend = _trend(imps)

            return {
                "keyword": keyword,
                "avg_weekly": avg,
                "latest_weekly": latest,
                "trend": trend,
                "quarterly": sum(imps[-13:]),
                "weeks": len(imps),
            }
        except urllib.error.HTTPError as e:
            if attempt < 2:
                time.sleep(1)
            else:
                return {"keyword": keyword, "error": f"HTTP {e.code}"}
        except Exception as e:
            if attempt < 2:
                time.sleep(1)
            else:
                return {"keyword": keyword, "error": str(e)}


def _trend(imps: list[int]) -> str:
    if len(imps) < 8:
        return "insufficient"
    recent = sum(imps[-4:]) // 4
    older = sum(imps[-8:-4]) // 4
    if older == 0:
        return "new"
    change = (recent - older) / older * 100
    arrow = "up" if change > 5 else "down" if change < -5 else "flat"
    return f"{arrow} {abs(change):.0f}%"


def _demand_bar(avg: int) -> str:
    if avg >= 5000:  return "HIGH     "
    if avg >= 1000:  return "MEDIUM   "
    if avg >= 100:   return "LOW      "
    if avg > 0:      return "MINIMAL  "
    return "NONE     "


def _print_row(r: dict):
    if "error" in r:
        print(f"  {r['keyword']:35s}  ERROR: {r['error']}")
        return
    bar = _demand_bar(r["avg_weekly"])
    print(f"  {r['keyword']:35s}  avg/wk={r['avg_weekly']:6d}  "
          f"qtr={r['quarterly']:7d}  {r['trend']:>10s}  [{bar}]")


def main():
    parser = argparse.ArgumentParser(description="Keyword volume via Bing Webmaster API")
    parser.add_argument("keywords", nargs="*", help="Keywords (comma-separated OK)")
    parser.add_argument("--file", "-f", help="File with keywords (one per line)")
    parser.add_argument("--country", "-c", default="cn")
    parser.add_argument("--lang", "-l", default="zh-CN")
    parser.add_argument("--csv", help="Export to CSV")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    kws = []
    if args.file:
        with open(args.file) as f:
            kws = [l.strip() for l in f if l.strip() and not l.startswith("#")]
    for k in args.keywords:
        if "," in k:
            kws.extend(s.strip() for s in k.split(","))
        else:
            kws.append(k)
    seen = set()
    kws = [k for k in kws if not (k in seen or seen.add(k))]

    if not kws:
        parser.print_help()
        sys.exit(1)

    print(f"\n{'='*100}")
    print(f"  Keyword Volume | {len(kws)} keywords | {args.country}/{args.lang}")
    print(f"{'='*100}\n")

    results = []
    for i, kw in enumerate(kws):
        r = get_stats(kw, args.country, args.lang)
        results.append(r)
        _print_row(r)
        if i < len(kws) - 1:
            time.sleep(0.3)

    valid = [r for r in results if r.get("avg_weekly", 0) > 0]
    print(f"\n  {len(valid)} with data | {len(kws) - len(valid)} no data")

    if valid:
        top = sorted(valid, key=lambda r: r["avg_weekly"], reverse=True)[:5]
        print(f"\n  TOP 5:")
        for r in top:
            print(f"    {r['keyword']:35s}  avg/wk={r['avg_weekly']:6d}  {r['trend']}")

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["keyword", "avg_weekly", "latest_weekly", "quarterly",
                        "trend", "weeks", "country", "language"])
            for r in results:
                w.writerow([r.get("keyword"), r.get("avg_weekly", 0),
                            r.get("latest_weekly", 0), r.get("quarterly", 0),
                            r.get("trend", "error"), r.get("weeks", 0),
                            args.country, args.lang])
        print(f"\n  CSV: {args.csv}")

    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
