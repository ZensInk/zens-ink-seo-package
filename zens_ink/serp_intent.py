#!/usr/bin/env python3
"""
SERP Intent — reverse-engineer search intent from actual Google results.

Instead of guessing intent from keyword text (like search_intent.py does),
this module fetches live SERP results and classifies each ranking page by
its actual content type. The distribution of page types reveals what Google
believes users want.

Two-layer scoring (Content Harmony 0-3 model):
    Each intent type gets a 0-3 score based on how many top-10 results
    match that intent's content type signature. This captures mixed intent
    (e.g. "workflow automation" = 70% informational + 30% commercial).

SERP feature detection:
    AI Overview, People Also Ask, Featured Snippet, Shopping, Knowledge
    Graph — each signals different intent and risk profiles.

Cross-validation with search_intent.py:
    When keyword-based classification and SERP-based classification agree,
    confidence is high. When they disagree, the SERP wins (Google's behavior
    is ground truth, not keyword text).

Usage:
    python -m zens_ink serp_intent "best astro theme"
    python -m zens_ink serp_intent "tarot meaning" --json
    python -m zens_ink serp_intent "生辰八字" --zh
    python -m zens_ink_pro.serp_intent "what is bazi" --json

Requires: SERPER_API_KEY environment variable.
"""

import json
import os
import re
import sys
import time
from urllib.parse import urlparse

# ── Config ──────────────────────────────────────────────────────────────────

SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")
SERPER_URL = "https://google.serper.dev/search"

# ── Page Type Detection ────────────────────────────────────────────────────
# Each organic result gets classified into exactly one page type.
# Page types are determined from URL path patterns, domain, and title signals.

# URL path patterns (checked in priority order)
_PATH_RULES = [
    # Transactional
    ("pricing",      [r"/pricing", r"/plans", r"/checkout", r"/buy", r"/order", r"/purchase", r"/subscribe"]),
    ("product",      [r"/product", r"/features", r"/app/", r"/software/", r"/platform/", r"/solution"]),
    # Tools / interactive
    ("tool",         [r"/tool", r"/calculator", r"/checker", r"/analyzer", r"/generator", r"/converter", r"/tester"]),
    # Content
    ("blog",         [r"/blog/", r"/article/", r"/post/", r"/guide/", r"/how-to", r"/tutorial", r"/news/", r"/insight"]),
    ("comparison",   [r"/vs/", r"/compare", r"/alternatives", r"/best-", r"/top-"]),
    ("documentation",[r"/docs", r"/documentation", r"/reference", r"/api/", r"/manual"]),
    ("directory",    [r"/directory", r"/list/", r"/category/", r"/catalog", r"/collection", r"/themes", r"/templates", r"/resources"]),
    ("wiki",         [r"/wiki/", r"/encyclopedia", r"/dictionary/"]),
    ("legal",        [r"/privacy", r"/terms", r"/legal", r"/cookie", r"/refund"]),
    ("about",        [r"/about", r"/contact", r"/team"]),
    # Shop / e-commerce paths
    ("shopping",     [r"/shop/", r"/store/", r"/product/", r"/item/", r"/p/", r"/dp/", r"/gp/product"]),
]

# Domains that override path-based detection
_DOMAIN_TYPES = {
    # Encyclopedic
    "en.wikipedia.org": "wiki", "zh.wikipedia.org": "wiki", "simple.wikipedia.org": "wiki",
    "britannica.com": "wiki", "baike.baidu.com": "wiki",
    "merriam-webster.com": "wiki", "dictionary.com": "wiki",
    # Video platforms
    "youtube.com": "video", "www.youtube.com": "video",
    "bilibili.com": "video", "www.bilibili.com": "video",
    "vimeo.com": "video",
    # Social / Q&A forums
    "reddit.com": "forum", "www.reddit.com": "forum",
    "quora.com": "forum", "www.quora.com": "forum",
    "stackoverflow.com": "forum",
    "zhihu.com": "forum", "www.zhihu.com": "forum",
    "douban.com": "forum",
    "medium.com": "blog",
    "weibo.com": "social", "www.weibo.com": "social",
    "pinterest.com": "social", "www.pinterest.com": "social",
    "instagram.com": "social", "www.instagram.com": "social",
    "facebook.com": "social", "www.facebook.com": "social",
    "x.com": "social", "twitter.com": "social",
    "tiktok.com": "video",
    "linkedin.com": "social", "www.linkedin.com": "social",
    # E-commerce
    "amazon.com": "shopping",
    "taobao.com": "shopping", "jd.com": "shopping",
    # App stores
    "apps.apple.com": "product", "play.google.com": "product",
    # Dev platforms
    "github.com": "repository",
    "npmjs.com": "repository", "www.npmjs.com": "repository",
    "pypi.org": "repository",
    # News/media
    "techcrunch.com": "blog", "wired.com": "blog", "www.wired.com": "blog",
    "theverge.com": "blog", "arstechnica.com": "blog",
    "cnet.com": "blog", "www.cnet.com": "blog",
}

# Title patterns for listicle / comparison detection (stronger than URL alone)
_LISTICLE_RE = re.compile(
    r"^(\d+\s+|top\s+\d+|best\s+\d+|the\s+\d+\s+(best|top)|\d+\s+(best|top|ways|tips|tools|free))"
    , re.IGNORECASE
)
_COMPARISON_TITLE_RE = re.compile(
    r"\b(vs\.?|versus|compared?\s+to|alternative[s]?\s+to|vs\b)", re.IGNORECASE
)
_REVIEW_TITLE_RE = re.compile(
    r"\b(review|reviewed|rated|rating|hands?\s*-?\s*on|tested)\b", re.IGNORECASE
)
# Buyer's guide / shopping intent in title
_BUYER_TITLE_RE = re.compile(
    r"\b(buy|buying\s+guide|where\s+to\s+buy|best\s+price|cheap|deal|sale|discount|"
    r"shop|order\s+online|free\s+shipping|coupon)\b", re.IGNORECASE
)

# Chinese title patterns
_ZH_LISTICLE_RE = re.compile(r"(十大|排行|排名|榜单|推荐\s*\d+|精选\s*\d+|\d+\s*(个|款|大|个最好))")
_ZH_COMPARISON_RE = re.compile(r"(对比|比较|区别|差异|哪个好|平替|替代品)")
_ZH_REVIEW_RE = re.compile(r"(评测|测评|评价|口碑|体验)")
_ZH_BUYER_RE = re.compile(r"(购买|买|哪里买|价格|多少钱|优惠|折扣|便宜|特价|包邮|正品)")


def _classify_page_type(url, title, organic_item=None):
    """Classify a SERP result into a page type.

    Priority:
        1. Domain override (youtube → video, reddit → forum, etc.)
        2. Title-based listicle/comparison/review detection (strong signal)
        3. URL path patterns
        4. Homepage detection
        5. Fallback: blog/article
    """
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    path = parsed.path.rstrip("/").lower()

    # 1. Domain override
    if domain in _DOMAIN_TYPES:
        dt = _DOMAIN_TYPES[domain]
        # But listicle/review/buyer titles still override platform domains
        if _LISTICLE_RE.search(title) or _ZH_LISTICLE_RE.search(title):
            return "listicle"
        if _COMPARISON_TITLE_RE.search(title) or _ZH_COMPARISON_RE.search(title):
            return "comparison"
        if _REVIEW_TITLE_RE.search(title) or _ZH_REVIEW_RE.search(title):
            return "review"
        if _BUYER_TITLE_RE.search(title) or _ZH_BUYER_RE.search(title):
            return "shopping"
        return dt

    # 2. Title-based detection (strong content format signal)
    if _LISTICLE_RE.search(title) or _ZH_LISTICLE_RE.search(title):
        return "listicle"
    if _COMPARISON_TITLE_RE.search(title) or _ZH_COMPARISON_RE.search(title):
        return "comparison"
    if _REVIEW_TITLE_RE.search(title) or _ZH_REVIEW_RE.search(title):
        return "review"
    if _BUYER_TITLE_RE.search(title) or _ZH_BUYER_RE.search(title):
        return "shopping"

    # 3. URL path patterns
    for ptype, patterns in _PATH_RULES:
        for pat in patterns:
            if re.search(pat, path):
                return ptype

    # 4. Homepage
    if path == "" or path == "/":
        return "homepage"

    # 5. Fallback
    return "article"


# ── Intent mapping ─────────────────────────────────────────────────────────
# Map each page type to the intent(s) it signals.
# A single page type can signal multiple intents with different weights.

_INTENT_WEIGHTS = {
    # page_type → {intent: weight}
    "blog":          {"informational": 3},
    "article":       {"informational": 1},  # generic — low confidence signal
    "wiki":          {"informational": 3},
    "documentation": {"informational": 3},
    "guide":         {"informational": 3},
    "tool":          {"informational": 1, "transactional": 2},  # "do" intent — users want to USE it
    "listicle":      {"commercial": 3},
    "comparison":    {"commercial": 3},
    "review":        {"commercial": 3},
    "directory":     {"commercial": 1, "informational": 1},
    "pricing":       {"transactional": 3},
    "product":       {"transactional": 2, "commercial": 1},
    "shopping":      {"transactional": 3, "commercial": 1},
    "homepage":      {"navigational": 1},  # weak — could be brand nav or just a tool homepage
    "forum":         {"informational": 1, "commercial": 1},  # mixed — Reddit threads
    "video":         {"informational": 2},  # tutorials, explainers
    "social":        {"navigational": 1, "informational": 1},
    "legal":         {"informational": 1},
    "about":         {"navigational": 2},
    "repository":    {"informational": 2, "transactional": 1},  # dev tools / OSS
}


def _score_intents(page_types):
    """Compute 0-3 intent scores from a list of page types.

    Uses position-weighted scoring: top results count more.
    Normalization denominator is the SAME for all intents (3 × sum of all
    position weights), so an intent with few matching pages gets a low
    score, not a falsely inflated one.
    """
    pos_weights = [1.00, 0.93, 0.86, 0.79, 0.72, 0.65, 0.58, 0.51, 0.44, 0.37]

    scores = {"informational": 0.0, "commercial": 0.0,
              "transactional": 0.0, "navigational": 0.0}

    # One global denominator — same for all intents
    n = len(page_types)
    total_weight = sum(pos_weights[min(i, 9)] for i in range(n))
    max_possible = 3.0 * total_weight  # theoretical max if every page scored 3

    for i, ptype in enumerate(page_types):
        pw = pos_weights[min(i, 9)]
        weights = _INTENT_WEIGHTS.get(ptype, {"informational": 1})
        for intent, w in weights.items():
            scores[intent] += w * pw

    # Normalize to 0-3 scale using global denominator
    result = {}
    for intent in scores:
        result[intent] = round(min(3.0, (scores[intent] / max_possible) * 3.0), 1)

    return result


# ── SERP feature detection ─────────────────────────────────────────────────

def _detect_serp_features(serp_data):
    """Extract SERP feature signals from Serper.dev response."""
    features = {
        "has_ai_overview": False,
        "has_answer_box": False,
        "has_people_also_ask": False,
        "has_knowledge_graph": False,
        "has_shopping": False,
        "has_featured_snippet": False,
        "has_news_box": False,
        "has_videos": False,
        "has_images": False,
        "has_local_pack": False,
        "has_sitelinks": False,
    }

    # Serper.dev response structure
    if serp_data.get("answerBox"):
        features["has_answer_box"] = True
        features["has_featured_snippet"] = True
    if serp_data.get("peopleAlsoAsk"):
        features["has_people_also_ask"] = True
    if serp_data.get("knowledgeGraph"):
        features["has_knowledge_graph"] = True
    if serp_data.get("shopping"):
        features["has_shopping"] = True
    if serp_data.get("news"):
        features["has_news_box"] = True
    if serp_data.get("videos"):
        features["has_videos"] = True
    if serp_data.get("images"):
        features["has_images"] = True
    if serp_data.get("places"):
        features["has_local_pack"] = True

    # Sitelinks (from organic results)
    for r in serp_data.get("organic", []):
        if r.get("sitelinks"):
            features["has_sitelinks"] = True
            break

    # AI Overview detection — Serper may include it under various keys
    for key in ("aiOverview", "ai_overview", "aiAnswer", "sgs",
                "searchGenerativeResponse", "relatedQuestions"):
        if serp_data.get(key):
            features["has_ai_overview"] = True
            break

    return features


# ── Content format recommendation ─────────────────────────────────────────

_CONTENT_FORMAT = {
    "informational": {
        "primary": "In-depth guide / tutorial (BLUF: answer first, then elaborate)",
        "structure": "H2/H3 hierarchy, FAQ section, clear definitions up top",
        "ai_risk": "HIGH — informational queries trigger AI Overviews 39.4% of the time. "
                   "Differentiate with unique data, original frameworks, or proprietary research.",
    },
    "commercial": {
        "primary": "Comparison table / ranked listicle / review",
        "structure": "Side-by-side feature matrix, pricing table, pros & cons per option",
        "ai_risk": "MEDIUM — ChatGPT triggers web search for commercial prompts 53.5% of the time. "
                   "Structure comparison data (price, features, ratings) for AI extraction.",
    },
    "transactional": {
        "primary": "Product / pricing / landing page (minimal friction)",
        "structure": "Clear CTA, pricing visible, no educational padding, trust signals",
        "ai_risk": "LOW — transactional queries rarely get AI Overviews. Focus on conversion.",
    },
    "navigational": {
        "primary": "Brand page / existing page optimization",
        "structure": "Ensure proper indexing, sitelinks, branded title tags",
        "ai_risk": "LOW — users want a specific destination, not synthesized answers.",
    },
}


def _recommend_format(scores, features):
    """Generate content format recommendation from intent scores + SERP features."""
    dominant = max(scores, key=scores.get)
    fmt = _CONTENT_FORMAT[dominant]

    # Detect mixed intent
    significant = {k: v for k, v in scores.items() if v >= 1.0}
    is_mixed = len(significant) > 1

    # Split intent advice
    split_advice = None
    if is_mixed:
        sorted_intents = sorted(significant.items(), key=lambda x: -x[1])
        parts = []
        total = sum(v for _, v in sorted_intents)
        for intent, score in sorted_intents:
            pct = round(score / total * 100)
            parts.append(f"{pct}% {intent}")
        split_advice = "Mixed intent SERP — " + " / ".join(parts) + \
                       ". Structure page to satisfy both paths."

    # AI Overview risk assessment
    ai_risk_level = "none"
    if features.get("has_ai_overview"):
        ai_risk_level = "confirmed"
    elif dominant == "informational":
        ai_risk_level = "high"
    elif dominant == "commercial":
        ai_risk_level = "medium"

    # PAA opportunity
    paa_advice = None
    if features.get("has_people_also_ask"):
        paa_advice = "PAA box detected — add FAQ section to target related questions."

    # Shopping signal
    shopping_advice = None
    if features.get("has_shopping"):
        shopping_advice = "Shopping results detected — Google sees transactional intent. " \
                          "If targeting informational, your content may get buried."

    return {
        "dominant_intent": dominant,
        "content_format": fmt["primary"],
        "content_structure": fmt["structure"],
        "ai_risk": fmt["ai_risk"] if ai_risk_level != "low" else "LOW — minimal AI Overview risk.",
        "ai_risk_level": ai_risk_level,
        "is_mixed_intent": is_mixed,
        "split_advice": split_advice,
        "paa_advice": paa_advice,
        "shopping_advice": shopping_advice,
    }


# ── Cross-validation with keyword-based intent ────────────────────────────

def _cross_validate(keyword_intent, serp_intent):
    """Compare keyword-based vs SERP-based intent classification."""
    if keyword_intent == serp_intent:
        return {
            "agreement": "match",
            "confidence": "high",
            "note": "Keyword text and SERP behavior agree — high confidence.",
        }
    else:
        return {
            "agreement": "mismatch",
            "confidence": "medium",
            "note": f"Keyword text suggests '{keyword_intent}' but SERP shows "
                    f"'{serp_intent}'. Trust the SERP — Google's behavior is ground truth. "
                    f"The keyword modifier may be misleading.",
        }


# ── HTTP ───────────────────────────────────────────────────────────────────

def _http_post_json(url, data, headers=None, timeout=15):
    import urllib.request
    body = json.dumps(data).encode("utf-8")
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=body, headers=h, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_serp(keyword, gl="us", hl="en", num=10):
    """Fetch SERP from Serper.dev."""
    if not SERPER_API_KEY:
        raise RuntimeError("SERPER_API_KEY not set")
    payload = {"q": keyword, "gl": gl, "hl": hl, "num": num}
    headers = {"X-API-KEY": SERPER_API_KEY}
    return _http_post_json(SERPER_URL, payload, headers=headers)


# ── Main analysis ─────────────────────────────────────────────────────────

def analyze(keyword, serp_data=None, gl="us", hl="en",
            keyword_intent=None):
    """Analyze search intent from SERP data.

    Args:
        keyword: The search query.
        serp_data: Pre-fetched SERP data (optional — fetches if None).
        gl: Geo location.
        hl: Language.
        keyword_intent: Intent from keyword-based classification (for cross-validation).

    Returns:
        Full intent analysis dict.
    """
    if serp_data is None:
        serp_data = fetch_serp(keyword, gl=gl, hl=hl)

    organic = serp_data.get("organic", [])
    if not organic:
        return {"error": "No organic results", "keyword": keyword}

    # Classify each result
    page_types = []
    results_detail = []
    for r in organic[:10]:
        url = r.get("link", "")
        title = r.get("title", "")
        pos = r.get("position", 99)
        ptype = _classify_page_type(url, title, r)
        page_types.append(ptype)
        results_detail.append({
            "position": pos,
            "title": title[:80],
            "url": url[:100],
            "domain": urlparse(url).netloc,
            "page_type": ptype,
        })

    # Score intents
    scores = _score_intents(page_types)
    dominant = max(scores, key=scores.get)

    # SERP features
    features = _detect_serp_features(serp_data)

    # Content format recommendation
    recommendation = _recommend_format(scores, features)

    # Cross-validation
    cross_val = None
    if keyword_intent:
        cross_val = _cross_validate(keyword_intent, dominant)

    # Page type distribution
    type_counts = {}
    for pt in page_types:
        type_counts[pt] = type_counts.get(pt, 0) + 1
    type_dist = dict(sorted(type_counts.items(), key=lambda x: -x[1]))

    # SERP uniqueness signal
    unique_domains = len(set(r["domain"] for r in results_detail))
    unique_page_types = len(set(page_types))

    return {
        "keyword": keyword,
        "dominant_intent": dominant,
        "intent_scores": scores,
        "page_type_distribution": type_dist,
        "serp_features": features,
        "recommendation": recommendation,
        "cross_validation": cross_val,
        "serp_diversity": {
            "unique_domains": unique_domains,
            "unique_page_types": unique_page_types,
            "is_fragmented": unique_page_types >= 5,
        },
        "results": results_detail,
    }


# ── Reporting ─────────────────────────────────────────────────────────────

def format_report(result):
    if result.get("error"):
        return f"Error: {result['error']}"

    lines = []
    lines.append("=" * 66)
    lines.append(f"  SERP Intent Analysis: {result['keyword']}")
    lines.append("=" * 66)
    lines.append("")

    # Dominant intent
    d = result["dominant_intent"]
    scores = result["intent_scores"]
    lines.append(f"  Dominant Intent: {d.upper()}")
    lines.append("")

    # Intent scores (visual bars)
    lines.append("  Intent Scores (0-3):")
    for intent in ["informational", "commercial", "transactional", "navigational"]:
        score = scores.get(intent, 0)
        bar = "█" * int(score) + "░" * (3 - int(score))
        lines.append(f"    {intent:15s} {bar} {score:.1f}")
    lines.append("")

    # Page type distribution
    lines.append("  SERP Page Types:")
    for ptype, count in result["page_type_distribution"].items():
        pct = round(count / 10 * 100)
        bar = "■" * count
        lines.append(f"    {ptype:15s} {count} ({pct}%) {bar}")
    lines.append("")

    # SERP features
    f = result["serp_features"]
    active_features = [k.replace("has_", "").replace("_", " ") for k, v in f.items() if v]
    if active_features:
        lines.append(f"  SERP Features: {', '.join(active_features)}")
    else:
        lines.append("  SERP Features: none detected")
    lines.append("")

    # Recommendation
    rec = result["recommendation"]
    lines.append("  ── Recommendation ──")
    lines.append(f"  Format:     {rec['content_format']}")
    lines.append(f"  Structure:  {rec['content_structure']}")

    if rec.get("is_mixed_intent") and rec.get("split_advice"):
        lines.append(f"  Split:      {rec['split_advice']}")

    lines.append(f"  AI Risk:    [{rec['ai_risk_level'].upper()}]")
    # Wrap AI risk text
    risk_text = rec["ai_risk"]
    while len(risk_text) > 60:
        split_at = risk_text.rfind(" ", 0, 61)
        if split_at == -1:
            split_at = 60
        lines.append(f"              {risk_text[:split_at]}")
        risk_text = risk_text[split_at+1:]
    if risk_text:
        lines.append(f"              {risk_text}")

    if rec.get("paa_advice"):
        lines.append(f"  PAA:        {rec['paa_advice']}")
    if rec.get("shopping_advice"):
        lines.append(f"  Shopping:   {rec['shopping_advice']}")
    lines.append("")

    # Cross-validation
    cv = result.get("cross_validation")
    if cv:
        icon = "✓" if cv["agreement"] == "match" else "⚠"
        lines.append(f"  {icon} Cross-validation: {cv['agreement']} (confidence: {cv['confidence']})")
        lines.append(f"    {cv['note']}")
        lines.append("")

    # SERP diversity
    div = result["serp_diversity"]
    if div["is_fragmented"]:
        lines.append(f"  ⚡ Fragmented SERP ({div['unique_page_types']} page types) — "
                     f"mixed signals, hard to satisfy all intents")
    lines.append("")

    # Top 10 breakdown
    lines.append("  ── Top 10 Results ──")
    for r in result["results"]:
        lines.append(f"    {r['position']:>2}. [{r['page_type']:12s}] {r['domain']}")
        lines.append(f"        {r['title']}")
    lines.append("")
    lines.append("=" * 66)

    return "\n".join(lines)


# ── CLI ───────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(
        prog="zens_ink serp_intent",
        description="SERP-based search intent analysis (reverse-engineers Google's behavior)",
    )
    parser.add_argument("keyword", help="Keyword to analyze")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--gl", default="us", help="Geo location (default: us)")
    parser.add_argument("--hl", default="en", help="Language (default: en)")
    parser.add_argument("--zh", action="store_true", help="Chinese mode (gl=cn, hl=zh-CN)")
    parser.add_argument("--cross", action="store_true",
                        help="Cross-validate with keyword-based intent classification")

    args = parser.parse_args()

    if not SERPER_API_KEY:
        print("Error: SERPER_API_KEY not set", file=sys.stderr)
        print("Get a free key at https://serper.dev (2500 free searches)", file=sys.stderr)
        sys.exit(1)

    gl = "cn" if args.zh else args.gl
    hl = "zh-CN" if args.zh else args.hl

    # Optional cross-validation
    kw_intent = None
    if args.cross:
        try:
            from zens_ink.search_intent import classify as kw_classify
            kw_intent = kw_classify(args.keyword)["intent"]
        except ImportError:
            pass

    serp = fetch_serp(args.keyword, gl=gl, hl=hl)
    result = analyze(args.keyword, serp_data=serp, gl=gl, hl=hl,
                     keyword_intent=kw_intent)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_report(result))


if __name__ == "__main__":
    main()
