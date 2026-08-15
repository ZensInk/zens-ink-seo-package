#!/usr/bin/env python3
"""
ZensInk MCP Server — expose ZensInk SEO tools to MCP clients (DSH, Claude, etc.)

Pure-stdlib MCP stdio server (JSON-RPC 2.0 over newline-delimited stdin/stdout).
Each tool runs the existing CLI module in a subprocess
(`python3 -m zens_ink.<tool> ... --json`), so behavior is byte-identical to
command-line usage and this file owns zero business logic.

Works with:
  - DSH (DeepSeek Harness) via @deepseek-ai/dsh-mcp-client (transport: stdio)
  - Any MCP client (Claude Desktop, Codex, ...) speaking the stdio transport

Usage:
  python3 -m zens_ink.mcp        # run as MCP stdio server

DSH profile entry (~/.dsh/profiles/<profile>/cordis.patch.yml):
  - insert:
      - id: mcp-zensink
        name: '@deepseek-ai/dsh-mcp-client'
        config:
          serverName: zensink
          transport: stdio
          command: python3
          args: ['-m', 'zens_ink.mcp']
          toolCallTimeoutMs: 300000

The model then sees tools named mcp__zensink__keyword_research, mcp__zensink__kd, ...
API keys are read from the package root .env (zens_ink/config.py), independent of cwd.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

from . import __version__

_PKG_ROOT = Path(__file__).resolve().parent.parent

# sys.executable can be '' in restricted/embedded contexts — fall back to PATH.
_PYTHON = sys.executable or shutil.which("python3") or "python3"

# ---------------------------------------------------------------------------
# Tool registry: presentation metadata only. CLI flags map 1:1 to schema
# properties (name = flag without dashes). positional entries become leading
# argv; "multiple" positionals accept an array of strings (nargs="*").
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "keyword_research",
        "module": "zens_ink.keyword_research",
        "description": (
            "Google Autocomplete long-tail keyword mining. Free, no API key. "
            "Discover what people actually type around a seed keyword; "
            "--expand appends a-z for deeper long-tail variants."
        ),
        "positional": [
            {"name": "keyword", "type": "string", "description": "Seed keyword, e.g. 'astro seo' or '八字排盘'"},
        ],
        "flags": [
            {"name": "lang", "flag": "--lang", "type": "string", "enum": ["en", "zh"], "description": "Language (default en)"},
            {"name": "expand", "flag": "--expand", "type": "boolean", "description": "Append a-z expansion for deeper long-tail (slower)"},
        ],
        "timeout": 240,
    },
    {
        "name": "keyword_volume",
        "module": "zens_ink.keyword_volume",
        "description": (
            "Real search volumes via Bing Webmaster API. Requires BING_API_KEY in .env. "
            "Pass keywords as an array (comma-separated also accepted by the CLI)."
        ),
        "positional": [
            {"name": "keywords", "type": "array", "items": "string", "multiple": True, "description": "Keywords to look up"},
        ],
        "flags": [
            {"name": "file", "flag": "--file", "type": "string", "description": "File with one keyword per line (alternative to keywords)"},
            {"name": "country", "flag": "--country", "type": "string", "description": "Country filter"},
            {"name": "lang", "flag": "--lang", "type": "string", "description": "Language filter"},
        ],
        "timeout": 120,
    },
    {
        "name": "brave_volume",
        "module": "zens_ink.brave_volume",
        "description": (
            "Brave Search API volume estimates — supplements Bing's volume gaps. "
            "Requires BRAVE_API_KEY in .env."
        ),
        "positional": [
            {"name": "keyword", "type": "string", "description": "Single keyword"},
        ],
        "flags": [
            {"name": "file", "flag": "--file", "type": "string", "description": "File with keywords (alternative to keyword)"},
            {"name": "country", "flag": "--country", "type": "string", "description": "Country code"},
            {"name": "lang", "flag": "--lang", "type": "string", "description": "Language code"},
            {"name": "zh", "flag": "--zh", "type": "boolean", "description": "Chinese mode"},
        ],
        "timeout": 120,
    },
    {
        "name": "keyword_cluster",
        "module": "zens_ink.keyword_cluster",
        "description": (
            "Group raw keywords into semantic topic clusters (pure-stdlib similarity). "
            "Feed the output JSON into content_matrix together with kgr_auto scores."
        ),
        "positional": [
            {"name": "keywords", "type": "array", "items": "string", "multiple": True, "description": "Keywords to cluster"},
        ],
        "flags": [
            {"name": "file", "flag": "--file", "type": "string", "description": "File with keywords, one per line or CSV (alternative)"},
            {"name": "threshold", "flag": "--threshold", "type": "number", "description": "Similarity threshold 0-1 (default 0.15, lower = more grouping)"},
            {"name": "min_size", "flag": "--min-size", "type": "integer", "description": "Minimum cluster size to include (default 1)"},
        ],
        "timeout": 120,
    },
    {
        "name": "kgr_auto",
        "module": "zens_ink.kgr_auto",
        "description": (
            "Automated KGR (Keyword Golden Ratio) opportunity scoring: allintitle-based "
            "low-competition keyword detection with search volume. Needs Bing volume key."
        ),
        "positional": [
            {"name": "keywords", "type": "array", "items": "string", "multiple": True, "description": "Keywords to score"},
        ],
        "flags": [
            {"name": "file", "flag": "--file", "type": "string", "description": "File with keywords (alternative)"},
            {"name": "lang", "flag": "--lang", "type": "string", "description": "Language (en/zh)"},
            {"name": "country", "flag": "--country", "type": "string", "description": "Country code"},
        ],
        "timeout": 300,
    },
    {
        "name": "content_matrix",
        "module": "zens_ink.content_matrix",
        "description": (
            "Prioritized content opportunity matrix: joins kgr_auto scored keywords "
            "(CSV or JSON file) with keyword_cluster clusters (JSON file). File-based tool."
        ),
        "flags": [
            {"name": "scores", "flag": "--scores", "type": "string", "description": "Path to scored keywords file (from kgr_auto)"},
            {"name": "clusters", "flag": "--clusters", "type": "string", "description": "Path to cluster JSON (from keyword_cluster)"},
        ],
        "timeout": 120,
    },
    {
        "name": "kd",
        "module": "zens_ink.kd",
        "description": (
            "Keyword Difficulty estimator — SERP-structure-based (homepage ratio, page "
            "types, niche maturity), not Ahrefs DR. Includes brand-keyword triple-"
            "fingerprint detection with derivative-entry difficulty (截流难度), link "
            "budget estimate (KD→referring domains), and optional Markdown report. "
            "Requires SERPER_API_KEY in .env."
        ),
        "positional": [
            {"name": "keyword", "type": "string", "description": "Keyword to analyze"},
        ],
        "flags": [
            {"name": "gl", "flag": "--gl", "type": "string", "description": "Geo location (default us)"},
            {"name": "hl", "flag": "--hl", "type": "string", "description": "Language (default en)"},
            {"name": "zh", "flag": "--zh", "type": "boolean", "description": "Chinese mode (gl=cn, hl=zh-CN)"},
            {"name": "no_volume", "flag": "--no-volume", "type": "boolean", "description": "Skip search volume lookup (faster)"},
            {"name": "markdown", "flag": "--markdown", "type": "boolean", "description": "Self-contained Markdown report (for AI ingestion)"},
        ],
        "timeout": 180,
    },
    {
        "name": "serp_intent",
        "module": "zens_ink.serp_intent",
        "description": (
            "Reverse-engineer search intent from actual Google SERP composition "
            "(page-type weighting, SERP features). Cross-validates with keyword-based "
            "classification via --cross. Requires SERPER_API_KEY in .env."
        ),
        "positional": [
            {"name": "keyword", "type": "string", "description": "Keyword to analyze"},
        ],
        "flags": [
            {"name": "gl", "flag": "--gl", "type": "string", "description": "Geo location (default us)"},
            {"name": "hl", "flag": "--hl", "type": "string", "description": "Language (default en)"},
            {"name": "zh", "flag": "--zh", "type": "boolean", "description": "Chinese mode"},
            {"name": "cross", "flag": "--cross", "type": "boolean", "description": "Cross-validate with keyword-based intent classification"},
        ],
        "timeout": 180,
    },
    {
        "name": "search_intent",
        "module": "zens_ink.search_intent",
        "description": (
            "Keyword-based search intent classification (informational / commercial / "
            "transactional / navigational + question/buyer/problem markers). No API key."
        ),
        "positional": [
            {"name": "keywords", "type": "array", "items": "string", "multiple": True, "description": "Keywords to classify"},
        ],
        "flags": [
            {"name": "file", "flag": "--file", "type": "string", "description": "File with one keyword per line (alternative)"},
        ],
        "timeout": 60,
    },
    {
        "name": "geo_fanout",
        "module": "zens_ink.geo_fanout",
        "description": (
            "GEO fan-out: reverse-engineer the query variants AI search engines generate "
            "for a topic (Query Fan-out content planning). Free autocomplete-backed."
        ),
        "positional": [
            {"name": "keyword", "type": "string", "description": "Seed keyword, e.g. 'best CRM'"},
        ],
        "flags": [
            {"name": "icp", "flag": "--icp", "type": "string", "description": "Ideal Customer Profile, e.g. 'healthcare SMBs'"},
            {"name": "lang", "flag": "--lang", "type": "string", "description": "Language for autocomplete"},
            {"name": "no_live", "flag": "--no-live", "type": "boolean", "description": "Skip live autocomplete checks (faster)"},
        ],
        "timeout": 240,
    },
    {
        "name": "reddit_blueocean",
        "module": "zens_ink.reddit_blueocean",
        "description": (
            "Find high-traffic, low-competition Reddit posts via Google Autocomplete "
            "mining — blue-ocean subreddit demand discovery. Free."
        ),
        "positional": [
            {"name": "keyword", "type": "string", "description": "Seed keyword"},
        ],
        "flags": [
            {"name": "subreddits", "flag": "--subreddits", "type": "string", "description": "Comma-separated subreddits (default: auto-discover)"},
            {"name": "niche", "flag": "--niche", "type": "string", "description": "Your niche/ICP, e.g. 'saas'"},
            {"name": "lang", "flag": "--lang", "type": "string", "description": "Language"},
            {"name": "no_demand", "flag": "--no-demand", "type": "boolean", "description": "Skip Google demand check (faster)"},
        ],
        "timeout": 240,
    },
    {
        "name": "competitor_gap",
        "module": "zens_ink.competitor_gap",
        "description": (
            "Competitor content gap: fetch sitemap(s) and list topics competitors cover "
            "that you don't. Pass url (one sitemap) or compare (several). Free."
        ),
        "flags": [
            {"name": "url", "flag": "--url", "type": "string", "description": "Single competitor sitemap URL"},
            {"name": "compare", "flag": "--compare", "type": "array", "items": "string", "description": "Multiple sitemap URLs to compare (your site first)"},
            {"name": "lang", "flag": "--lang", "type": "string", "description": "Filter by language (en, zh, ...)"},
        ],
        "timeout": 240,
    },
    {
        "name": "site_audit",
        "module": "zens_ink.site_audit",
        "description": (
            "Technical SEO audit of a built static site directory (33 checks: links/meta/"
            "images/GEO/i18n/performance/structured data). Point dist at the build output."
        ),
        "flags": [
            {"name": "dist", "flag": "--dist", "type": "string", "description": "Build output directory (default dist)"},
            {"name": "sitemap", "flag": "--sitemap", "type": "string", "description": "Sitemap XML path (auto-detects sitemap-0.xml)"},
            {"name": "base", "flag": "--base", "type": "string", "description": "Base path prefix filter, e.g. /en"},
            {"name": "format", "flag": "--format", "type": "string", "enum": ["text", "json"], "description": "Output format (default text)"},
            {"name": "max_image_kb", "flag": "--max-image-kb", "type": "integer", "description": "Max image size in KB before flagging (default 200)"},
            {"name": "verbose", "flag": "--verbose", "type": "boolean", "description": "Show all link targets"},
        ],
        "json_flag": False,  # uses --format json instead of --json
        "timeout": 300,
    },
    {
        "name": "rank_tracker",
        "module": "zens_ink.rank_tracker",
        "description": (
            "SQLite-backed keyword rank tracker: add keywords for your domain, "
            "run check to snapshot current Google positions (Serper), then see "
            "status/trend/history over time. State persists in ~/.zens_ink/ranks.db."
        ),
        "positional": [
            {"name": "action", "type": "string", "description": "add | check | status | trend | history | remove"},
        ],
        "flags": [
            {"name": "keywords", "flag": "--keywords", "type": "string", "description": "Keyword(s) for add/history/remove (comma-separated)"},
            {"name": "domain", "flag": "--domain", "type": "string", "description": "Your domain to track (add)"},
            {"name": "tag", "flag": "--tag", "type": "string", "description": "Optional group tag (add)"},
            {"name": "gl", "flag": "--gl", "type": "string", "description": "Geo (default us)"},
            {"name": "hl", "flag": "--hl", "type": "string", "description": "Language (default en)"},
            {"name": "num", "flag": "--num", "type": "integer", "description": "SERP depth per keyword (default 20)"},
            {"name": "limit", "flag": "--limit", "type": "integer", "description": "History rows (default 20)"},
        ],
        "timeout": 600,
    },
    {
        "name": "onpage_audit",
        "module": "zens_ink.onpage_audit",
        "description": (
            "On-page quality scoring (7 dimensions, 100-point A-F) for built HTML pages. "
            "Optionally weight by a keywords file. Point dist at the build output."
        ),
        "flags": [
            {"name": "dist", "flag": "--dist", "type": "string", "description": "Path to built site directory"},
            {"name": "sitemap", "flag": "--sitemap", "type": "string", "description": "Path to sitemap XML"},
            {"name": "keywords", "flag": "--keywords", "type": "string", "description": "Keywords file, one per line"},
            {"name": "base", "flag": "--base", "type": "string", "description": "Base URL path filter, e.g. /en"},
            {"name": "format", "flag": "--format", "type": "string", "enum": ["text", "json"], "description": "Output format (default text)"},
        ],
        "json_flag": False,
        "timeout": 300,
    },
    {
        "name": "search_performance",
        "module": "zens_ink.search_performance",
        "description": (
            "Your site's real Google Search Console data (impressions/clicks/position). "
            "Requires GSC_SITE_URL + ADC credentials configured via setup_gsc."
        ),
        "flags": [
            {"name": "start", "flag": "--start", "type": "string", "description": "Start date YYYY-MM-DD"},
            {"name": "end", "flag": "--end", "type": "string", "description": "End date YYYY-MM-DD or 'today'"},
            {"name": "limit", "flag": "--limit", "type": "integer", "description": "Row limit (default 50)"},
            {"name": "page", "flag": "--page", "type": "string", "description": "Filter to a specific page path"},
            {"name": "queries", "flag": "--queries", "type": "boolean", "description": "List top queries instead of pages"},
            {"name": "pages", "flag": "--pages", "type": "boolean", "description": "List top pages"},
            {"name": "country", "flag": "--country", "type": "boolean", "description": "Break down by country"},
        ],
        "timeout": 120,
    },
]


def _extra_tools():
    """Merge Pro tools when zens_ink_pro is installed next to this package.

    OSS-only installs never ship Pro code, so the import simply fails and the
    tool list stays OSS-only. No Pro metadata lives in this public file.
    """
    try:
        from zens_ink_pro.mcp_registry import PRO_TOOLS  # type: ignore
        return list(PRO_TOOLS)
    except Exception:
        return []


# Final tool registry: OSS tools + (if present) Pro tools.
TOOLS = TOOLS + _extra_tools()

MAX_OUTPUT_CHARS = 60000


def _schema_type(spec):
    if spec["type"] == "array":
        return {"type": "array", "items": {"type": spec.get("items", "string")}}
    return {"type": spec["type"]}


def tool_definitions():
    defs = []
    for t in TOOLS:
        props = {}
        required = []
        for p in t.get("positional", []):
            prop = _schema_type(p)
            prop["description"] = p["description"]
            props[p["name"]] = prop
            if not p.get("multiple") and not p.get("optional"):
                required.append(p["name"])  # single positionals are required unless marked optional
        for f in t.get("flags", []):
            prop = _schema_type(f)
            prop["description"] = f["description"]
            props[f["name"]] = prop
        defs.append({
            "name": t["name"],
            "description": t["description"],
            "inputSchema": {
                "type": "object",
                "properties": props,
                "required": required,
            },
        })
    return defs


def build_command(name, arguments):
    t = next(x for x in TOOLS if x["name"] == name)
    arguments = arguments or {}
    cmd = [_PYTHON, "-m", t["module"]]
    for p in t.get("positional", []):
        v = arguments.get(p["name"])
        if v is None:
            if p.get("multiple") or p.get("optional"):
                continue
            raise ValueError(f"missing required argument '{p['name']}'")
        if isinstance(v, list):
            cmd += [str(x) for x in v]
        else:
            cmd.append(str(v))
    for f in t.get("flags", []):
        v = arguments.get(f["name"])
        if v is None:
            continue
        if f["type"] == "boolean":
            if v:
                cmd.append(f["flag"])
        elif isinstance(v, list):
            cmd.append(f["flag"])
            cmd += [str(x) for x in v]
        else:
            cmd += [f["flag"], str(v)]
    if t.get("json_flag", True):
        cmd.append("--json")
    return cmd, t


def call_tool(name, arguments):
    if name not in {t["name"] for t in TOOLS}:
        raise ValueError(f"unknown tool '{name}'")
    cmd, t = build_command(name, arguments)
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(_PKG_ROOT),
            capture_output=True,
            text=True,
            timeout=t.get("timeout", 240),
        )
    except subprocess.TimeoutExpired:
        return {
            "content": [{"type": "text", "text": f"Tool timed out after {t.get('timeout', 240)}s: {' '.join(cmd)}"}],
            "isError": True,
        }
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    if proc.returncode != 0:
        text = err or out or f"exit code {proc.returncode}"
        return {"content": [{"type": "text", "text": text}], "isError": True}
    text = out or err or "(no output)"
    if len(text) > MAX_OUTPUT_CHARS:
        text = text[:MAX_OUTPUT_CHARS] + f"\n... (truncated, {len(text) - MAX_OUTPUT_CHARS} more chars)"
    return {"content": [{"type": "text", "text": text}]}


def dispatch(method, params):
    if method == "initialize":
        return {
            "protocolVersion": params.get("protocolVersion", "2024-11-05"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "zens-ink", "version": __version__},
        }
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": tool_definitions()}
    if method == "tools/call":
        return call_tool(params.get("name"), params.get("arguments"))
    raise KeyError(method)


def serve():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(msg, dict) or "id" not in msg:
            continue  # notification or malformed — nothing to answer
        reply = {"jsonrpc": "2.0", "id": msg["id"]}
        try:
            reply["result"] = dispatch(msg.get("method"), msg.get("params") or {})
        except KeyError:
            reply["error"] = {"code": -32601, "message": f"method not found: {msg.get('method')}"}
        except Exception as e:  # noqa: BLE001 — surface any tool error to the client
            reply["error"] = {"code": -32603, "message": str(e)}
        sys.stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    serve()
