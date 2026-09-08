#!/usr/bin/env python3
"""ai_crawler_audit — robots.txt AI-crawler policy + llms.txt layer audit.

Checks who can actually reach your content: training crawlers, AI search
crawlers, content signals, and the llms.txt discovery layer. Zero deps.

Usage:
  python3 -m zens_ink.ai_crawler_audit https://example.com
  python3 -m zens_ink.ai_crawler_audit https://example.com --markdown report.md
  python3 -m zens_ink.ai_crawler_audit https://example.com --json out.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from urllib.parse import urljoin, urlparse

# --- crawler roster: (token, group label, what it powers) ---
AI_CRAWLERS = [
    ("GPTBot",            "OpenAI",     "training (ChatGPT model data)"),
    ("OAI-SearchBot",     "OpenAI",     "AI search (ChatGPT search grounding)"),
    ("ChatGPT-User",      "OpenAI",     "user-initiated fetch"),
    ("ClaudeBot",         "Anthropic",  "training (Claude model data)"),
    ("Claude-User",       "Anthropic",  "user-initiated fetch"),
    ("Claude-SearchBot",  "Anthropic",  "AI search (Claude web search)"),
    ("Google-Extended",   "Google",     "opt-out for Gemini/Vertex training"),
    ("Googlebot",         "Google",     "Search + AI Overviews grounding"),
    ("CCBot",             "CommonCrawl","open crawl corpus (many models train on it)"),
    ("PerplexityBot",     "Perplexity","AI search answers"),
    ("Perplexity-User",   "Perplexity","user-initiated fetch"),
    ("Bytespider",        "ByteDance",  "training (often disallowed)"),
    ("Amazonbot",         "Amazon",     "training + Alexa"),
    ("Applebot-Extended", "Apple",      "Apple Intelligence training opt-out"),
    ("meta-externalagent","Meta",       "training"),
    ("cohere-ai",         "Cohere",     "training"),
    ("Diffbot",           "Diffbot",    "knowledge graph / retrieval"),
]

CONTENT_SIGNAL_KEYS = ("ai-train", "ai-input", "search", "noai", "noimageai")
TRAINING_UAS = {
    "GPTBot", "ClaudeBot", "Google-Extended", "CCBot", "Bytespider",
    "Amazonbot", "Applebot-Extended", "meta-externalagent", "cohere-ai", "Diffbot",
}
SEARCH_UAS = {
    "OAI-SearchBot", "Claude-SearchBot", "Googlebot", "PerplexityBot",
}


def fetch_text(url: str, timeout: int = 15) -> tuple[int | None, str]:
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (compatible; zens-ink-ai-crawler-audit/1.0)"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:
        return None, str(e)


def parse_robots(txt: str) -> dict:
    """Minimal robots.txt group parser: ua -> rules + global extras."""
    groups: dict[str, list[str]] = {}
    sitemaps: list[str] = []
    signals: list[str] = []
    current: list[str] = []
    for raw in txt.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        key, _, val = line.partition(":")
        key = key.strip().lower()
        val = val.strip()
        if key == "user-agent":
            current = [val] if val else []
            for ua in current:
                groups.setdefault(ua, [])
        elif key == "sitemap":
            if val:
                sitemaps.append(val)
        elif key in ("disallow", "allow"):
            for ua in current:
                if ua in groups:
                    groups[ua].append(f"{key}:{val}")
        # Content-Signal: ai-train=no, search=yes, ai-input=yes (comma-separated)
        # also catches signal mentions in comments / plain lines
        if key == "content-signal" or key == "x-content-signal" or True:
            for m in re.finditer(r"\b(ai-train|ai-input|noai|noimageai|search)\s*[=:]\s*(yes|no|true|false)\b",
                                 raw, re.I):
                sig = f"{m.group(1).lower()}={m.group(2).lower()}"
                if sig not in signals:
                    signals.append(sig)
    return {"groups": groups, "sitemaps": sitemaps, "signals": signals}


def crawl_status(groups: dict[str, list[str]], ua: str) -> str:
    """blocked / partial / allowed / unlisted for a UA token (exact match first)."""
    def site_block(rules: list[str]) -> str | None:
        """None = no signal; 'blocked' (site-wide) / 'partial' (subpaths only)."""
        has_rule = False
        for r in rules:
            kind, _, val = r.partition(":")
            val = val.strip()
            if not val:
                continue
            has_rule = True
            if kind == "disallow" and val in ("/", "$", "/*"):
                return "blocked"
        if has_rule:
            return "partial"
        return None

    if ua in groups:
        st = site_block(groups[ua])
        if st == "blocked":
            return "blocked"
        if st == "partial":
            return "partial"
        if st is None and groups[ua]:
            return "allowed"
    if "*" in groups:
        st = site_block(groups["*"])
        if st == "blocked":
            return "blocked-by-*"
        if st == "partial":
            return "partial-by-*"
    return "unlisted"


def llms_layer(base: str) -> dict:
    out = {}
    for name in ("llms.txt", "llms-full.txt"):
        status, body = fetch_text(urljoin(base, "/" + name))
        links = 0
        if status == 200:
            md_links = len(re.findall(r"\]\((/|https?://)[^)]*\)", body))
            url_tokens = len(re.findall(r"https?://\S+", body))
            links = max(md_links, url_tokens)
        out[name] = {"status": status, "bytes": len(body) if status == 200 else 0,
                     "links": links if status == 200 else 0}
    return out


def audit(url: str) -> dict:
    p = urlparse(url if "://" in url else "https://" + url)
    base = f"{p.scheme}://{p.netloc}"
    rstatus, rtxt = fetch_text(base + "/robots.txt")
    robots_ok = rstatus == 200
    parsed = parse_robots(rtxt) if robots_ok else {"groups": {}, "sitemaps": [], "signals": []}

    rows = []
    for ua, vendor, purpose in AI_CRAWLERS:
        status = crawl_status(parsed["groups"], ua)
        rows.append({"ua": ua, "vendor": vendor, "purpose": purpose, "status": status})

    llms = llms_layer(base)

    # verdict heuristics
    notes = []
    BLK = ("blocked", "blocked-by-*")
    training_blocked = [r["ua"] for r in rows
                        if r["ua"] in TRAINING_UAS and r["status"] in BLK]
    search_blocked = [r["ua"] for r in rows
                      if r["ua"] in SEARCH_UAS and r["status"] in BLK]
    if search_blocked:
        notes.append(f"AI-search crawlers blocked: {', '.join(search_blocked)} — "
                     "your pages cannot be cited by these engines. Usually a mistake "
                     "when owners disallow everything to stop training.")
    if len(training_blocked) >= 5:
        notes.append(f"Aggressive training opt-out ({len(training_blocked)} UAs) — "
                     "consistent with an IP-protection strategy; keep llms.txt open "
                     "so AI search can still quote you.")
    if not robots_ok:
        notes.append("robots.txt unreachable — default allow-all for every crawler.")
    OKS = ("allowed", "allowed-by-*", "partial", "partial-by-*", "unlisted")
    if robots_ok and all(c["status"] in OKS for c in rows if c["ua"] in TRAINING_UAS):
        notes.append("robots.txt allows every AI crawler — edge bot management "
                     "(e.g. Cloudflare AI Scrapers toggle) may still 403 them; "
                     "the two layers are independent, verify one real fetch if unsure.")
    if "ai-train=no" in parsed["signals"] and "search=yes" not in parsed["signals"]:
        notes.append("Signals say ai-train=no without search=yes — add search=yes "
                     "so the opt-out is not read as total exclusion.")
    if llms["llms.txt"]["status"] == 200 and llms["llms.txt"]["links"] == 0:
        notes.append("llms.txt exists but lists zero URLs — likely malformed.")
    if llms["llms.txt"]["status"] != 200:
        notes.append("No llms.txt — AI engines discover content depth from it first. "
                     "zens_ink llms_gen can generate one from your sitemap or build dir.")
    score = 100
    score -= 12 * len([r for r in rows if r["ua"] in SEARCH_UAS and r["status"] in BLK])
    score -= 8 if not robots_ok else 0
    score -= 8 if llms["llms.txt"]["status"] != 200 else 0
    score -= 4 if llms["llms-full.txt"]["status"] != 200 else 0
    score = max(0, min(100, score))

    return {"base": base, "robots_status": rstatus, "robots_bytes": len(rtxt),
            "sitemap_declared": bool(parsed["sitemaps"]),
            "sitemap_urls": parsed["sitemaps"][:5], "content_signals": parsed["signals"],
            "crawlers": rows, "llms": llms, "notes": notes, "score": score}


def render_text(rep: dict) -> str:
    L = []
    L.append(f"AI Crawler Audit — {rep['base']}")
    L.append(f"robots.txt: HTTP {rep['robots_status']} ({rep['robots_bytes']} bytes) · "
             f"sitemap declared: {'yes' if rep['sitemap_declared'] else 'no'} · "
             f"signals: {', '.join(rep['content_signals']) or 'none'}")
    L.append("")
    W = max(len(c["ua"]) for c in rep["crawlers"])
    for c in rep["crawlers"]:
        mark = {"blocked": "BLOCKED", "blocked-by-*": "BLOCKED *",
                "partial": "partial", "partial-by-*": "partial *",
                "allowed": "allowed", "allowed-by-*": "allowed *",
                "unlisted": "unlisted"}[c["status"]]
        L.append(f"  {c['ua']:<{W}}  {mark:<10} {c['vendor']:<10} {c['purpose']}")
    L.append("")
    for name, d in rep["llms"].items():
        L.append(f"  {name}: HTTP {d['status']} · {d['bytes']} bytes · {d['links']} links")
    L.append("")
    L.append(f"Notes:")
    for n in rep["notes"]:
        L.append(f"  - {n}")
    L.append(f"\nAI-readiness score: {rep['score']}/100")
    return "\n".join(L)


def render_markdown(rep: dict) -> str:
    L = [f"# AI Crawler Audit — {rep['base']}", ""]
    L.append(f"- robots.txt: HTTP {rep['robots_status']} ({rep['robots_bytes']} bytes)")
    L.append(f"- Sitemap declared: {'yes' if rep['sitemap_declared'] else 'no'}")
    L.append(f"- Content signals: {', '.join(rep['content_signals']) or 'none'}")
    L.append(f"- AI-readiness score: **{rep['score']}/100**")
    L.append("", "| Crawler | Vendor | Status | Powers |", "|---|---|---|---|")
    for c in rep["crawlers"]:
        L.append(f"| {c['ua']} | {c['vendor']} | {c['status']} | {c['purpose']} |")
    L.append("")
    for name, d in rep["llms"].items():
        L.append(f"- `{name}`: HTTP {d['status']} · {d['bytes']} bytes · {d['links']} links")
    if rep["notes"]:
        L.append("", "## Notes")
        for n in rep["notes"]:
            L.append(f"- {n}")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(prog="zens-ink ai_crawler_audit",
                                 description="Audit robots.txt AI-crawler policy + llms.txt layer")
    ap.add_argument("url", help="site root, e.g. https://example.com")
    ap.add_argument("--markdown", metavar="FILE", help="also write markdown report")
    ap.add_argument("--json", metavar="FILE", help="also write JSON report")
    args = ap.parse_args()

    rep = audit(args.url)
    print(render_text(rep))
    if args.markdown:
        with open(args.markdown, "w", encoding="utf-8") as f:
            f.write(render_markdown(rep) + "\n")
        print(f"\n[markdown] {args.markdown}")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(rep, f, ensure_ascii=False, indent=1)
        print(f"[json] {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
