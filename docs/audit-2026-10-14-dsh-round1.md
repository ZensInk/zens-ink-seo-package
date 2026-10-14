Repo is untouched — no tracked file modified, and the only untracked files predate this session.

# Independent audit — zens-ink OSS toolkit v1.4.10

Method: read all 25 modules in `zens_ink/` end to end, traced CLI → output-file data flow, and reproduced every finding locally under `/tmp` with synthetic data (network stubbed via monkeypatched `urlopen`; no paid-API calls). Findings surfaced by delegated deep reads were re-verified by me directly before inclusion — one delegation claim (`serp_intent` blog→product) initially *failed* to reproduce because my own test URL hit a domain override, and only reproduced on a neutral domain. Ground rules were honored: the repo is byte-identical to how I found it.

### 1. [H] zens_ink/mcp.py:263-275 — `competitor_gap` is registered without `json_flag: False`, so every MCP call passes an unsupported `--json` and fails
Evidence:
```python
        "name": "competitor_gap",
        "module": "zens_ink.competitor_gap",
...
        "timeout": 240,
    },
```
Why it fails: the registry omits `"json_flag": False` (which `site_audit`/`onpage_audit` both set), so `build_command` appends `--json`; `competitor_gap.main()` has no `--json` flag. Verified end-to-end: `tools/call` for `competitor_gap` returns `isError: true` with `competitor_gap.py: error: unrecognized arguments: --json` — the tool is 100% unusable over MCP.
Fix: add `"json_flag": False,` to the `competitor_gap` entry (it only prints text).

### 2. [H] zens_ink/keyword_research.py:32 (also geo_fanout.py:155, reddit_blueocean.py:185) — autocomplete returns `None` instead of `[]`, crashing every caller
Evidence:
```python
        data = json.loads(resp.read().decode())
        return data[1] if len(data) > 1 else []
    except Exception as e:
```
Why it fails: the guard checks the *length* of the envelope, not the type of element 1. For the valid response `["q", null]` the function returns `None`, and the parse succeeded so `except` never fires. Verified: `research('x')` → `TypeError: 'NoneType' object is not iterable`; `kgr_auto.score_keyword` and `geo_fanout.generate_fanout` crash identically.
Fix: `s = data[1] if len(data) > 1 else []` then `return s if isinstance(s, list) else []`.

### 3. [H] zens_ink/site_audit.py:874,919 — JSON-LD `@type` detection uses a literal `\s*` so pretty-printed schema is never found
Evidence:
```python
                if f'"@type":\\s*"{t}"' in block or f'"@type":"{t}"' in block:
```
Why it fails: in a plain (non-raw) f-string `\\s` is a literal backslash + `s`, not a regex class, so only the minified `"@type":"Product"` form matches. Verified: a `pricing/index.html` containing valid pretty-printed `"@type": "Product"` is reported as `missing_product_schema` / "invisible to Google Shopping". `check_schema_types` (line 874) has the identical defect.
Fix: `if re.search(r'"@type"\s*:\s*"%s"' % re.escape(t), block):`.

### 4. [H] zens_ink/kgr_auto.py:63 — the missing-Bing-key path calls `sys.exit(1)`, aborting the entire run after promising graceful degradation
Evidence:
```python
    vol_data = get_volume(keyword, country, bing_lang)
```
Why it fails: `keyword_volume.get_stats` (line 38-40) does `if not BING_API_KEY: print(...); sys.exit(1)`. Verified: `kgr_auto.main()` with no key prints "volume will be 0 for all keywords" and then dies on the first keyword with exit 1, emitting no results — contradicting its own message and the SKILL.md claim "Tools without keys auto-skip gracefully".
Fix: return `{"keyword": keyword, "avg_weekly": 0, ...}` from `get_stats` when the key is unset.

### 5. [H] zens_ink/geo_fanout.py:221-224 — inverted substring test marks every generated sub-query as demand-validated
Evidence:
```python
            has_live_demand = query_lower in live_suggestions or any(
                query_lower in s or s in query_lower
                for s in live_suggestions
            )
```
Why it fails: the `s in query_lower` arm lets a short suggestion validate any query containing it. Verified with a single suggestion `"crm"`: all 54 sub-queries get `live_demand: True` and 22 become "gold mines", while the report prints "Live search demand validated: 1 queries".
Fix: drop the reverse-containment arm and match suggestions exactly.

### 6. [H] zens_ink/ai_crawler_audit.py:78-81 — consecutive `User-agent:` lines overwrite instead of accumulating, so blocked crawlers report "unlisted"
Evidence:
```python
        if key == "user-agent":
            current = [val] if val else []
            for ua in current:
                groups.setdefault(ua, [])
```
Why it fails: each `User-agent:` line resets `current`, but robots.txt groups share one rule block across consecutive UA lines. Verified with the standard group `User-agent: GPTBot` / `User-agent: ChatGPT-User` / `Disallow: /`: `GPTBot` parses to `[]` and `crawl_status` returns **"unlisted"** — the report says GPTBot is absent and allowed when it is fully disallowed, and the AI-readiness score is computed from that wrong status.
Fix: `current.append(val)`, resetting only on a blank line or a new group.

### 7. [H] zens_ink/rank_tracker.py:90,93 — `lstrip("www.")` mangles leading `w` and the substring test matches foreign domains
Evidence:
```python
    target = domain.lower().lstrip("www.") if domain else ""
        if target and (d == target or d.endswith("." + target) or target in d):
```
Why it fails: `lstrip` strips a character *set*, so `walmart.com` → `almart.com` and `webflow.com` → `ebflow.com`, and no SERP domain ever matches → the keyword is permanently recorded as not-ranking. The `target in d` arm matches `pineapple.com` for `apple.com` and `notexample.com` for `example.com`, storing a stranger's position as yours.
Fix: `target = domain.lower().removeprefix("www.")` and match only exact / `endswith("." + target)`.

### 8. [H] zens_ink/site_audit.py:1343,147 — `build_link_map` drops the root path, so the homepage is always reported as an orphan
Evidence:
```python
            clean = href.split("#")[0].split("?")[0].rstrip("/")
            if clean:
                all_links.add(clean)
```
Why it fails: for `<a href="/">` the cleaned value is `""`, discarded, so `/` can never appear in `link_sources`; `check_orphan_pages` then misses the sitemap's `/` entry and emits `orphan_page`. Verified on a site whose homepage explicitly links to itself: `/` is still flagged "In sitemap but no internal links found" — a false positive on every site.
Fix: `clean = (href.split("#")[0].split("?")[0].rstrip("/")) or "/"`.

### 9. [H] zens_ink/search_intent.py:38 — the bare token `get` in the transactional alternation pre-empts informational "how to" queries
Evidence:
```python
        r"\b(buy|purchase|order|shop|deals?|discount|coupon|sale|sign\s?up|subscribe|download|free\s?trial|hire|get|pricing|plans?|checkout)\b",
```
Why it fails: rules are priority-ordered and first-match-wins. Verified: `"how to get more organic traffic"` → `transactional`, confidence 0.95, content type "Product / pricing / landing page"; `serp_intent --cross` consumes this via `search_intent.classify(...)`, so the cross-validation verdict is corrupted too.
Fix: drop `get` from the alternation, or require a transactional object.

### 10. [H] zens_ink/serp_intent.py:53 (evaluated at 170-173) — unanchored path rules type blog posts as `product`
Evidence:
```python
    ("product",      [r"/product", r"/features", r"/app/", r"/software/", r"/platform/", r"/solution"]),
```
```python
    for ptype, patterns in _PATH_RULES:
        for pat in patterns:
            if re.search(pat, path):
                return ptype
```
Why it fails: `re.search` matches anywhere in the path, and `product` (index 1) is tested before `blog` (index 3). Verified on a neutral domain: `/blog/product-led-growth` and `/blog/features-of-a-good-crm` both return **`product`** (weighted transactional) instead of `blog`, while the control `/blog/how-to-choose-a-crm` correctly returns `blog` — isolating the cause to the substring match. The dominant intent and the content-format recommendation are driven by this error.
Fix: anchor to a segment, e.g. `r"^/(product|features|solution|software|platform)(/|$)"`, and test content rules before transactional ones.

### 11. [H] zens_ink/competitor_gap.py:72 — sub-sitemaps are silently capped at 10
Evidence:
```python
        for sub in xml_urls[:10]:
            page_urls.extend(fetch_sitemap(sub, timeout, depth + 1))
```
Why it fails: the slice drops entries with no warning. Verified with a stubbed index declaring 12 sub-sitemaps of 2 pages each: exactly **10 sub-sitemaps fetched, 20 of 24 pages returned**. `--compare` then prints "Unique to site X" from a partial inventory — a confidently wrong competitive conclusion, which is the one thing this tool exists to get right.
Fix: remove the cap (a `depth` guard already exists) or emit `[warn] only first 10 of N sub-sitemaps analyzed`.

### 12. [H] zens_ink/reddit_blueocean.py:214 — substring matching of short words like `top` flags unrelated posts as commercial blue oceans
Evidence:
```python
    has_commercial = any(w in title_lower for w in _COMMERCIAL_INTENT_WORDS)
```
Why it fails: `_COMMERCIAL_INTENT_WORDS` contains `"top"`, `"vs"`, `"sale"`, `"how to"`, matched as raw substrings. Verified: `"My laptop stopped working"`, `"Desktop setup tour"` and `"How do I stop procrastinating"` all score `is_blue_ocean=True` because `top` matches inside *laptop*/*desktop*/*stop*; the `commercial_bonus=2` is exactly what crosses the `>= 2` threshold.
Fix: `any(re.search(rf"\b{re.escape(w)}\b", title_lower) for w in _COMMERCIAL_INTENT_WORDS)`.

### 13. [M] zens_ink/site_audit.py:1435-1453 — text output collapses all same-type issues into one line, hiding the rest
Evidence:
```python
        unique_paths = sorted({i["path"] for i in group})
...
                detail = next(
                    (i["detail"] for i in group if i["path"] == path), ""
                )
```
Why it fails: issues are keyed only by `path`, so multiple findings on one page render as one line with the *first* detail. Verified: a page missing `og:title`, `og:description`, `og:image`, `og:url` prints `MISSING OPEN GRAPH TAGS: 1 unique (4 total)` showing only `→ Missing og:title` — three findings invisible in the default format while still inflating the summary counts.
Fix: group by `(path, type)`, or iterate every matching issue when printing details.

### 14. [M] zens_ink/competitor_gap.py:97-98 — the topic extractor filters out `/blog/`, `/pricing/` etc., emptying the report for content sites
Evidence:
```python
        if re.match(r"^/(pricing|blog|api|admin|login|signup|account)", path):
            continue
```
Why it fails: the filter runs *after* the language prefix is stripped, so `/en/blog/seo-guide` and `/blog/seo-guide` are both discarded. Verified on a rival sitemap of 5 URLs: only `features/best-tarot-app` and `theme/modern` survive — every `/blog/...` and `/pricing` page is dropped, i.e. exactly the content the competitor competes with.
Fix: skip only when the segment is the whole path.

### 15. [M] zens_ink/competitor_gap.py:152 — `--compare` keyed by netloc, so two sitemaps on one domain overwrite each other
Evidence:
```python
    for url in urls_to_check:
        _, topics = analyze(url, args.lang)
        all_topics[urlparse(url).netloc] = set(topics.keys())
```
Why it fails: `urlparse` drops the path, so two sitemap parts on one domain collapse to one key; `if len(all_topics) > 1:` (line 154) is then False and the entire cross-site section is skipped silently — the user asked for a comparison and gets two standalone dumps.
Fix: key by full URL (or netloc+path) and union topics for a shared netloc.

### 16. [M] zens_ink/content_matrix.py:30-34 — the JSON branch skips the numeric coercion the CSV branch performs, causing a `TypeError`
Evidence:
```python
    if path.suffix == ".json":
        data = json.loads(text)
        if isinstance(data, dict) and "results" in data:
            data = data["results"]
        return data
```
Why it fails: the CSV path casts `opportunity_score` and friends to numbers, the JSON path does not. Verified with `[{"opportunity_score":"50"},{"opportunity_score":10}]` → `TypeError: '<' not supported between instances of 'str' and 'int'` at the sort on line 72; feeding the tool its own `--json` output back in yields an `AttributeError`.
Fix: coerce after load regardless of format and skip non-dict rows.

### 17. [M] zens_ink/site_audit.py:775-777 — a favicon file on disk never clears the "missing favicon" issue, because the loop only adds problems
Evidence:
```python
    for name in ["favicon.ico", "favicon.svg", "favicon.png"]:
        if (dist_dir / name).exists() or (dist_dir / "public" / name).exists():
            return issues
```
Why it fails: the loop returns as soon as a favicon file exists, but the earlier `<link rel="icon">` check already appended `missing_favicon`, so it returns *with* the false issue. Verified: `dist/favicon.ico` present, no `<link>` tag → still reports "No favicon link found in <head>".
Fix: move the file-existence check before the link check, or make it suppress the issue.

### 18. [M] zens_ink/site_audit.py:416-422 — inconsistent dedup keys re-report the same image and swallow the size warning
Evidence:
```python
                    key = (img_src, size_kb)
                    if key not in seen_imgs:
...
                key = ("no_alt", img_src, rel)
```
Why it fails: the oversized-image key omits `rel` while the alt/dimension keys include it. Verified with `img/big.png` (300KB) referenced from two pages: `oversized_image` reports once (attributed to only one page) while `missing_alt_text`/`missing_dimensions` report twice.
Fix: use one consistent key shape, e.g. `(kind, img_src, rel)`.

### 19. [M] zens_ink/site_audit.py:88 — `parse_sitemap` calls `sys.exit(1)` inside a library function, killing the MCP server and `onpage_audit`
Evidence:
```python
            print(f"ERROR: Sitemap not found: {sitemap_path}", file=sys.stderr)
            sys.exit(1)
```
Why it fails: `site_audit.run()` and `onpage_audit.run()` call this during normal operation. Verified: `run(...)` raises `SystemExit(1)` instead of returning an error, so a missing sitemap terminates the whole process — including the `mcp.py` subprocess.
Fix: raise `FileNotFoundError` (or return `set()`) and convert it at the call site.

### 20. [M] zens_ink/domain_rating.py:33,66-72 — the DR cache lives in the package root and every write failure is swallowed, so it is inert on a pip install
Evidence:
```python
CACHE_PATH = Path(__file__).resolve().parent.parent / "dr-cache.json"
...
def _save_cache(cache):
    try:
        CACHE_PATH.write_text(
```
Why it fails: for a normal `pip install`, `parent.parent` is `site-packages`, which is not writable, so `write_text` raises and `except Exception: pass` discards it. The cache never populates and every run re-queries the API — dead code precisely in the deployment it ships for.
Fix: default to `Path.home() / ".zens_ink" / "dr-cache.json"` and warn once on failure.

### 21. [M] zens_ink/setup_gsc.py:108 — `os.makedirs(os.path.dirname(ADC_PATH))` fails for a bare filename, discarding a freshly issued refresh token
Evidence:
```python
    os.makedirs(os.path.dirname(ADC_PATH), exist_ok=True)
    with open(ADC_PATH, "w") as f:
        json.dump(creds, f, indent=2)
```
Why it fails: with `ADC_PATH=creds.json`, `os.path.dirname` returns `""` and `os.makedirs("")` raises `FileNotFoundError` (verified in isolation). The crash lands *after* the browser OAuth flow, throwing away the refresh token the user just authorized.
Fix: `d = os.path.dirname(ADC_PATH); if d: os.makedirs(d, exist_ok=True)`.

### 22. [M] zens_ink/brave_volume.py:78-79 — the `None` guard immediately dereferences the `None` it just detected
Evidence:
```python
    if not brave_data or brave_data.get("error"):
        return {"keyword": keyword, "demand_score": 0, "source": "brave", "error": brave_data.get("error", "no data")}
```
Why it fails: when `brave_data is None` the condition is true, and the return expression then calls `.get` on it. Verified traceback at line 79. Reachable because `search_brave` returns `None` when the key is unset (lines 35-36); the CLI is shielded by its own `sys.exit(1)`, but the exported `estimate_demand`/`batch_volume` are not.
Fix: `err = (brave_data or {}).get("error", "no data")`.

### 23. [M] zens_ink/rank_tracker.py:117 — `remove` does not split its comma-separated argument the way `add` does
Evidence:
```python
    cur = c.execute("DELETE FROM keywords WHERE keyword=?", (args.keywords,))
    c.execute("DELETE FROM snapshots WHERE keyword=?", (args.keywords,))
```
Why it fails: `act_add` (line 101) splits and strips; `act_remove` binds the raw string. Verified: after `add "alpha,beta"` (2 keywords stored), `remove "alpha,beta"` returns `{"removed": None}` and both keywords and snapshots remain.
Fix: reuse the same comma split in `act_remove`.

### 24. [M] zens_ink/rank_tracker.py:185 — the trend delta is computed against the 999 sentinel, fabricating huge rank changes
Evidence:
```python
        cur = snaps[0]["position"]
        prev = snaps[1]["position"] if len(snaps) > 1 else None
        delta = (prev - cur) if prev is not None else None
```
Why it fails: `_NOT_FOUND = 999` is masked for *display* at lines 187-188, but the arithmetic runs on raw values first. Verified against a real DB: snapshots `999` then `3` return `{'position': 3, 'previous': None, 'delta': 996}`, rendering as `kw  3  —  +996` — the same row says "no previous data" and "improved by 996 places". The reverse order fabricates a 997-place drop.
Fix: mask the sentinel before subtracting so a never-ranked snapshot yields `delta = None`.

### 25. [M] zens_ink/content_qc.py:112,118 — ASCII-only word counting plus unanchored substring matching make the publishing gate meaningless
Evidence:
```python
    words = re.findall(r"[A-Za-z][A-Za-z'-]*", text)
    word_count = len(words)
...
    vague_hits = sum(1 for w in VAGUE_WORDS if w in lower_text)
```
Why it fails: every CJK character is skipped, so the derived densities divide by a near-zero `word_count`. Verified on a normal Chinese Markdown draft: `Words: 3 | Facts/1k: 1000.0`, with the "Fact density >= 4/1k words" gate **passing** on that ratio. Separately, the sentence "Germany almost awesome something foremost." scores `Vague/1k: 103.4` (from *Germany*, *something*, *almost*/*foremost*) and fails the vagueness gate. The repo ships `README.zh.md`/`CHANGELOG.zh.md`, so the CJK path is real.
Fix: count CJK per character and match vague words on `\b` boundaries.

### 26. [M] zens_ink/search_performance.py:98-105 — page-limited row sums are printed as site totals with no truncation marker
Evidence:
```python
    total_imp = sum(r.get("impressions", 0) for r in rows)
...
    print(f"  {len(rows)} rows | {total_imp} impressions | {total_clk} clicks")
```
Why it fails: `query()` sends only `rowLimit` and never `startRow`, so `rows` is at most `--limit` (default 50). On a larger property the printed impressions/clicks are the top-50 subtotal presented as the period total.
Fix: paginate with `startRow`, or label the line as "top {limit} rows".

### 27. [M] zens_ink/mcp.py:466-478 — no protocol version negotiation, and invalid params return -32603 instead of -32602
Evidence:
```python
    if method == "initialize":
        return {
            "protocolVersion": params.get("protocolVersion", "2024-11-05"),
```
Why it fails: the server echoes whatever version the client claims — verified returning `{"protocolVersion": "9999-99-99"}` — so an unsupported revision is reported as supported. Separately, `tools/call` with no name returns `-32603` (`unknown tool 'None'`) where the spec requires `-32602`.
Fix: return a fixed supported version, and map param errors to `-32602`.

### 28. [M] zens_ink/serp_intent.py:532 — percentages are divided by a hardcoded 10
Evidence:
```python
        pct = round(count / 10 * 100)
```
Why it fails: `analyze` slices `organic[:10]` but Google often returns fewer results and nothing pads to 10. Verified: a SERP with 5 organic results all typed `blog` prints `blog 5 (50%)`; the correct figure is 100%.
Fix: divide by `sum(result["page_type_distribution"].values()) or 1`.

### 29. [M] zens_ink/serp_intent.py:408 — no HTTP error handling, so an invalid key surfaces as a raw traceback
Evidence:
```python
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))
```
Why it fails: `fetch_serp` is called unguarded from `main` (line 634). Verified with `urlopen` raising `HTTPError 403`: the exception propagates out of `main` as a traceback, discarding Serper's JSON error body. `brave_volume.search_brave` handles the identical situation correctly (lines 56-60), so this is an inconsistency rather than a design choice. The same defect exists in `kd._http_post_json`, where `kd "keyword"` with a bad key terminates in `urllib.error.HTTPError: HTTP Error 403`.
Fix: catch `urllib.error.HTTPError` and surface `e.code` plus the body.

### 30. [L] zens_ink/kd.py:422-427 — operator precedence makes `authority_score >= 0.70` bypass the `page_type == "dedicated"` filter
Evidence:
```python
    mature_dedicated = sum(
        1 for r in results
        if r["page_type"] == "dedicated"
        and (r.get("registration_year") and datetime.now(timezone.utc).year - r["registration_year"] > 8
             or r["authority_score"] >= 0.70)
    )
```
Why it fails: `and` binds tighter than `or`, so a homepage or inner page with authority ≥ 0.70 counts as "mature dedicated". Verified: `page_type="homepage"`, `authority=0.75`, `registration_year=None` evaluates `True`, inflating the `mature_niche` modifier and the KD.
Fix: `and (r["authority_score"] >= 0.70 or (r.get("registration_year") and ...))`.

### 31. [L] zens_ink/geo_fanout.py:336-338 — the dimension section prints each header several times because it iterates a gold-score-sorted list
Evidence:
```python
    current_dim = ""
    for sq in data["sub_queries"]:
        if sq["dimension"] != current_dim:
            current_dim = sq["dimension"]
```
Why it fails: `generate_fanout` sorts `results` by `gold_score` (line 255), so rows of the same dimension are interleaved and the "changed dimension" test fires repeatedly. Verified: `format_report` emits **14 headers for 7 dimensions** — "Use Case / Scenario" and "Objections / Concerns" 3× each.
Fix: iterate `INTENT_DIMENSIONS` in order and filter `sub_queries` per dimension.

### 32. [L] zens_ink/keyword_cluster.py:251 — CSV reading splits on the first comma, ignoring quoting
Evidence:
```python
                    keywords.append(line.split(",")[0].strip().strip('"'))
```
Why it fails: the module advertises CSV input, but a quoted keyword containing a comma is truncated, and the dedup at line 266 then silently drops the collapsed duplicates. Verified: two rows `"best crm, free"` / `"best crm, paid"` yield `['best crm']` — clustering runs on 1 keyword instead of 2.
Fix: parse with `csv.reader`.

### 33. [L] zens_ink/competitor_gap.py:79-86 — unreachable dead code after the `return []` at line 77
Evidence:
```python
    print(f"  [warn] no sitemap found for {url}", file=sys.stderr)
    return []

    urls = re.findall(r"<loc>([^<]+)</loc>", data)
```
Why it fails: a stale duplicate of the live logic at lines 67-74 sitting after an unconditional return; it can never execute and will mislead the next editor into patching the wrong copy.
Fix: delete lines 79-86.

### 34. [L] zens_ink/llms_gen.py:103-108 (also 110-114) — sitemap `<loc>` values are used raw, with no entity decoding or stripping, and the initial fetch is unguarded
Evidence:
```python
            return r.read().decode("utf-8", errors="replace")

    xml = fetch(sitemap_url)
```
Why it fails: `re.findall(r"<loc>([^<]+)</loc>", ...)` never applies `html.unescape` or `.strip()`. Verified: `<loc>https://shop.example.com/c?cat=shoes&amp;size=42</loc>` is emitted verbatim with `&amp;` into the generated AI-discovery file, and a pretty-printed `<loc>` that wraps across lines yields a URL with embedded newlines. Separately, `fetch(sitemap_url)` at line 108 has no try/except (unlike the per-page fetch at 123-127), so a typo'd or 404 sitemap raises a raw traceback instead of "No pages found."
Fix: `u = html.unescape(m.group(1)).strip()` for every match, and wrap the initial `fetch`.

### 35. [L] zens_ink/__main__.py:8-30 — `content_qc` and `llms_gen` are documented CLI tools but missing from the dispatcher
Evidence:
```python
TOOLS = {
    # Discovery
    "keyword_research":   "Discover keywords via Google Autocomplete",
```
Why it fails: the package ships 22 tool modules, all with `main()`, but `TOOLS` lists 20 and omits those two. Verified: `python3 -m zens_ink content_qc draft.md` prints "Unknown tool: content_qc" and exits 1, although `SKILL.md:229` documents `zens-ink content_qc draft.md` and `SKILL.md:249` documents `zens-ink llms_gen ...`. (`tests/test_smoke.py`'s 22-name list is correct — the drift is only in the dispatcher.)
Fix: add both entries and assert registry == module set in a test.

### 36. [L] zens_ink/__init__.py:4 — `TOOLS_COUNT = 20` disagrees with the 22 tool modules shipped
Evidence:
```python
TOOLS_COUNT = 20
```
Why it fails: `zens_ink/` contains 22 importable tool modules (excluding `__init__`, `__main__`, `config`), and `tests/test_smoke.py` enumerates 22. `SKILL.md` is further behind, advertising `version: "1.2.1"` and "13 zero-dependency Python tools" against package version 1.4.10.
Fix: set `TOOLS_COUNT = 22` and refresh the SKILL.md version/tool-count lines.

### 37. [L] zens_ink/keyword_cluster.py:99 — `weighted_jaccard` is dead code and its documented 50/50 blend contradicts the 60/40 in use
Evidence:
```python
    Blended similarity: 50% plain Jaccard + 50% IDF-weighted Jaccard.
...
    return 0.6 * plain + 0.4 * weighted
```
Why it fails: neither `weighted_jaccard` nor `jaccard` is called anywhere; `cluster()` (lines 177-190) reimplements the blend inline with different weights, so the tuning the docstring describes is not the tuning in effect.
Fix: call `weighted_jaccard` from `cluster()` and correct the docstring, or delete the helpers.

### 38. [L] zens_ink/kd.py:268-276 — the domain-age authority curve does not match the table in its own comment
Evidence:
```python
        # 1yr→0.28, 2yr→0.34, 3yr→0.38, 5yr→0.45, 8yr→0.52, 10yr→0.56,
        # 15yr→0.63, 20yr→0.68, 25yr→0.72
            score = min(0.72, 0.22 + 0.15 * math.log(age) / math.log(3))
```
Why it fails: evaluating the formula gives 1yr→0.315 (not 0.28), 10yr→0.547 (not 0.56) and 25yr→0.665 (not 0.72); the `min(0.72, …)` cap is never reached, so the top of the stated range is unreachable. Every unknown domain's authority proxy — and thus each KD score — is offset from the documented model.
Fix: recalibrate the constants, or replace the comment with the values the formula produces.

### 39. [L] zens_ink/geo_fanout.py:263 — `keyword.title()` mangles acronyms and casing in the generated pillar title
Evidence:
```python
        "recommended_pillar_article": f"The Ultimate Guide to {keyword.title()}" if lang == "en" else f"{keyword} 完全指南",
```
Why it fails: `str.title()` upper-cases the first letter of every word, so `"ai video generator"` becomes `"The Ultimate Guide to Ai Video Generator"` and `"best CRM"` becomes `"Best Crm"` — a headline recommendation a user would copy verbatim.
Fix: use a casing-preserving transform, e.g. capitalize only the first character.

### 40. UNVERIFIED — zens_ink/brave_volume.py:88 `web.get("count", 0)` may always be 0, disabling the primary demand signal
Evidence:
```python
    total_count = web.get("count", 0) or 0
    if total_count > 0:
        count_score = min(60, math.log10(max(1, total_count)) * 8)
    else:
        count_score = 15  # fallback if no count
```
Why it fails: Brave's `web` object carries `results`, and the module itself hedges with "Brave sometimes returns this". If the field is absent, `count_score` is permanently the flat 15 fallback and the log-scaled result-count signal named in the module docstring never fires. I verified only with synthetic payloads, where `result_count` is always 0. The live schema could not be checked offline, and the ground rules forbid paid calls.
Fix: use `len(results)` (already exposed as `total_results_seen`) or Brave's real total field; confirming needs one keyed API response.

TOTAL: 40 findings (H:12 M:15 L:13)

Overall code health: the toolkit is cleanly laid out and genuinely stdlib-only, with safe subprocess use (argument lists, never `shell=True`) and fully parameterized SQL — but it is not release-ready. Twelve high-severity defects sit on the default paths of the headline tools, and the defining pattern is that they **fail silently rather than loudly**: the autocomplete `None` propagates as a crash three callers deep, the literal `\s*` makes valid JSON-LD invisible, the homepage is always an orphan, a `Disallow: /` block reads as "unlisted", a competitor's rank is stored as yours, and `mcp__zensink__competitor_gap` simply never works. For a tool whose output drives publishing and outreach decisions, confidently-wrong is far worse than broken. Three root causes recur across modules — autocomplete envelope parsing (×4), substring matching where word/segment matching is needed (×5), and sentinel/masking handling (×2) — which points at a missing shared-helper layer rather than isolated slips; fixing those three patterns would clear roughly a third of this list.
