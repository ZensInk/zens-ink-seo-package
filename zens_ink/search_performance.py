#!/usr/bin/env python3
"""
Search Performance — your site's real Google search data.

Uses the Google Search Console API (free) to show which queries
bring impressions, clicks, and what position you rank at.

Requires one-time OAuth setup — run setup_gsc.py first.

Usage:
  python3 -m zens_ink.search_performance --queries
  python3 -m zens_ink.search_performance --pages
  python3 -m zens_ink.search_performance --page /blog/
  python3 -m zens_ink.search_performance --country --start 2025-01-01
"""

import argparse
import datetime
import json
import sys
import urllib.parse
import urllib.request

from zens_ink.config import ADC_PATH, GSC_SITE_URL


def get_access_token() -> str:
    try:
        with open(ADC_PATH) as f:
            creds = json.load(f)
    except FileNotFoundError:
        print(f"ERROR: No credentials at {ADC_PATH}\n"
              f"Run: python3 -m zens_ink.setup_gsc", file=sys.stderr)
        sys.exit(1)

    data = urllib.parse.urlencode({
        "client_id": creds["client_id"],
        "client_secret": creds["client_secret"],
        "refresh_token": creds["refresh_token"],
        "grant_type": "refresh_token",
    }).encode()
    resp = urllib.request.urlopen(
        urllib.request.Request("https://oauth2.googleapis.com/token", data=data), timeout=15)
    return json.loads(resp.read().decode())["access_token"]


def query(token: str, dimensions: list[str], start: str, end: str,
          page_filter: str | None = None, limit: int = 100) -> dict:
    payload = {"startDate": start, "endDate": end, "dimensions": dimensions, "rowLimit": limit}
    if page_filter:
        payload["dimensionFilterGroups"] = [{
            "filters": [{"dimension": "page", "operator": "contains", "expression": page_filter}]
        }]

    site = urllib.parse.quote(GSC_SITE_URL, safe="")
    url = (f"https://searchconsole.googleapis.com/webmasters/v3/sites/{site}"
           f"/searchAnalytics/query")

    def _post(p):
        req = urllib.request.Request(
            url, data=json.dumps(p).encode(),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            method="POST")
        resp = urllib.request.urlopen(req, timeout=15)
        return json.loads(resp.read().decode())

    # Paginate with startRow — a single rowLimit page silently truncates the
    # totals on larger properties (GSC caps at 25,000 rows per day range)
    rows = []
    start_row = 0
    while True:
        payload["startRow"] = start_row
        batch = _post(payload).get("rows", [])
        rows.extend(batch)
        if len(batch) < limit or len(rows) >= 25000:
            break
        start_row += len(batch)
    return {"rows": rows}


def main():
    if not GSC_SITE_URL:
        print("ERROR: GSC_SITE_URL not set in .env", file=sys.stderr)
        sys.exit(1)

    p = argparse.ArgumentParser(description="Search performance via Google Search Console")
    p.add_argument("--start", default="2025-01-01")
    p.add_argument("--end", default="today")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--queries", action="store_true")
    p.add_argument("--pages", action="store_true")
    p.add_argument("--page", type=str, help="Filter to specific page path")
    p.add_argument("--country", action="store_true")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    end = datetime.date.today().isoformat() if args.end == "today" else args.end
    if args.pages:
        dims = ["page"]
    elif args.country:
        dims = ["country"]
    else:
        dims = ["query"]  # default

    token = get_access_token()
    result = query(token, dims, args.start, end, args.page, args.limit)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    rows = result.get("rows", [])
    total_imp = sum(r.get("impressions", 0) for r in rows)
    total_clk = sum(r.get("clicks", 0) for r in rows)

    print(f"\n{'='*80}")
    print(f"  {GSC_SITE_URL} | {', '.join(dims)} | {args.start} - {end}")
    if args.page:
        print(f"  Page filter: {args.page}")
    print(f"  {len(rows)} rows | {total_imp} impressions | {total_clk} clicks")
    print(f"{'='*80}\n")

    if not rows:
        print("  No data yet — Google hasn't indexed your pages or traffic is zero.")
        return

    for r in sorted(rows, key=lambda x: x.get("impressions", 0), reverse=True):
        label = " / ".join(r.get("keys", ["?"]))
        print(f"  {label:45s}  imp={r.get('impressions',0):5d}  "
              f"clk={r.get('clicks',0):3d}  "
              f"CTR={r.get('ctr',0)*100:4.1f}%  "
              f"pos={r.get('position',0):5.1f}")


if __name__ == "__main__":
    main()
