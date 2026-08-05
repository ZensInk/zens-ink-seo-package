#!/usr/bin/env python3
"""
GEO Fan-out — Reverse-engineer AI search queries for content strategy.

AI search engines (ChatGPT, Perplexity, Gemini) don't just search one query.
They expand a user's query into 8-12 sub-queries (Query Fan-out), then
aggregate answers. If your content matches ANY sub-query and ranks well,
you get cited as a source.

This tool generates those Fan-out sub-queries for your seed keyword,
classifies them by intent dimension, and helps you find "gold mine"
content opportunities — sub-queries that match your ICP with low competition.

Methodology adapted from Span (zyppy.com) AI Citation Ranking Factors
and the GEO paper (arxiv:2311.09735).

Usage:
  python3 -m zens_ink.geo_fanout "best CRM"
  python3 -m zens_ink.geo_fanout "ai video generator" --icp "content creators"
  python3 -m zens_ink.geo_fanout "八字排盘" --lang zh
  python3 -m zens_ink.geo_fanout "best CRM" --json

Zero dependencies beyond Python stdlib.
"""

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from collections import OrderedDict

# ── Intent Dimensions ──────────────────────────────────────────────────────
#
# When AI expands a query, it covers different user-decision dimensions.
# Each dimension maps to a content opportunity.

INTENT_DIMENSIONS = OrderedDict([
    ("icp", {
        "label": "ICP / Persona",
        "description": "Who is searching? Role, industry, company size",
        "templates": [
            "{kw} for {icp}",
            "{kw} for small business",
            "{kw} for enterprise",
            "{kw} for startups",
            "{kw} for healthcare",
            "{kw} for ecommerce",
            "{kw} for agencies",
            "{kw} for developers",
        ],
        "commercial_weight": "high",
    }),
    ("scenario", {
        "label": "Use Case / Scenario",
        "description": "What are they trying to do? Specific workflow or goal",
        "templates": [
            "{kw} for social media",
            "{kw} for content marketing",
            "{kw} for lead generation",
            "how to use {kw} for {icp}",
            "{kw} workflow",
            "{kw} use cases",
            "{kw} examples",
            "{kw} in action",
        ],
        "commercial_weight": "medium",
    }),
    ("pricing", {
        "label": "Pricing / Cost",
        "description": "Buying decision — these users have wallet out",
        "templates": [
            "{kw} pricing",
            "{kw} cost",
            "{kw} free",
            "{kw} free alternative",
            "{kw} vs free",
            "cheapest {kw}",
            "{kw} discount",
            "{kw} roi",
        ],
        "commercial_weight": "very_high",
    }),
    ("features", {
        "label": "Features / Capabilities",
        "description": "Functional requirements — comparing what each tool does",
        "templates": [
            "{kw} features",
            "{kw} comparison",
            "{kw} integrations",
            "{kw} api",
            "{kw} automation",
            "{kw} ai powered",
            "{kw} open source",
            "{kw} no code",
        ],
        "commercial_weight": "medium",
    }),
    ("competitors", {
        "label": "Competitors / Alternatives",
        "description": "Direct comparison — strongest commercial intent",
        "templates": [
            "{kw} alternatives",
            "{kw} vs competitors",
            "best {kw}",
            "top {kw}",
            "{kw} review",
            "{kw} compared",
            "{kw} showdown",
        ],
        "commercial_weight": "very_high",
    }),
    ("objection", {
        "label": "Objections / Concerns",
        "description": "What's stopping them? Risk and trust signals",
        "templates": [
            "{kw} safe",
            "{kw} worth it",
            "{kw} pros and cons",
            "{kw} limitations",
            "{kw} problems",
            "{kw} scam",
            "{kw} reliable",
            "is {kw} legit",
        ],
        "commercial_weight": "medium",
    }),
    ("education", {
        "label": "Educational / Awareness",
        "description": "Top-of-funnel — learning what this thing is",
        "templates": [
            "what is {kw}",
            "how does {kw} work",
            "{kw} explained",
            "{kw} guide",
            "{kw} tutorial",
            "{kw} meaning",
            "{kw} vs {alt_kw}",
            "{kw} basics",
        ],
        "commercial_weight": "low",
    }),
])


def get_autocomplete(keyword: str, hl: str = "en") -> list[str]:
    """Fetch Google Autocomplete suggestions for a keyword."""
    q = urllib.parse.quote(keyword)
    url = f"https://suggestqueries.google.com/complete/search?client=firefox&q={q}&hl={hl}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read().decode())
        return data[1] if len(data) > 1 else []
    except Exception:
        return []


def generate_fanout(
    keyword: str,
    icp: str = "",
    lang: str = "en",
    live_check: bool = True,
) -> dict:
    """
    Generate the full Fan-out sub-query tree for a seed keyword.

    Returns structured dict with:
    - seed keyword
    - sub-queries grouped by intent dimension
    - live autocomplete validation (which queries have real search demand)
    - gold mine scores (high intent + low competition)
    """
    hl = "zh-CN" if lang == "zh" else "en"
    # Normalize: strip filler words that make templates awkward
    filler_prefixes = ["best ", "top ", "the "]
    kw_clean = keyword
    for fp in filler_prefixes:
        if kw_clean.lower().startswith(fp):
            kw_clean = kw_clean[len(fp):]
            break
    kw_clean = kw_clean.strip()
    kw_lower = kw_clean.lower()

    # Auto-detect alt keyword for comparison templates
    # e.g., "best CRM" → alt = "spreadsheet" or similar
    alt_kw = ""  # Let LLM/agent fill this; we leave blank for now

    # Collect live autocomplete data first
    live_suggestions: set[str] = set()
    if live_check:
        # Direct autocomplete
        for s in get_autocomplete(keyword, hl):
            live_suggestions.add(s.lower())
        # Expanded: keyword + modifier hints
        expansion_seeds = [
            keyword, f"best {keyword}", f"{keyword} for", f"{keyword} vs",
            f"{keyword} free", f"{keyword} pricing", f"{keyword} alternative",
            f"{keyword} review", f"how to {keyword}", f"is {keyword}",
        ]
        for seed in expansion_seeds:
            time.sleep(0.12)
            for s in get_autocomplete(seed, hl):
                live_suggestions.add(s.lower())

    # Generate sub-queries from templates
    results: list[dict] = []
    seen: set[str] = set()

    for dim_key, dim_meta in INTENT_DIMENSIONS.items():
        for template in dim_meta["templates"]:
            query = template.format(kw=kw_clean, icp=icp or "small business", alt_kw=alt_kw or "alternatives")
            query_lower = query.lower()

            if query_lower in seen:
                continue
            seen.add(query_lower)

            # Check if real users search this
            has_live_demand = query_lower in live_suggestions or any(
                query_lower in s or s in query_lower
                for s in live_suggestions
            )

            # Estimate competition (very rough proxy)
            # Long-tail queries (>4 words) tend to be lower competition
            word_count = len(query.split())
            if word_count >= 5:
                competition = "low"
            elif word_count >= 3:
                competition = "medium"
            else:
                competition = "high"

            # Gold mine score: high commercial intent + low competition
            cw = dim_meta["commercial_weight"]
            cw_score = {"very_high": 3, "high": 2, "medium": 1, "low": 0}[cw]
            comp_penalty = {"low": 0, "medium": 1, "high": 2}[competition]
            gold_score = cw_score * 2 - comp_penalty + (1 if has_live_demand else 0)

            results.append({
                "query": query,
                "dimension": dim_key,
                "dimension_label": dim_meta["label"],
                "description": dim_meta["description"],
                "commercial_intent": cw,
                "competition_estimate": competition,
                "live_demand": has_live_demand,
                "word_count": word_count,
                "gold_score": gold_score,  # higher = better opportunity
            })

    # Sort: gold_score desc, then commercial intent, then word_count
    results.sort(key=lambda x: (-x["gold_score"], -x["word_count"]))

    # Find gold mines (score >= 4)
    gold_mines = [r for r in results if r["gold_score"] >= 4]

    # Build pillar/cluster recommendation
    pillar = {
        "pillar_keyword": keyword,
        "recommended_pillar_article": f"The Ultimate Guide to {keyword.title()}" if lang == "en" else f"{keyword} 完全指南",
        "cluster_articles": [],
    }

    # Top gold mines become cluster articles
    for gm in gold_mines[:10]:
        pillar["cluster_articles"].append({
            "title": gm["query"],
            "dimension": gm["dimension_label"],
            "why": f"{gm['commercial_intent']} commercial intent, {gm['competition_estimate']} competition" +
                   (", validated by live search demand" if gm["live_demand"] else ""),
        })

    # Live suggestions not covered by templates (serendipity)
    template_queries = {r["query"].lower() for r in results}
    uncovered = sorted(
        s for s in live_suggestions
        if s not in template_queries and kw_lower in s
    )

    return {
        "seed_keyword": keyword,
        "icp": icp or "(generic)",
        "language": lang,
        "total_subqueries": len(results),
        "gold_mine_count": len(gold_mines),
        "live_suggestions_found": len(live_suggestions),
        "dimensions": {k: v["label"] for k, v in INTENT_DIMENSIONS.items()},
        "sub_queries": results,
        "gold_mines": gold_mines,
        "pillar_cluster_plan": pillar,
        "uncovered_live_suggestions": uncovered[:20],
    }


def format_report(data: dict) -> str:
    """Format the Fan-out report as readable text."""
    import io
    buf = io.StringIO()
    sep = "=" * 60
    seed = data["seed_keyword"]

    buf.write(f"{sep}\n")
    buf.write(f"GEO Fan-out Report: \"{seed}\"\n")
    buf.write(f"{sep}\n\n")

    buf.write(f"ICP: {data['icp']}\n")
    buf.write(f"Language: {data['language']}\n")
    buf.write(f"Total sub-queries generated: {data['total_subqueries']}\n")
    buf.write(f"Gold mine opportunities: {data['gold_mine_count']}\n")
    buf.write(f"Live search demand validated: {data['live_suggestions_found']} queries\n")

    # ── Gold Mines ──
    buf.write(f"\n{sep}\n")
    buf.write(f"GOLD MINE QUERIES (high intent + low competition)\n")
    buf.write(f"{sep}\n\n")

    if data["gold_mines"]:
        buf.write(f"{'Query':<45} {'Intent':<12} {'Comp':<8} {'Live'}\n")
        buf.write("-" * 75 + "\n")
        for gm in data["gold_mines"][:15]:
            live = "✓" if gm["live_demand"] else "—"
            buf.write(f"  {gm['query']:<43} {gm['commercial_intent']:<12} {gm['competition_estimate']:<8} {live}\n")
    else:
        buf.write("  No high-score gold mines detected. Try a more specific seed keyword.\n")

    # ── By Dimension ──
    buf.write(f"\n{sep}\n")
    buf.write(f"SUB-QUERIES BY INTENT DIMENSION\n")
    buf.write(f"{sep}\n")

    current_dim = ""
    for sq in data["sub_queries"]:
        if sq["dimension"] != current_dim:
            current_dim = sq["dimension"]
            dim_meta = INTENT_DIMENSIONS[current_dim]
            buf.write(f"\n  [{dim_meta['label']}] ({dim_meta['commercial_weight']} intent)\n")
            buf.write(f"  {dim_meta['description']}\n\n")

        gold = " ★" if sq["gold_score"] >= 4 else ""
        live = " ✓" if sq["live_demand"] else ""
        buf.write(f"    {sq['query']:<50} comp:{sq['competition_estimate']:<7}{gold}{live}\n")

    # ── Content Plan ──
    buf.write(f"\n{sep}\n")
    buf.write(f"PILLAR + CLUSTER CONTENT PLAN\n")
    buf.write(f"{sep}\n\n")

    plan = data["pillar_cluster_plan"]
    buf.write(f"  Pillar: {plan['recommended_pillar_article']}\n\n")
    buf.write(f"  Cluster articles ({len(plan['cluster_articles'])}):\n")
    for i, ca in enumerate(plan["cluster_articles"], 1):
        buf.write(f"    {i}. {ca['title']}\n")
        buf.write(f"       → {ca['why']}\n")

    # ── Uncovered Live Suggestions ──
    if data["uncovered_live_suggestions"]:
        buf.write(f"\n{sep}\n")
        buf.write(f"SERENDIPITOUS QUERIES (from live search, not in templates)\n")
        buf.write(f"{sep}\n\n")
        for s in data["uncovered_live_suggestions"]:
            buf.write(f"  • {s}\n")

    # ── GEO Tips ──
    buf.write(f"\n{sep}\n")
    buf.write(f"GEO CONTENT TIPS\n")
    buf.write(f"{sep}\n\n")
    buf.write("  1. BLUF: Answer each sub-query in the first 2 sentences\n")
    buf.write("  2. Structure: Use tables for comparisons (pricing, features, vs)\n")
    buf.write("  3. Specificity: Write 'for healthcare SMB' not 'for everyone'\n")
    buf.write("  4. External signals: Reddit threads + G2 reviews = AI citation fuel\n")
    buf.write("  5. Pillar page: Cover the broad topic, then deep-link clusters\n")
    buf.write("  6. Schema: Add FAQPage schema answering each sub-query\n")
    buf.write("  7. Refresh: Update dates and stats — AI prefers recent content\n")

    buf.write(f"\n{sep}\n")

    return buf.getvalue()


def main():
    parser = argparse.ArgumentParser(
        description="Generate AI search Query Fan-out sub-queries for content strategy."
    )
    parser.add_argument("keyword", help="Seed keyword (e.g., 'best CRM', 'ai video generator')")
    parser.add_argument("--icp", default="", help="Your Ideal Customer Profile (e.g., 'healthcare SMBs')")
    parser.add_argument("--lang", default="en", choices=["en", "zh"], help="Language for autocomplete")
    parser.add_argument("--no-live", action="store_true", help="Skip live autocomplete checks (faster)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    data = generate_fanout(
        keyword=args.keyword,
        icp=args.icp,
        lang=args.lang,
        live_check=not args.no_live,
    )

    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(format_report(data))


if __name__ == "__main__":
    main()
