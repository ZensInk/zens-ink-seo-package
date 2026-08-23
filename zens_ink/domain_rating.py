#!/usr/bin/env python3
"""
Domain Rating — real Ahrefs DR via the free public API.

Ahrefs exposes a free, no-cost endpoint (v3/public/domain-rating-free) that
returns the Domain Rating (0-100) for any domain or URL. It only requires a
free APIv3 key. This closes the "off-page authority" gap that kd.py works
around with curated authority-domain proxies.

License note: Ahrefs' Domain Rating License requires attribution.
Always keep the "Domain Rating by Ahrefs" credit in outputs/exports.

Usage:
  python3 -m zens_ink.domain_rating example.com
  python3 -m zens_ink.domain_rating a.com b.com c.com --json
  python3 -m zens_ink.domain_rating --file domains.txt --csv dr.csv
  cat serp_domains.txt | python3 -m zens_ink.domain_rating --json     # stdin pipe
"""

import json
import csv
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path

from zens_ink.config import AHREFS_API_KEY

AHREFS_DR_URL = "https://api.ahrefs.com/v3/public/domain-rating-free"
ATTRIBUTION = "Domain Rating by Ahrefs (https://ahrefs.com/)"

CACHE_PATH = Path(__file__).resolve().parent.parent / "dr-cache.json"


# ── Input normalization ────────────────────────────────────────────────────

def normalize_target(raw):
    """Accept domain or full URL; return a canonical registrable string.

    'https://www.example.com/page?x=1' -> 'example.com'
    """
    raw = raw.strip().lower()
    if not raw:
        return ""
    if "://" in raw:
        raw = urllib.parse.urlparse(raw).netloc or raw
    raw = raw.split("/")[0].split("?")[0].split("#")[0]
    raw = raw.split("@")[-1]  # strip userinfo if any
    if raw.startswith("www."):
        raw = raw[4:]
    return raw


# ── Cache ───────────────────────────────────────────────────────────────────

def _load_cache():
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_cache(cache):
    try:
        CACHE_PATH.write_text(
            json.dumps(cache, indent=1, ensure_ascii=False), encoding="utf-8"
        )
    except Exception:
        pass


# ── API ─────────────────────────────────────────────────────────────────────

def get_domain_rating(target, use_cache=True, retries=3):
    """Query Ahrefs free DR endpoint for one domain/URL.

    Returns dict: {target, domain_rating, cached, error}
    """
    key = normalize_target(target)
    if not key:
        return {"target": target, "domain_rating": None, "cached": False,
                "error": "empty target"}

    cache = _load_cache() if use_cache else {}
    if use_cache and key in cache:
        return {"target": key, "domain_rating": cache[key],
                "cached": True, "error": None}

    if not AHREFS_API_KEY:
        return {"target": key, "domain_rating": None, "cached": False,
                "error": "AHREFS_API_KEY not set (free key: ahrefs.com -> "
                         "Account settings -> API keys)"}

    url = f"{AHREFS_DR_URL}?{urllib.parse.urlencode({'target': key, 'output': 'json'})}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {AHREFS_API_KEY}",
        "Accept": "application/json",
    })

    data = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                break
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < retries - 1:
                time.sleep(5 * (attempt + 1))  # rate-limit backoff
                continue
            detail = ""
            try:
                detail = e.read().decode("utf-8", "replace")[:200]
            except Exception:
                pass
            return {"target": key, "domain_rating": None, "cached": False,
                    "error": f"HTTP {e.code} {detail}".strip()}
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2)
                continue
            return {"target": key, "domain_rating": None, "cached": False,
                    "error": str(e)}

    dr = None
    if data:
        dr = (data.get("domain_rating") or {}).get("domain_rating")
    if dr is None:
        return {"target": key, "domain_rating": None, "cached": False,
                "error": f"unexpected response: {json.dumps(data)[:200]}"}

    if use_cache:
        cache = _load_cache()
        cache[key] = dr
        _save_cache(cache)

    return {"target": key, "domain_rating": dr, "cached": False, "error": None}


def batch_domain_rating(targets, use_cache=True, delay=1.2):
    """Look up multiple domains with polite pacing. Returns list of dicts."""
    results = []
    seen = set()
    for i, t in enumerate(targets):
        key = normalize_target(t)
        if not key or key in seen:
            continue
        seen.add(key)
        r = get_domain_rating(t, use_cache=use_cache)
        results.append(r)
        dr = r["domain_rating"]
        status = f"DR {dr:.0f}" if dr is not None else f"ERR {r['error'][:40]}"
        cached = " (cache)" if r["cached"] else ""
        print(f"  [{i+1}/{len(targets)}] {key:<40} {status}{cached}")
        if i < len(targets) - 1 and not r["cached"]:
            time.sleep(delay)
    return results


# ── CLI ─────────────────────────────────────────────────────────────────────

def main():
    import argparse
    p = argparse.ArgumentParser(
        description="Domain Rating lookup via Ahrefs free public API",
        epilog=f"Data: {ATTRIBUTION}")
    p.add_argument("domains", nargs="*", help="Domain(s) or full URL(s)")
    p.add_argument("--file", "-f", help="File with one domain per line")
    p.add_argument("--csv", help="Export results to CSV")
    p.add_argument("--json", action="store_true", help="JSON output")
    p.add_argument("--no-cache", action="store_true", help="Bypass local cache")
    args = p.parse_args()

    targets = list(args.domains)
    if args.file:
        with open(args.file) as f:
            targets += [l.strip() for l in f if l.strip() and not l.startswith("#")]
    if not targets and not sys.stdin.isatty():
        targets += [l.strip() for l in sys.stdin if l.strip() and not l.startswith("#")]

    if not targets:
        p.print_help()
        sys.exit(1)

    if not AHREFS_API_KEY:
        print("ERROR: AHREFS_API_KEY not set. Generate a free APIv3 key at "
              "app.ahrefs.com/account/api-keys and put it in .env",
              file=sys.stderr)
        sys.exit(1)

    print(f"\n  Domain Rating | {len(targets)} target(s) | Data: {ATTRIBUTION}\n")
    results = batch_domain_rating(targets, use_cache=not args.no_cache)

    ok = [r for r in results if r["domain_rating"] is not None]
    if ok:
        avg = sum(r["domain_rating"] for r in ok) / len(ok)
        top = max(ok, key=lambda r: r["domain_rating"])
        print(f"\n  ── {len(ok)}/{len(results)} resolved | avg DR {avg:.1f} | "
              f"strongest: {top['target']} (DR {top['domain_rating']:.0f})")

    if args.json:
        payload = {"data": results, "attribution": ATTRIBUTION}
        print(json.dumps(payload, indent=2, ensure_ascii=False))

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["domain", "domain_rating", "source"])
            for r in results:
                w.writerow([r["target"], r["domain_rating"] if r["domain_rating"] is not None else "",
                            "ahrefs-free-api"])
        print(f"\n  CSV: {args.csv}")


if __name__ == "__main__":
    main()
