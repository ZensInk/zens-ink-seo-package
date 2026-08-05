#!/usr/bin/env python3
"""
Site Audit — scan built HTML for common technical SEO issues.

Checks:
  1. Orphan pages: in sitemap but no internal links found in built HTML
  2. Missing trailing slashes: internal links that cause 301 redirects
  3. Broken internal links: paths not present in sitemap (404 candidates)
  4. Missing/short/long meta descriptions: <meta name="description"> length issues
  5. Duplicate meta descriptions: same description across multiple pages
  6. Missing/short/long title tags: <title> length issues
  7. Duplicate titles: same <title> across multiple pages
  8. Missing H1: pages without an <h1> tag in server HTML
  9. Multiple H1: pages with more than one <h1>
 10. Heading hierarchy skips: H1→H3 without H2
 11. Canonical issues: missing, duplicate, or conflicting canonical tags
 12. Oversized images: local image files exceeding size threshold (default 200KB)
 13. Missing alt text: <img> tags without alt attribute
 14. Missing width/height: <img> tags without dimensions (causes CLS)
 15. robots.txt: missing, empty, or no sitemap declaration
 16. Open Graph: missing og:title, og:description, og:image, og:url
 17. JSON-LD: pages without structured data (GEO/AI visibility)
 18. Viewport meta: missing or misconfigured mobile viewport
 19. HTML lang: missing lang attribute on <html> tag
 20. Thin content: pages with < 100 words of body text
 21. Favicon: missing favicon file or link tag

GEO/AI Visibility:
 22. llms.txt: missing or thin (AI discovery infrastructure)
 23. llms-full.txt: missing comprehensive version
 24. Schema types: blog articles missing FAQPage/HowTo schema
 25. Content signals: robots.txt missing ai-input/search declarations
 26. Content structure: content pages lacking H2 headings, lists, or tables
 27. BLUF: content pages missing summary/TL;DR block
 28. Crawl blocking: noindex on content pages or disallow-all in robots.txt

i18n & Performance:
 29. Hreflang: missing alternate language tags or x-default fallback
 30. Large HTML: pages exceeding size threshold (crawl budget impact)

Works on any static build output (Astro, Next.js export, Hugo, etc.).

Usage:
  python3 -m zens_ink.site_audit --dist dist --sitemap dist/sitemap.xml
  python3 -m zens_ink.site_audit --dist dist --sitemap dist/sitemap.xml --base /en
  python3 -m zens_ink.site_audit --dist dist --sitemap dist/sitemap.xml --format json
  python3 -m zens_ink.site_audit --dist dist --sitemap dist/sitemap.xml --format csv --output audit.csv

Options:
  --dist       Path to build output directory (default: dist)
  --sitemap    Path to sitemap XML file (auto-detects sitemap-0.xml / sitemap.xml)
  --base       Base URL path prefix to filter (e.g., /en for English-only audit)
  --format     Output format: text, json, csv (default: text)
  --output     Write to file instead of stdout (for json/csv)
  --verbose    Show all link targets, not just issues
"""

import argparse
import csv
import io
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

_STATIC_EXTS = {
    ".svg", ".png", ".jpg", ".jpeg", ".gif", ".webp",
    ".css", ".js", ".xml", ".json", ".webmanifest",
    ".woff", ".woff2", ".ttf", ".otf", ".txt", ".ico",
    ".pdf", ".zip", ".mp4", ".mp3", ".map",
}


# ── Parsing ──────────────────────────────────────────────────────────────

def parse_sitemap(sitemap_path: Path, base_path: str = "") -> set[str]:
    """Extract URL paths from sitemap XML (supports sitemap-index)."""
    if not sitemap_path.exists():
        for alt in ["sitemap-0.xml", "sitemap.xml"]:
            alt_path = sitemap_path.parent / alt
            if alt_path.exists():
                sitemap_path = alt_path
                break
        else:
            print(f"ERROR: Sitemap not found: {sitemap_path}", file=sys.stderr)
            sys.exit(1)

    content = sitemap_path.read_text(errors="ignore")

    # If this is a sitemap index, follow sub-sitemaps
    if "<sitemapindex" in content:
        sub_locs = re.findall(r"<loc>(.*?\.xml)</loc>", content)
        paths = set()
        for sub_url in sub_locs:
            parsed = urlparse(sub_url)
            sub_file = sitemap_path.parent / Path(parsed.path).name
            if sub_file.exists():
                sub_paths = parse_sitemap(sub_file, base_path)
                paths.update(sub_paths)
        # Also scan for any sitemap-*.xml siblings
        for sibling in sitemap_path.parent.glob("sitemap*.xml"):
            if sibling == sitemap_path:
                continue
            sibling_content = sibling.read_text(errors="ignore")
            if "<sitemapindex" in sibling_content:
                continue  # already handled above
            sub_paths = parse_sitemap(sibling, base_path)
            paths.update(sub_paths)
        return paths

    urls = re.findall(r"<loc>(.*?)</loc>", content)

    paths = set()
    for url in urls:
        parsed = urlparse(url)
        path = parsed.path or "/"
        if base_path and not path.startswith(base_path):
            continue
        paths.add(path.rstrip("/") or "/")

    return paths


def find_html_files(dist_dir: Path) -> list[Path]:
    """Find all .html files in the dist directory."""
    return sorted(dist_dir.rglob("*.html"))


def extract_hrefs(content: str) -> list[str]:
    """Extract all internal href="/..." paths from HTML."""
    return re.findall(r'href="(/[^"]*)"', content)


# ── Checks ───────────────────────────────────────────────────────────────

def check_orphan_pages(
    sitemap_paths: set[str],
    link_sources: dict[str, set[str]],
) -> list[dict]:
    """Pages in sitemap but no incoming internal links."""
    issues = []
    for path in sorted(sitemap_paths):
        normalized = path.rstrip("/") or "/"
        if normalized not in link_sources:
            if not any(
                normalized == k or normalized == k.rstrip("/")
                for k in link_sources
            ):
                issues.append({
                    "type": "orphan_page",
                    "severity": "warning",
                    "path": path,
                    "detail": "In sitemap but no internal links found",
                })
    return issues


def check_trailing_slashes(dist_dir: Path) -> list[dict]:
    """Internal links without trailing slash that would cause 301 redirects."""
    issues = []
    seen = set()
    for html_file in dist_dir.rglob("*.html"):
        try:
            content = html_file.read_text(errors="ignore")
        except Exception:
            continue
        hrefs = extract_hrefs(content)
        rel = str(html_file.relative_to(dist_dir))
        for href in hrefs:
            if any(href.endswith(ext) for ext in _STATIC_EXTS):
                continue
            if href.endswith("/"):
                continue
            if "?" in href or "#" in href:
                continue
            key = (rel, href)
            if key in seen:
                continue
            seen.add(key)
            issues.append({
                "type": "missing_trailing_slash",
                "severity": "info",
                "path": href,
                "source": rel,
                "detail": "May cause 301 redirect",
            })
    return issues


def check_dangling_links(
    sitemap_paths: set[str],
    dist_dir: Path,
) -> list[dict]:
    """Links in HTML that don't match any sitemap URL (potential 404s)."""
    sitemap_normalized = {p.rstrip("/") or "/" for p in sitemap_paths}
    issues = []
    seen = set()
    for html_file in dist_dir.rglob("*.html"):
        try:
            content = html_file.read_text(errors="ignore")
        except Exception:
            continue
        hrefs = extract_hrefs(content)
        rel = str(html_file.relative_to(dist_dir))
        for href in hrefs:
            clean = href.split("#")[0].split("?")[0].rstrip("/") or "/"
            if clean == "/" or clean in sitemap_normalized:
                continue
            if any(clean.endswith(ext) for ext in _STATIC_EXTS):
                continue
            key = (rel, href)
            if key in seen:
                continue
            seen.add(key)
            issues.append({
                "type": "broken_link",
                "severity": "error",
                "path": href,
                "source": rel,
                "detail": "Link target not in sitemap (potential 404)",
            })
    return issues


def check_canonical(dist_dir: Path) -> list[dict]:
    """Pages missing <link rel="canonical">."""
    issues = []
    for html_file in dist_dir.rglob("*.html"):
        try:
            content = html_file.read_text(errors="ignore")
        except Exception:
            continue
        if 'rel="canonical"' not in content and "rel='canonical'" not in content:
            rel = str(html_file.relative_to(dist_dir))
            # Skip 404 pages
            if "404" in rel:
                continue
            issues.append({
                "type": "missing_canonical",
                "severity": "warning",
                "path": rel,
                "detail": "No canonical tag found",
            })
    return issues


def check_meta_description(dist_dir: Path) -> list[dict]:
    """Pages missing or suboptimal meta description."""
    issues = []
    pattern = re.compile(
        r'<meta\s+name=["\']description["\']\s+content=["\'](.*?)["\']',
        re.IGNORECASE | re.DOTALL,
    )
    exists_pattern = re.compile(
        r'<meta\s+name=["\']description["\']', re.IGNORECASE
    )
    for html_file in dist_dir.rglob("*.html"):
        try:
            content = html_file.read_text(errors="ignore")
        except Exception:
            continue
        rel = str(html_file.relative_to(dist_dir))
        if "404" in rel:
            continue
        if not exists_pattern.search(content):
            issues.append({
                "type": "missing_meta_description",
                "severity": "warning",
                "path": rel,
                "detail": "No meta description tag",
            })
            continue
        # Check length
        match = pattern.search(content)
        if match:
            desc = match.group(1).strip()
            length = len(desc)
            if length < 50:
                issues.append({
                    "type": "short_meta_description",
                    "severity": "warning",
                    "path": rel,
                    "detail": f"{length} chars — too short (aim for 70-160)",
                })
            elif length > 200:
                issues.append({
                    "type": "long_meta_description",
                    "severity": "info",
                    "path": rel,
                    "detail": f"{length} chars — may get truncated in SERP (aim for ≤160)",
                })
    return issues


def check_title_tag(dist_dir: Path) -> list[dict]:
    """Pages with missing, short, or long <title> tags."""
    issues = []
    title_pattern = re.compile(r"<title>(.*?)</title>", re.IGNORECASE | re.DOTALL)
    for html_file in dist_dir.rglob("*.html"):
        try:
            content = html_file.read_text(errors="ignore")
        except Exception:
            continue
        rel = str(html_file.relative_to(dist_dir))
        if "404" in rel:
            continue
        match = title_pattern.search(content)
        if not match:
            issues.append({
                "type": "missing_title",
                "severity": "error",
                "path": rel,
                "detail": "No <title> tag",
            })
            continue
        title = match.group(1).strip()
        length = len(title)
        if length < 10:
            issues.append({
                "type": "short_title",
                "severity": "warning",
                "path": rel,
                "detail": f'"{title[:40]}..." {length} chars — too short',
            })
        elif length > 65:
            issues.append({
                "type": "long_title",
                "severity": "info",
                "path": rel,
                "detail": f'"{title[:40]}..." {length} chars — may get truncated in SERP',
            })
    return issues


def check_h1(dist_dir: Path) -> list[dict]:
    """Pages missing H1 or having multiple H1 tags."""
    issues = []
    h1_pattern = re.compile(r"<h1[\s>]", re.IGNORECASE)
    h1_text_pattern = re.compile(r"<h1[^>]*>(.*?)</h1>", re.IGNORECASE | re.DOTALL)
    for html_file in dist_dir.rglob("*.html"):
        try:
            content = html_file.read_text(errors="ignore")
        except Exception:
            continue
        rel = str(html_file.relative_to(dist_dir))
        if "404" in rel:
            continue
        count = len(h1_pattern.findall(content))
        if count == 0:
            issues.append({
                "type": "missing_h1",
                "severity": "warning",
                "path": rel,
                "detail": "No H1 tag in server HTML",
            })
        elif count > 1:
            issues.append({
                "type": "multiple_h1",
                "severity": "info",
                "path": rel,
                "detail": f"{count} H1 tags found (recommend exactly 1)",
            })
        else:
            # Check H1 text length
            text_match = h1_text_pattern.search(content)
            if text_match:
                h1_text = re.sub(r"<[^>]+>", "", text_match.group(1)).strip()
                if len(h1_text) < 3:
                    issues.append({
                        "type": "short_h1",
                        "severity": "info",
                        "path": rel,
                        "detail": f'H1 too short: "{h1_text}"',
                    })
    return issues


def check_images(dist_dir: Path, max_size_kb: int = 200) -> list[dict]:
    """Check images referenced in HTML for size, alt text, and dimensions."""
    issues = []
    img_pattern = re.compile(r'<img[^>]+>', re.IGNORECASE)
    src_pattern = re.compile(r'src=["\'](\!?\./)?([^"\']+)["\']', re.IGNORECASE)
    alt_pattern = re.compile(r'\salt=', re.IGNORECASE)
    wh_pattern = re.compile(r'\s(width|height)=', re.IGNORECASE)
    seen_imgs = set()

    for html_file in dist_dir.rglob("*.html"):
        try:
            content = html_file.read_text(errors="ignore")
        except Exception:
            continue
        rel = str(html_file.relative_to(dist_dir))
        if "404" in rel:
            continue

        for img_tag in img_pattern.findall(content):
            src_match = src_pattern.search(img_tag)
            if not src_match:
                continue
            img_src = src_match.group(2)

            # Skip external images, data URIs, SVGs (vector, no size concern)
            if img_src.startswith("http") or img_src.startswith("data:"):
                continue
            if img_src.endswith(".svg"):
                # Still check alt/width/height for SVGs
                pass
            elif not any(img_src.endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif")):
                continue

            # Check file size for local raster images
            if not img_src.startswith("http") and not img_src.startswith("data:"):
                img_path = dist_dir / img_src.lstrip("/")
                if img_path.exists() and not img_src.endswith(".svg"):
                    file_size = img_path.stat().st_size
                    size_kb = file_size / 1024
                    key = (img_src, size_kb)
                    if key not in seen_imgs:
                        seen_imgs.add(key)
                        if size_kb > max_size_kb:
                            issues.append({
                                "type": "oversized_image",
                                "severity": "warning",
                                "path": img_src,
                                "source": rel,
                                "detail": f"{size_kb:.0f}KB (threshold: {max_size_kb}KB) — compress or convert to WebP/AVIF",
                            })

            # Check alt text
            if not alt_pattern.search(img_tag):
                key = ("no_alt", img_src, rel)
                if key not in seen_imgs:
                    seen_imgs.add(key)
                    issues.append({
                        "type": "missing_alt_text",
                        "severity": "warning",
                        "path": img_src,
                        "source": rel,
                        "detail": "<img> missing alt attribute",
                    })

            # Check width/height (CLS prevention)
            if not wh_pattern.search(img_tag):
                key = ("no_wh", img_src, rel)
                if key not in seen_imgs:
                    seen_imgs.add(key)
                    issues.append({
                        "type": "missing_dimensions",
                        "severity": "info",
                        "path": img_src,
                        "source": rel,
                        "detail": "<img> missing width/height (may cause layout shift)",
                    })

    return issues


def check_robots_txt(dist_dir: Path) -> list[dict]:
    """Check robots.txt presence and basic validity."""
    issues = []
    robots_path = dist_dir / "robots.txt"
    if not robots_path.exists():
        issues.append({
            "type": "missing_robots",
            "severity": "warning",
            "path": "robots.txt",
            "detail": "No robots.txt found — search engines may crawl inefficiently",
        })
        return issues
    content = robots_path.read_text(errors="ignore")
    if not content.strip():
        issues.append({
            "type": "empty_robots",
            "severity": "warning",
            "path": "robots.txt",
            "detail": "robots.txt is empty",
        })
    has_sitemap = "sitemap" in content.lower()
    if not has_sitemap:
        issues.append({
            "type": "robots_no_sitemap",
            "severity": "info",
            "path": "robots.txt",
            "detail": "robots.txt does not declare a sitemap URL",
        })
    return issues


def check_open_graph(dist_dir: Path) -> list[dict]:
    """Check for missing Open Graph tags."""
    issues = []
    og_tags = ["og:title", "og:description", "og:image", "og:url"]
    for html_file in dist_dir.rglob("*.html"):
        try:
            content = html_file.read_text(errors="ignore")
        except Exception:
            continue
        rel = str(html_file.relative_to(dist_dir))
        if "404" in rel:
            continue
        for tag in og_tags:
            if f'property="{tag}"' not in content and f"property='{tag}'" not in content:
                issues.append({
                    "type": "missing_open_graph",
                    "severity": "info" if tag != "og:image" else "warning",
                    "path": rel,
                    "detail": f"Missing og:{tag.split(':')[1]}",
                })
    return issues


def check_json_ld(dist_dir: Path) -> list[dict]:
    """Check for structured data (JSON-LD) presence."""
    issues = []
    pattern = re.compile(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>',
        re.IGNORECASE,
    )
    for html_file in dist_dir.rglob("*.html"):
        try:
            content = html_file.read_text(errors="ignore")
        except Exception:
            continue
        rel = str(html_file.relative_to(dist_dir))
        if "404" in rel:
            continue
        if not pattern.search(content):
            issues.append({
                "type": "missing_json_ld",
                "severity": "info",
                "path": rel,
                "detail": "No JSON-LD structured data (important for GEO/AI visibility)",
            })
    return issues


def check_viewport(dist_dir: Path) -> list[dict]:
    """Check for viewport meta tag."""
    issues = []
    pattern = re.compile(
        r'<meta\s+name=["\']viewport["\']', re.IGNORECASE
    )
    width_pattern = re.compile(
        r'<meta\s+name=["\']viewport["\']\s+content=["\'](.*?)["\']',
        re.IGNORECASE,
    )
    for html_file in dist_dir.rglob("*.html"):
        try:
            content = html_file.read_text(errors="ignore")
        except Exception:
            continue
        rel = str(html_file.relative_to(dist_dir))
        if "404" in rel:
            continue
        if not pattern.search(content):
            issues.append({
                "type": "missing_viewport",
                "severity": "error",
                "path": rel,
                "detail": "No viewport meta tag (mobile rendering broken)",
            })
        else:
            match = width_pattern.search(content)
            if match and "width=device-width" not in match.group(1):
                issues.append({
                    "type": "bad_viewport",
                    "severity": "warning",
                    "path": rel,
                    "detail": f'Viewport does not use width=device-width: "{match.group(1)}"',
                })
    return issues


def check_html_lang(dist_dir: Path) -> list[dict]:
    """Check for lang attribute on <html> tag."""
    issues = []
    pattern = re.compile(r"<html[^>]*>", re.IGNORECASE)
    lang_pattern = re.compile(r'<html[^>]*\slang\s*=\s*["\']([a-zA-Z\-]+)["\']', re.IGNORECASE)
    for html_file in dist_dir.rglob("*.html"):
        try:
            content = html_file.read_text(errors="ignore")
        except Exception:
            continue
        rel = str(html_file.relative_to(dist_dir))
        if "404" in rel:
            continue
        html_match = pattern.search(content)
        if html_match and not lang_pattern.search(content):
            issues.append({
                "type": "missing_html_lang",
                "severity": "warning",
                "path": rel,
                "detail": "<html> tag missing lang attribute",
            })
    return issues


def check_duplicate_meta(dist_dir: Path) -> list[dict]:
    """Check for duplicate meta descriptions and titles across pages."""
    issues = []
    desc_pattern = re.compile(
        r'<meta\s+name=["\']description["\']\s+content=["\'](.*?)["\']',
        re.IGNORECASE | re.DOTALL,
    )
    title_pattern = re.compile(r"<title>(.*?)</title>", re.IGNORECASE | re.DOTALL)

    desc_map: dict[str, list[str]] = {}
    title_map: dict[str, list[str]] = {}

    for html_file in dist_dir.rglob("*.html"):
        try:
            content = html_file.read_text(errors="ignore")
        except Exception:
            continue
        rel = str(html_file.relative_to(dist_dir))
        if "404" in rel:
            continue

        d_match = desc_pattern.search(content)
        if d_match:
            desc = d_match.group(1).strip()[:200]
            if len(desc) > 10:
                desc_map.setdefault(desc, []).append(rel)

        t_match = title_pattern.search(content)
        if t_match:
            title = t_match.group(1).strip()
            if len(title) > 3:
                title_map.setdefault(title, []).append(rel)

    for desc, pages in desc_map.items():
        if len(pages) > 1:
            issues.append({
                "type": "duplicate_meta_description",
                "severity": "warning",
                "path": ", ".join(pages[:5]),
                "detail": f'Same description on {len(pages)} pages: "{desc[:60]}..."',
            })

    for title, pages in title_map.items():
        if len(pages) > 1:
            issues.append({
                "type": "duplicate_title",
                "severity": "warning",
                "path": ", ".join(pages[:5]),
                "detail": f'Same title on {len(pages)} pages: "{title[:60]}"',
            })

    return issues


def check_heading_hierarchy(dist_dir: Path) -> list[dict]:
    """Check for heading level skips (e.g. H1→H3 without H2)."""
    issues = []
    heading_pattern = re.compile(r"<(h[1-6])[\s>]", re.IGNORECASE)
    for html_file in dist_dir.rglob("*.html"):
        try:
            content = html_file.read_text(errors="ignore")
        except Exception:
            continue
        rel = str(html_file.relative_to(dist_dir))
        if "404" in rel:
            continue
        headings = [(m.group(1).lower(), m.start()) for m in heading_pattern.finditer(content)]
        if not headings:
            continue
        prev_level = 0
        for tag, _pos in headings:
            level = int(tag[1])
            if prev_level > 0 and level > prev_level + 1:
                issues.append({
                    "type": "heading_skip",
                    "severity": "info",
                    "path": rel,
                    "detail": f"Heading skip: H{prev_level} → H{level}",
                })
            prev_level = level
    return issues


def check_thin_content(dist_dir: Path, min_words: int = 100) -> list[dict]:
    """Check for pages with very little text content."""
    issues = []
    # Strip script/style/noscript tags then count words
    strip_pattern = re.compile(
        r"<(script|style|noscript|svg|head)[^>]*>.*?</\1>",
        re.IGNORECASE | re.DOTALL,
    )
    tag_pattern = re.compile(r"<[^>]+>")
    for html_file in dist_dir.rglob("*.html"):
        try:
            content = html_file.read_text(errors="ignore")
        except Exception:
            continue
        rel = str(html_file.relative_to(dist_dir))
        if "404" in rel:
            continue
        stripped = strip_pattern.sub("", content)
        text = tag_pattern.sub(" ", stripped)
        words = len(text.split())
        if words < min_words:
            issues.append({
                "type": "thin_content",
                "severity": "warning",
                "path": rel,
                "detail": f"~{words} words of body text (threshold: {min_words})",
            })
    return issues


def check_multiple_canonical(dist_dir: Path) -> list[dict]:
    """Check for pages with multiple conflicting canonical tags."""
    issues = []
    pattern = re.compile(
        r'<link\s+[^>]*rel=["\']canonical["\'][^>]*>',
        re.IGNORECASE,
    )
    href_pattern = re.compile(r'href=["\'](.*?)["\']', re.IGNORECASE)
    for html_file in dist_dir.rglob("*.html"):
        try:
            content = html_file.read_text(errors="ignore")
        except Exception:
            continue
        rel = str(html_file.relative_to(dist_dir))
        if "404" in rel:
            continue
        matches = pattern.findall(content)
        if len(matches) > 1:
            hrefs = [href_pattern.search(m).group(1) for m in matches if href_pattern.search(m)]
            unique = set(hrefs)
            if len(unique) > 1:
                issues.append({
                    "type": "conflicting_canonical",
                    "severity": "error",
                    "path": rel,
                    "detail": f"{len(matches)} canonical tags with different URLs",
                })
            else:
                issues.append({
                    "type": "duplicate_canonical",
                    "severity": "info",
                    "path": rel,
                    "detail": f"{len(matches)} identical canonical tags (should be 1)",
                })
    return issues


def check_favicon(dist_dir: Path) -> list[dict]:
    """Check for favicon reference."""
    issues = []
    icon_patterns = [
        re.compile(r'rel=["\']icon["\']', re.IGNORECASE),
        re.compile(r'rel=["\']shortcut icon["\']', re.IGNORECASE),
        re.compile(r'rel=["\']apple-touch-icon["\']', re.IGNORECASE),
    ]
    # Check index.html or root-level html
    root_html = dist_dir / "index.html"
    if not root_html.exists():
        for h in dist_dir.glob("*.html"):
            root_html = h
            break
    if root_html.exists():
        content = root_html.read_text(errors="ignore")
        if not any(p.search(content) for p in icon_patterns):
            issues.append({
                "type": "missing_favicon",
                "severity": "info",
                "path": "index.html",
                "detail": "No favicon link found in <head>",
            })
    # Also check file exists
    for name in ["favicon.ico", "favicon.svg", "favicon.png"]:
        if (dist_dir / name).exists() or (dist_dir / "public" / name).exists():
            return issues
    if not issues:
        issues.append({
            "type": "missing_favicon",
            "severity": "info",
            "path": "/",
            "detail": "No favicon file found in dist root",
        })
    return issues


# ── GEO Checks ───────────────────────────────────────────────────────────

def check_llms_txt(dist_dir: Path) -> list[dict]:
    """Check for llms.txt files (GEO infrastructure for AI discoverability)."""
    issues = []
    llms = dist_dir / "llms.txt"
    llms_full = dist_dir / "llms-full.txt"
    if not llms.exists():
        issues.append({
            "type": "missing_llms_txt",
            "severity": "warning",
            "path": "llms.txt",
            "detail": "No llms.txt found — AI engines won't discover your content efficiently",
        })
    elif llms.stat().st_size < 50:
        issues.append({
            "type": "thin_llms_txt",
            "severity": "info",
            "path": "llms.txt",
            "detail": "llms.txt is very small — consider adding more page links",
        })
    if not llms_full.exists():
        issues.append({
            "type": "missing_llms_full",
            "severity": "info",
            "path": "llms-full.txt",
            "detail": "No llms-full.txt — consider a comprehensive version for deep AI crawling",
        })
    return issues


def check_schema_types(dist_dir: Path) -> list[dict]:
    """Check for specific high-value JSON-LD schema types (Article, FAQPage, HowTo, Organization)."""
    issues = []
    jsonld_pattern = re.compile(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        re.IGNORECASE | re.DOTALL,
    )
    high_value_types = {"Article", "BlogPosting", "FAQPage", "HowTo", "Organization",
                        "Product", "BreadcrumbList", "WebSite", "ProfilePage"}

    for html_file in dist_dir.rglob("*.html"):
        try:
            content = html_file.read_text(errors="ignore")
        except Exception:
            continue
        rel = str(html_file.relative_to(dist_dir))
        if "404" in rel:
            continue
        blocks = jsonld_pattern.findall(content)
        if not blocks:
            continue
        found_types = set()
        for block in blocks:
            for t in high_value_types:
                if f'"@type":\\s*"{t}"' in block or f'"@type":"{t}"' in block:
                    found_types.add(t)
        if not found_types & {"FAQPage", "HowTo"} and "blog/" in rel and "/category/" not in rel:
            issues.append({
                "type": "missing_faq_schema",
                "severity": "info",
                "path": rel,
                "detail": "Blog article without FAQPage or HowTo schema (AI engines favor Q&A format)",
            })
    return issues


def check_commercial_schema(dist_dir: Path) -> list[dict]:
    """Check that commercial pages (pricing, themes, services, unlock) have Product/Service schema.

    Google uses Product JSON-LD to populate rich results (price, availability, ratings).
    Pages that sell things without this schema are invisible to Google Shopping and
    commercial rich results — a high-impact blind spot.
    """
    issues: list[dict] = []
    jsonld_re = re.compile(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        re.IGNORECASE | re.DOTALL,
    )
    # Path patterns that indicate a commercial/product page
    commercial_patterns = (
        "pricing", "themes/", "unlock", "services",
        "buy", "checkout", "plans", "shop/",
    )
    commercial_types = {"Product", "Service", "SoftwareApplication", "Offer"}

    for html_file in dist_dir.rglob("*.html"):
        rel = str(html_file.relative_to(dist_dir))
        if "404" in rel:
            continue
        if not any(pat in rel for pat in commercial_patterns):
            continue
        try:
            content = html_file.read_text(errors="ignore")
        except Exception:
            continue
        blocks = jsonld_re.findall(content)
        found = False
        for block in blocks:
            for t in commercial_types:
                if f'"@type":\\s*"{t}"' in block or f'"@type":"{t}"' in block:
                    found = True
                    break
            if found:
                break
        if not found:
            issues.append({
                "type": "missing_product_schema",
                "severity": "warning",
                "path": rel,
                "detail": "Commercial/pricing page without Product, Service, or Offer JSON-LD — invisible to Google Shopping & commercial rich results",
            })
    return issues


def check_content_signals(dist_dir: Path) -> list[dict]:
    """Check robots.txt for AI Content Signals (ai-train, ai-input, search)."""
    issues = []
    robots_path = dist_dir / "robots.txt"
    if not robots_path.exists():
        return issues
    content = robots_path.read_text(errors="ignore")
    has_ai_train = "ai-train" in content.lower()
    has_ai_input = "ai-input" in content.lower()
    has_search = "search" in content.lower()
    if not has_ai_input:
        issues.append({
            "type": "missing_ai_input_signal",
            "severity": "info",
            "path": "robots.txt",
            "detail": "No ai-input signal — AI search engines may not index you",
        })
    if not has_search:
        issues.append({
            "type": "missing_search_signal",
            "severity": "info",
            "path": "robots.txt",
            "detail": "No search signal — consider declaring search engine crawling policy",
        })
    return issues


def check_content_structure(dist_dir: Path) -> list[dict]:
    """Check content pages for AI-friendly structure (H2+ headings, lists, tables)."""
    issues = []
    h2_pattern = re.compile(r"<h2[\s>]", re.IGNORECASE)
    list_pattern = re.compile(r"<(ul|ol)[\s>]", re.IGNORECASE)
    table_pattern = re.compile(r"<table[\s>]", re.IGNORECASE)

    for html_file in dist_dir.rglob("*.html"):
        try:
            content = html_file.read_text(errors="ignore")
        except Exception:
            continue
        rel = str(html_file.relative_to(dist_dir))
        if "404" in rel or "blog/category/" in rel:
            continue
        if "blog/" not in rel:
            continue
        h2_count = len(h2_pattern.findall(content))
        has_lists = bool(list_pattern.search(content))
        has_tables = bool(table_pattern.search(content))

        if h2_count == 0:
            issues.append({
                "type": "no_h2_headings",
                "severity": "warning",
                "path": rel,
                "detail": "Content page with no H2 — AI engines chunk by sections",
            })
        if not has_lists and not has_tables:
            issues.append({
                "type": "no_structured_content",
                "severity": "info",
                "path": rel,
                "detail": "No lists/tables — structured data helps AI cite your content",
            })
    return issues


def check_bluf(dist_dir: Path) -> list[dict]:
    """Check content pages for BLUF (Bottom Line Up Front) summary indicators."""
    issues = []
    bluf_re = re.compile(
        r'<summary|class="[^"]*(?:summary|tldr|bluf|key-takeaway)[^"]*"'
        r'|>TL;DR<|>Key takeaways|>In summary|<!--\s*BLUF',
        re.IGNORECASE,
    )
    for html_file in dist_dir.rglob("*.html"):
        try:
            content = html_file.read_text(errors="ignore")
        except Exception:
            continue
        rel = str(html_file.relative_to(dist_dir))
        if "404" in rel or "blog/category/" in rel:
            continue
        if "blog/" not in rel:
            continue
        if not bluf_re.search(content):
            issues.append({
                "type": "missing_bluf",
                "severity": "info",
                "path": rel,
                "detail": "No BLUF/summary/TL;DR block — AI engines prefer content with clear takeaways",
            })
    return issues


def check_crawl_blocking(dist_dir: Path) -> list[dict]:
    """Check for signals that block AI/search crawling."""
    issues = []
    noindex_pattern = re.compile(
        r'<meta\s+name=["\']robots["\']\s+content=["\'][^"\']*noindex',
        re.IGNORECASE,
    )
    for html_file in dist_dir.rglob("*.html"):
        try:
            content = html_file.read_text(errors="ignore")
        except Exception:
            continue
        rel = str(html_file.relative_to(dist_dir))
        if "404" in rel:
            continue
        if noindex_pattern.search(content) and ("blog/" in rel or rel == "index.html"):
            issues.append({
                "type": "noindex_on_content",
                "severity": "warning",
                "path": rel,
                "detail": "Content page has noindex — search engines and AI won't index this",
            })
    robots_path = dist_dir / "robots.txt"
    if robots_path.exists():
        robots = robots_path.read_text(errors="ignore")
        if re.search(r'user-agent:\s*\*\s*\n\s*disallow:\s*/\s*$', robots, re.IGNORECASE | re.MULTILINE):
            issues.append({
                "type": "block_all_crawl",
                "severity": "error",
                "path": "robots.txt",
                "detail": "User-agent: * Disallow: / — blocks ALL crawling",
            })
    return issues


# ── i18n & Performance ───────────────────────────────────────────────────

def check_hreflang(dist_dir: Path) -> list[dict]:
    """Check for hreflang tags on pages (i18n SEO)."""
    issues = []
    hreflang_pattern = re.compile(
        r'<link\s+[^>]*rel=["\']alternate["\'][^>]*hreflang=["\']([^"\']+)["\']',
        re.IGNORECASE,
    )
    # Check if site appears to be multi-language
    has_en_dir = (dist_dir / "en").is_dir() or (dist_dir / "/en").is_dir()
    has_zh_dir = (dist_dir / "zh").is_dir()

    for html_file in dist_dir.rglob("*.html"):
        try:
            content = html_file.read_text(errors="ignore")
        except Exception:
            continue
        rel = str(html_file.relative_to(dist_dir))
        if "404" in rel:
            continue
        matches = hreflang_pattern.findall(content)
        if not matches and rel == "index.html":
            issues.append({
                "type": "missing_hreflang",
                "severity": "info",
                "path": rel,
                "detail": "No hreflang tags (only needed for multi-language sites)",
            })
        if matches:
            if "x-default" not in [m.lower() for m in matches]:
                issues.append({
                    "type": "missing_x_default",
                    "severity": "info",
                    "path": rel,
                    "detail": "hreflang tags present but missing x-default fallback",
                })
    return issues


def check_page_size(dist_dir: Path, max_kb: int = 500) -> list[dict]:
    """Flag HTML pages that are too large (crawl budget impact)."""
    issues = []
    for html_file in dist_dir.rglob("*.html"):
        try:
            content = html_file.read_text(errors="ignore")
        except Exception:
            continue
        rel = str(html_file.relative_to(dist_dir))
        if "404" in rel:
            continue
        size_kb = len(content.encode("utf-8")) / 1024
        if size_kb > max_kb:
            issues.append({
                "type": "large_html",
                "severity": "warning",
                "path": rel,
                "detail": f"{size_kb:.0f}KB (threshold: {max_kb}KB) — may impact crawl budget",
            })
    return issues


# ── Sitemap URL Inventory ────────────────────────────────────────────────

def check_sitemap_inventory(sitemap_path: Path, base_path: str = "") -> list[dict]:
    """Group sitemap URLs by top-level directory to produce a site map overview."""
    issues: list[dict] = []
    sitemap_urls = parse_sitemap(sitemap_path, base_path)
    if not sitemap_urls:
        return issues

    # Group by first path segment
    from collections import OrderedDict
    groups: dict[str, list[str]] = OrderedDict()
    for url_path in sorted(sitemap_urls):
        clean = url_path.strip("/")
        if not clean:
            top = "/ (root)"
        else:
            parts = clean.split("/")
            top = f"/{parts[0]}/" if len(parts) > 1 else f"/{parts[0]}"
        groups.setdefault(top, []).append(url_path)

    # Report as info — helps understand site structure
    inventory_lines = []
    for dir_name, urls in sorted(groups.items(), key=lambda x: -len(x[1])):
        example = urls[0] if urls else ""
        inventory_lines.append(f"  {dir_name}: {len(urls)} URLs (e.g. {example})")

    if inventory_lines:
        issues.append({
            "type": "sitemap_inventory",
            "severity": "info",
            "path": str(sitemap_path),
            "detail": f"Sitemap URL inventory ({len(sitemap_urls)} URLs across {len(groups)} directories):\n" + "\n".join(inventory_lines),
        })
    return issues


# ── Staging Subdomain Leak Detection ──────────────────────────────────────

_STAGING_PREFIXES = ("test.", "staging.", "dev.", "preview.", "beta.", "uat.")

def check_staging_leak(dist_dir: Path) -> list[dict]:
    """Detect staging/dev subdomain URLs that leaked into production build."""
    issues: list[dict] = []
    seen_domains: set[str] = set()

    for html_file in dist_dir.rglob("*.html"):
        try:
            content = html_file.read_text(errors="ignore")
        except Exception:
            continue

        rel = str(html_file.relative_to(dist_dir))
        if "404" in rel:
            continue

        # Check canonical, og:url, and absolute links for staging domains
        url_pattern = r'https?://([a-z0-9][-a-z0-9]*\.[a-z0-9][-a-z0-9.]*?)[:/"]'
        found = re.findall(url_pattern, content.lower())
        for domain in found:
            if any(domain.startswith(prefix) for prefix in _STAGING_PREFIXES):
                if domain not in seen_domains:
                    seen_domains.add(domain)
                    issues.append({
                        "type": "staging_subdomain_leak",
                        "severity": "error",
                        "path": rel,
                        "detail": f"Staging subdomain '{domain}' found in production HTML — may cause indexing of test environments",
                    })

        # Also check for localhost IPs
        if re.search(r'https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0)[:/"\n]', content):
            issues.append({
                "type": "staging_subdomain_leak",
                "severity": "error",
                "path": rel,
                "detail": "localhost/127.0.0.1 URL found in production HTML",
            })

    return issues


# ── Schema Field Validation ───────────────────────────────────────────────

# Required fields per Schema.org @type (missing → warning)
_SCHEMA_REQUIRED: dict[str, list[str]] = {
    "Article": ["headline", "datePublished", "author"],
    "BlogPosting": ["headline", "datePublished", "author"],
    "NewsArticle": ["headline", "datePublished", "author"],
    "Product": ["name", "offers"],
    "FAQPage": ["mainEntity"],
    "HowTo": ["name", "step"],
    "Organization": ["name", "url"],
    "WebSite": ["name", "url"],
    "LocalBusiness": ["name", "address"],
    "BreadcrumbList": ["itemListElement"],
}

# Recommended fields (missing → info)
_SCHEMA_RECOMMENDED: dict[str, list[str]] = {
    "Article": ["image", "dateModified", "publisher"],
    "BlogPosting": ["image", "dateModified", "publisher"],
    "Product": ["aggregateRating", "brand", "description"],
    "Organization": ["logo", "sameAs"],
}

# Nested field requirements: parent → required sub-fields
_SCHEMA_NESTED: dict[str, dict[str, list[str]]] = {
    "Product": {"offers": ["price", "priceCurrency"]},
    "FAQPage": {"mainEntity": ["name", "acceptedAnswer"]},
    "HowTo": {"step": ["text"]},
}

def check_schema_fields(dist_dir: Path) -> list[dict]:
    """Validate JSON-LD structured data: required/recommended fields + nesting."""
    issues: list[dict] = []
    jsonld_re = re.compile(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        re.DOTALL | re.IGNORECASE,
    )

    for html_file in dist_dir.rglob("*.html"):
        try:
            content = html_file.read_text(errors="ignore")
        except Exception:
            continue

        rel = str(html_file.relative_to(dist_dir))
        if "404" in rel:
            continue

        for match in jsonld_re.finditer(content):
            raw = match.group(1).strip()
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            # Flatten @graph
            schemas = []
            if isinstance(data, list):
                schemas = [s for s in data if isinstance(s, dict)]
            elif isinstance(data, dict):
                if "@graph" in data and isinstance(data["@graph"], list):
                    schemas = [s for s in data["@graph"] if isinstance(s, dict)]
                else:
                    schemas = [data]

            for schema in schemas:
                stype = schema.get("@type", "")
                if isinstance(stype, list):
                    stype = stype[0] if stype else ""
                if not isinstance(stype, str) or not stype:
                    continue

                # Check required fields
                required = _SCHEMA_REQUIRED.get(stype, [])
                for field in required:
                    val = schema.get(field)
                    if val is None or (isinstance(val, str) and not val.strip()):
                        issues.append({
                            "type": "schema_missing_field",
                            "severity": "warning",
                            "path": rel,
                            "detail": f"JSON-LD {stype}: missing required field '{field}'",
                        })

                # Check recommended fields
                recommended = _SCHEMA_RECOMMENDED.get(stype, [])
                for field in recommended:
                    val = schema.get(field)
                    if val is None or (isinstance(val, str) and not val.strip()):
                        issues.append({
                            "type": "schema_recommended_field",
                            "severity": "info",
                            "path": rel,
                            "detail": f"JSON-LD {stype}: missing recommended field '{field}'",
                        })

                # Check nested fields
                nested_reqs = _SCHEMA_NESTED.get(stype, {})
                for parent_field, sub_fields in nested_reqs.items():
                    parent_val = schema.get(parent_field)
                    if parent_val is None:
                        continue
                    items = parent_val if isinstance(parent_val, list) else [parent_val]
                    if items and isinstance(items[0], dict):
                        first = items[0]
                        for sf in sub_fields:
                            sub_val = first.get(sf)
                            if sub_val is None or (isinstance(sub_val, str) and not sub_val.strip()):
                                issues.append({
                                    "type": "schema_nested_field",
                                    "severity": "warning",
                                    "path": rel,
                                    "detail": f"JSON-LD {stype}.{parent_field}: missing '{sf}'",
                                })

    return issues


# ── Link source map ──────────────────────────────────────────────────────

def build_link_map(
    dist_dir: Path,
) -> tuple[dict[str, set[str]], set[str]]:
    """Scan all HTML for internal links. Returns (path→sources, all_targets)."""
    link_sources: dict[str, set[str]] = {}
    all_links: set[str] = set()
    for html_file in dist_dir.rglob("*.html"):
        try:
            content = html_file.read_text(errors="ignore")
        except Exception:
            continue
        hrefs = extract_hrefs(content)
        rel = str(html_file.relative_to(dist_dir))
        for href in hrefs:
            clean = href.split("#")[0].split("?")[0].rstrip("/")
            if clean:
                all_links.add(clean)
                if clean not in link_sources:
                    link_sources[clean] = set()
                link_sources[clean].add(rel)
    return link_sources, all_links


# ── Output ───────────────────────────────────────────────────────────────

def format_text(
    issues: list[dict],
    sitemap_count: int,
    html_count: int,
    verbose: bool,
    link_sources: dict[str, set[str]],
) -> str:
    """Format issues as human-readable text."""
    buf = io.StringIO()
    sep = "=" * 60

    buf.write(f"{sep}\nSite Audit Report\n{sep}\n")
    buf.write(f"Sitemap URLs: {sitemap_count}\n")
    buf.write(f"HTML files scanned: {html_count}\n")

    if verbose:
        buf.write(f"\n--- All link targets ({len(link_sources)}) ---\n")
        for target in sorted(link_sources):
            buf.write(f"  {target} ({len(link_sources[target])} refs)\n")

    # Group by type
    by_type: dict[str, list[dict]] = {}
    for issue in issues:
        by_type.setdefault(issue["type"], []).append(issue)

    type_labels = {
        "orphan_page": "ORPHAN PAGES",
        "missing_trailing_slash": "MISSING TRAILING SLASHES",
        "broken_link": "BROKEN LINKS (potential 404)",
        "missing_canonical": "MISSING CANONICAL TAGS",
        "conflicting_canonical": "CONFLICTING CANONICAL TAGS",
        "duplicate_canonical": "DUPLICATE CANONICAL TAGS",
        "missing_meta_description": "MISSING META DESCRIPTIONS",
        "short_meta_description": "SHORT META DESCRIPTIONS (<50 chars)",
        "long_meta_description": "LONG META DESCRIPTIONS (>200 chars)",
        "duplicate_meta_description": "DUPLICATE META DESCRIPTIONS",
        "missing_title": "MISSING TITLE TAGS",
        "short_title": "SHORT TITLE TAGS (<10 chars)",
        "long_title": "LONG TITLE TAGS (>65 chars)",
        "duplicate_title": "DUPLICATE TITLE TAGS",
        "missing_h1": "MISSING H1 TAGS",
        "multiple_h1": "MULTIPLE H1 TAGS",
        "short_h1": "SHORT H1 TEXT (<3 chars)",
        "heading_skip": "HEADING HIERARCHY SKIPS",
        "oversized_image": "OVERSIZED IMAGES",
        "missing_alt_text": "MISSING ALT TEXT",
        "missing_dimensions": "MISSING IMAGE DIMENSIONS (CLS risk)",
        "missing_robots": "MISSING ROBOTS.TXT",
        "empty_robots": "EMPTY ROBOTS.TXT",
        "robots_no_sitemap": "ROBOTS.TXT MISSING SITEMAP DECLARATION",
        "missing_open_graph": "MISSING OPEN GRAPH TAGS",
        "missing_json_ld": "MISSING JSON-LD STRUCTURED DATA",
        "missing_product_schema": "COMMERCIAL PAGE WITHOUT PRODUCT/SERVICE SCHEMA",
        "missing_viewport": "MISSING VIEWPORT META",
        "bad_viewport": "BAD VIEWPORT META",
        "missing_html_lang": "MISSING HTML LANG ATTRIBUTE",
        "thin_content": "THIN CONTENT (<100 words)",
        "missing_favicon": "MISSING FAVICON",
        "missing_llms_txt": "MISSING llms.txt (GEO)",
        "thin_llms_txt": "THIN llms.txt (GEO)",
        "missing_llms_full": "MISSING llms-full.txt (GEO)",
        "missing_faq_schema": "MISSING FAQ/HOWTO SCHEMA (GEO)",
        "missing_ai_input_signal": "MISSING AI-INPUT SIGNAL (GEO)",
        "missing_search_signal": "MISSING SEARCH SIGNAL (GEO)",
        "no_h2_headings": "NO H2 HEADINGS ON CONTENT (GEO)",
        "no_structured_content": "NO LISTS/TABLES ON CONTENT (GEO)",
        "missing_bluf": "MISSING BLUF/SUMMARY (GEO)",
        "noindex_on_content": "NOINDEX ON CONTENT PAGE",
        "block_all_crawl": "BLOCKS ALL CRAWLING",
        "missing_hreflang": "MISSING HREFLANG (i18n)",
        "missing_x_default": "MISSING X-DEFAULT HREFLANG",
        "large_html": "LARGE HTML PAGES (crawl budget)",
        "sitemap_inventory": "SITEMAP URL INVENTORY",
        "staging_subdomain_leak": "STAGING SUBDOMAIN LEAK (critical)",
        "schema_missing_field": "SCHEMA MISSING REQUIRED FIELDS",
        "schema_recommended_field": "SCHEMA MISSING RECOMMENDED FIELDS",
        "schema_nested_field": "SCHEMA NESTED FIELD ISSUES",
    }

    for issue_type, label in type_labels.items():
        group = by_type.get(issue_type, [])
        unique_paths = sorted({i["path"] for i in group})
        buf.write(f"\n{sep}\n{label}: {len(unique_paths)} unique")
        if len(group) != len(unique_paths):
            buf.write(f" ({len(group)} total)")
        buf.write(f"\n{sep}\n")
        if unique_paths:
            for path in unique_paths:
                detail = next(
                    (i["detail"] for i in group if i["path"] == path), ""
                )
                source = next(
                    (i.get("source", "") for i in group if i["path"] == path), ""
                )
                suffix = f"  (in {source})" if source else ""
                buf.write(f"  {path}{suffix}\n")
                if detail:
                    buf.write(f"    → {detail}\n")
        else:
            buf.write("  None — all good.\n")

    # Summary
    errors = sum(1 for i in issues if i["severity"] == "error")
    warnings = sum(1 for i in issues if i["severity"] == "warning")
    infos = sum(1 for i in issues if i["severity"] == "info")

    buf.write(f"\n{sep}\nSUMMARY\n{sep}\n")
    buf.write(f"  Errors:   {errors}\n")
    buf.write(f"  Warnings: {warnings}\n")
    buf.write(f"  Info:     {infos}\n")
    buf.write(f"  Total:    {len(issues)}\n")
    if errors == 0 and warnings == 0:
        buf.write("\n  ✓ No critical issues found!\n")
    buf.write(sep + "\n")

    return buf.getvalue()


def format_json(issues: list[dict], sitemap_count: int, html_count: int) -> str:
    """Format as JSON."""
    errors = sum(1 for i in issues if i["severity"] == "error")
    warnings = sum(1 for i in issues if i["severity"] == "warning")
    data = {
        "summary": {
            "sitemap_urls": sitemap_count,
            "html_files": html_count,
            "total_issues": len(issues),
            "errors": errors,
            "warnings": warnings,
        },
        "issues": issues,
    }
    return json.dumps(data, indent=2, ensure_ascii=False)


def format_csv(issues: list[dict]) -> str:
    """Format as CSV."""
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf,
        fieldnames=["type", "severity", "path", "source", "detail"],
    )
    writer.writeheader()
    for issue in issues:
        writer.writerow({
            "type": issue.get("type", ""),
            "severity": issue.get("severity", ""),
            "path": issue.get("path", ""),
            "source": issue.get("source", ""),
            "detail": issue.get("detail", ""),
        })
    return buf.getvalue()


# ── Main ─────────────────────────────────────────────────────────────────

def run(
    dist_dir: Path,
    sitemap_path: Path,
    base_path: str = "",
    output_format: str = "text",
    output_file: str = "",
    verbose: bool = False,
    max_image_kb: int = 200,
) -> str:
    """Run the full audit and return formatted output."""
    # 1. Parse sitemap
    sitemap_paths = parse_sitemap(sitemap_path, base_path)

    # 2. Scan HTML files
    html_files = find_html_files(dist_dir)

    # 3. Build link map
    link_sources, _ = build_link_map(dist_dir)

    # 4. Run all checks
    all_issues: list[dict] = []
    all_issues.extend(check_orphan_pages(sitemap_paths, link_sources))
    all_issues.extend(check_trailing_slashes(dist_dir))
    all_issues.extend(check_dangling_links(sitemap_paths, dist_dir))
    all_issues.extend(check_canonical(dist_dir))
    all_issues.extend(check_meta_description(dist_dir))
    all_issues.extend(check_h1(dist_dir))
    all_issues.extend(check_title_tag(dist_dir))
    all_issues.extend(check_images(dist_dir, max_size_kb=max_image_kb))
    all_issues.extend(check_robots_txt(dist_dir))
    all_issues.extend(check_open_graph(dist_dir))
    all_issues.extend(check_json_ld(dist_dir))
    all_issues.extend(check_viewport(dist_dir))
    all_issues.extend(check_html_lang(dist_dir))
    all_issues.extend(check_duplicate_meta(dist_dir))
    all_issues.extend(check_heading_hierarchy(dist_dir))
    all_issues.extend(check_thin_content(dist_dir))
    all_issues.extend(check_multiple_canonical(dist_dir))
    all_issues.extend(check_favicon(dist_dir))
    # GEO checks
    all_issues.extend(check_llms_txt(dist_dir))
    all_issues.extend(check_schema_types(dist_dir))
    all_issues.extend(check_commercial_schema(dist_dir))
    all_issues.extend(check_content_signals(dist_dir))
    all_issues.extend(check_content_structure(dist_dir))
    all_issues.extend(check_bluf(dist_dir))
    all_issues.extend(check_crawl_blocking(dist_dir))
    all_issues.extend(check_hreflang(dist_dir))
    all_issues.extend(check_page_size(dist_dir))
    # New checks (inspired by community best practices)
    all_issues.extend(check_sitemap_inventory(sitemap_path, base_path))
    all_issues.extend(check_staging_leak(dist_dir))
    all_issues.extend(check_schema_fields(dist_dir))

    # 5. Format output
    if output_format == "json":
        result = format_json(all_issues, len(sitemap_paths), len(html_files))
    elif output_format == "csv":
        result = format_csv(all_issues)
    else:
        result = format_text(
            all_issues, len(sitemap_paths), len(html_files),
            verbose, link_sources,
        )

    if output_file:
        Path(output_file).write_text(result, encoding="utf-8")
        return f"Written to {output_file}"

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Technical SEO audit for static site builds",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  python3 -m zens_ink.site_audit --dist dist --sitemap dist/sitemap.xml
  python3 -m zens_ink.site_audit --dist dist --base /en --verbose
  python3 -m zens_ink.site_audit --dist dist --format json --output report.json
""",
    )
    parser.add_argument(
        "--dist", default="dist",
        help="Build output directory (default: dist)",
    )
    parser.add_argument(
        "--sitemap", default="dist/sitemap.xml",
        help="Sitemap XML path (auto-detects sitemap-0.xml)",
    )
    parser.add_argument(
        "--base", default="",
        help="Base path prefix filter (e.g., /en)",
    )
    parser.add_argument(
        "--format", choices=["text", "json", "csv"], default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--output", default="",
        help="Write to file instead of stdout",
    )
    parser.add_argument(
        "--max-image-kb", type=int, default=200,
        help="Max image size in KB before flagging (default: 200)",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Show all link targets",
    )
    args = parser.parse_args()

    dist_dir = Path(args.dist)
    if not dist_dir.exists():
        print(f"ERROR: dist directory not found: {dist_dir}", file=sys.stderr)
        sys.exit(1)

    sitemap_path = Path(args.sitemap)

    result = run(
        dist_dir=dist_dir,
        sitemap_path=sitemap_path,
        base_path=args.base,
        output_format=args.format,
        output_file=args.output,
        verbose=args.verbose,
        max_image_kb=args.max_image_kb,
    )
    print(result)


if __name__ == "__main__":
    main()
