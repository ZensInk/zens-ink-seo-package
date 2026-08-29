#!/usr/bin/env python3
"""
Content QC — Pre-publish gate for AI-citable content.

The publishing-side companion to geo_score (which grades live pages).
content_qc grades a DRAFT before it ships, so problems get fixed at the
desk instead of after Google re-crawls:

  1. BLUF        — does the article state its conclusion up front?
  2. Facts       — specific numbers, dates, named entities (not vague claims)
  3. Sources     — outbound links, verifiable references
  4. Structure   — heading hierarchy, lists/tables, FAQ Q&A format
  5. AI Readable — frontmatter hygiene, title/description length, image alt

Pure Python stdlib, zero dependencies. Works on Markdown (with YAML
frontmatter) and plain HTML.

Usage:
  python3 -m zens_ink.content_qc draft.md
  python3 -m zens_ink.content_qc draft.md --format json
  python3 -m zens_ink.content_qc drafts/            # whole directory
"""

import argparse
import json
import re
import sys
from pathlib import Path

# ════════════════════════════════════════════════════════════════
# Checks
# ════════════════════════════════════════════════════════════════

VAGUE_WORDS = {
    "many", "various", "several", "some", "few", "most", "a lot of",
    "significant", "substantial", "numerous", "countless", "plenty of",
    "a number of", "quite a few", "state of the art", "cutting edge",
    "industry leading", "best in class", "world class", "revolutionary",
    "game changing", "next generation", "seamless", "robust",
}

NUMBER_RE = re.compile(r"\b\d[\d,.]*\s*(%|x|k|m|bn|billion|million|percent)?\b", re.I)
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
QUESTION_RE = re.compile(r"\?\s*$")


def split_frontmatter(text: str):
    """Return (frontmatter dict, body) for md with YAML frontmatter, else ({}, text)."""
    fm = {}
    body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            body = parts[2]
            for line in parts[1].strip().splitlines():
                m = re.match(r"^([a-zA-Z_]+):\s*(.*)$", line)
                if m:
                    key, val = m.group(1), m.group(2).strip().strip('"').strip("'")
                    if val:
                        fm[key] = val
    return fm, body


def strip_html(html: str) -> str:
    html = re.sub(r"<script.*?</script>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<style.*?</style>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", html).strip()


def check_draft(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8", errors="replace")
    is_html = path.suffix.lower() in (".html", ".htm")

    if is_html:
        text = strip_html(raw)
        fm = {}
        title_m = re.search(r"<title>(.*?)</title>", raw, re.S | re.I)
        if title_m:
            fm["title"] = title_m.group(1).strip()
        desc_m = re.search(r'<meta\s+name="description"\s+content="([^"]*)"', raw, re.I)
        if desc_m:
            fm["description"] = desc_m.group(1)
        h1s = re.findall(r"<h1[^>]*>(.*?)</h1>", raw, re.S | re.I)
        h2s = re.findall(r"<h2[^>]*>(.*?)</h2>", raw, re.S | re.I)
        headings = [strip_html(h) for h in h1s + h2s]
        links = re.findall(r'href="(https?://[^"]+)"', raw)
        internal_links = re.findall(r'href="(/[^"]*)"', raw)
        img_alts = re.findall(r'<img[^>]*alt="([^"]*)"', raw)
        imgs = re.findall(r"<img", raw)
        lists = bool(re.search(r"<(ul|ol)", raw, re.I))
        tables = bool(re.search(r"<table", raw, re.I))
        bluf = bool(re.search(r"(TL;DR|tl;dr|Bottom line|In short:|Key takeaway)", raw))
        faq = "FAQPage" in raw or "Frequently Asked" in raw
        dates = bool(re.search(r"<time[^>]*datetime", raw, re.I))
    else:
        fm, body = split_frontmatter(raw)
        text = body
        headings = re.findall(r"^#{1,2}\s+(.+)$", text, re.M)
        links = re.findall(r"\]\((https?://[^)]+)\)", text)
        internal_links = re.findall(r"\]\((/[^)]+)\)", text)
        html_imgs = re.findall(r'<img[^>]*alt="([^"]*)"', body)
        md_imgs = re.findall(r"!\[([^\]]*)\]\(", body)
        img_alts = html_imgs + md_imgs
        imgs = re.findall(r"!\[[^\]]*\]\(", body) + re.findall(r"<img", body)
        lists = bool(re.search(r"^\s*([-*+]|\d+\.)\s", text, re.M))
        tables = "|" in text and re.search(r"^\|.*\|$", text, re.M) is not None
        bluf = "bluf" in fm or bool(re.search(r"(TL;DR|tl;dr|Bottom line|In short:|Key takeaway)", body[:3000]))
        faq = "faq" in fm or bool(re.search(r"^faq:", raw, re.M)) or "FAQPage" in raw or "Frequently Asked" in raw
        dates = bool(re.search(r"\b(19|20)\d{2}\b", fm.get("date", "") + fm.get("updated", "")))

    words = re.findall(r"[A-Za-z][A-Za-z'-]*", text)
    word_count = len(words)
    numbers = NUMBER_RE.findall(text)
    years = YEAR_RE.findall(text)

    lower_text = text.lower()
    vague_hits = sum(1 for w in VAGUE_WORDS if w in lower_text)
    vague_density = (vague_hits * 1000 / max(word_count, 1))
    fact_density = ((len(numbers) + len(years)) * 1000 / max(word_count, 1))

    question_headings = [h for h in headings if QUESTION_RE.search(h)]

    checks = []

    def add(name, ok, weight, note=""):
        checks.append({"check": name, "pass": bool(ok), "weight": weight, "note": note})

    add("BLUF up front", bluf, 15,
        "state the conclusion in the first screen — add a TL;DR block or bluf frontmatter")
    add("Fact density >= 4/1k words", fact_density >= 4, 15,
        f"currently {fact_density:.1f} — add concrete numbers, versions, dates, prices")
    add("Vague-word density < 3/1k", vague_density < 3, 10,
        f"currently {vague_density:.1f} — replace 'various/significant/numerous' with specifics")
    add("Outbound source links >= 2", len(links) >= 2, 10,
        f"currently {len(links)} — cite primary sources (docs, data, repos)")
    add("Internal links >= 2", len(internal_links) >= 2, 5,
        f"currently {len(internal_links)} — cross-link related pages")
    add("H2 sections >= 3", len(headings) >= 3, 10,
        f"currently {len(headings)} — AI extracts answers per-section")
    add("Question-format heading", len(question_headings) >= 1, 5,
        "at least one H2/H3 phrased as a real user question")
    add("FAQ block present", faq, 10,
        "3 Q&As matching real queries; mark up with FAQPage schema")
    add("Lists or tables", lists or tables, 5,
        "structured data answers get extracted more than prose")

    title = fm.get("title", "")
    add("Title 20-65 chars", 20 <= len(title) <= 65, 5,
        f"'{title[:40]}' is {len(title)} chars")
    desc = fm.get("description", "")
    add("Description 70-160 chars", 70 <= len(desc) <= 160, 5,
        f"description is {len(desc)} chars")

    alt_ok = not imgs or (len([a for a in img_alts if a.strip()]) >= len(imgs) * 0.8)
    add("Image alt >= 80%", alt_ok, 3,
        f"{len([a for a in img_alts if a.strip()])}/{len(imgs)} images have alt")
    add("Date signal", dates, 2,
        "visible publish/update date (frontmatter date/updated or <time>)")

    total_weight = sum(c["weight"] for c in checks)
    score = sum(c["weight"] for c in checks if c["pass"])
    return {
        "file": str(path),
        "score": round(score * 100 / total_weight),
        "word_count": word_count,
        "fact_density": round(fact_density, 1),
        "vague_density": round(vague_density, 1),
        "checks": checks,
    }


def grade(score: int) -> str:
    if score >= 85: return "A — ship it"
    if score >= 70: return "B — minor fixes"
    if score >= 55: return "C — needs work"
    return "D — do not publish"


# ════════════════════════════════════════════════════════════════
# Output
# ════════════════════════════════════════════════════════════════

def print_report(r: dict):
    print(f"\n{'=' * 60}")
    print(f"Content QC: {r['file']}")
    print(f"Score: {r['score']}/100 — {grade(r['score'])}")
    print(f"Words: {r['word_count']} | Facts/1k: {r['fact_density']} | Vague/1k: {r['vague_density']}")
    print(f"{'=' * 60}")
    for c in sorted(r["checks"], key=lambda x: -x["weight"]):
        mark = "PASS" if c["pass"] else "FIX "
        print(f"  [{mark}] {c['check']}  (w={c['weight']})")
        if not c["pass"]:
            print(f"         → {c['note']}")
    failed = [c for c in r["checks"] if not c["pass"]]
    if failed:
        top = sorted(failed, key=lambda x: -x["weight"])[:3]
        print(f"\n  P0 fixes: " + "; ".join(c["check"].lower() for c in top))
    else:
        print("\n  All checks passed.")


def main():
    ap = argparse.ArgumentParser(
        prog="zens_ink.content_qc",
        description="Pre-publish content gate — will AI engines cite this draft?",
    )
    ap.add_argument("path", help="Markdown/HTML file or directory of drafts")
    ap.add_argument("--format", choices=["text", "json"], default="text")
    ap.add_argument("--min-score", type=int, default=70,
                    help="Exit code 1 if any draft scores below this (default 70)")
    args = ap.parse_args()

    p = Path(args.path)
    if p.is_dir():
        files = sorted(
            list(p.glob("*.md")) + list(p.glob("*.html")) + list(p.glob("*.htm"))
        )
    else:
        files = [p]

    if not files:
        print(f"No drafts found at {args.path}")
        sys.exit(1)

    results = [check_draft(f) for f in files]
    failed_gate = [r for r in results if r["score"] < args.min_score]

    if args.format == "json":
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        for r in results:
            print_report(r)
        if len(results) > 1:
            avg = sum(r["score"] for r in results) // len(results)
            print(f"\n{len(results)} drafts | avg {avg}/100 | below {args.min_score}: {len(failed_gate)}")

    sys.exit(1 if failed_gate else 0)


if __name__ == "__main__":
    main()
