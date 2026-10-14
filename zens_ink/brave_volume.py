#!/usr/bin/env python3
"""
Brave Search Volume — supplement Bing's volume gaps.

Brave Search API doesn't have a dedicated volume endpoint, but we can
estimate relative search demand through result diversity analysis:
- Total result count (more results = more popular topic)
- Number of dedicated articles (informational demand)
- Presence of ads (commercial intent = higher volume)
- Freshness of results (active topic = ongoing searches)

This gives a relative demand score (1-100) that supplements Bing's
absolute volume numbers where Bing returns 0 or no data.

Usage:
  python3 -m zens_ink.brave_volume "tarot card meanings"
  python3 -m zens_ink.brave_volume --file keywords.txt --csv results.csv
"""

import json
import csv
import sys
import time
import math
import urllib.request
import urllib.parse

from zens_ink.config import BRAVE_API_KEY

BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"


def search_brave(keyword, count=20, country="US", search_lang="en"):
    """Query Brave Search API."""
    if not BRAVE_API_KEY:
        return None

    params = urllib.parse.urlencode({
        "q": keyword,
        "count": count,
        "country": country,
        "search_lang": search_lang,
        "result_filter": "web",
    })
    url = f"{BRAVE_URL}?{params}"

    req = urllib.request.Request(url, headers={
        "X-Subscription-Token": BRAVE_API_KEY,
        "Accept": "application/json",
    })

    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 2:
                time.sleep(3 * (attempt + 1))  # rate limit backoff
                continue
            return {"error": f"HTTP {e.code}"}
        except Exception as e:
            if attempt < 2:
                time.sleep(2)
                continue
            return {"error": str(e)}


def estimate_demand(keyword, brave_data):
    """
    Estimate relative search demand (0-100) from Brave SERP signals.
    
    Heuristics:
    - Total results count: log-scaled (10K results = score ~30, 1M = ~60)
    - Dedicated articles: each adds to demand signal
    - Title keyword matches: indicates established content ecosystem
    - Result freshness: recent results = active search demand
    """
    if not brave_data or brave_data.get("error"):
        err = (brave_data or {}).get("error", "no data")
        return {"keyword": keyword, "demand_score": 0, "source": "brave", "error": err}

    web = brave_data.get("web", {})
    results = web.get("results", [])

    if not results:
        return {"keyword": keyword, "demand_score": 0, "source": "brave", "note": "no results"}

    # Total result count (Brave sometimes returns this). NOTE: if live
    # responses never carry "count", the log-scaled signal stays at the flat
    # 15 fallback — needs one keyed live response to confirm (audit #40).
    total_count = web.get("count", 0) or 0

    # Score from total count (log-scaled)
    if total_count > 0:
        count_score = min(60, math.log10(max(1, total_count)) * 8)
    else:
        count_score = 15  # fallback if no count

    # Dedicated article score (title matches keyword)
    kw_lower = keyword.lower()
    kw_words = [w for w in kw_lower.split() if len(w) > 2]
    dedicated = 0
    title_matches = 0
    for r in results:
        title = r.get("title", "").lower()
        if kw_words:
            matches = sum(1 for w in kw_words if w in title)
            if matches >= max(1, len(kw_words) * 0.5):
                dedicated += 1
                title_matches += 1

    dedicated_score = min(25, dedicated * 3.5)

    # Freshness score (results published recently = active topic)
    fresh_count = 0
    for r in results:
        # Brave sometimes returns page_age or extra_snippets with dates
        page_age = r.get("page_age", "")
        if page_age and "2025" in str(page_age):
            fresh_count += 1
        elif page_age and "2026" in str(page_age):
            fresh_count += 1
    freshness_score = min(15, fresh_count * 3)

    # Combine
    demand_score = min(100, count_score + dedicated_score + freshness_score)

    # Estimate monthly volume from demand score
    # Calibration: demand_score 30 → ~500/mo, 50 → ~2K/mo, 70 → ~10K/mo, 90 → ~50K/mo
    if demand_score >= 80:
        est_volume = int(30000 + (demand_score - 80) * 3000)
    elif demand_score >= 60:
        est_volume = int(5000 + (demand_score - 60) * 1000)
    elif demand_score >= 40:
        est_volume = int(1000 + (demand_score - 40) * 200)
    elif demand_score >= 20:
        est_volume = int(200 + (demand_score - 20) * 40)
    else:
        est_volume = max(10, int(demand_score * 10))

    return {
        "keyword": keyword,
        "demand_score": round(demand_score, 1),
        "estimated_monthly_volume": est_volume,
        "volume_source": "brave_estimate",
        "result_count": total_count,
        "dedicated_results": dedicated,
        "fresh_results": fresh_count,
        "total_results_seen": len(results),
    }


def batch_volume(keywords, country="US", lang="en", delay=0.5):
    """Run volume estimation on a batch of keywords."""
    results = []
    for i, kw in enumerate(keywords):
        brave_data = search_brave(kw, count=20, country=country, search_lang=lang)
        result = estimate_demand(kw, brave_data)
        results.append(result)

        score = result.get("demand_score", 0)
        vol = result.get("estimated_monthly_volume", 0)
        print(f"  [{i+1}/{len(keywords)}] {kw[:40]:<40}  demand={score:>5}  est_vol={vol:>6}")

        if i < len(keywords) - 1:
            time.sleep(delay)

    return results


def main():
    import argparse
    p = argparse.ArgumentParser(description="Brave Search volume estimation")
    p.add_argument("keyword", nargs="?", help="Single keyword")
    p.add_argument("--file", "-f", help="File with keywords")
    p.add_argument("--country", "-c", default="US")
    p.add_argument("--lang", "-l", default="en")
    p.add_argument("--zh", action="store_true", help="Chinese mode")
    p.add_argument("--csv", help="Export to CSV")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    if not BRAVE_API_KEY:
        print("ERROR: BRAVE_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    kws = []
    if args.file:
        with open(args.file) as f:
            kws = [l.strip() for l in f if l.strip() and not l.startswith("#")]
    if args.keyword:
        kws.append(args.keyword)

    if not kws:
        p.print_help()
        sys.exit(1)

    country = "CN" if args.zh else args.country
    lang = "zh" if args.zh else args.lang

    print(f"\n  Brave Volume Estimation | {len(kws)} keywords | {country}/{lang}\n")

    results = batch_volume(kws, country=country, lang=lang)

    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["keyword", "demand_score", "estimated_monthly_volume",
                        "result_count", "dedicated_results", "fresh_results"])
            for r in results:
                w.writerow([r.get("keyword"), r.get("demand_score", 0),
                           r.get("estimated_monthly_volume", 0),
                           r.get("result_count", 0), r.get("dedicated_results", 0),
                           r.get("fresh_results", 0)])
        print(f"\n  CSV: {args.csv}")


if __name__ == "__main__":
    main()
