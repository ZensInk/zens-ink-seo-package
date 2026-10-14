F2 fully fixed end-to-end. My verification is complete. Here is the report.

---

# Verification audit — zens-ink v1.4.11 fix round

**Method:** read every cited location in the current code; re-ran each round-1 reproduction locally under `/tmp` against the current tree, and diffed behaviour against a v1.4.10 baseline (`git archive HEAD`) to distinguish *fixed* from *newly broken*. HTTP was monkeypatched; no keyed or paid calls. `python3 -m unittest discover -s tests` → **18 tests, OK**. Repo left byte-identical (all scratch in `/tmp`).

### Findings

1. **FIXED** — `mcp.py:274` now sets `"json_flag": False`; `build_command("competitor_gap", …)` emits no `--json`.
2. **FIXED** — `isinstance(s, list)` guard present at all three autocomplete sites; `["q", null]` → `[]` in `keyword_research`, `geo_fanout`, `reddit_blueocean`, and end-to-end through `kgr_auto.score_keyword` (no longer raises `TypeError`).
3. **FIXED** — both `check_schema_types` and `check_commercial_schema` use `re.search(r'"@type"\s*:\s*"…"')`; a pretty-printed `"@type": "Product"` on `/pricing/index.html` no longer reports the schema missing.
4. **FIXED** — `keyword_volume.get_stats` returns `{"avg_weekly": 0, …, "error": "BING_API_KEY not set"}` instead of `sys.exit(1)`; the loud exit was relocated into the CLI `main()`, so the CLI still fails fast while library callers degrade.
5. **PARTIAL** — reverse-containment (`s in query_lower`) is gone, but the replacement `query_lower.startswith(s)` still over-validates: with `live={"crm"}`, the unrelated `"crm pricing"` and `"crm alternatives"` both score `live_demand=True`. A short suggestion still validates every query that begins with it.
6. **FIXED** — `current.append(val)` accumulates consecutive `User-agent:` lines; `GPTBot`/`ChatGPT-User` with a shared `Disallow: /` both report `blocked` (was `unlisted`), and a blank line still starts a new group.
7. **FIXED** — `removeprefix("www.")` yields `walmart.com`/`webflow.com` correctly, and the `target in d` substring arm is removed.
8. **FIXED** — `… rstrip("/")) or "/"` puts `/` into `link_sources`; the sitemap homepage entry is no longer an orphan.
9. **FIXED** — bare `get` removed from the transactional alternation; `"how to get more organic traffic"` → `informational` (was `transactional` @0.95), while `"get pricing"` still → `transactional`.
10. **FIXED (for the reported case) — but see NEW DEFECT #1** — `/blog/product-led-growth` and `/blog/features-of-a-good-crm` now correctly type `blog`; the transactional/product/tool rules are properly anchored.
11. **FIXED** — the `xml_urls[:10]` slice is gone; a stubbed 12-sub-sitemap index now returns all 24 pages (was 20), with a `[warn]` for very large indexes.
12. **FIXED** — word-boundary matching via `_has_commercial_intent`; `"my laptop stopped working"`, `"desktop setup tour"`, `"how do I stop procrastinating"` all `False`, `"top 10 crm tools"` still `True`.
13. **FIXED** — `format_text` now prints every detail for a path; 4 OG findings render as 4 `→` lines (was 1).
14. **FIXED** — the filter is anchored to whole segments (`^/(pricing|api|…)(/|$)`); `/blog/seo-guide` and `/en/blog/seo-guide` survive, `/pricing` alone is still dropped.
15. **FIXED** — `--compare` keys by `netloc + path`; two sitemaps on one domain no longer collapse and the cross-site section runs.
16. **FIXED** — JSON branch coerces numerics and skips non-dict rows; mixed `"50"`/`10` sorts without `TypeError`. (One field still uncoerced — see NEW DEFECT #2.)
17. **FIXED** — `has_favicon_file` is computed first and suppresses the `<link>` issue, so `dist/favicon.ico` with no `<link>` reports clean.
18. **FIXED** — consistent `(kind, img_src, rel, …)` keys; a 300KB image on two pages now reports `oversized_image` 2×, matching `missing_alt_text`/`missing_dimensions` 2× (was 1×/2×).
19. **FIXED** — `parse_sitemap` raises `FileNotFoundError`; `site_audit.run()` catches it and returns an actionable `ERROR:` string; `onpage_audit.run()` catches it and degrades to `set()`.
20. **FIXED** — cache defaults to `~/.zens_ink/dr-cache.json` when the package parent isn't writable, `mkdir(parents=True)` is attempted, and one `[warn]` is emitted on failure instead of a silent `pass`.
21. **FIXED** — `if _adc_dir:` guards the bare-filename case, so a fresh refresh token is no longer discarded after the OAuth flow.
22. **FIXED** — `err = (brave_data or {}).get("error", "no data")`; `estimate_demand("kw", None)` returns a clean dict instead of `AttributeError`.
23. **FIXED** — `act_remove` splits/strips like `act_add`; `remove "alpha, beta"` deletes both keywords and returns them.
24. **FIXED** — the 999 sentinel is masked before subtraction; `999→3` and `3→999` both yield `delta: None`, while a genuine `10→4` still yields `delta: 6`.
25. **FIXED** — CJK counted per character (132 words on the Chinese draft, was 3) and vague words matched on boundaries (`"Germany almost awesome something foremost."` → `vague_density 0.0`, was 103.4).
26. **FIXED** — `query()` now paginates with `startRow` (verified 120 rows fetched over 3 pages, and exact-multiple termination at 50 without an infinite loop), so the printed totals are the real totals rather than a top-`limit` subtotal.
27. **FIXED** — `initialize` returns a fixed supported version (`9999-99-99` → `2024-11-05`, supported `2025-03-26` echoed), and `tools/call` param errors raise `InvalidParams` → `-32602`.
28. **FIXED** — percentages divide by the actual distribution total; a 5-result all-`blog` SERP prints `100%` (was `50%`).
29. **PARTIAL** — `serp_intent._http_post_json` catches `HTTPError` and raises `RuntimeError` with `e.code` + body, but `kd._http_post_json` — explicitly named in the same finding — is untouched (`HTTPError` still escapes; `kd.py` has zero diff for it).
30. **FIXED** — parenthesised precedence; `mature_dedicated_count` is now `0` for a homepage/inner page at authority 0.75 and `1` only for `page_type == "dedicated"`.
31. **FIXED** — `format_report` iterates `INTENT_DIMENSIONS` and filters; exactly 7 headers for 7 dimensions, no duplicates (was 14 headers).
32. **FIXED** — `csv.reader` honours quoting; `"best crm, free"` / `"best crm, paid"` both survive, and plain-text and `#`-comment input still parse.
33. **FIXED** — the unreachable post-`return []` duplicate is deleted.
34. **FIXED** — `html.unescape(...).strip()` on every `<loc>` (`?cat=shoes&amp;size=42` → `&`, wrapped/whitespaced URLs cleaned), the initial fetch is wrapped (404 → `ERROR:` + `[]`), and sub-sitemap fetches warn instead of aborting.
35. **FIXED** — `content_qc` and `llms_gen` added to `__main__.TOOLS`; dispatcher set == module set (22/22), both now print real usage instead of "Unknown tool".
36. **FIXED** — `TOOLS_COUNT = 22`, matching the 22 shipped tool modules.
37. **FIXED** — `cluster()` now calls `weighted_jaccard`, and the docstring states the 60/40 blend actually in use.
38. **FIXED** — the age-curve comment was recalibrated to the formula; all nine cited points now match to ±0.005 and the 0.72 cap is reachable.
39. **FIXED** — `str.title()` replaced with first-character capitalisation; `"best CRM"` → `"The Ultimate Guide to Best CRM"` (was `Best Crm`) and `"Best CRM Software"` is preserved. (A lowercase input like `"ai video generator"` still sentence-cases to `"Ai video generator"` — inherent to first-letter capitalisation, not the reported bug.)
40. **DEFERRED** — the `audit #40` note is present at `brave_volume.py:88-90`, stating the log-scaled signal stays at the flat 15 fallback if live responses lack `count`. No new offline evidence; no live keyed call made. Behaviour deliberately unchanged.

## NEW DEFECTS

1. **[H] `zens_ink/serp_intent.py:53-56` — the F10 fix reintroduced the same unanchored-substring bug for content patterns, mistyping product/pricing/tool/shopping pages as `blog`**
```python
("blog", [r"^/blog/", r"^/article/", r"^/post/", r"/guide(/|$)", r"/how-to(/|$)", r"/tutorial(/|$)", r"^/news/", r"/insight(/|$)"]),
```
The section rules were correctly anchored, but the four content rules moved *ahead* of them are bare substrings matched with `re.search` against the whole path. Any transactional or product URL containing `/guide`, `/how-to`, `/tutorial` or `/insight` is now typed `blog`. Baseline-vs-current on a neutral domain, 10 of 17 probed paths changed classification, e.g. `/pricing/guide` `pricing`→`blog`, `/shop/guide` `shopping`→`blog`, `/tool/guide` `tool`→`blog`, `/product/guide` `product`→`blog`, `/products/how-to` `product`→`blog`, `/software/how-to` `product`→`blog`, `/templates/guide` `directory`→`blog`. The impact is exactly the failure mode F10 was filed about, inverted: `/pricing/guide` moves from `transactional:3` to `informational:3`, flipping the dominant intent and the content-format recommendation. Fix: anchor these too, e.g. `r"^/(guide|how-to|tutorial|insight)(/|$)"`, mirroring the rules that were fixed.

2. **[M] `zens_ink/content_matrix.py:37-48` — the JSON branch coerces only 3 of the 6 numeric fields, so a JSON scores file with a string volume still crashes**
```python
for key in ("opportunity_score", "competition_score", "volume_score"):
```
The CSV branch (lines 55-66) additionally coerces `avg_weekly_volume`, `quarterly_volume` and `autocomplete_count` to `int`. Those three are used in arithmetic (`r.get("avg_weekly_volume", 0) > 0` and `sum(...)` at lines 131-132), so `{"avg_weekly_volume": "1500"}` in JSON raises `TypeError: '>' not supported between instances of 'str' and 'int'` — verified end-to-end via `python3 -m zens_ink content_matrix --scores scores.json`. This gap predates the fix (baseline fails identically), but F16's stated goal was JSON/CSV parity and the touched code stopped one field short. Fix: apply the same six-key coercion to both branches.

*Also noted, not scored as new:* the F6 fix leaves a pre-existing limitation where a `User-agent:` line following a rules line (no blank separator) inherits the prior group's rules — `"User-agent: A\nDisallow: /x\nUser-agent: B\nAllow: /"` still gives `A` the `allow:`. Verified byte-identical in baseline, so it is neither introduced nor worsened by the fix, and the standard blank-line-separated form parses correctly.

## VERDICT: 38/40 resolved

(FIXED 36 — findings 1-4, 6-28, 30-39; PARTIAL 2 — 5, 29; DEFERRED 1 — 40. Recounting strictly: 37 FIXED/PARTIAL-or-better against the fixable set of 39, with #5 and #29 incomplete.) Precise tally: **37 of the 39 actionable findings are fully FIXED, 2 are PARTIAL (5, 29), and 40 is correctly DEFERRED** — 38/40 resolved counting the deferred item as properly handled.

**Releasable: NO.** Two round-1 findings are only partially fixed (F5 still over-validates demand from a short suggestion; F29's identical `kd._http_post_json` defect was left untouched), and the serp_intent fix introduced a high-severity regression that mistypes `/pricing/guide`, `/product/guide`, `/tool/guide` and similar as `blog`, corrupting dominant intent on real SERPs. Both are small, localized changes — but until the unanchored content patterns are anchored, shipping v1.4.11 would trade one intent-classification bug for a broader one.
