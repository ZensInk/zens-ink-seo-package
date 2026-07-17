---
name: zens-ink
description: >-
  Free SEO toolkit for indie builders. 8 zero-dependency Python tools covering
  the full SEO workflow: keyword discovery (Google Autocomplete), keyword difficulty
  (SERP structure analysis, no Ahrefs needed), search volume (Bing + Brave), competitor
  content gap analysis (sitemap comparison), technical site audit (broken links, orphan
  pages, missing canonicals/H1/meta), and real ranking data (Google Search Console).
  Pure Python stdlib — no pip install required beyond this package. Optional API keys
  unlock volume data but all core tools work without any keys.
version: "1.1.0"
authors:
  - name: Jask
    url: https://zens.ink
license: MIT
compatibility: >-
  Python 3.10+ (stdlib only, zero pip dependencies). Optional API keys:
  BING_API_KEY (keyword volume), BRAVE_API_KEY (alternative volume),
  SERPER_API_KEY (SERP data for KD scoring), Google ADC credentials (search performance).
  Tools without keys auto-skip gracefully.
runtime:
  language: python
  entry_point: zens-ink
allowed-tools: shell file_read file_write
triggers:
  - seo keyword research
  - find long tail keywords
  - keyword difficulty check
  - can i rank for this keyword
  - competitor content gap
  - seo site audit
  - check broken links
  - find orphan pages
  - google search console data
  - search ranking performance
  - website seo check
  - technical seo audit
---

# ZensInk — Free SEO Toolkit for Indie Builders

## Setup (one-time)

```bash
pip install git+https://github.com/respectevery01/zens-ink-seo-package.git
```

After install, `zens-ink` command is available globally. Verify:
```bash
zens-ink --help
```

All 8 tools can also be run as Python modules:
```bash
python3 -m zens_ink.keyword_research "tarot meaning"
```

## The 8 Tools

### 1. keyword_research — Discover Keywords (FREE, no API key)

Mines Google Autocomplete for long-tail keyword variations.

```bash
zens-ink keyword_research "tarot meaning"
zens-ink keyword_research "tarot meaning" --expand    # a-z deep discovery
zens-ink keyword_research "塔罗牌" --lang zh            # Chinese keywords
zens-ink keyword_research "tarot meaning" --json        # JSON output
```

### 2. kd — Keyword Difficulty (needs SERPER_API_KEY, free 2500/mo)

SERP structure analysis — no expensive Ahrefs DR data needed. Outputs GO / CAUTION / WAIT / AVOID.

```bash
zens-ink kd "tarot reading"
zens-ink kd "bazi calculator" --lang zh
```

### 3. keyword_volume — Search Volume (needs BING_API_KEY, free)

Real monthly search volume from Bing Webmaster API.

```bash
zens-ink keyword_volume "tarot meaning" --lang en
```

### 4. brave_volume — Alternative Volume (needs BRAVE_API_KEY, free 2000/mo)

Supplements Bing volume data. Especially useful when Bing returns 0 for Chinese keywords.

```bash
zens-ink brave_volume "tarot reading" --count 5
```

### 5. competitor_gap — Competitor Content Analysis (FREE, no API key)

Compares sitemaps to find topics competitors cover that you don't.

```bash
zens-ink competitor_gap \
  --url https://yoursite.com \
  --compare https://competitor1.com https://competitor2.com
```

### 6. site_audit — Technical SEO Audit (FREE, no API key)

Scans built HTML for 7 common issues: orphan pages, missing trailing slashes, broken internal links, missing canonical tags, missing meta descriptions, missing H1 tags, multiple H1 tags.

```bash
zens-ink site_audit --dist dist --sitemap dist/sitemap.xml
zens-ink site_audit --dist dist --sitemap dist/sitemap.xml --format json
```

Works with any static build output: Astro, Next.js export, Hugo, Gatsby, etc.

### 7. setup_gsc — Connect Google Search Console (FREE, one-time)

One-time OAuth setup for Google Search Console.

```bash
zens-ink setup_gsc
```

### 8. search_performance — Real Ranking Data (FREE, needs setup_gsc)

Pulls actual Google Search Console data: impressions, clicks, CTR, average position.

```bash
zens-ink search_performance
zens-ink search_performance --start 2025-01-01 --end 2025-06-30
zens-ink search_performance --query tarot
```

## Typical Workflow

```
keyword_research  →  what should I target?
       ↓
kd                →  can I win?
       ↓
keyword_volume    →  is it worth the effort?
       ↓
competitor_gap    →  what am I missing?
       ↓
site_audit        →  is my site technically healthy?
       ↓
search_performance →  how am I doing?
```

## API Key Setup (Optional)

Create a `.env` file in your project root:

```env
BING_API_KEY=xxx      # Free from bing.com/webmasters
BRAVE_API_KEY=xxx     # Free 2000/mo from brave.com/search/api
SERPER_API_KEY=xxx    # Free 2500/mo from serper.dev
```

Google Search Console: run `zens-ink setup_gsc` and follow the OAuth flow.

## Going Further

**ZensInk Pro** adds automated workflow engines: Winability Score (personalized KD), Content Radar (weekly editorial calendar), Competitor Radar (pricing/features/Reddit sentiment), GEO Visibility (does AI mention your brand?), GEO Score (will AI cite your page? 5-layer 16-dimension scoring with prioritized action plan), Search Intent classification, On-Page quality audit, and full 12-step automated audit with HTML report.

Learn more: https://zens.ink

## Tech Notes

- **Zero dependencies**: Pure Python stdlib. Only `zens-ink` package itself needs installing.
- **Cross-platform**: macOS, Linux, Windows.
- **Privacy-first**: All processing local. No telemetry, no tracking.
