#!/usr/bin/env python3
"""
LLMS Generator — auto-build llms.txt + llms-full.txt from a build.

AI discovery infrastructure generator: scans your static build (or
sitemap) and emits the two-tier catalog pattern that modern AI crawlers
understand:

  llms.txt       — curated short list: brand line, core pages, sections
  llms-full.txt  — comprehensive catalog: every page with title/desc

Works from a dist directory (Astro/Next/Hugo static output) or a
remote sitemap.xml. Pure Python stdlib, zero dependencies.

Usage:
  python3 -m zens_ink.llms_gen --dist dist --site https://example.com
  python3 -m zens_ink.llms_gen --sitemap https://example.com/sitemap.xml --site https://example.com
  python3 -m zens_ink.llms_gen --dist dist --site https://example.com --full-only
"""

import argparse
import re
import sys
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse


class MetaParser(HTMLParser):
    """Extract title + meta description + h1 + date from a built page."""

    def __init__(self):
        super().__init__()
        self.title = ""
        self.description = ""
        self.h1 = ""
        self.in_title = False
        self.in_h1 = False
        self.date = ""

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self.in_title = True
        elif tag == "h1" and not self.h1:
            self.in_h1 = True
        elif tag == "meta":
            d = dict(attrs)
            name = (d.get("name") or d.get("property") or "").lower()
            if name == "description" and d.get("content"):
                self.description = d["content"].strip()
            if name in ("article:published_time", "og:updated_time") and d.get("content") and not self.date:
                self.date = d["content"][:10]

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        elif tag == "h1":
            self.in_h1 = False

    def handle_data(self, data):
        if self.in_title and not self.title:
            self.title = data.strip()
        elif self.in_h1:
            self.h1 = (self.h1 + " " + data.strip()).strip()


SKIP_DIRS = {"admin", "api", "account", "404"}


def scan_dist(dist: Path, base_url: str) -> list:
    pages = []
    for idx in sorted(dist.rglob("index.html")):
        rel = idx.parent.relative_to(dist).as_posix()
        url = "/" if rel == "." else "/" + rel + "/"
        seg0 = rel.split("/")[0] if rel != "." else ""
        if seg0 in SKIP_DIRS:
            continue
        raw = idx.read_text(encoding="utf-8", errors="replace")
        if idx.stat().st_size < 200000 and "noindex" in raw[:4000]:
            continue
        parser = MetaParser()
        try:
            parser.feed(raw)
        except Exception:
            continue
        title = parser.title or parser.h1 or url
        pages.append({
            "url": base_url.rstrip("/") + url,
            "path": url,
            "title": title,
            "description": parser.description,
            "date": parser.date,
            "depth": 0 if url == "/" else url.rstrip("/").count("/"),
        })
    return pages


def scan_sitemap(sitemap_url: str) -> list:
    """Fetch sitemap (handles sitemap-index too) and probe each URL."""
    urls = []

    def fetch(u):
        req = urllib.request.Request(u, headers={"User-Agent": "zens-ink llms_gen"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8", errors="replace")

    xml = fetch(sitemap_url)
    if "<sitemapindex" in xml:
        for m in re.finditer(r"<loc>([^<]+)</loc>", xml):
            xml2 = fetch(m.group(1))
            urls += re.findall(r"<loc>([^<]+)</loc>", xml2)
    else:
        urls = re.findall(r"<loc>([^<]+)</loc>", xml)

    pages = []
    for u in urls:
        path = urlparse(u).path or "/"
        seg0 = path.strip("/").split("/")[0]
        if seg0 in SKIP_DIRS:
            continue
        parser = MetaParser()
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "zens-ink llms_gen"})
            with urllib.request.urlopen(req, timeout=20) as r:
                parser.feed(r.read().decode("utf-8", errors="replace"))
        except Exception:
            parser.title = path
        title = parser.title or path
        pages.append({
            "url": u,
            "path": path if path.endswith("/") else path + "/",
            "title": title,
            "description": parser.description,
            "date": parser.date,
            "depth": 0 if path == "/" else path.strip("/").count("/"),
        })
    return pages


def group_by_section(pages: list) -> dict:
    sections = {}
    for p in pages:
        if p["path"] == "/":
            sections.setdefault("(homepage)", []).append(p)
        else:
            seg = p["path"].strip("/").split("/")[0].replace("-", " ").title()
            sections.setdefault(seg, []).append(p)
    return sections


def build_llms_txt(site: str, pages: list, name: str, tagline: str) -> str:
    """Curated tier: top-level + section roots only."""
    out = ["# " + name, "> " + tagline, "> Site: " + site, ""]
    out.append("## Core Pages")
    roots = [p for p in pages if p["depth"] <= 1]
    for p in sorted(roots, key=lambda x: x["path"]):
        desc = p.get("description", "")
        if len(desc) > 110:
            desc = desc[:110] + "…"
        out.append("- {}: {}".format(p["url"], p["title"]) + (" — " + desc if desc else ""))
    out.append("")
    out.append("## Full Catalog")
    out.append("- {}/llms-full.txt: every page on this site with descriptions".format(site.rstrip("/")))
    return "\n".join(out) + "\n"


def build_llms_full(site: str, pages: list, name: str, tagline: str) -> str:
    out = ["# {} — Full Catalog".format(name), "> " + tagline, "> Site: " + site, ""]
    for section, items in sorted(group_by_section(pages).items()):
        out.append("## " + section)
        for p in sorted(items, key=lambda x: x["path"]):
            date = " ({})".format(p["date"]) if p.get("date") else ""
            desc = p.get("description", "")
            out.append("- {}:{}{}".format(p["url"], p["title"], date) + ("\n  " + desc if desc else ""))
        out.append("")
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser(
        prog="zens_ink.llms_gen",
        description="Generate llms.txt + llms-full.txt from a static build or sitemap",
    )
    ap.add_argument("--dist", help="Static build directory (e.g. dist/)")
    ap.add_argument("--sitemap", help="Remote sitemap.xml URL (alternative to --dist)")
    ap.add_argument("--site", required=True, help="Canonical site URL")
    ap.add_argument("--name", help="Brand name for the header (default: domain)")
    ap.add_argument("--tagline", default="", help="One-line description")
    ap.add_argument("--out", help="Output directory (default: dist/ or cwd)")
    ap.add_argument("--full-only", action="store_true", help="Only write llms-full.txt")
    args = ap.parse_args()

    if not args.dist and not args.sitemap:
        ap.error("need --dist or --sitemap")

    if args.dist:
        pages = scan_dist(Path(args.dist), args.site)
        out_dir = Path(args.out or args.dist)
    else:
        pages = scan_sitemap(args.sitemap)
        out_dir = Path(args.out or ".")

    if not pages:
        print("No pages found.")
        sys.exit(1)

    name = args.name or urlparse(args.site).netloc.split(".")[0].title()
    tagline = args.tagline or "{} — {} pages, generated for AI discovery".format(name, len(pages))

    out_dir.mkdir(parents=True, exist_ok=True)
    if not args.full_only:
        llms = build_llms_txt(args.site, pages, name, tagline)
        (out_dir / "llms.txt").write_text(llms, encoding="utf-8")
        print("wrote {} ({} bytes, curated tier)".format(out_dir / "llms.txt", len(llms)))

    full = build_llms_full(args.site, pages, name, tagline)
    (out_dir / "llms-full.txt").write_text(full, encoding="utf-8")
    print("wrote {} ({} bytes, {} pages)".format(out_dir / "llms-full.txt", len(full), len(pages)))


if __name__ == "__main__":
    main()
