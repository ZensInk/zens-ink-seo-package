#!/usr/bin/env python3
"""
Content Matrix — generate a prioritized content opportunity matrix.

Takes scored keywords (from kgr_auto CSV/JSON) or clustered keywords
(from keyword_cluster), and produces a structured content plan:
topics ranked by opportunity, grouped into actionable content buckets.

This is the decision layer: turns raw data into "what to write first."

Usage:
  python3 -m zens_ink_pro.content_matrix --scores kgr_results.csv
  python3 -m zens_ink_pro.content_matrix --scores kgr_results.json --clusters clusters.json
  python3 -m zens_ink_pro.content_matrix --scores kgr_results.csv --csv matrix.csv
"""

import argparse
import csv
import json
import sys
from pathlib import Path

# ── Data Loading ───────────────────────────────────────────

def load_scores(filepath: str) -> list[dict]:
    """Load scored keywords from JSON or CSV."""
    path = Path(filepath)
    text = path.read_text(encoding="utf-8")

    if path.suffix == ".json":
        data = json.loads(text)
        if isinstance(data, dict) and "results" in data:
            data = data["results"]
        return data

    # CSV
    results = []
    with open(filepath, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Normalize numeric fields
            for key in ("opportunity_score", "competition_score", "volume_score"):
                if key in row:
                    try:
                        row[key] = float(row[key])
                    except (ValueError, TypeError):
                        row[key] = 0.0
            for key in ("avg_weekly_volume", "quarterly_volume", "autocomplete_count"):
                if key in row:
                    try:
                        row[key] = int(row[key])
                    except (ValueError, TypeError):
                        row[key] = 0
            results.append(row)
    return results


def load_clusters(filepath: str) -> list[dict]:
    """Load cluster data from JSON."""
    return json.loads(Path(filepath).read_text(encoding="utf-8"))


# ── Matrix Generation ──────────────────────────────────────

def generate_matrix(scores: list[dict],
                    clusters: list[dict] | None = None) -> dict:
    """
    Build a structured content opportunity matrix.
    Returns: {buckets, clusters, summary}
    """
    # Sort by opportunity score descending
    ranked = sorted(scores, key=lambda r: r.get("opportunity_score", 0), reverse=True)

    # ── Priority buckets ──
    buckets = {
        "P0_strike_now": [],
        "P1_do_soon": [],
        "P2_nice_to_have": [],
        "P3_skip": [],
    }

    tier_map = {"P0": "P0_strike_now", "P1": "P1_do_soon",
                "P2": "P2_nice_to_have", "P3": "P3_skip"}

    for r in ranked:
        tier = r.get("priority", "P3")
        bucket = tier_map.get(tier, "P3_skip")
        buckets[bucket].append(r)

    # ── Cluster-level aggregation ──
    cluster_summary = []
    if clusters:
        # Map keywords to clusters
        kw_to_cluster = {}
        for c in clusters:
            for m in c["members"]:
                kw_to_cluster[m.lower()] = c

        cluster_scores: dict[str, list[float]] = {}
        for r in ranked:
            kw = r["keyword"].lower()
            c = kw_to_cluster.get(kw)
            if c:
                cluster_scores.setdefault(c["label"], []).append(
                    r.get("opportunity_score", 0))

        for label, opps in cluster_scores.items():
            cluster_summary.append({
                "cluster": label,
                "keyword_count": len(opps),
                "avg_opportunity": round(sum(opps) / len(opps), 1),
                "max_opportunity": round(max(opps), 1),
            })
        cluster_summary.sort(key=lambda c: c["avg_opportunity"], reverse=True)

    # ── Summary stats ──
    total = len(ranked)
    has_vol = sum(1 for r in ranked if r.get("avg_weekly_volume", 0) > 0)
    total_vol = sum(r.get("avg_weekly_volume", 0) for r in ranked)

    summary = {
        "total_keywords": total,
        "keywords_with_volume": has_vol,
        "total_weekly_volume": total_vol,
        "p0_count": len(buckets["P0_strike_now"]),
        "p1_count": len(buckets["P1_do_soon"]),
        "p2_count": len(buckets["P2_nice_to_have"]),
        "p3_count": len(buckets["P3_skip"]),
    }

    return {
        "buckets": buckets,
        "clusters": cluster_summary,
        "summary": summary,
        "ranked": ranked,
    }


def render_report(matrix: dict) -> str:
    """Render human-readable markdown report."""
    s = matrix["summary"]
    lines = [
        f"\n{'='*70}",
        f"  Content Opportunity Matrix",
        f"{'='*70}",
        f"\n  Keywords analyzed : {s['total_keywords']}",
        f"  With volume data  : {s['keywords_with_volume']}",
        f"  Total weekly vol  : {s['total_weekly_volume']:,}",
        f"\n  Priority Distribution:",
        f"    P0 (strike now)  : {s['p0_count']}",
        f"    P1 (do soon)     : {s['p1_count']}",
        f"    P2 (nice to have): {s['p2_count']}",
        f"    P3 (skip)        : {s['p3_count']}",
    ]

    for bucket_name, label in [
        ("P0_strike_now", "P0 — Strike Now"),
        ("P1_do_soon", "P1 — Do Soon"),
        ("P2_nice_to_have", "P2 — Nice to Have"),
    ]:
        items = matrix["buckets"][bucket_name]
        if not items:
            continue
        lines.append(f"\n  ── {label} ({len(items)} keywords) ──")
        for r in items[:15]:
            vol = r.get("avg_weekly_volume", 0)
            opp = r.get("opportunity_score", 0)
            trend = r.get("trend", "?")
            lines.append(f"    {r['keyword']:35s}  vol={vol:5d}  opp={opp:5.1f}  {trend}")
        if len(items) > 15:
            lines.append(f"    ... +{len(items) - 15} more")

    if matrix["clusters"]:
        lines.append(f"\n  ── Cluster Opportunities ──")
        for c in matrix["clusters"][:10]:
            lines.append(f"    {c['cluster']:30s}  {c['keyword_count']:3d} kw  "
                         f"avg_opp={c['avg_opportunity']:5.1f}")

    return "\n".join(lines)


def export_csv(matrix: dict, filepath: str):
    """Export ranked keywords to CSV."""
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["rank", "keyword", "priority", "opportunity_score",
                    "avg_weekly_volume", "trend", "competition_score"])
        for i, r in enumerate(matrix["ranked"], 1):
            w.writerow([
                i, r.get("keyword", ""), r.get("priority", ""),
                r.get("opportunity_score", 0), r.get("avg_weekly_volume", 0),
                r.get("trend", ""), r.get("competition_score", 0),
            ])


def main():
    p = argparse.ArgumentParser(description="Generate prioritized content opportunity matrix")
    p.add_argument("--scores", "-s", required=True,
                   help="Scored keywords (CSV or JSON from kgr_auto)")
    p.add_argument("--clusters", "-c", help="Cluster data (JSON from keyword_cluster)")
    p.add_argument("--csv", help="Export ranked matrix to CSV")
    p.add_argument("--json", action="store_true", help="JSON output")
    args = p.parse_args()

    scores = load_scores(args.scores)
    clusters = load_clusters(args.clusters) if args.clusters else None

    matrix = generate_matrix(scores, clusters)

    if args.json:
        # Serialize buckets (lists of dicts are JSON-safe)
        print(json.dumps(matrix, ensure_ascii=False, indent=2, default=str))
    else:
        print(render_report(matrix))

    if args.csv:
        export_csv(matrix, args.csv)
        print(f"\n  CSV: {args.csv}")


if __name__ == "__main__":
    main()
