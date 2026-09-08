## v1.4.8 — 2026-09-08

**New tool: ai_crawler_audit — who can actually read your content.**
site_audit checks pages; this checks the gatekeepers. It audits robots.txt
against 17 AI crawlers (training vs AI search, per vendor), reads Content
Signals, verifies the llms.txt / llms-full.txt layer, and scores AI
readiness out of 100 with plain-language notes. Site-wide blocks are
distinguished from subpath-only blocks — `Disallow: /admin` is not
`Disallow: /`. Zero deps, no API key. Pairs with llms_gen (audit what you
have, generate what's missing).

- **New tool: ai_crawler_audit** — robots.txt AI-crawler policy + llms.txt
  discovery-layer audit with AI-readiness score. Markdown + JSON output.
- Verified on live sites across the full policy spectrum: full allow,
  subpath-only disallow, site-wide blocks, and content-signal strategies.
- Version bump 1.4.7 → 1.4.8. TOOLS_COUNT 19 → 20.

# Changelog

## v1.4.7 — 2026-08-29

**Two new tools: content_qc + llms_gen — the publish-side GEO loop closes.**
Scoring live pages (site_audit, geo scoring) tells you what went wrong after
the fact. These two tools move the check to before you ship, and generate the
AI discovery layer automatically.

- **New tool: content_qc** — pre-publish gate for AI-citable content. Grades
  drafts on 14 weighted checks: BLUF up front, fact density per 1k words,
  vague-word ceiling, outbound sources, FAQ block, question-format headings,
  title/description length, alt coverage, date signal. Markdown + HTML,
  directory mode, `--min-score` gate with CI exit code. Cross-validated
  against site_audit findings on a live site.
- **New tool: llms_gen** — generates `llms.txt` (curated) + `llms-full.txt`
  (full catalog, grouped by section) from a static build directory or a
  remote sitemap. Auto-skips admin/api/noindex routes. Zero deps.
- Version bump 1.4.6 → 1.4.7.

## v1.4.6 — 2026-08-23

**PyPI release infrastructure.** zens-ink is now installable via pip, and
future releases publish themselves from a git tag.

- Published to PyPI: `pip install zens-ink` (replaces the git+https install command)
- GitHub Actions auto-publish: push a `v*` tag and CI builds + uploads to PyPI (PYPI_API_TOKEN as repo secret)
- TOOLS_COUNT fix: 16 -> 19 (module registry count had drifted behind the actual tool set)

## v1.4.5 — 2026-08-23

**New tool: domain_rating — real Ahrefs DR, free.** Off-page authority used to be the known gap: kd.py works around it with curated authority-domain proxies. Ahrefs now exposes a free public Domain Rating endpoint, so the gap closes at zero cost:

- `domain_rating` queries `v3/public/domain-rating-free` for any domain or URL (0-100 log scale)
- Accepts domains as args, from a file, or piped via stdin — built for batch SERP-competitor checks
- Local cache (`dr-cache.json`, gitignored) so repeated runs never burn rate limit; `--no-cache` to bypass
- CSV / JSON export, URL auto-normalization (`https://www.example.com/x` -> `example.com`)
- Also registered in the MCP server tool list
- Attribution "Domain Rating by Ahrefs" included in every output per the DR License
- Requires a free AHREFS_API_KEY (generate at app.ahrefs.com/account/api-keys)

## v1.4.4 — 2026-08-23

**Agent-readiness checks in site_audit.** The web is increasingly read by autonomous agents, not just humans and crawlers. `site_audit` now flags the two llms.txt gaps that decide whether agents understand your product:

- **New check: agent when-to-use** — llms.txt without a `When to use` section reads as marketing, not guidance; agents can't tell which jobs your site fits. Flagged as a warning with a fix hint.
- **New check: agent how-to-call** — llms.txt without an install command / endpoint / MCP entry point gives agents no way to act on the discovery. Flagged as info.
- Both checks are deterministic, zero-dependency, and run inside the existing `site_audit` flow — no new flags needed.
- Verified against a production build: a complete llms.txt passes clean; stripping the when-to-use section triggers the warning.

Context: this ships alongside ZensInk Pro v2.4.0, which adds a full Agent Readiness Score (8 checks, 0-100, P0/P1/P2 fix plan). The reference implementation of that checklist took zens.ink from 64 to 98/100 on [is-agentic.com](https://is-agentic.com/scan/zens.ink).

## v1.4.3 — 2026-08-15

**KD brand-keyword forensics + rank tracking.**

- kd brand triple-fingerprint: official domain in top3, domain-family seats >= 2, platform-ecosystem density — brand keywords no longer poison generic KD
- `kd_entry`: derivative-entry difficulty after removing official pages and platform-fixed seats
- KD -> referring-domains link budget curve (editorial vs directory tracks)
- `--markdown` self-contained report mode
- **New tool: rank_tracker** — SQLite-backed keyword position history
- competitor_gap: deeper sitemap parsing

## v1.4.2 — 2026-08-14

- **MCP stdio server** — `zens-ink mcp` exposes every CLI tool as a native model tool for MCP clients (DSH, Claude, Codex)
- **New tool: serp_intent** — SERP-driven intent evaluation via Serper (20+ page types, 4 intents, SERP-feature detection); cross-validates keyword-based `search_intent`

## v1.4.1 — 2026-08-06

- **New tool: geo_fanout** — Query Fan-out content planning
- **New tool: reddit_blueocean** — Reddit blue-ocean mining via Google Autocomplete
- site_audit: +3 checks (staging-leak detection, sitemap inventory, schema field validation)

## v1.3.0 — 2026-07-20

- site_audit expanded to 30 checks: images, GEO, i18n, performance

## v1.2.0 — 2026-07-17

- 8 → 13 tools: keyword_cluster, search_intent, kgr_auto, content_matrix, onpage_audit

## v1.0.0 — 2026-06-25

- Initial public release: 8 free CLI tools, zero dependencies, bilingual docs
