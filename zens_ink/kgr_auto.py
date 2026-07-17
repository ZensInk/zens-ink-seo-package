#!/usr/bin/env python3
"""
KGR Auto — automated keyword opportunity scoring.

Scores each keyword by comparing competition signals (Google autocomplete
saturation) against search demand (Bing Webmaster volume). Produces an
opportunity score and priority tier for content planning.

Note: This uses an approximation of the KGR (Keyword Golden Ratio) concept.
True KGR requires allintitle: counts from live Google search, which cannot
be reliably obtained via free APIs. Instead, we use autocomplete-based
competition estimation combined with Bing volume data.

Scoring formula:
  opportunity = volume_score × (1 − competition_score) × trend_multiplier

  volume_score      = min(avg_weekly_volume / 500, 1.0)
  competition_score = min(autocomplete_density / 20, 1.0)
  trend_multiplier  = 1.2 (up), 1.0 (flat), 0.8 (down)

Usage:
  python3 -m zens_ink_pro.kgr_auto "tarot meaning" "dream interpretation"
  python3 -m zens_ink_pro.kgr_auto --file keywords.txt --country us --lang en-US
  python3 -m zens_ink_pro.kgr_auto --file keywords.txt --json
"""

import argparse
import csv
import json
import sys
import time

# Reuse free toolkit functions
try:
    from zens_ink.keyword_research import get_autocomplete
    from zens_ink.keyword_volume import get_stats as get_volume
    from zens_ink.config import BING_API_KEY
except ImportError:
    print("ERROR: zens-ink free toolkit not found.\n"
          "Install: pip install zens-ink or git clone zens-ink repo",
          file=sys.stderr)
    sys.exit(1)


# ── Scoring ────────────────────────────────────────────────

def score_keyword(keyword: str, lang: str = "en",
                  country: str = "us", bing_lang: str = "en-US") -> dict:
    """Score a single keyword's opportunity."""
    hl = "zh-CN" if lang == "zh" else "en"

    # Competition signal: autocomplete density
    suggestions = get_autocomplete(keyword, hl)
    in_autocomplete = keyword.lower() in [s.lower() for s in suggestions]
    autocomplete_density = len(suggestions)

    competition_score = min(autocomplete_density / 20, 1.0)
    # Bonus competition if keyword itself is in autocomplete (saturated)
    if in_autocomplete:
        competition_score = min(competition_score + 0.15, 1.0)

    # Volume signal
    vol_data = get_volume(keyword, country, bing_lang)
    avg_weekly = vol_data.get("avg_weekly", 0)
    trend = vol_data.get("trend", "no_data")

    volume_score = min(avg_weekly / 500, 1.0)

    # Trend multiplier
    if trend.startswith("up"):
        trend_mult = 1.2
    elif trend.startswith("down"):
        trend_mult = 0.8
    else:
        trend_mult = 1.0

    # Final opportunity score (0-100)
    opportunity = volume_score * (1 - competition_score) * trend_mult * 100

    # Priority tier
    if opportunity >= 60:
        tier = "P0"
    elif opportunity >= 40:
        tier = "P1"
    elif opportunity >= 20:
        tier = "P2"
    else:
        tier = "P3"

    return {
        "keyword": keyword,
        "avg_weekly_volume": avg_weekly,
        "quarterly_volume": vol_data.get("quarterly", 0),
        "trend": trend,
        "autocomplete_count": autocomplete_density,
        "in_autocomplete": in_autocomplete,
        "competition_score": round(competition_score, 3),
        "volume_score": round(volume_score, 3),
        "opportunity_score": round(opportunity, 1),
        "priority": tier,
        "country": country,
    }


def score_keywords(keywords: list[str], lang: str = "en",
                   country: str = "us", bing_lang: str = "en-US") -> list[dict]:
    """Score a batch of keywords with rate limiting."""
    results = []
    total = len(keywords)
    for i, kw in enumerate(keywords):
        print(f"  [{i+1}/{total}] {kw}...", file=sys.stderr, end="", flush=True)
        r = score_keyword(kw, lang, country, bing_lang)
        results.append(r)
        print(f"  vol={r['avg_weekly_volume']:5d}  opp={r['opportunity_score']:5.1f}  {r['priority']}",
              file=sys.stderr)
        if i < total - 1:
            time.sleep(0.5)  # Rate limit: autocomplete + Bing
    return results


# ── I/O ────────────────────────────────────────────────────

def read_keywords(filepath: str | None = None, args: list[str] | None = None) -> list[str]:
    keywords = []
    if filepath:
        with open(filepath, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    keywords.append(line.split(",")[0].strip().strip('"'))
    if args:
        keywords.extend(args)
    seen = set()
    return [k for k in keywords if not (k.lower() in seen or seen.add(k.lower()))]


def main():
    p = argparse.ArgumentParser(description="Automated keyword opportunity scoring")
    p.add_argument("keywords", nargs="*", help="Keywords to score")
    p.add_argument("--file", "-f", help="File with keywords")
    p.add_argument("--lang", "-l", default="en", choices=["en", "zh"])
    p.add_argument("--country", "-c", default="us")
    p.add_argument("--bing-lang", default=None, help="Bing language (default: auto from --lang)")
    p.add_argument("--json", action="store_true")
    p.add_argument("--csv", help="Export to CSV")
    args = p.parse_args()

    bing_lang = args.bing_lang or ("zh-CN" if args.lang == "zh" else "en-US")
    keywords = read_keywords(args.file, args.keywords)
    if not keywords:
        p.print_help()
        sys.exit(1)

    if not BING_API_KEY:
        print("WARNING: BING_API_KEY not set — volume will be 0 for all keywords.\n"
              "Set it in .env to get real volume data.\n", file=sys.stderr)

    print(f"\n{'='*70}", file=sys.stderr)
    print(f"  Scoring {len(keywords)} keywords | {args.lang} | {args.country}", file=sys.stderr)
    print(f"{'='*70}\n", file=sys.stderr)

    results = score_keywords(keywords, args.lang, args.country, bing_lang)
    results.sort(key=lambda r: r["opportunity_score"], reverse=True)

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print(f"\n{'='*90}")
        print(f"  Keyword | Vol/wk | Trend | Comp | Opp Score | Tier")
        print(f"{'='*90}")
        for r in results:
            print(f"  {r['keyword']:35s}  {r['avg_weekly_volume']:6d}  "
                  f"{r['trend']:>10s}  {r['competition_score']:.2f}  "
                  f"{r['opportunity_score']:7.1f}   {r['priority']}")
        print(f"\n  P0={sum(1 for r in results if r['priority']=='P0')}  "
              f"P1={sum(1 for r in results if r['priority']=='P1')}  "
              f"P2={sum(1 for r in results if r['priority']=='P2')}  "
              f"P3={sum(1 for r in results if r['priority']=='P3')}")

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["keyword", "avg_weekly_volume", "quarterly_volume", "trend",
                        "autocomplete_count", "competition_score", "volume_score",
                        "opportunity_score", "priority", "country"])
            for r in results:
                w.writerow([r["keyword"], r["avg_weekly_volume"], r["quarterly_volume"],
                            r["trend"], r["autocomplete_count"], r["competition_score"],
                            r["volume_score"], r["opportunity_score"], r["priority"],
                            r["country"]])
        print(f"\n  CSV: {args.csv}")


if __name__ == "__main__":
    main()
