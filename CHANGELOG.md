# Changelog

## v1.4.11 — 2026-10-14

**Independent audit hardening — 39 defects fixed (DSH round 1: 40 findings, 12H/15M/13L).**
The toolkit went through its first full independent code audit (DeepSeek Harness,
every module read end-to-end, every finding reproduced locally before the fix).
The defining pattern the audit exposed: tools that fail *silently confidently*
rather than loudly. This release fixes all 39 verified findings; one item
(Brave `count` field schema) stays flagged UNVERIFIED pending a live keyed check.

High-severity fixes:
- `mcp`: competitor_gap was unusable over MCP — every call passed an
  unsupported `--json` and errored (registry now flags `json_flag: False`).
- `keyword_research` / `geo_fanout` / `reddit_blueocean`: autocomplete
  envelope `["q", null]` returned `None` and crashed every caller; now `[]`.
- `site_audit`: JSON-LD `@type` matching used a literal `\s*` so
  pretty-printed schema was invisible (Product/FAQ never detected).
- `site_audit`: the homepage was always reported as an orphan (`/` was
  dropped from the link map).
- `ai_crawler_audit`: consecutive `User-agent:` lines overwrote each other —
  `Disallow: /` groups read as "unlisted" for all but the last agent.
- `rank_tracker`: `lstrip("www.")` mangled domains (`walmart.com` →
  `almart.com`, never matched); substring matching stored strangers' ranks
  as yours; the 999 not-found sentinel fabricated ±996-place "trends".
- `search_intent`: bare `get` token made "how to get more traffic"
  transactional. `serp_intent`: unanchored path rules typed
  `/blog/product-led-growth` as product; percentages divided by hardcoded 10.
- `competitor_gap`: sub-sitemaps silently capped at 10 (partial inventories
  compared as complete); `--compare` keyed by netloc so same-domain sitemaps
  overwrote each other.
- `geo_fanout`: inverted containment marked every sub-query as
  demand-validated; dimension report printed each header up to 3×.
- `kgr_auto`: missing Bing key aborted the run after promising graceful
  degradation (keyword_volume now degrades in-library, CLI still exits loudly).
- `reddit_blueocean`: substring matching let `top` hit *laptop*/*desktop*.

Medium/low: MCP protocol negotiation now honest (unsupported versions fall
back instead of echoing), invalid params map to -32602; `content_qc` counts
CJK characters (the publishing gate was meaningless on Chinese drafts);
`search_performance` paginates GSC rows (top-50 subtotals no longer printed
as totals); `keyword_cluster` parses quoted CSV properly; `content_matrix`
JSON input coerces numerics; `domain_rating` cache falls back to ~/.zens_ink
when site-packages isn't writable; `llms_gen` unescapes sitemap entities and
survives a 404 sitemap; `setup_gsc` no longer discards a fresh OAuth token
on a bare-filename path; CLI dispatcher registered `content_qc` + `llms_gen`
(were documented but "Unknown tool"); TOOLS_COUNT 20 → 22; SKILL.md frontmatter
refreshed (was stale at v1.2.1 / 13 tools).

Round 2 (full re-verification): 37/39 fully fixed, 2 PARTIAL (geo_fanout
prefix over-validation; kd HTTP error handling), 1 correctly DEFERRED — plus
2 new defects introduced by the fixes themselves (serp_intent /guide-style
patterns left unanchored mistyped /pricing/guide as blog; content_matrix JSON
coerced only 3 of 6 numeric fields). All four corrected in round 3: content
path patterns fully anchored (`/pricing/guide` stays pricing, `/guide/x` is
blog), six-field numeric coercion in both branches, exact-match live demand,
kd HTTPError handling. Round-2 report archived as
`docs/audit-2026-10-14-dsh-round2.md`.

Round 3 (spot check on the four round-2 items): all four verified FIXED,
v1.4.11 cleared as releasable. Reports archived:
`docs/audit-2026-10-14-dsh-round{1,2,3}.md`.

New: `tests/test_audit_fixes.py` — 18 regression tests pinning every fix
above; smoke tests extended. Audit reports archived in-repo
(`docs/audit-2026-10-14-dsh-round1.md`, `docs/audit-2026-10-14-dsh-round2.md`).

## v1.4.10 — 2026-10-01

**Brand card refresh.**
- New hero banner (EN + ZH): current Z mark, tool pipeline, `pip install`
  line — replaces the retired ink-drop design.
- README hero images now use absolute URLs so they render on PyPI too.

## v1.4.9 — 2026-09-30

**Repo agent layer — make the repo itself AI-readable.**
Gitingest and GitDiagram (15k+ stars combined) turned "how AI tools digest
your repository" into a real surface: agents now meet your project through
these digests before they meet your code. This release ships that layer for
zens-ink itself, dogfooding the new Pro repo_readiness audit.

- **llms.txt + llms-full.txt** in the repo root — agent-readable digest:
  20-tool inventory, MCP / skill entry points, install commands, links.
- **ARCHITECTURE.md** — module layering and data flow in one page, so
  generated digests describe structure instead of guessing it.
- **Smoke tests** (`tests/test_smoke.py`) — imports and CLI surface keep
  working as the toolkit grows.
- **FUNDING.yml** — points at zens.ink pricing.
- Verified with the new Pro v2.6.0 `repo_readiness` audit: 76/C → 91/A.
  Compare: gitdiagram 63/D, psf/requests 59/F — the classic repos most in
  need of the same layer.

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
