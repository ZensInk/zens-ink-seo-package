#!/usr/bin/env python3
"""
Rank Tracker — SQLite-backed keyword rank tracking.

Track your domain's Google positions for a keyword set, store every check as a
snapshot, and see trends across time. Pure stdlib (sqlite3), SERPER_API_KEY
for SERP fetches — 1 API call per keyword per check.

Storage: ~/.zens_ink/ranks.db (created automatically)

Actions:
  add      Track keywords:            python3 -m zens_ink.rank_tracker add "kw1,kw2" --domain example.com
  check    Fetch + snapshot all:      python3 -m zens_ink.rank_tracker check
  status   Latest position per kw:    python3 -m zens_ink.rank_tracker status
  trend    Latest vs previous:        python3 -m zens_ink.rank_tracker trend
  history  One keyword's snapshots:   python3 -m zens_ink.rank_tracker history "kw"
  remove   Untrack a keyword:         python3 -m zens_ink.rank_tracker remove "kw"

All actions print human tables by default, JSON with --json.
"""

import argparse
import json
import os
import sqlite3
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from .config import load_env

load_env()

SERPER_API_KEY = os.environ.get("SERPER_API_KEY", "")
DB_PATH = Path.home() / ".zens_ink" / "ranks.db"

_NOT_FOUND = 999  # sentinel: domain not in top-N results


# ── DB ──────────────────────────────────────────────────────────────────────

def _conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.executescript("""
    CREATE TABLE IF NOT EXISTS keywords (
      keyword TEXT PRIMARY KEY,
      domain TEXT NOT NULL DEFAULT '',
      tag TEXT NOT NULL DEFAULT '',
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS snapshots (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      keyword TEXT NOT NULL,
      position INTEGER NOT NULL,
      url TEXT NOT NULL DEFAULT '',
      checked_at TEXT NOT NULL,
      FOREIGN KEY(keyword) REFERENCES keywords(keyword)
    );
    CREATE INDEX IF NOT EXISTS idx_snap_kw ON snapshots(keyword, checked_at);
    """)
    return c


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── SERP ────────────────────────────────────────────────────────────────────

def _domain_of(url):
    try:
        host = url.split("//", 1)[1].split("/", 1)[0]
        return host[4:] if host.startswith("www.") else host
    except (IndexError, AttributeError):
        return ""


def fetch_positions(keyword, domain, gl="us", hl="en", num=20):
    """Return (position, url) for the first result whose domain matches."""
    payload = {"q": keyword, "gl": gl, "hl": hl, "num": num}
    req = urllib.request.Request(
        "https://google.serper.dev/search",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "X-API-KEY": SERPER_API_KEY})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode())
    target = domain.lower().lstrip("www.") if domain else ""
    for r in data.get("organic", []):
        d = _domain_of(r.get("link", ""))
        if target and (d == target or d.endswith("." + target) or target in d):
            return r.get("position", _NOT_FOUND), r.get("link", "")
    return _NOT_FOUND, ""


# ── Actions ─────────────────────────────────────────────────────────────────

def act_add(args):
    kws = [k.strip() for k in args.keywords.replace("\n", ",").split(",") if k.strip()]
    c = _conn()
    now = _now()
    for kw in kws:
        c.execute(
            "INSERT INTO keywords(keyword, domain, tag, created_at) VALUES(?,?,?,?) "
            "ON CONFLICT(keyword) DO UPDATE SET domain=excluded.domain, tag=excluded.tag",
            (kw, args.domain or "", args.tag or "", now))
    c.commit()
    total = c.execute("SELECT COUNT(*) FROM keywords").fetchone()[0]
    c.close()
    return {"added": kws, "total_tracked": total, "db": str(DB_PATH)}


def act_remove(args):
    c = _conn()
    cur = c.execute("DELETE FROM keywords WHERE keyword=?", (args.keywords,))
    c.execute("DELETE FROM snapshots WHERE keyword=?", (args.keywords,))
    c.commit()
    n = cur.rowcount
    c.close()
    return {"removed": args.keywords if n else None}


def act_check(args):
    if not SERPER_API_KEY:
        return {"error": "SERPER_API_KEY missing — add it to .env (free tier: serper.dev)"}
    c = _conn()
    rows = c.execute("SELECT keyword, domain FROM keywords ORDER BY keyword").fetchall()
    if not rows:
        c.close()
        return {"error": "no tracked keywords — run: rank_tracker add 'kw1,kw2' --domain example.com"}
    now = _now()
    results = []
    for r in rows:
        kw, dom = r["keyword"], r["domain"]
        if not dom:
            results.append({"keyword": kw, "error": "no domain set (add with --domain)"})
            continue
        try:
            pos, url = fetch_positions(kw, dom, gl=args.gl, hl=args.hl, num=args.num)
        except Exception as e:
            results.append({"keyword": kw, "error": str(e)})
            continue
        c.execute("INSERT INTO snapshots(keyword, position, url, checked_at) VALUES(?,?,?,?)",
                  (kw, pos, url, now))
        results.append({"keyword": kw, "position": (None if pos == _NOT_FOUND else pos),
                        "url": url, "checked_at": now})
    c.commit()
    c.close()
    return {"checked": len(results), "ok": sum(1 for x in results if "error" not in x),
            "results": results}


def act_status(args):
    c = _conn()
    rows = c.execute("""
        SELECT k.keyword, k.tag, s.position, s.url, s.checked_at
        FROM keywords k
        LEFT JOIN snapshots s ON s.keyword = k.keyword
          AND s.id = (SELECT MAX(id) FROM snapshots WHERE keyword = k.keyword)
        ORDER BY k.keyword""").fetchall()
    c.close()
    return {"keywords": [
        {"keyword": r["keyword"], "tag": r["tag"],
         "position": r["position"], "url": r["url"],
         "last_checked": r["checked_at"]} for r in rows]}


def act_trend(args):
    c = _conn()
    rows = c.execute("SELECT keyword FROM keywords ORDER BY keyword").fetchall()
    out = []
    for r in rows:
        kw = r["keyword"]
        snaps = c.execute(
            "SELECT position, checked_at FROM snapshots WHERE keyword=? "
            "ORDER BY id DESC LIMIT ?", (kw, args.limit + 1)).fetchall()
        if not snaps:
            out.append({"keyword": kw, "position": None, "delta": None,
                        "history_len": 0})
            continue
        cur = snaps[0]["position"]
        prev = snaps[1]["position"] if len(snaps) > 1 else None
        delta = (prev - cur) if prev is not None else None
        out.append({"keyword": kw,
                    "position": None if cur == _NOT_FOUND else cur,
                    "previous": None if prev in (None, _NOT_FOUND) else prev,
                    "delta": delta,  # +improved, -dropped
                    "history_len": len(snaps)})
    c.close()
    return {"trends": out}


def act_history(args):
    c = _conn()
    snaps = c.execute(
        "SELECT position, url, checked_at FROM snapshots WHERE keyword=? "
        "ORDER BY id DESC LIMIT ?", (args.keywords, args.limit)).fetchall()
    c.close()
    return {"keyword": args.keywords, "snapshots": [
        {"position": (None if s["position"] == _NOT_FOUND else s["position"]),
         "url": s["url"], "checked_at": s["checked_at"]} for s in snaps]}


# ── Render ──────────────────────────────────────────────────────────────────

def _fmt_pos(p):
    if p is None or p == _NOT_FOUND:
        return "—"
    return str(p)


def _fmt_delta(d):
    if d is None:
        return ""
    return f"+{d}" if d > 0 else str(d)


def render(data, action):
    if "error" in data:
        return f"error: {data['error']}"
    if action == "add":
        return (f"tracking {len(data['added'])} keyword(s): {', '.join(data['added'])}\n"
                f"total tracked: {data['total_tracked']}  (db: {data['db']})")
    if action == "remove":
        return f"removed: {data['removed']}" if data["removed"] else "not tracked"
    if action == "check":
        lines = [f"checked {data['ok']}/{data['checked']} keywords:"]
        for r in data["results"]:
            if "error" in r:
                lines.append(f"  ✗ {r['keyword']}: {r['error']}")
            else:
                lines.append(f"  #{_fmt_pos(r['position']):>4}  {r['keyword']}")
        return "\n".join(lines)
    if action == "status":
        lines = ["keyword                                        pos   last checked"]
        for k in data["keywords"]:
            lines.append(f"{k['keyword'][:44]:<46} {_fmt_pos(k['position']):>4}  {k['last_checked'] or 'never'}")
        return "\n".join(lines)
    if action == "trend":
        lines = ["keyword                                        pos   prev  Δ"]
        for t in data["trends"]:
            lines.append(f"{t['keyword'][:44]:<46} {_fmt_pos(t['position']):>4}  "
                         f"{_fmt_pos(t.get('previous')):>4}  {_fmt_delta(t['delta']):>3}")
        return "\n".join(lines)
    if action == "history":
        lines = [f"history: {data['keyword']}"]
        for s in data["snapshots"]:
            lines.append(f"  {s['checked_at']}  #{_fmt_pos(s['position']):>4}  {s['url']}")
        return "\n".join(lines) or "no snapshots"
    return json.dumps(data, ensure_ascii=False, indent=2)


def main():
    p = argparse.ArgumentParser(
        prog="zens_ink.rank_tracker",
        description="SQLite-backed keyword rank tracking (add / check / status / trend / history / remove).")
    sub = p.add_subparsers(dest="action", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="JSON output")

    sp = sub.add_parser("add", help="Track keywords (comma-separated)", parents=[common])
    sp.add_argument("keywords")
    sp.add_argument("--domain", default="", help="Your domain, e.g. example.com")
    sp.add_argument("--tag", default="", help="Optional tag/group")

    sp = sub.add_parser("remove", parents=[common], help="Stop tracking a keyword")
    sp.add_argument("keywords")

    sp = sub.add_parser("check", parents=[common], help="Fetch current positions and snapshot")
    sp.add_argument("--gl", default="us")
    sp.add_argument("--hl", default="en")
    sp.add_argument("--num", type=int, default=20, help="SERP depth per keyword (default 20)")

    sub.add_parser("status", parents=[common], help="Latest known position per keyword")

    sp = sub.add_parser("trend", parents=[common], help="Latest vs previous snapshot")
    sp.add_argument("--limit", type=int, default=2)

    sp = sub.add_parser("history", parents=[common], help="Snapshot history for one keyword")
    sp.add_argument("keywords")
    sp.add_argument("--limit", type=int, default=20)

    args = p.parse_args()

    fn = {"add": act_add, "remove": act_remove, "check": act_check,
          "status": act_status, "trend": act_trend, "history": act_history}[args.action]
    data = fn(args)

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(render(data, args.action))


if __name__ == "__main__":
    main()
