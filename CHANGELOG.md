# Changelog

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
