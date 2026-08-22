# Changelog

## v1.6.1 — 2026-08-23

**Agent-readiness checks in site_audit.** The web is increasingly read by autonomous agents, not just humans and crawlers. `site_audit` now flags the two llms.txt gaps that decide whether agents understand your product:

- **New check: agent when-to-use** — llms.txt without a `When to use` section reads as marketing, not guidance; agents can't tell which jobs your site fits. Flagged as a warning with a fix hint.
- **New check: agent how-to-call** — llms.txt without an install command / endpoint / MCP entry point gives agents no way to act on the discovery. Flagged as info.
- Both checks are deterministic, zero-dependency, and run inside the existing `site_audit` flow — no new flags needed.
- Verified against a production build: a complete llms.txt passes clean; stripping the when-to-use section triggers the warning.

Context: this ships alongside ZensInk Pro v2.4.0, which adds a full Agent Readiness Score (8 checks, 0-100, P0/P1/P2 fix plan). The reference implementation of that checklist took zens.ink from 64 to 98/100 on [is-agentic.com](https://is-agentic.com/scan/zens.ink).

## v1.6.0 — 2026-08-22

**Brand-keyword forensics in kd.** Brand keywords poison generic KD scores — this release detects them and recomputes difficulty on contestable seats only.

- Brand triple-fingerprint: official domain in top3, domain-family seats >= 2, platform-ecosystem density
- `kd_entry`: derivative-entry difficulty after removing official pages and platform-fixed seats
- KD -> referring-domains link budget curve (editorial vs directory tracks)
- `--markdown` self-contained report mode

## v1.5.0 — 2026-07-17

- **GEO Score** — per-page AI citation readiness: 5 layers (Fact 35% / Structure 25% / Semantic 15% / AI Access 15% / Trust 10%), deterministic 0-100 with letter grade and P0/P1/P2 action plan. Zero API cost.
- **MCP stdio server** — `zens-ink mcp` exposes every CLI tool to MCP clients (DSH, Claude, Codex).

## v1.4.x — 2026-06/07

- v1.4.2: MCP stdio server
- v1.4.1: 33-check site_audit (links / meta / images / GEO / i18n / staging-leak detection)
- v1.4.0: search_intent four-way classification, onpage_audit 7-dimension scoring, full_audit 12-step orchestration

## v1.3.x — 2026-06

- serp_intent: SERP-driven intent evaluation via Serper (20+ page types, 4 intents, SERP-feature detection)
- Winability Score, Content Radar, Competitor Radar (Pro-synced methodology)

## v1.1.0 — 2026-06-25

- Initial public release: keyword discovery, volume, KD, GSC performance, competitor gap, KGR, clustering
