#!/usr/bin/env python3
"""
Reddit Blue Ocean — Find high-traffic, low-competition Reddit posts.

Two-layer discovery:
  Layer 1 (always available): Google Autocomplete — find what people search
    with "reddit" prefix, revealing real Reddit search demand.
  Layer 2 (when Reddit API reachable): Fetch live post data (votes, comments,
    age) to score competition level.

Methodology: "Blue ocean" Reddit posts have high search traffic but few
votes/comments — meaning they rank well in Google but have low competition
for your content to be seen.

Inspired by 子木 (bysocket.com) Reddit blue ocean mining framework.

Scoring:
  Blue Ocean Score = traffic_signal * 3 - engagement_penalty
  Where:
    traffic_signal  = Google Autocomplete demand (1 or 0)
    engagement_penalty = vote_count/10 + comment_count/20 (capped at 5)
  
  Posts with score >= 2 are "blue ocean" — high traffic, low competition.

Usage:
  python3 -m zens_ink.reddit_blueocean "ai video generator"
  python3 -m zens_ink.reddit_blueocean "crm for small business" --niche saas
  python3 -m zens_ink.reddit_blueocean "ai video generator" --subreddits generativeAI,AI_Agents
  python3 -m zens_ink.reddit_blueocean "ai video generator" --json

Zero dependencies beyond Python stdlib.
"""

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from zens_ink.keyword_research import get_autocomplete

# ── Defaults ────────────────────────────────────────────────────────────────

_MAX_RESULTS = 25
_SUBREDDIT_LIMIT = 3  # max subreddits to search per keyword
_POST_FETCH_LIMIT = 50  # max posts to fetch per subreddit search

_COMMERCIAL_INTENT_WORDS = {
    "best", "alternative", "alternatives", "vs", "review", "compared",
    "recommend", "top", "cheapest", "worth it", "buy", "pricing",
    "how to", "which", "should i",
}

# Subreddits commonly associated with commercial-intent discussions
_COMMERCIAL_SUBREDDITS = {
    "entrepreneur", "smallbusiness", "saas", "startup", "indiehackers",
    "ecommerce", "digital_marketing", "seo", "webdev", "selfhosted",
    "software", "apps", "tools", "productivity",
}


# ── Reddit API ──────────────────────────────────────────────────────────────


def _reddit_request(endpoint: str, params: dict, timeout: int = 10) -> list | None:
    """Fetch data from Reddit's JSON API. Returns list of post dicts."""
    query = urllib.parse.urlencode(params)
    url = f"https://www.reddit.com/{endpoint}?{query}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "zens_ink/reddit_blueocean v1.0 (research bot)",
        "Accept": "application/json",
    })
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        data = json.loads(resp.read().decode())
        children = data.get("data", {}).get("children", [])
        return [c["data"] for c in children if "data" in c]
    except Exception as e:
        print(f"  [warn] Reddit API failed: {e}", file=sys.stderr)
        return None


def search_reddit(
    keyword: str,
    subreddits: list[str] | None = None,
    sort: str = "top",
    time_filter: str = "year",
    limit: int = _POST_FETCH_LIMIT,
) -> list[dict]:
    """
    Search Reddit for posts matching a keyword.
    
    Args:
        keyword: Search query
        subreddits: List of subreddit names to search (None = search all)
        sort: top, new, hot, relevant
        time_filter: hour, day, week, month, year, all
        limit: Max posts to fetch
    
    Returns list of normalized post dicts.
    """
    all_posts: list[dict] = []
    seen_ids: set[str] = set()

    if subreddits:
        # Search specific subreddits
        for sr in subreddits[:_SUBREDDIT_LIMIT]:
            posts = _reddit_request(
                f"r/{sr}/search.json",
                {
                    "q": keyword,
                    "sort": sort,
                    "t": time_filter,
                    "limit": str(limit),
                    "restrict_sr": "1",
                },
            )
            if posts:
                for p in posts:
                    if p["id"] not in seen_ids:
                        seen_ids.add(p["id"])
                        all_posts.append(_normalize_post(p))
            time.sleep(0.5)  # rate limit courtesy
    else:
        # Search all of Reddit
        posts = _reddit_request(
            "search.json",
            {
                "q": keyword,
                "sort": sort,
                "t": time_filter,
                "limit": str(limit),
                "type": "link",
            },
        )
        if posts:
            for p in posts:
                if p["id"] not in seen_ids:
                    seen_ids.add(p["id"])
                    all_posts.append(_normalize_post(p))

    return all_posts


def _normalize_post(raw: dict) -> dict:
    """Normalize a Reddit API post into a clean dict."""
    created = raw.get("created_utc", 0)
    now = datetime.now(timezone.utc).timestamp()
    age_days = int((now - created) / 86400) if created else 0

    title = raw.get("title", "")
    permalink = raw.get("permalink", "")
    url = f"https://www.reddit.com{permalink}" if permalink else raw.get("url", "")

    return {
        "id": raw.get("id", ""),
        "title": title,
        "subreddit": raw.get("subreddit", ""),
        "subreddit_full": raw.get("subreddit_name_prefixed", ""),
        "url": url,
        "score": raw.get("score", 0),
        "num_comments": raw.get("num_comments", 0),
        "upvote_ratio": raw.get("upvote_ratio", 0),
        "created_utc": created,
        "age_days": age_days,
        "is_self": raw.get("is_self", False),
        "flair": raw.get("link_flair_text", ""),
        "domain": raw.get("domain", ""),
    }


# ── Google Autocomplete (traffic signal) ────────────────────────────────────


def check_google_demand(query: str, hl: str = "en") -> bool:
    """Check if a query has Google Autocomplete suggestions (traffic signal)."""
    q = urllib.parse.quote(query)
    url = f"https://suggestqueries.google.com/complete/search?client=firefox&q={q}&hl={hl}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        resp = urllib.request.urlopen(req, timeout=8)
        data = json.loads(resp.read().decode())
        suggestions = data[1] if len(data) > 1 else []
        # If any suggestion contains the query, there's demand
        q_lower = query.lower()
        for s in suggestions:
            if q_lower in s.lower():
                return True
        return len(suggestions) > 3
    except Exception:
        return False  # can't verify, assume no


# ── Blue Ocean Scoring ──────────────────────────────────────────────────────


def score_post(post: dict, check_demand: bool = True) -> dict:
    """
    Calculate Blue Ocean Score for a Reddit post.
    
    Blue Ocean = high traffic potential + low competition (few votes/comments)
    """
    title = post["title"]
    title_lower = title.lower()

    # Engagement penalty: more votes/comments = more competitive
    vote_penalty = min(post["score"] / 10, 3)
    comment_penalty = min(post["num_comments"] / 20, 3)
    engagement_penalty = vote_penalty + comment_penalty

    # Commercial intent: does the title suggest buyer-ready audience?
    has_commercial = any(w in title_lower for w in _COMMERCIAL_INTENT_WORDS)
    is_commercial_sub = post["subreddit"].lower() in _COMMERCIAL_SUBREDDITS
    commercial_bonus = 2 if has_commercial else (1 if is_commercial_sub else 0)

    # Traffic signal from Google Autocomplete
    traffic_signal = 0
    if check_demand:
        traffic_signal = 1 if check_google_demand(title[:80]) else 0

    # Age factor: older posts with steady traffic are more valuable
    age_bonus = 0
    if post["age_days"] > 90 and post["age_days"] < 730:
        # 3 months to 2 years — established but not stale
        age_bonus = 1

    # Blue Ocean Score
    blue_ocean_score = (traffic_signal * 3) + commercial_bonus + age_bonus - engagement_penalty

    return {
        **post,
        "blue_ocean_score": round(blue_ocean_score, 1),
        "has_commercial_intent": has_commercial,
        "commercial_subreddit": is_commercial_sub,
        "traffic_signal": traffic_signal,
        "engagement_penalty": round(engagement_penalty, 1),
        "age_bonus": age_bonus,
        "is_blue_ocean": blue_ocean_score >= 2,
    }


# ── Discovery Workflow ──────────────────────────────────────────────────────


def discover_google_demand(keyword: str, lang: str = "en") -> dict:
    """
    Layer 1: Use Google Autocomplete to discover Reddit search demand.
    Always available (no Reddit API needed).
    
    Searches variations of "reddit {keyword}" to find what people are
    actively searching for on Reddit via Google.
    """
    hl = "zh-CN" if lang == "zh" else "en"
    
    # Build search variants
    modifiers = [
        "",  # bare keyword
        "best", "free", "alternative", "alternatives",
        "vs", "review", "pricing", "worth it",
        "how to", "is it", "should i",
    ]
    
    all_queries: dict[str, list[str]] = {}
    for mod in modifiers:
        q = f"reddit {mod} {keyword}".strip() if mod else f"reddit {keyword}"
        suggestions = get_autocomplete(q, hl)
        if suggestions:
            all_queries[q] = suggestions
        time.sleep(0.12)
    
    # Collect unique Reddit-intent queries (strip the "reddit" prefix for analysis)
    reddit_queries: dict[str, list[str]] = {}  # original search → autocomplete suggestions
    for search_q, suggests in all_queries.items():
        # These suggestions show what people search WITH the reddit prefix
        clean_suggests = []
        for s in suggests:
            # Keep suggestions that include the keyword
            if keyword.lower() in s.lower():
                clean_suggests.append(s)
        if clean_suggests:
            reddit_queries[search_q] = clean_suggests
    
    # Flatten and classify
    flat_queries: list[dict] = []
    seen: set[str] = set()
    for search_q, suggests in reddit_queries.items():
        for s in suggests:
            s_clean = s.strip()
            if s_clean.lower() in seen:
                continue
            seen.add(s_clean.lower())
            
            s_lower = s_clean.lower()
            has_commercial = any(w in s_lower for w in _COMMERCIAL_INTENT_WORDS)
            word_count = len(s_clean.split())
            competition = "low" if word_count >= 5 else ("medium" if word_count >= 3 else "high")
            
            flat_queries.append({
                "query": s_clean,
                "source_search": search_q,
                "has_commercial_intent": has_commercial,
                "competition_estimate": competition,
                "word_count": word_count,
                "blue_ocean_score": (3 if has_commercial else 1) - ({"low": 0, "medium": 1, "high": 2}[competition]),
            })
    
    flat_queries.sort(key=lambda x: -x["blue_ocean_score"])
    blue_ocean = [q for q in flat_queries if q["blue_ocean_score"] >= 2]
    
    return {
        "keyword": keyword,
        "total_queries_found": len(flat_queries),
        "blue_ocean_count": len(blue_ocean),
        "reddit_demand_queries": flat_queries,
        "blue_ocean_queries": blue_ocean,
    }


def discover(
    keyword: str,
    subreddits: list[str] | None = None,
    niche: str = "",
    lang: str = "en",
    check_demand: bool = True,
    limit: int = _MAX_RESULTS,
) -> dict:
    """
    Full Reddit blue ocean discovery workflow.
    
    Layer 1: Google Autocomplete demand discovery (always runs)
    Layer 2: Reddit API live data (optional, when network allows)
    """
    # Always run Layer 1
    demand_data = discover_google_demand(keyword, lang)

    # Try Layer 2 (Reddit API)
    auto_subreddits = subreddits
    if not auto_subreddits:
        broad_results = search_reddit(keyword, subreddits=None, limit=50)
        if broad_results:
            sr_counts: dict[str, int] = {}
            for p in broad_results:
                sr = p["subreddit"]
                sr_counts[sr] = sr_counts.get(sr, 0) + 1
            auto_subreddits = sorted(sr_counts, key=sr_counts.get, reverse=True)[:_SUBREDDIT_LIMIT]
        else:
            auto_subreddits = []
    
    all_posts = []
    if subreddits:
        all_posts = search_reddit(keyword, subreddits=subreddits, limit=50)
    elif auto_subreddits:
        all_posts = search_reddit(keyword, subreddits=auto_subreddits, limit=50)

    # Score posts if we got any
    scored = []
    for p in all_posts:
        s = score_post(p, check_demand=check_demand)
        scored.append(s)
        if check_demand:
            time.sleep(0.15)

    scored.sort(key=lambda x: -x["blue_ocean_score"])
    blue_ocean_posts = [s for s in scored if s["is_blue_ocean"]]

    # Merge demand queries into recommendations
    recommendations = _generate_recommendations(
        scored, blue_ocean_posts, keyword, niche
    )
    
    # Add Google demand findings to recommendations
    if demand_data["blue_ocean_queries"]:
        recommendations.insert(0, f"GOOGLE DEMAND: {demand_data['blue_ocean_count']} blue ocean Reddit queries found on Google.")
    if demand_data["reddit_demand_queries"]:
        top_demand = demand_data["reddit_demand_queries"][:3]
        for d in top_demand:
            recommendations.insert(1, f"  Search: '{d['query']}' ({d['competition_estimate']} competition, {'commercial' if d['has_commercial_intent'] else 'informational'})")

    return {
        "keyword": keyword,
        "niche": niche,
        "subreddits_searched": auto_subreddits or ["(API unavailable — Google demand only)"],
        "google_demand": demand_data,
        "total_posts": len(scored),
        "blue_ocean_count": len(blue_ocean_posts) + demand_data["blue_ocean_count"],
        "blue_ocean_posts": blue_ocean_posts[:limit],
        "all_posts": scored[:limit],
        "recommendations": recommendations,
    }


def _generate_recommendations(
    all_posts: list[dict],
    blue_ocean: list[dict],
    keyword: str,
    niche: str,
) -> list[str]:
    """Generate actionable content recommendations."""
    recs = []

    if not blue_ocean:
        recs.append(f"No clear blue ocean posts found for '{keyword}'. Try a more specific long-tail variant.")
        return recs

    # Top opportunity
    top = blue_ocean[0]
    recs.append(
        f"TOP OPPORTUNITY: \"{top['title']}\" in r/{top['subreddit']} "
        f"(score {top['score']}, {top['num_comments']} comments, BO={top['blue_ocean_score']})"
    )

    # Commercial intent posts
    commercial = [p for p in blue_ocean if p["has_commercial_intent"]]
    if commercial:
        recs.append(
            f"{len(commercial)} blue ocean posts with commercial intent "
            f"(best/alternatives/vs/review) — prioritize these for conversion."
        )

    # Low engagement but traffic signal
    traffic_no_engagement = [p for p in blue_ocean if p["traffic_signal"] and p["score"] < 20]
    if traffic_no_engagement:
        recs.append(
            f"{len(traffic_no_engagement)} posts with Google demand but <20 upvotes — "
            f"easy to rank with a helpful answer."
        )

    # Subreddit concentration
    sr_counts: dict[str, int] = {}
    for p in blue_ocean:
        sr_counts[p["subreddit"]] = sr_counts.get(p["subreddit"], 0) + 1
    top_sr = max(sr_counts, key=sr_counts.get) if sr_counts else ""
    if top_sr and sr_counts[top_sr] >= 2:
        recs.append(f"r/{top_sr} has the most blue ocean posts ({sr_counts[top_sr]}) — focus your content here.")

    # Content angle suggestions
    recs.append("CONTENT ANGLES:")
    recs.append(f"  • Write a blog post answering the same question, then link from Reddit")
    recs.append(f"  • Create a comparison table (vs/alternatives) — AI engines love tables")
    recs.append(f"  • Post genuine value answers in low-comment threads to build authority")
    recs.append(f"  • Monitor these posts weekly — new comments are new entry points")

    return recs


# ── Output ──────────────────────────────────────────────────────────────────


def format_report(data: dict) -> str:
    import io
    buf = io.StringIO()
    sep = "=" * 60
    kw = data["keyword"]

    buf.write(f"{sep}\n")
    buf.write(f"Reddit Blue Ocean Report: \"{kw}\"\n")
    buf.write(f"{sep}\n\n")

    buf.write(f"Niche: {data.get('niche') or '(unspecified)'}\n")
    buf.write(f"Subreddits: {', '.join(data.get('subreddits_searched', []))}\n")
    buf.write(f"Total posts found: {data['total_posts']}\n")
    buf.write(f"Blue ocean total: {data['blue_ocean_count']}\n")

    # ── Google Demand Layer ──
    gd = data.get("google_demand", {})
    if gd and gd.get("reddit_demand_queries"):
        buf.write(f"\n{sep}\n")
        buf.write(f"GOOGLE REDDIT DEMAND (Layer 1 — Autocomplete)\n")
        buf.write(f"{sep}\n\n")

        bo_queries = gd.get("blue_ocean_queries", [])
        all_queries = gd.get("reddit_demand_queries", [])

        if bo_queries:
            buf.write(f"Blue ocean queries (high demand + low competition):\n\n")
            for q in bo_queries[:15]:
                ci = "$" if q["has_commercial_intent"] else " "
                buf.write(
                    f"  {ci} BO={q['blue_ocean_score']:>2.0f} | {q['competition_estimate']:<6} | {q['query']}\n"
                )
        elif all_queries:
            buf.write(f"Reddit demand queries found:\n\n")
            for q in all_queries[:10]:
                ci = "$" if q["has_commercial_intent"] else " "
                buf.write(f"  {ci} {q['query']}\n")

    # ── Reddit API Blue Ocean Posts ──
    blue = data.get("blue_ocean_posts", [])
    if blue:
        buf.write(f"\n{sep}\n")
        buf.write(f"BLUE OCEAN POSTS (Layer 2 — Reddit API)\n")
        buf.write(f"{sep}\n\n")
        for p in blue[:20]:
            t = p["title"][:48]
            traffic = "✓" if p["traffic_signal"] else "—"
            buf.write(f"  ↑{p['score']} 💬{p['num_comments']} BO={p['blue_ocean_score']:.1f} {traffic}\n")
            buf.write(f"    {t}\n")
            buf.write(f"    r/{p['subreddit']}  ·  {p['url']}\n\n")

    # ── All Reddit Posts ──
    all_p = data.get("all_posts", [])
    if all_p:
        buf.write(f"\n{sep}\n")
        buf.write(f"ALL REDDIT POSTS (ranked by Blue Ocean Score)\n")
        buf.write(f"{sep}\n\n")
        for p in all_p[:25]:
            marker = " ★" if p["is_blue_ocean"] else ""
            commercial = " $" if p["has_commercial_intent"] else ""
            buf.write(
                f"  BO={p['blue_ocean_score']:>5.1f} | r/{p['subreddit']:<15} | "
                f"↑{p['score']:<5} 💬{p['num_comments']:<5} | {p['title'][:45]}{marker}{commercial}\n"
            )

    # ── Recommendations ──
    buf.write(f"\n{sep}\n")
    buf.write(f"RECOMMENDATIONS\n")
    buf.write(f"{sep}\n\n")
    for r in data.get("recommendations", []):
        buf.write(f"  {r}\n")

    buf.write(f"\n{sep}\n")

    return buf.getvalue()


# ── CLI ─────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Find Reddit blue ocean posts: high traffic, low competition opportunities."
    )
    parser.add_argument("keyword", help="Seed keyword (e.g., 'ai video generator')")
    parser.add_argument("--subreddits", "-s", default="", help="Comma-separated subreddits (default: auto-discover)")
    parser.add_argument("--niche", "-n", default="", help="Your niche/ICP (e.g., 'saas', 'ecommerce')")
    parser.add_argument("--lang", default="en", choices=["en", "zh"], help="Language")
    parser.add_argument("--no-demand", action="store_true", help="Skip Google demand check (faster)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    subreddits = [s.strip() for s in args.subreddits.split(",") if s.strip()] or None

    data = discover(
        keyword=args.keyword,
        subreddits=subreddits,
        niche=args.niche,
        lang=args.lang,
        check_demand=not args.no_demand,
    )

    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(format_report(data))


if __name__ == "__main__":
    main()
