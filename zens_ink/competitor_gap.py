#!/usr/bin/env python3
"""
Competitor Gap — discover content topics competitors have that you don't.

Analyzes public sitemaps to reveal URL patterns, content categories,
and language coverage. No API key needed.

Usage:
  python3 -m zens_ink.competitor_gap --url https://example.com/sitemap.xml
  python3 -m zens_ink.competitor_gap --url https://tarotap.com/sitemap.xml --lang en
  python3 -m zens_ink.competitor_gap --compare https://site-a.com/sitemap.xml https://site-b.com/sitemap.xml
"""

import argparse
import re
import sys
import urllib.request
from collections import Counter
from urllib.parse import urlparse


def fetch_sitemap(url: str, timeout: int = 10, depth: int = 0) -> list[str]:
    """Fetch and parse sitemap XML, following nested sitemap indexes.

    Accepts a sitemap URL, a site root (auto-discovers via robots.txt /
    common paths), or a bare domain. Never raises — returns [] on failure.
    """
    if depth > 2:
        return []

    url = url.strip()
    if not url:
        return []
    if "://" not in url:
        url = "https://" + url

    candidates = [url]
    # If the URL has no path (bare root/domain), try discovery
    parsed = urlparse(url)
    if parsed.path in ("", "/") and not url.endswith(".xml"):
        candidates = [
            url.rstrip("/") + "/sitemap.xml",
            url.rstrip("/") + "/sitemap_index.xml",
            url.rstrip("/") + "/sitemap-index.xml",
        ]
        # robots.txt Sitemap: declaration wins — check it first
        try:
            req = urllib.request.Request(
                url.rstrip("/") + "/robots.txt",
                headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                for line in resp.read().decode(errors="ignore").splitlines():
                    m = re.match(r"(?i)sitemap:\s*(\S+)", line.strip())
                    if m:
                        candidates.insert(0, m.group(1))
                        break
        except Exception:
            pass

    for cand in candidates:
        req = urllib.request.Request(cand, headers={"User-Agent": "Mozilla/5.0"})
        try:
            resp = urllib.request.urlopen(req, timeout=timeout)
            data = resp.read().decode(errors="ignore")
        except Exception:
            continue
        urls = re.findall(r"<loc>([^<]+)</loc>", data)
        if not urls:
            continue
        xml_urls = [u for u in urls if u.endswith(".xml")]
        page_urls = [u for u in urls if not u.endswith(".xml")]
        for sub in xml_urls[:10]:
            page_urls.extend(fetch_sitemap(sub, timeout, depth + 1))
        return page_urls

    print(f"  [warn] no sitemap found for {url}", file=sys.stderr)
    return []

    urls = re.findall(r"<loc>([^<]+)</loc>", data)
    xml_urls = [u for u in urls if u.endswith(".xml")]
    page_urls = [u for u in urls if not u.endswith(".xml")]

    for sub in xml_urls[:10]:
        page_urls.extend(fetch_sitemap(sub, timeout, depth + 1))

    return page_urls


def extract_topics(urls: list[str], lang: str | None = None) -> Counter:
    """Extract meaningful path segments from URLs."""
    topics = []
    for u in urls:
        path = urlparse(u).path
        if lang and f"/{lang}/" not in path:
            continue
        path = re.sub(r"^/(en|zh|ja|ko|de|fr|it|ru|es|pt|nl|th|tr|pl|da)/", "/", path)
        if re.match(r"^/(pricing|blog|api|admin|login|signup|account)", path):
            continue
        segments = [s for s in path.split("/") if s]
        if segments:
            topics.append("/".join(segments))
    return Counter(topics)


def analyze(url: str, lang: str | None = None):
    print(f"\n{'='*60}")
    print(f"  {urlparse(url).netloc}")
    print(f"{'='*60}")

    urls = fetch_sitemap(url)
    print(f"  Total pages: {len(urls)}")
    if not urls:
        print("  No URLs found — sitemap may be blocked.")
        return [], Counter()

    # Language distribution
    lang_counts = Counter()
    for u in urls:
        m = re.search(r"/(en|zh|ja|ko|de|fr|it|ru|es|pt|nl|th|tr|pl|da)/", u)
        lang_counts[m.group(1) if m else "root"] += 1
    print(f"  Languages: {dict(lang_counts.most_common(10))}")

    # Topic patterns
    topics = extract_topics(urls, lang)
    label = f"[{lang}]" if lang else "[ALL]"
    print(f"\n  Content patterns {label} ({len(topics)} unique):")
    for topic, count in topics.most_common(25):
        print(f"    {count:3d}x  {topic}")

    return urls, topics


def main():
    p = argparse.ArgumentParser(description="Competitor content gap analysis via sitemaps")
    p.add_argument("--url", "-u", help="Single competitor sitemap URL")
    p.add_argument("--compare", "-c", nargs="+", help="Multiple sitemaps to compare")
    p.add_argument("--lang", "-l", help="Filter by language (en, zh, etc.)")
    args = p.parse_args()

    urls_to_check = []
    if args.compare:
        urls_to_check = args.compare
    elif args.url:
        urls_to_check = [args.url]
    else:
        p.print_help()
        sys.exit(1)

    all_topics = {}
    for url in urls_to_check:
        _, topics = analyze(url, args.lang)
        all_topics[urlparse(url).netloc] = set(topics.keys())

    if len(all_topics) > 1:
        print(f"\n{'='*60}")
        print("  Cross-site comparison")
        print(f"{'='*60}")
        common = set.intersection(*all_topics.values())
        print(f"\n  Shared topics ({len(common)}):")
        for t in sorted(common)[:20]:
            print(f"    {t}")

        for site, topics in all_topics.items():
            others = set.union(*[s for k, s in all_topics.items() if k != site])
            unique = topics - others
            if unique:
                print(f"\n  Unique to {site} ({len(unique)}):")
                for t in sorted(unique)[:15]:
                    print(f"    {t}")


if __name__ == "__main__":
    main()
