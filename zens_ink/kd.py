#!/usr/bin/env python3
"""
Keyword Difficulty (KD) estimator — ZensInk lightweight edition.

Core innovation: SERP structure analysis (homepage ratio, domain age profile,
niche maturity) as the primary difficulty signal, eliminating the need for
expensive Ahrefs DR data.

Scoring model (0-100):
  Base score from weighted SERP structure (page-type × position × authority)
  + Signal modifiers (homepage density, brand dominance, niche maturity,
    weak-domain opportunity, domain age profile)

Usage:
  python -m zens_ink kd "the fool tarot meaning"
  python -m zens_ink kd "tarot meaning" --json
  python -m zens_ink kd "生辰八字" --zh
"""

import json
import sys
import os
import time
import math
import urllib.request
import urllib.parse
from datetime import datetime, timezone

# ── Config ──────────────────────────────────────────────────────────────────

from zens_ink.config import SERPER_API_KEY, BING_API_KEY
SERPER_URL = "https://google.serper.dev/search"
BING_STATS_URL = "https://ssl.bing.com/webmaster/api.svc/json/GetKeywordStats"

# Curated authority domains (high DR proxies — no API needed)
AUTHORITY_DOMAINS = {
    # Encyclopedic (DR 95+)
    "en.wikipedia.org": 0.95, "zh.wikipedia.org": 0.95, "simple.wikipedia.org": 0.95,
    "wikimedia.org": 0.90, "britannica.com": 0.92,
    # Platforms (high authority, but beatable for informational queries)
    "youtube.com": 0.95, "www.youtube.com": 0.95,
    "reddit.com": 0.90, "www.reddit.com": 0.90,
    "quora.com": 0.88, "www.quora.com": 0.88,
    "pinterest.com": 0.92, "www.pinterest.com": 0.92,
    "medium.com": 0.90, "tiktok.com": 0.92,
    "instagram.com": 0.93, "www.instagram.com": 0.93,
    "facebook.com": 0.95, "www.facebook.com": 0.95,
    "twitter.com": 0.93, "x.com": 0.93,
    "linkedin.com": 0.93, "www.linkedin.com": 0.93,
    # App stores
    "apps.apple.com": 0.95, "play.google.com": 0.95, "apps.microsoft.com": 0.93,
    # Major tech
    "amazon.com": 0.95, "github.com": 0.94, "stackoverflow.com": 0.92,
    # Major media / news (DR 90+)
    "forbes.com": 0.93, "www.forbes.com": 0.93,
    "cnbc.com": 0.92, "www.cnbc.com": 0.92,
    "nytimes.com": 0.95, "www.nytimes.com": 0.95,
    "bbc.com": 0.95, "www.bbc.com": 0.95,
    "cnn.com": 0.94, "www.cnn.com": 0.94,
    "reuters.com": 0.94, "www.reuters.com": 0.94,
    "bloomberg.com": 0.93, "www.bloomberg.com": 0.93,
    "theguardian.com": 0.93, "www.theguardian.com": 0.93,
    "washingtonpost.com": 0.94,
    "vogue.com": 0.91, "www.vogue.com": 0.91,
    "elle.com": 0.88, "www.elle.com": 0.88,
    "cosmopolitan.com": 0.87,
    "hindustantimes.com": 0.85, "www.hindustantimes.com": 0.85,
    # Tech media
    "techcrunch.com": 0.92, "wired.com": 0.91, "www.wired.com": 0.91,
    "theverge.com": 0.91, "arstechnica.com": 0.90,
    "cnet.com": 0.91, "www.cnet.com": 0.91,
    "pcmag.com": 0.88, "engadget.com": 0.90,
    # Finance / credit
    "nerdwallet.com": 0.90, "www.nerdwallet.com": 0.90,
    "bankrate.com": 0.89, "www.bankrate.com": 0.89,
    "creditkarma.com": 0.88, "www.creditkarma.com": 0.88,
    "creditcards.com": 0.87, "www.creditcards.com": 0.87,
    "investopedia.com": 0.91, "www.investopedia.com": 0.91,
    "mastercard.com": 0.88, "www.mastercard.com": 0.88,
    "visa.com": 0.88, "www.visa.com": 0.88,
    # Health / medical
    "healthline.com": 0.90, "webmd.com": 0.90, "mayoclinic.org": 0.90,
    "psychologytoday.com": 0.88, "verywellmind.com": 0.87,
    "medicalnewstoday.com": 0.88, "medlineplus.gov": 0.90,
    "webmd.com": 0.90,
    # Travel
    "tripadvisor.com": 0.92, "www.tripadvisor.com": 0.92,
    "booking.com": 0.93, "www.booking.com": 0.93,
    "expedia.com": 0.90, "www.expedia.com": 0.90,
    # Education
    "coursera.org": 0.91, "edx.org": 0.89, "udemy.com": 0.90,
    "khanacademy.org": 0.90,
    # Reviews / recommendations
    "consumerreports.org": 0.90, "tomsguide.com": 0.88,
    "thepointsguy.com": 0.85, "www.thepointsguy.com": 0.85,
    # Q&A / reference
    "merriam-webster.com": 0.91, "dictionary.com": 0.88,
    "cambridge.org": 0.90,
    # Chinese platforms
    "baike.baidu.com": 0.90, "zhihu.com": 0.88, "www.zhihu.com": 0.88,
    "douban.com": 0.87, "weibo.com": 0.90, "www.weibo.com": 0.90,
    "csdn.net": 0.82, "www.csdn.net": 0.82,
    "juejin.cn": 0.80, "www.juejin.cn": 0.80,
    "bilibili.com": 0.88, "www.bilibili.com": 0.88,
    "sina.com.cn": 0.90, "www.sina.com.cn": 0.90,
    "sohu.com": 0.87, "www.sohu.com": 0.87,
    "163.com": 0.89, "www.163.com": 0.89,
}

PLATFORM_DOMAINS = {
    "youtube.com", "www.youtube.com", "reddit.com", "www.reddit.com",
    "quora.com", "www.quora.com", "pinterest.com", "www.pinterest.com",
    "medium.com", "instagram.com", "www.instagram.com",
    "facebook.com", "www.facebook.com", "twitter.com", "x.com",
    "linkedin.com", "www.linkedin.com", "tiktok.com",
    "apps.apple.com", "play.google.com", "apps.microsoft.com",
    "zhihu.com", "www.zhihu.com", "weibo.com", "www.weibo.com",
    "douban.com", "bilibili.com", "www.bilibili.com",
}

# ── HTTP helpers ────────────────────────────────────────────────────────────

def _http_get_json(url, headers=None, timeout=15):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))

def _http_post_json(url, data, headers=None, timeout=15):
    body = json.dumps(data).encode("utf-8")
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=body, headers=h, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))

# ── RDAP domain age ────────────────────────────────────────────────────────

# Persistent domain age cache — avoids redundant RDAP lookups across keywords
_DOMAIN_AGE_CACHE = {}
_DOMAIN_AGE_CACHE_PATH = os.path.join(os.path.expanduser("~"), ".zens_ink", "domain-age-cache.json")
def _load_domain_age_cache():
    global _DOMAIN_AGE_CACHE
    if not _DOMAIN_AGE_CACHE:
        try:
            with open(_DOMAIN_AGE_CACHE_PATH) as f:
                _DOMAIN_AGE_CACHE = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            _DOMAIN_AGE_CACHE = {}
def _save_domain_age_cache():
    try:
        os.makedirs(os.path.dirname(_DOMAIN_AGE_CACHE_PATH), exist_ok=True)
        with open(_DOMAIN_AGE_CACHE_PATH, "w") as f:
            json.dump(_DOMAIN_AGE_CACHE, f, indent=2)
    except Exception:
        pass

def get_domain_age(domain):
    """Return registration year (int) via RDAP, or None. Cached persistently."""
    clean = domain.replace("www.", "")
    _load_domain_age_cache()
    if clean in _DOMAIN_AGE_CACHE:
        return _DOMAIN_AGE_CACHE[clean]
    try:
        req = urllib.request.Request(f"https://rdap.org/domain/{clean}")
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        for event in data.get("events", []):
            if event.get("eventAction") == "registration":
                year = int(event["eventDate"][:4])
                _DOMAIN_AGE_CACHE[clean] = year
                _save_domain_age_cache()
                return year
    except Exception:
        pass
    _DOMAIN_AGE_CACHE[clean] = None
    _save_domain_age_cache()
    return None

# ── Serper SERP fetch ──────────────────────────────────────────────────────

def fetch_serp(keyword, gl="us", hl="en", num=10):
    payload = {"q": keyword, "gl": gl, "hl": hl, "num": num}
    headers = {"X-API-KEY": SERPER_API_KEY}
    return _http_post_json(SERPER_URL, payload, headers=headers)

# ── Bing search volume ─────────────────────────────────────────────────────

def fetch_search_volume(keyword, market="en-US"):
    if not BING_API_KEY:
        return None
    params = urllib.parse.urlencode({"q": keyword, "market": market, "apikey": BING_API_KEY})
    url = f"{BING_STATS_URL}?{params}"
    try:
        data = _http_get_json(url, timeout=10)
        stats = data.get("d", [])
        if stats:
            return stats[0].get("BroadImpression", 0)
    except Exception:
        pass
    return None

# ── URL / domain analysis ─────────────────────────────────────────────────

def parse_url(url):
    parsed = urllib.parse.urlparse(url)
    return parsed.netloc.lower(), parsed.path.rstrip("/")

def is_homepage(url):
    _, path = parse_url(url)
    return path == "" or path == "/"

def is_platform(url):
    domain, _ = parse_url(url)
    return domain in PLATFORM_DOMAINS

def get_authority(url):
    domain, _ = parse_url(url)
    return AUTHORITY_DOMAINS.get(domain)

def title_matches_keyword(title, keyword):
    title_lower = title.lower()
    keyword_lower = keyword.lower()
    kw_words = [w for w in keyword_lower.split() if len(w) > 2]
    if not kw_words:
        return keyword_lower in title_lower
    matches = sum(1 for w in kw_words if w in title_lower)
    return matches >= max(1, len(kw_words) * 0.6)

def classify_result(result, keyword):
    url = result.get("link", "")
    title = result.get("title", "")
    pos = result.get("position", 99)
    has_sitelinks = bool(result.get("sitelinks"))

    domain, _ = parse_url(url)
    home = is_homepage(url)
    platform = is_platform(url)
    known_auth = get_authority(url)

    if home:
        page_type, type_mult = "homepage", 1.0
    elif title_matches_keyword(title, keyword):
        page_type, type_mult = "dedicated", 0.65
    else:
        page_type, type_mult = "inner", 0.45

    return {
        "position": pos, "url": url, "domain": domain, "title": title,
        "page_type": page_type, "type_multiplier": type_mult,
        "is_homepage": home, "is_platform": platform,
        "known_authority": known_auth,
        "has_sitelinks": has_sitelinks,
        "registration_year": None,
        "authority_score": known_auth,
        "auth_source": "known_list" if known_auth is not None else None,
    }

# ── Domain authority estimation ───────────────────────────────────────────

def estimate_domain_auth(domain, registration_year=None):
    """Estimate authority (0-1) without Ahrefs DR. Domain age is primary proxy."""
    known = AUTHORITY_DOMAINS.get(domain) or AUTHORITY_DOMAINS.get(domain.replace("www.", ""))
    if known is not None:
        return known, "known_list"

    if registration_year:
        age = datetime.now(timezone.utc).year - registration_year
        # Conservative age curve (can't match real DR, just a rough proxy):
        # 1yr→0.28, 2yr→0.34, 3yr→0.38, 5yr→0.45, 8yr→0.52, 10yr→0.56,
        # 15yr→0.63, 20yr→0.68, 25yr→0.72
        if age <= 0:
            score = 0.20
        else:
            score = min(0.72, 0.22 + 0.15 * math.log(age) / math.log(3))
        return score, f"age_{age}yr"

    return 0.35, "unknown"

# ── KD Scoring ────────────────────────────────────────────────────────────

# Ahrefs public-study KD → referring domains needed for top-10 (approximation,
# used for link-budget interpolation only — not a ranking guarantee)
KD_RD_CURVE = [
    (0, 4), (10, 10), (20, 28), (30, 55), (40, 90), (50, 140),
    (60, 220), (70, 350), (80, 540), (90, 850), (100, 1300),
]
DIRECTORY_LINK_MULTIPLIER = 3.5  # easy/directory links are weaker per link


def estimate_link_budget(kd_score):
    """Interpolate referring domains needed to enter top-10 from a KD score.
    Dual track (哥飞-model): editorial (quality) links vs directory (easy) links.
    Returns low/mid/high bands. Estimates only — basis is Ahrefs' public curve."""
    def interp(score):
        for (k0, v0), (k1, v1) in zip(KD_RD_CURVE, KD_RD_CURVE[1:]):
            if k0 <= score <= k1:
                t = (score - k0) / (k1 - k0)
                return v0 + t * (v1 - v0)
        return KD_RD_CURVE[-1][1]

    mid = interp(kd_score)
    return {
        "kd_basis": round(kd_score, 1),
        "editorial": {
            "low": max(1, round(mid * 0.6)),
            "mid": max(2, round(mid)),
            "high": max(3, round(mid * 1.5)),
        },
        "directory": {
            "low": max(3, round(mid * 0.6 * DIRECTORY_LINK_MULTIPLIER)),
            "mid": max(5, round(mid * DIRECTORY_LINK_MULTIPLIER)),
            "high": max(8, round(mid * 1.5 * DIRECTORY_LINK_MULTIPLIER)),
        },
        "basis": (
            "interpolated from Ahrefs KD→referring-domains public study (top-10); "
            "editorial = quality links, directory = easy links (~3.5x more needed); "
            "estimates for planning, not a ranking guarantee"
        ),
    }


def detect_brand_keyword(results, keyword, serp_data=None):
    """Triple-fingerprint brand detection (哥飞-model, adapted to free SERP data).

    F1 official_domain   — a top-3 domain's brand matches the keyword
    F2 brand_dominance   — brand domain family occupies >=3 top-10 slots
                           (proxy for expanded Sitelinks: brand SERPs show
                           multiple same-brand pages; Serper has no sitelinks field)
    F3 platform_ecosystem— app store present + >=2 platform results, or >=3 platforms
    +  knowledge_panel   — knowledgeGraph block present (bonus confirm)

    >=2 fingerprints → brand keyword. Brand mode then reports the
    derivative-entry difficulty (截流口径) instead of direct ranking odds.
    """
    kw_lower = keyword.lower().strip()
    kw_words = [w for w in kw_lower.split() if len(w) >= 3] or [kw_lower.split()[0]]
    primary = kw_words[0]
    joined = kw_lower.replace(" ", "")

    fingerprints = []
    brand_root = None
    brand_domain = None

    def _brand_label(domain):
        """Root brand label of a domain, stripping service subdomains
        (docs./support./chat./...) so docs.google.com counts as google."""
        d = domain.replace("www.", "")
        parts = d.split(".")
        strip = {"docs", "support", "help", "mail", "m", "play", "chat",
                 "developer", "developers", "business", "news", "blog", "app"}
        while len(parts) > 2 and parts[0] in strip:
            parts = parts[1:]
        return parts[0]

    # F1: same-name official domain in top 3 (exact / prefix / near-plural match).
    # Guards against generic-word false fires: prefix match requires brand len>=5,
    # plural match requires primary len>=5 (excludes "time"-style generic roots).
    for r in results[:3]:
        dom = r["domain"].replace("www.", "")
        brand_part = _brand_label(dom)
        if len(brand_part) >= 4 and (
            joined == brand_part
            or (len(brand_part) >= 5 and joined.startswith(brand_part))
            or (len(primary) >= 5 and brand_part.startswith(primary)
                and len(brand_part) - len(primary) <= 2)
        ):
            fingerprints.append("official_domain")
            brand_root = brand_part
            parts = dom.split(".")
            brand_domain = ".".join(parts[-2:]) if len(parts) >= 2 else dom
            break

    # F2: brand domain family occupies >=2 slots (expanded-sitelinks proxy:
    # brand SERPs surface multiple same-brand pages; Serper has no sitelinks field)
    if brand_root:
        fam = sum(1 for r in results if _brand_label(r["domain"]) == brand_root)
        if fam >= 2:
            fingerprints.append("brand_dominance")

    # F3: platform ecosystem density (app store / brand community)
    platform_count = sum(1 for r in results if r["is_platform"])
    appstore = any(
        r["domain"] in ("apps.apple.com", "play.google.com", "apps.microsoft.com")
        for r in results
    )
    if (platform_count >= 2 and appstore) or platform_count >= 3:
        fingerprints.append("platform_ecosystem")

    # Bonus: knowledge panel
    if (serp_data or {}).get("knowledgeGraph"):
        fingerprints.append("knowledge_panel")

    return {
        "is_brand": len(fingerprints) >= 2,
        "fingerprints": fingerprints,
        "brand_root": brand_root,
        "brand_domain": brand_domain,
    }


def _score_signals(results, search_volume=None):
    """Multi-signal KD scoring over classified results (哥飞-style page-type
    discounting: homepage 100% / dedicated 65% / casual inner 45%, position-
    weighted) on free data. Returns score components + SERP counts."""
    pos_weights = [1.00, 0.93, 0.86, 0.79, 0.72, 0.65, 0.58, 0.51, 0.44, 0.37]
    weighted_sum = 0.0
    weight_total = 0.0
    for i, r in enumerate(results):
        pw = pos_weights[min(i, 9)]
        weighted_sum += r["authority_score"] * r["type_multiplier"] * pw
        weight_total += pw
    serp_strength = weighted_sum / weight_total if weight_total else 0.5

    home_count = sum(1 for r in results if r["is_homepage"])
    ages = [datetime.now(timezone.utc).year - r["registration_year"]
            for r in results if r.get("registration_year")]
    avg_age = sum(ages) / len(ages) if ages else None
    platform_count = sum(1 for r in results if r["is_platform"])
    has_sitelinks = any(r["has_sitelinks"] for r in results)

    mature_dedicated = sum(
        1 for r in results
        if r["page_type"] == "dedicated"
        and (r.get("registration_year") and datetime.now(timezone.utc).year - r["registration_year"] > 8
             or r["authority_score"] >= 0.70)
    )
    weak_domains = [r for r in results if r["authority_score"] < 0.50 and not r["is_platform"]]
    weak_in_top5 = [r for r in weak_domains if r["position"] <= 5]
    new_domains = [r for r in results if r.get("registration_year")
                   and datetime.now(timezone.utc).year - r["registration_year"] < 2]

    base = serp_strength * 60
    modifiers = {}

    if home_count >= 7:
        modifiers["homepage_crowded"] = 18
    elif home_count >= 5:
        modifiers["homepage_heavy"] = 10
    elif home_count >= 3:
        modifiers["homepage_moderate"] = 4
    elif home_count == 0:
        modifiers["no_homepages"] = -5

    if mature_dedicated >= 5:
        modifiers["mature_niche"] = 14
    elif mature_dedicated >= 3:
        modifiers["established_niche"] = 7

    if has_sitelinks and platform_count >= 3:
        modifiers["brand_dominated"] = 12
    elif platform_count >= 5:
        modifiers["platform_heavy"] = 6

    if avg_age:
        if avg_age >= 15:
            modifiers["old_domains"] = 6
        elif avg_age <= 3:
            modifiers["young_domains"] = -6

    if weak_in_top5:
        modifiers["weak_top5"] = -min(15, len(weak_in_top5) * 5)
    elif weak_domains:
        modifiers["weak_lower"] = -min(8, len(weak_domains) * 3)

    if new_domains:
        modifiers["new_domain_proof"] = -5

    top3 = results[:3]
    top3_strong = all(
        r["authority_score"] >= 0.80 or (r["is_homepage"] and r["authority_score"] >= 0.60)
        for r in top3
    )
    if top3_strong:
        modifiers["top3_fortress"] = 6

    if search_volume:
        if search_volume > 500000:
            modifiers["very_high_volume"] = 6
        elif search_volume > 100000:
            modifiers["high_volume"] = 3
        elif search_volume < 500:
            modifiers["low_volume"] = -2

    modifier_total = sum(modifiers.values())
    raw_score = base + modifier_total
    final_score = max(1, min(99, raw_score))

    dedicated_count = sum(1 for r in results if r["page_type"] == "dedicated")
    return {
        "base": base,
        "modifiers": modifiers,
        "modifier_total": modifier_total,
        "raw_score": raw_score,
        "final_score": final_score,
        "serp_counts": {
            "homepage_count": home_count,
            "dedicated_count": dedicated_count,
            "inner_count": len(results) - home_count - dedicated_count,
            "platform_count": platform_count,
            "has_brand_sitelinks": has_sitelinks,
            "mature_dedicated_count": mature_dedicated,
            "avg_domain_age": round(avg_age, 1) if avg_age else None,
            "weak_domain_count": len(weak_domains),
            "weak_in_top5": len(weak_in_top5),
            "new_domain_count": len(new_domains),
        },
    }

def calculate_kd(serp_data, keyword, search_volume=None):
    organic = serp_data.get("organic", [])
    if not organic:
        return {"error": "No organic results", "keyword": keyword, "kd": None}

    # Phase 1: Classify all results
    results = [classify_result(r, keyword) for r in organic[:10]]

    # Phase 2: Fetch domain ages for unknown-authority domains (top 8)
    to_check = {r["domain"] for r in results[:8] if r["authority_score"] is None}
    domain_ages = {}
    for domain in to_check:
        year = get_domain_age(domain)
        if year:
            domain_ages[domain] = year
        time.sleep(0.08)

    # Phase 3: Estimate authority for all results
    for r in results:
        if r["authority_score"] is None:
            reg = domain_ages.get(r["domain"])
            r["registration_year"] = reg
            auth, src = estimate_domain_auth(r["domain"], reg)
            r["authority_score"] = auth
            r["auth_source"] = src

    # Phase 3.5: Brand keyword detection (triple fingerprint, 哥飞-model)
    brand = detect_brand_keyword(results, keyword, serp_data)
    is_brand_keyword = brand["is_brand"]
    brand_warning = None

    # Phase 4: Normal scoring — all 10 results (direct-attack perspective)
    scored = _score_signals(results, search_volume)
    base = scored["base"]
    modifiers = scored["modifiers"]
    modifier_total = scored["modifier_total"]
    final_score = scored["final_score"]
    sc = scored["serp_counts"]

    # Phase 4.5: Brand mode → derivative-entry difficulty (截流口径)
    # Drop the brand's own pages + platform fixed slots, rescore the
    # competit-able positions only. That's the number an outside site
    # can actually act on (alternative / vs / review pages).
    entry_scored = None
    if is_brand_keyword and brand["brand_root"]:
        competitive = [
            r for r in results
            if r["domain"].replace("www.", "").split(".")[0] != brand["brand_root"]
            and not r["is_platform"]
        ]
        if len(competitive) >= 3:
            entry_scored = _score_signals(competitive, search_volume)

    if is_brand_keyword:
        fps = ", ".join(brand["fingerprints"])
        brand_warning = (
            f'⚠ Brand keyword detected ({fps}). Google treats "{keyword}" as a brand query\n'
            f"  ({brand['brand_domain'] or 'official site'} owns the intent).\n"
            f"  Direct ranking is nearly impossible — the actionable number is the\n"
            f"  DERIVATIVE-ENTRY difficulty below (alternative/vs/review pages).\n"
            f"\n"
            f"⚠ 品牌词检测（指纹: {fps}）：Google 将「{keyword}」识别为品牌查询\n"
            f"  （{brand['brand_domain'] or '官方站点'} 占据意图位）。正面排名几乎不可能，\n"
            f"  行动参考下方「截流难度」——打衍生词才有意义：\n"
            f"  · `{keyword} alternative` / `{keyword} 替代`\n"
            f"  · `{keyword} vs [竞品]`\n"
            f"  · `{keyword} review` / `{keyword} 评价`\n"
            f"  · `best {keyword} alternatives`\n"
            f"  · `how to use {keyword}`\n"
            f"  · `{keyword} pricing` / `{keyword} 定价`"
        )

    # Label
    if final_score >= 70:
        label, label_en = "极难", "Very Hard"
        rec = "新站不建议正面进攻，考虑长尾变体或衍生内容"
    elif final_score >= 55:
        label, label_en = "困难", "Hard"
        rec = "需要高质量专门页 + 时间积累，长尾词优先"
    elif final_score >= 40:
        label, label_en = "中等", "Medium"
        rec = "有机会，做好内容质量和内链即可竞争"
    elif final_score >= 25:
        label, label_en = "较易", "Easy"
        rec = "好机会，一篇高质量文章即可冲击首页"
    else:
        label, label_en = "极易", "Very Easy"
        rec = "蓝海词，优先创建内容抢占先机"

    if entry_scored:
        e = entry_scored["final_score"]
        if e >= 70:
            entry_label, entry_label_en = "极难", "Very Hard"
        elif e >= 55:
            entry_label, entry_label_en = "困难", "Hard"
        elif e >= 40:
            entry_label, entry_label_en = "中等", "Medium"
        elif e >= 25:
            entry_label, entry_label_en = "较易", "Easy"
        else:
            entry_label, entry_label_en = "极易", "Very Easy"
    else:
        entry_label = entry_label_en = None

    # Link budget (KD → referring domains, 哥飞-model Ahrefs-curve interpolation)
    # Brand keywords budget on the entry score — that's the actionable path
    budget_basis = entry_scored["final_score"] if entry_scored else final_score
    link_budget = estimate_link_budget(budget_basis)

    return {
        "keyword": keyword,
        "kd": round(final_score, 1),
        "label": label, "label_en": label_en,
        "recommendation": rec,
        "is_brand_keyword": is_brand_keyword,
        "brand_fingerprints": brand["fingerprints"],
        "brand_domain": brand["brand_domain"],
        "kd_entry": round(entry_scored["final_score"], 1) if entry_scored else None,
        "kd_entry_label": entry_label,
        "kd_entry_label_en": entry_label_en,
        "brand_warning": brand_warning,
        "search_volume": search_volume,
        "base_score": round(base, 1),
        "modifiers": modifiers,
        "modifier_total": modifier_total,
        "link_budget": link_budget,
        "serp_analysis": {
            "homepage_count": sc["homepage_count"],
            "dedicated_count": sc["dedicated_count"],
            "inner_count": sc["inner_count"],
            "platform_count": sc["platform_count"],
            "has_brand_sitelinks": sc["has_brand_sitelinks"],
            "mature_dedicated_count": sc["mature_dedicated_count"],
            "avg_domain_age": sc["avg_domain_age"],
            "weak_domain_count": sc["weak_domain_count"],
            "weak_in_top5": sc["weak_in_top5"],
            "new_domain_count": sc["new_domain_count"],
        },
        "results": [
            {
                "position": r["position"],
                "domain": r["domain"],
                "page_type": r["page_type"],
                "authority": round(r["authority_score"], 2),
                "auth_source": r.get("auth_source", ""),
                "is_homepage": r["is_homepage"],
                "has_sitelinks": r["has_sitelinks"],
                "registration_year": r.get("registration_year"),
            }
            for r in results
        ],
    }

# ── Markdown report (self-contained, for AI ingestion / archives) ──────────

def format_markdown(result):
    """Self-contained Markdown report (哥飞-style format=markdown)."""
    if result.get("error"):
        return f"**Error:** {result['error']}"

    M = []
    M.append(f"# KD Analysis: {result['keyword']}")
    M.append("")

    if result.get("is_brand_keyword"):
        fps = ", ".join(result.get("brand_fingerprints", []))
        M.append(f"**Brand keyword** (fingerprints: {fps}) — official site "
                 f"`{result.get('brand_domain') or '?'}` owns the intent.")
        M.append("")
        if result.get("kd_entry") is not None:
            M.append(f"- **Derivative-entry difficulty (截流难度): {result['kd_entry']}/100**"
                     f" [{result.get('kd_entry_label','')} / {result.get('kd_entry_label_en','')}] — actionable number")
            M.append(f"- Direct-attack score: {result['kd']}/100 (reference only)")
        else:
            M.append(f"- ⛔ No competitive slots on this exact query — derivative keywords only")
            M.append(f"- Raw score {result['kd']}/100 (not meaningful for brand queries)")
        if result.get("search_volume"):
            M.append(f"- Search volume: ~{result['search_volume']:,}/month (Bing broad)")
        M.append("")
        M.append("**Target derivative keywords instead:**")
        M.append("")
        kw = result["keyword"]
        for d in [f"`{kw} alternative`", f"`{kw} vs [competitor]`", f"`{kw} review`",
                  f"`best {kw} alternatives`", f"`how to use {kw}`", f"`{kw} pricing`"]:
            M.append(f"- {d}")
    else:
        M.append(f"**Score: {result['kd']}/100** — {result['label_en']} ({result['label']})")
        if result.get("search_volume"):
            M.append(f"- Search volume: ~{result['search_volume']:,}/month (Bing broad)")
        M.append(f"- Base: {result['base_score']} / modifiers: {result['modifier_total']:+.0f}")
        M.append(f"- Recommendation: {result['recommendation']}")
    M.append("")

    lb = result.get("link_budget")
    if lb:
        M.append("## Link Budget (estimate)")
        M.append("")
        M.append(f"| Track | Low | Mid | High |")
        M.append(f"|---|---|---|---|")
        M.append(f"| Editorial (quality links) | {lb['editorial']['low']} | {lb['editorial']['mid']} | {lb['editorial']['high']} |")
        M.append(f"| Directory (easy links) | {lb['directory']['low']} | {lb['directory']['mid']} | {lb['directory']['high']} |")
        M.append("")
        M.append(f"_Referring domains to enter top-10, interpolated from Ahrefs KD→RD curve at KD={lb['kd_basis']}. Planning estimate, not a ranking guarantee._")
        M.append("")

    sa = result.get("serp_analysis", {})
    if sa:
        M.append("## SERP Structure")
        M.append("")
        M.append(f"- Homepages: {sa.get('homepage_count', '?')}/10 · Dedicated: {sa.get('dedicated_count', '?')}/10 · Inner: {sa.get('inner_count', '?')}/10")
        M.append(f"- Platforms: {sa.get('platform_count', '?')}/10 · Avg domain age: {sa.get('avg_domain_age') or '?'}yr")
        M.append(f"- Weak domains in top-5: {sa.get('weak_in_top5', '?')} · New domains (<2yr): {sa.get('new_domain_count', '?')}")
        M.append("")

    mods = result.get("modifiers") or {}
    if mods:
        M.append("## Signal Modifiers")
        M.append("")
        for name, val in mods.items():
            M.append(f"- {name}: {val:+d}")
        M.append("")

    if result.get("results"):
        M.append("## Top 10 Breakdown")
        M.append("")
        M.append("| # | Domain | Type | Authority | Year |")
        M.append("|---|---|---|---|---|")
        for r in result["results"]:
            M.append(f"| {r['position']} | {r['domain']} | {r['page_type']} | {r['authority']:.2f} | {r.get('registration_year') or '—'} |")
        M.append("")

    return "\n".join(M)


# ── CLI ────────────────────────────────────────────────────────────────────

def format_report(result):
    if result.get("error"):
        return f"Error: {result['error']}"

    L = []
    w = 62
    L.append(f"┌─ KD Analysis: {result['keyword']}")
    L.append(f"│")
    
    # Brand keyword warning (takes priority over score)
    if result.get("brand_warning"):
        for line in result["brand_warning"].split("\n"):
            L.append(f"│  {line}")
        L.append(f"│")
        if result.get("kd_entry") is not None:
            L.append(f"│  ★ Derivative-ENTRY difficulty (截流难度): {result['kd_entry']}/100"
                     f"  [{result.get('kd_entry_label','')} / {result.get('kd_entry_label_en','')}]")
            L.append(f"│    (vs direct-attack score {result['kd']}/100 — entry is the actionable one)")
        else:
            L.append(f"│  ⛔ No competitive slots on this exact query (SERP is fully")
            L.append(f"│     brand-owned + platform pages) — derivative keywords only.")
            L.append(f"│  (FYI raw score: {result['kd']}/100 — not meaningful for brand queries)")
        L.append(f"│")
    else:
        L.append(f"│  Score: {result['kd']}/100  [{result['label']} / {result['label_en']}]")
        if result.get("search_volume"):
            L.append(f"│  Volume: ~{result['search_volume']:,}/month (Bing broad)")
        L.append(f"│  Base: {result['base_score']}  +  Modifiers: {result['modifier_total']:+.0f}")
        L.append(f"│  → {result['recommendation']}")
    L.append(f"│")

    sa = result["serp_analysis"]
    L.append(f"│  SERP Structure:")
    L.append(f"│    Homepages: {sa['homepage_count']}/10  |  Dedicated: {sa['dedicated_count']}/10  |  Inner: {sa['inner_count']}/10")
    L.append(f"│    Platforms: {sa['platform_count']}/10  |  Brand sitelinks: {'Yes' if sa['has_brand_sitelinks'] else 'No'}")
    L.append(f"│    Mature niche sites: {sa['mature_dedicated_count']}/10  |  Avg domain age: {sa['avg_domain_age'] or '?'}yr")
    L.append(f"│    Weak domains (top5): {sa['weak_in_top5']}  |  Weak domains (total): {sa['weak_domain_count']}")
    L.append(f"│    New domains (<2yr): {sa['new_domain_count']}")

    if result["modifiers"]:
        L.append(f"│")
        L.append(f"│  Signal Modifiers:")
        for name, val in result["modifiers"].items():
            L.append(f"│    {name}: {val:+d}")

    L.append(f"│")
    lb = result.get("link_budget")
    if lb:
        L.append(f"│  Link Budget (est. referring domains to enter top-10):")
        L.append(f"│    Editorial (quality links): ~{lb['editorial']['mid']} "
                 f"({lb['editorial']['low']}–{lb['editorial']['high']})")
        L.append(f"│    Directory  (easy links):  ~{lb['directory']['mid']} "
                 f"({lb['directory']['low']}–{lb['directory']['high']})")
        L.append(f"│    basis: KD={lb['kd_basis']} → Ahrefs KD-RD curve (estimate)")
        L.append(f"│")
    L.append(f"│  Top 10 Breakdown:")
    for r in result["results"]:
        flags = []
        if r["is_homepage"]: flags.append("HOME")
        if r["has_sitelinks"]: flags.append("SITELINKS")
        if r["is_homepage"] and r["authority"] >= 0.6: flags.append("STRONG")
        flag_str = f" [{', '.join(flags)}]" if flags else ""
        age_str = f" ({r['registration_year']})" if r.get("registration_year") else ""
        L.append(
            f"│    {r['position']:>2}. {r['domain']:<32} "
            f"{r['page_type']:<10} "
            f"A≈{r['authority']:.2f}{age_str}{flag_str}"
        )
    L.append(f"└{'─' * w}")
    return "\n".join(L)


def main():
    import argparse
    parser = argparse.ArgumentParser(
        prog="zens_ink kd",
        description="Keyword Difficulty estimator (SERP structure based)",
    )
    parser.add_argument("keyword", help="Keyword to analyze")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--gl", default="us", help="Geo location (default: us)")
    parser.add_argument("--hl", default="en", help="Language (default: en)")
    parser.add_argument("--zh", action="store_true", help="Chinese mode (gl=cn, hl=zh-CN)")
    parser.add_argument("--no-volume", action="store_true", help="Skip search volume lookup")
    parser.add_argument("--markdown", action="store_true",
                        help="Self-contained Markdown report (for AI ingestion/archives)")

    args = parser.parse_args()

    if not SERPER_API_KEY:
        print("Error: SERPER_API_KEY not set", file=sys.stderr)
        print("Get a free key at https://serper.dev (2500 free searches)", file=sys.stderr)
        sys.exit(1)

    gl = "cn" if args.zh else args.gl
    hl = "zh-CN" if args.zh else args.hl
    market = "zh-CN" if args.zh else "en-US"

    serp = fetch_serp(args.keyword, gl=gl, hl=hl)
    volume = None if args.no_volume else fetch_search_volume(args.keyword, market=market)
    result = calculate_kd(serp, args.keyword, volume)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.markdown:
        print(format_markdown(result))
    else:
        print(format_report(result))

if __name__ == "__main__":
    main()
