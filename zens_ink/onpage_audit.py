#!/usr/bin/env python3
"""
On-Page Audit — quality scoring for built HTML pages.

Goes beyond the free site_audit (which checks existence) to score
each page on 7 dimensions:

  1. Title tag (length, keyword, uniqueness)
  2. Meta description (length, keyword, uniqueness)
  3. Heading structure (H1 count, hierarchy, keyword presence)
  4. Image optimization (alt coverage)
  5. Internal links (count, density)
  6. URL structure (length, hyphens, lowercase, no query)
  7. Content structure (word count, BLUF check)

Score: 0-100 per page, with actionable recommendations.

Works on any static build output (Astro, Next.js export, Hugo, etc.).
Pure stdlib (html.parser).

Usage:
  python3 -m zens_ink_pro.onpage_audit --dist dist --sitemap dist/sitemap.xml
  python3 -m zens_ink_pro.onpage_audit --dist dist --sitemap dist/sitemap.xml --json
  python3 -m zens_ink_pro.onpage_audit --dist dist --keywords keywords.txt
"""

import argparse
import json
import math
import re
import sys
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

# Reuse sitemap parsing from free site_audit
try:
    from zens_ink.site_audit import parse_sitemap
except ImportError:
    def parse_sitemap(sitemap_path: Path, base_path: str = "") -> set:
        """Fallback: extract URL paths from sitemap XML."""
        if not sitemap_path.exists():
            for alt in ["sitemap-0.xml", "sitemap.xml"]:
                alt_path = sitemap_path.parent / alt
                if alt_path.exists():
                    sitemap_path = alt_path
                    break
            else:
                return set()
        text = sitemap_path.read_text(encoding="utf-8", errors="replace")
        locs = re.findall(r"<loc>(.*?)</loc>", text)
        paths = set()
        for loc in locs:
            loc = loc.strip()
            if base_path and not loc.startswith(base_path):
                continue
            p = urlparse(loc).path or loc
            paths.add(p)
        return paths


_STATIC_EXTS = {
    ".svg", ".png", ".jpg", ".jpeg", ".gif", ".webp",
    ".css", ".js", ".xml", ".json", ".webmanifest",
    ".woff", ".woff2", ".ttf", ".otf", ".txt", ".ico",
    ".pdf", ".zip", ".mp4", ".mp3", ".map",
}


# ── HTML Parser ─────────────────────────────────────────────

class PageParser(HTMLParser):
    """Extract on-page SEO signals from a single HTML file."""

    def __init__(self):
        super().__init__()
        self.title = ""
        self._in_title = False
        self.meta_desc = ""
        self.h1_texts = []
        self.h2_count = 0
        self.h3_count = 0
        self._heading_levels = []  # track order for hierarchy check
        self._current_tag = None
        self._current_text = ""
        self._in_h1 = False

        # Images
        self.img_total = 0
        self.img_missing_alt = 0
        self.img_empty_alt = 0

        # Links
        self.internal_links = []
        self.external_links = []

        # Content
        self.text_parts = []
        self._word_count = None

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        tag_l = tag.lower()

        if tag_l == "title":
            self._in_title = True
        elif tag_l == "meta":
            name = attrs_dict.get("name", "").lower()
            prop = attrs_dict.get("property", "").lower()
            if name == "description":
                self.meta_desc = attrs_dict.get("content", "")
        elif tag_l == "h1":
            self._in_h1 = True
            self._current_text = ""
            self._heading_levels.append(1)
        elif tag_l == "h2":
            self.h2_count += 1
            self._heading_levels.append(2)
        elif tag_l == "h3":
            self.h3_count += 1
            self._heading_levels.append(3)
        elif tag_l == "img":
            self.img_total += 1
            if "alt" not in attrs_dict:
                self.img_missing_alt += 1
            elif not attrs_dict["alt"].strip():
                self.img_empty_alt += 1
        elif tag_l == "a":
            href = attrs_dict.get("href", "")
            if href and not href.startswith(("#", "mailto:", "javascript:")):
                if href.startswith("http"):
                    self.external_links.append(href)
                elif href.startswith("/"):
                    self.internal_links.append(href)

    def handle_endtag(self, tag):
        tag_l = tag.lower()
        if tag_l == "title":
            self._in_title = False
        elif tag_l == "h1":
            self._in_h1 = False
            if self._current_text.strip():
                self.h1_texts.append(self._current_text.strip())

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif self._in_h1:
            self._current_text += data
        # Collect text for word count
        stripped = data.strip()
        if stripped:
            self.text_parts.append(stripped)

    @property
    def word_count(self):
        if self._word_count is None:
            text = " ".join(self.text_parts)
            # CJK-aware: count CJK chars individually + Latin words
            cjk = len(re.findall(r"[\u4e00-\u9fff\u3400-\u4dbf]", text))
            latin = len(re.findall(r"[a-zA-Z]+", text))
            self._word_count = cjk + latin
        return self._word_count

    @property
    def first_100_words(self):
        text = " ".join(self.text_parts)
        return text[:500].lower()


# ── Scoring ─────────────────────────────────────────────────

def _score_title(title: str, all_titles: list[str], keywords: list[str]) -> tuple:
    """Score title tag. Returns (score, max, issues, tips)."""
    score = 0
    max_score = 15
    issues = []
    tips = []

    length = len(title)

    if length == 0:
        issues.append("Missing title tag")
        return 0, max_score, issues, tips
    if 30 <= length <= 60:
        score += 10
    elif 20 <= length < 30 or 60 < length <= 75:
        score += 6
        tips.append(f"Title is {length} chars — optimal is 30-60")
    else:
        score += 2
        tips.append(f"Title is {length} chars — optimal is 30-60")

    # Keyword presence
    title_lower = title.lower()
    kw_match = False
    for kw in keywords:
        if kw.lower() in title_lower:
            score += 3
            kw_match = True
            break
    if not kw_match and keywords:
        tips.append("Target keyword not found in title")

    # Uniqueness
    dup_count = sum(1 for t in all_titles if t.lower() == title_lower) - 1
    if dup_count > 0:
        score = max(0, score - 3)
        issues.append(f"Duplicate title (appears on {dup_count + 1} pages)")

    return min(score, max_score), max_score, issues, tips


def _score_meta(desc: str, all_descs: list[str], keywords: list[str]) -> tuple:
    """Score meta description. Returns (score, max, issues, tips)."""
    score = 0
    max_score = 15
    issues = []
    tips = []

    length = len(desc)

    if length == 0:
        issues.append("Missing meta description")
        return 0, max_score, issues, tips
    if 120 <= length <= 160:
        score += 10
    elif 80 <= length < 120 or 160 < length <= 200:
        score += 6
        tips.append(f"Meta description is {length} chars — optimal is 120-160")
    else:
        score += 2
        tips.append(f"Meta description is {length} chars — optimal is 120-160")

    # Keyword presence
    desc_lower = desc.lower()
    for kw in keywords:
        if kw.lower() in desc_lower:
            score += 3
            break

    # Uniqueness
    dup_count = sum(1 for d in all_descs if d.lower() == desc_lower) - 1
    if dup_count > 0:
        score = max(0, score - 3)
        issues.append(f"Duplicate meta description (appears on {dup_count + 1} pages)")

    return min(score, max_score), max_score, issues, tips


def _score_headings(parser: PageParser, keywords: list[str]) -> tuple:
    """Score heading structure. Returns (score, max, issues, tips)."""
    score = 0
    max_score = 20
    issues = []
    tips = []

    h1_count = len(parser.h1_texts)

    if h1_count == 1:
        score += 8
    elif h1_count == 0:
        issues.append("No H1 tag found")
    else:
        score += 2
        issues.append(f"{h1_count} H1 tags found — use exactly 1")

    # Keyword in H1
    if parser.h1_texts:
        h1_text = parser.h1_texts[0].lower()
        for kw in keywords:
            if kw.lower() in h1_text:
                score += 4
                break

    # Hierarchy check — no jumps (e.g., h1 → h3)
    prev_level = 0
    hierarchy_ok = True
    for level in parser._heading_levels:
        if prev_level > 0 and level > prev_level + 1:
            hierarchy_ok = False
            break
        prev_level = level
    if hierarchy_ok:
        score += 4
    else:
        issues.append("Heading hierarchy skips levels (e.g., H1 → H3)")

    # Reasonable H2 count
    if 2 <= parser.h2_count <= 8:
        score += 4
    elif parser.h2_count > 8:
        score += 2
        tips.append(f"{parser.h2_count} H2 tags — consider consolidating")
    elif parser.h2_count >= 1:
        score += 2

    return min(score, max_score), max_score, issues, tips


def _score_images(parser: PageParser) -> tuple:
    """Score image optimization. Returns (score, max, issues, tips)."""
    score = 0
    max_score = 10
    issues = []
    tips = []

    if parser.img_total == 0:
        return 7, max_score, [], ["No images on this page"]

    missing = parser.img_missing_alt
    empty = parser.img_empty_alt
    total_bad = missing + empty
    pct = total_bad / parser.img_total

    if pct == 0:
        score += 5
    elif pct < 0.2:
        score += 3
    elif pct < 0.5:
        score += 1
    else:
        issues.append(f"{missing} images missing alt text")

    # Non-generic alt (basic heuristic)
    score += 5 if pct == 0 else max(0, int(5 * (1 - pct)))

    if missing > 0:
        tips.append(f"{missing} images without alt attribute")

    return min(score, max_score), max_score, issues, tips


def _score_internal_links(parser: PageParser) -> tuple:
    """Score internal linking. Returns (score, max, issues, tips)."""
    score = 0
    max_score = 15
    issues = []
    tips = []

    link_count = len(set(parser.internal_links))

    if link_count == 0:
        issues.append("No internal links found in HTML")
        return 0, max_score, issues, tips

    if link_count >= 3:
        score += 5
    elif link_count >= 1:
        score += 3
        tips.append(f"Only {link_count} internal link(s) — aim for 3+")

    # Link density
    wc = parser.word_count
    if wc > 0:
        density = link_count / (wc / 100) if wc > 100 else link_count
        if density >= 0.5:
            score += 5
        elif density >= 0.2:
            score += 3

    # Unique link ratio
    if len(parser.internal_links) > 0:
        unique_ratio = len(set(parser.internal_links)) / len(parser.internal_links)
        if unique_ratio > 0.8:
            score += 5
        elif unique_ratio > 0.5:
            score += 3

    return min(score, max_score), max_score, issues, tips


def _score_url(path: str) -> tuple:
    """Score URL structure. Returns (score, max, issues, tips)."""
    score = 0
    max_score = 10
    issues = []
    tips = []

    # Lowercase
    if path == path.lower():
        score += 2
    else:
        issues.append("URL contains uppercase characters")

    # Hyphens not underscores/spaces
    if "_" not in path and "%20" not in path:
        score += 2
    else:
        issues.append("URL uses underscores or spaces — use hyphens")

    # Length
    if len(path) <= 75:
        score += 3
    else:
        tips.append(f"URL is {len(path)} chars — consider shortening")

    # No query parameters
    if "?" not in path and "#" not in path:
        score += 3
    else:
        issues.append("URL has query parameters — use clean URLs")

    return min(score, max_score), max_score, issues, tips


def _score_content(parser: PageParser, keywords: list[str]) -> tuple:
    """Score content structure. Returns (score, max, issues, tips)."""
    score = 0
    max_score = 15
    issues = []
    tips = []

    wc = parser.word_count

    if wc >= 800:
        score += 10
    elif wc >= 300:
        score += 5
        tips.append(f"Content is {wc} words — top-ranking pages often have 800+")
    elif wc > 0:
        score += 2
        issues.append(f"Thin content ({wc} words)")
    else:
        issues.append("No readable content detected (may be client-rendered)")

    # BLUF — keyword in first 500 chars
    if keywords and wc > 0:
        first_text = parser.first_100_words
        for kw in keywords:
            if kw.lower() in first_text:
                score += 5
                break
        else:
            tips.append("Target keyword not in first paragraph (BLUF)")

    return min(score, max_score), max_score, issues, tips


# ── Page Audit ──────────────────────────────────────────────

def audit_page(html_path: Path, url_path: str, all_titles: list,
               all_descs: list, keywords: list[str]) -> dict:
    """Audit a single HTML page."""
    html = html_path.read_text(encoding="utf-8", errors="replace")

    parser = PageParser()
    try:
        parser.feed(html)
    except Exception:
        pass

    title_s, title_max, title_issues, title_tips = _score_title(
        parser.title, all_titles, keywords)
    meta_s, meta_max, meta_issues, meta_tips = _score_meta(
        parser.meta_desc, all_descs, keywords)
    head_s, head_max, head_issues, head_tips = _score_headings(parser, keywords)
    img_s, img_max, img_issues, img_tips = _score_images(parser)
    link_s, link_max, link_issues, link_tips = _score_internal_links(parser)
    url_s, url_max, url_issues, url_tips = _score_url(url_path)
    content_s, content_max, content_issues, content_tips = _score_content(parser, keywords)

    total = title_s + meta_s + head_s + img_s + link_s + url_s + content_s
    total_max = title_max + meta_max + head_max + img_max + link_max + url_max + content_max

    all_issues = title_issues + meta_issues + head_issues + img_issues + link_issues + url_issues + content_issues
    all_tips = title_tips + meta_tips + head_tips + img_tips + link_tips + url_tips + content_tips

    grade = "A" if total >= 85 else ("B" if total >= 70 else ("C" if total >= 50 else ("D" if total >= 30 else "F")))

    return {
        "path": url_path,
        "score": total,
        "grade": grade,
        "title": parser.title[:80],
        "word_count": parser.word_count,
        "h1_count": len(parser.h1_texts),
        "img_total": parser.img_total,
        "img_missing_alt": parser.img_missing_alt,
        "internal_links": len(set(parser.internal_links)),
        "details": {
            "title": {"score": title_s, "max": title_max},
            "meta": {"score": meta_s, "max": meta_max},
            "headings": {"score": head_s, "max": head_max},
            "images": {"score": img_s, "max": img_max},
            "links": {"score": link_s, "max": link_max},
            "url": {"score": url_s, "max": url_max},
            "content": {"score": content_s, "max": content_max},
        },
        "issues": all_issues,
        "tips": all_tips,
    }


def run(dist_dir: str, sitemap_path: str = None, keywords_file: str = None,
        base_path: str = "") -> dict:
    """Run on-page audit on all HTML files in dist_dir.

    Returns dict with pages list + summary.
    """
    dist = Path(dist_dir)
    if not dist.exists():
        return {"error": f"dist_dir not found: {dist_dir}"}

    # Load keywords
    keywords = []
    if keywords_file:
        kw_path = Path(keywords_file)
        if kw_path.exists():
            keywords = [k.strip() for k in kw_path.read_text(encoding="utf-8-sig").splitlines() if k.strip()]
            # Use top 20 keywords for matching (avoid slowdown)
            keywords = keywords[:20]

    # Find HTML files (filter hidden dirs in relative path)
    html_files = []
    for f in sorted(dist.rglob("*.html")):
        rel = f.relative_to(dist)
        if any(part.startswith(".") for part in rel.parts[:-1]):
            continue
        html_files.append(f)

    if not html_files:
        return {"error": "No HTML files found in dist_dir"}

    # Parse sitemap for URL paths
    sitemap_paths = set()
    if sitemap_path:
        sm = Path(sitemap_path)
        if sm.exists():
            sitemap_paths = parse_sitemap(sm, base_path)

    # First pass: collect all titles and descriptions for uniqueness checks
    all_titles = []
    all_descs = []
    page_data = []

    for html_file in html_files:
        html = html_file.read_text(encoding="utf-8", errors="replace")
        parser = PageParser()
        try:
            parser.feed(html)
        except Exception:
            pass
        all_titles.append(parser.title)
        all_descs.append(parser.meta_desc)

        # Map to URL path
        rel = str(html_file.relative_to(dist))
        if rel.endswith("/index.html"):
            url_path = "/" + rel[:-11]  # strip /index.html
        elif rel == "index.html":
            url_path = "/"
        else:
            url_path = "/" + rel.replace("\\", "/")

        page_data.append((html_file, url_path))

    # Second pass: score each page
    results = []
    for html_file, url_path in page_data:
        result = audit_page(html_file, url_path, all_titles, all_descs, keywords)
        results.append(result)

    # Summary
    scores = [r["score"] for r in results]
    avg_score = sum(scores) / len(scores) if scores else 0
    grade_dist = dict(Counter(r["grade"] for r in results))

    all_issues_flat = []
    for r in results:
        for issue in r["issues"]:
            all_issues_flat.append({"path": r["path"], "issue": issue})

    all_tips_flat = []
    for r in results:
        for tip in r["tips"]:
            all_tips_flat.append({"path": r["path"], "tip": tip})

    return {
        "summary": {
            "total_pages": len(results),
            "avg_score": round(avg_score, 1),
            "grade_distribution": grade_dist,
            "total_issues": len(all_issues_flat),
            "total_tips": len(all_tips_flat),
        },
        "pages": results,
        "issues": all_issues_flat,
        "tips": all_tips_flat,
    }


def render_report(data: dict) -> str:
    """Render human-readable text report."""
    s = data["summary"]
    lines = [
        "=" * 60,
        "  On-Page SEO Audit",
        "=" * 60,
        "",
        f"  Pages audited: {s['total_pages']}",
        f"  Average score: {s['avg_score']}/100",
        f"  Total issues:  {s['total_issues']}",
        f"  Total tips:    {s['total_tips']}",
        "",
        "  Grade Distribution:",
    ]

    for grade in ["A", "B", "C", "D", "F"]:
        count = s["grade_distribution"].get(grade, 0)
        if count:
            lines.append(f"    {grade}: {count} pages")

    lines.append("")

    # Worst pages
    sorted_pages = sorted(data["pages"], key=lambda p: p["score"])
    lines.append("  ── Pages Needing Attention (bottom 10) ──")
    lines.append("")
    for p in sorted_pages[:10]:
        lines.append(f"    [{p['grade']}] {p['score']:3d}/100  {p['path']}")
        for issue in p["issues"][:3]:
            lines.append(f"         ! {issue}")
        for tip in p["tips"][:2]:
            lines.append(f"         ~ {tip}")
        lines.append("")

    # Top pages
    good_pages = [p for p in sorted_pages if p["score"] >= 70]
    if good_pages:
        lines.append(f"  ── Well-Optimized Pages ({len(good_pages)}) ──")
        lines.append("")
        for p in good_pages[:5]:
            lines.append(f"    [{p['grade']}] {p['score']:3d}/100  {p['path']}")
        if len(good_pages) > 5:
            lines.append(f"    ... and {len(good_pages) - 5} more")
        lines.append("")

    return "\n".join(lines)


# ── CLI ────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="On-page SEO quality audit")
    p.add_argument("--dist", required=True, help="Path to built site directory")
    p.add_argument("--sitemap", help="Path to sitemap XML")
    p.add_argument("--keywords", "-k", help="Keywords file (one per line)")
    p.add_argument("--base", help="Base URL path filter (e.g., /en)")
    p.add_argument("--format", choices=["text", "json"], default="text")
    p.add_argument("--output", "-o", help="Write to file")
    args = p.parse_args()

    sitemap = args.sitemap or str(Path(args.dist) / "sitemap.xml")
    result = run(args.dist, sitemap, args.keywords, args.base or "")

    if "error" in result:
        print(f"ERROR: {result['error']}", file=sys.stderr)
        sys.exit(1)

    if args.format == "json":
        output = json.dumps(result, ensure_ascii=False, indent=2)
    else:
        output = render_report(result)

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"Written to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
