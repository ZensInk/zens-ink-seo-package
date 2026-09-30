# Architecture

ZensInk is a flat Python package of independent CLI tools sharing one config loader. No framework, no plugin system, no daemon. Each tool is a module under `zens_ink/`, runnable two ways:

```
zens-ink <tool> [args]          # installed entry point (setup.py console_scripts)
python3 -m zens_ink.<tool>      # module invocation, no install needed
```

```
zens_ink/
├── config.py            ← single .env loader; every tool imports from here
├── keyword_research.py  ┐
├── kd.py                │ independent CLI tools (see README table)
├── site_audit.py        │ each = argparse main() + pure functions
├── mcp.py               ┘
└── __main__.py            `zens-ink <tool>` dispatcher
```

## Data flow

Every tool follows the same three-stage pipeline:

```
free data source → in-memory analysis → report file (JSON/CSV/MD)
```

Data sources and their consumers:

```
Google Autocomplete ──→ keyword_research, keyword_cluster, reddit_blueocean, kgr_auto
Bing Webmaster API ──→ keyword_volume, kgr_auto
Serper.dev SERP    ──→ kd, serp_intent, rank_tracker
Brave Search API   ──→ brave_volume
Ahrefs public API  ──→ domain_rating
Google Search Cons─→ search_performance (OAuth via setup_gsc)
Local files        ──→ site_audit, onpage_audit, content_qc (dist/ + sitemap.xml)
```

No tool writes to a database except `rank_tracker` (SQLite). Caches are per-tool JSON files (`kd-cache.json`, `dr-cache.json`) written next to the working directory.

## Config

`config.py` reads the package-root `.env` once at import time and exports `SERPER_API_KEY`, `BING_API_KEY`, `BRAVE_API_KEY`, `AHREFS_API_KEY`, `GSC_*`. Tools degrade gracefully: a tool whose key is missing prints an error pointing at `.env.example`; it never crashes the dispatcher. `runtime.conf` (optional) maps key aliases for multi-profile setups.

## MCP server

`mcp.py` is a stdio JSON-RPC server that reflects over the package and exposes every tool as an MCP tool (`mcp__zensink__keyword_research`, ...). If the Pro package (`zens_ink_pro`) is installed alongside, its tools are detected and exposed by the same server. Zero extra dependencies — the protocol layer is hand-rolled JSON over stdin/stdout.

## Cross-tool intent validation

Two intent layers exist on purpose: `search_intent` classifies from the keyword text; `serp_intent` classifies from the actual SERP composition. The Pro pipeline cross-validates them — when both disagree, the SERP wins (Google's ranking behavior is ground truth over keyword heuristics).

## Invariants

- Zero third-party dependencies (stdlib only) — enforced by review; `requirements.txt` is empty placeholder
- Every tool runs standalone; no tool imports another tool's module (shared logic lives in `config.py`)
- Python 3.10+, no EOL-syntax compat shims
