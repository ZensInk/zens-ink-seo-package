#!/usr/bin/env python3
"""
Keyword Cluster — group raw keywords into semantic topic clusters.

Takes a flat list of keywords (from discovery, CSV, or stdin) and groups
them by shared meaning using token-level similarity. Works for both
English and Chinese keywords.

Algorithm:
  1. Detect language per keyword (CJK vs Latin)
  2. Tokenize (English: words with stopword removal; Chinese: char bigrams)
  3. Compute pairwise Jaccard similarity on token sets
  4. Union-find clustering with configurable threshold
  5. Label each cluster by its most frequent shared tokens

Usage:
  python3 -m zens_ink_pro.keyword_cluster keywords.txt
  python3 -m zens_ink_pro.keyword_cluster --file keywords.txt --threshold 0.25
  python3 -m zens_ink_pro.keyword_cluster "tarot meaning" "tarot card meanings" "dream interpretation"
  cat keywords.csv | python3 -m zens_ink_pro.keyword_cluster --stdin
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

# ── Stopwords ──────────────────────────────────────────────

EN_STOPWORDS = frozenset(
    "a an the of for to in on at by with from as is are was were be been "
    "being do does did done have has had having what how why when where "
    "which who whom whose that this these those it its their there here "
    "can could should would will may might must shall about into over under "
    "again more most some such no nor not only own same so than too very "
    "can will just don should now i you he she we they me him her us them "
    "my your his our their mine yours hers ours theirs and or but if then "
    "else up down out off all any each few many other some such".split()
)

CJK_PATTERN = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")


# ── Tokenization ───────────────────────────────────────────

def is_chinese(text: str) -> bool:
    return bool(CJK_PATTERN.search(text))


def tokenize(keyword: str) -> set[str]:
    """Extract significant tokens from a keyword."""
    kw = keyword.strip().lower()
    if is_chinese(kw):
        # Chinese: use character bigrams + first-2-chars prefix for grouping
        chars = CJK_PATTERN.findall(kw)
        tokens = set()
        for i in range(len(chars) - 1):
            tokens.add(chars[i] + chars[i + 1])
        # First 2 chars as prefix token (strong topic signal in Chinese SEO)
        if len(chars) >= 2:
            tokens.add("__pfx_" + chars[0] + chars[1])
        # For short keywords, use the whole thing
        if not tokens and chars:
            tokens.add("".join(chars))
        return tokens
    else:
        # English/Latin: split on non-alphanumeric
        words = re.findall(r"[a-z0-9]+", kw)
        return {w for w in words if w not in EN_STOPWORDS and len(w) > 1}


# ── Similarity & Clustering ────────────────────────────────

def jaccard(a: set[str], b: set[str]) -> float:
    """Plain Jaccard similarity (fallback, not used in main path)."""
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def compute_idf(keywords_tokens: list[set[str]]) -> dict[str, float]:
    """Compute Inverse Document Frequency for each token."""
    import math
    n = len(keywords_tokens)
    if n == 0:
        return {}
    df: dict[str, int] = {}
    for tokens in keywords_tokens:
        for t in tokens:
            df[t] = df.get(t, 0) + 1
    # IDF: tokens in many keywords → low weight (e.g. "meaning", "reading")
    return {t: math.log(n / d) for t, d in df.items()}


def weighted_jaccard(a: set[str], b: set[str],
                     idf: dict[str, float]) -> float:
    """
    Blended similarity: 50% plain Jaccard + 50% IDF-weighted Jaccard.
    Plain Jaccard captures topic words shared across keywords.
    IDF-weighted upweights rare tokens to prevent over-grouping.
    Chinese prefix tokens (__pfx_*) get boosted weight.
    """
    if not a or not b:
        return 0.0
    inter = a & b
    union = a | b
    if not union:
        return 0.0

    # Plain Jaccard
    plain = len(inter) / len(union)

    # IDF-weighted Jaccard
    def token_weight(t):
        w = idf.get(t, 1.0)
        return w * (3.0 if t.startswith("__pfx_") else 1.0)

    inter_weight = sum(token_weight(t) for t in inter)
    union_weight = sum(token_weight(t) for t in union)
    weighted = inter_weight / union_weight if union_weight else 0.0

    return 0.6 * plain + 0.4 * weighted


class UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))
        self.rank = [0] * n

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, x: int, y: int):
        rx, ry = self.find(x), self.find(y)
        if rx == ry:
            return
        if self.rank[rx] < self.rank[ry]:
            rx, ry = ry, rx
        self.parent[ry] = rx
        if self.rank[rx] == self.rank[ry]:
            self.rank[rx] += 1


def cluster(keywords: list[str], threshold: float = 0.15) -> list[dict]:
    """
    Cluster keywords by token similarity using greedy centroid assignment.
    Prevents single-link chaining (A~B, B~C → A,C merged even if dissimilar).
    Each keyword joins the cluster with highest centroid similarity, or forms
    a new one if below threshold.
    Returns list of cluster dicts: {label, members, size, language}
    """
    n = len(keywords)
    if n == 0:
        return []

    tokens = [tokenize(kw) for kw in keywords]
    idf = compute_idf(tokens)

    # Greedy centroid-based clustering
    clusters: list[dict] = []  # each: {indices, token_sum, token_count}

    for i in range(n):
        best_cluster = -1
        best_score = 0.0

        for ci, c in enumerate(clusters):
            # Centroid = weighted average of cluster's tokens
            # Similarity = weighted_jaccard(keyword_tokens, centroid_tokens)
            # Approximate centroid by union of member tokens weighted by frequency
            inter_weight = sum(
                idf.get(t, 1.0) * (3.0 if t.startswith("__pfx_") else 1.0)
                for t in tokens[i] & c["token_set"]
            )
            union_weight = sum(
                idf.get(t, 1.0) * (3.0 if t.startswith("__pfx_") else 1.0)
                for t in tokens[i] | c["token_set"]
            ) or 1.0
            score = inter_weight / union_weight
            # Blend with plain jaccard against centroid
            plain_inter = len(tokens[i] & c["token_set"])
            plain_union = len(tokens[i] | c["token_set"]) or 1
            plain_score = plain_inter / plain_union
            score = 0.6 * plain_score + 0.4 * score

            if score > best_score:
                best_score = score
                best_cluster = ci

        if best_cluster >= 0 and best_score >= threshold:
            clusters[best_cluster]["indices"].append(i)
            clusters[best_cluster]["token_set"] |= tokens[i]
        else:
            clusters.append({"indices": [i], "token_set": set(tokens[i])})

    # Build cluster objects
    results = []
    for c in clusters:
        indices = c["indices"]
        members = [keywords[i] for i in indices]
        # Find the most common tokens across cluster members
        token_counter: Counter = Counter()
        for i in indices:
            for t in tokens[i]:
                token_counter[t] += 1

        # Label: top 1-3 most frequent tokens (hide internal prefix markers)
        top_tokens = [t.replace("__pfx_", "") if t.startswith("__pfx_") else t
                      for t, _ in token_counter.most_common(3)
                      if not t.startswith("__pfx_")]
        # Include prefix token as label if present
        if not top_tokens:
            top_tokens = [t.replace("__pfx_", "") for t, _ in token_counter.most_common(3)]
        label = " ".join(top_tokens) if top_tokens else members[0]

        lang = "zh" if is_chinese(members[0]) else "en"

        results.append({
            "label": label,
            "members": sorted(members),
            "size": len(members),
            "language": lang,
            "top_tokens": top_tokens,
        })

    # Sort by size descending
    results.sort(key=lambda c: c["size"], reverse=True)
    return results


# ── I/O ────────────────────────────────────────────────────

def read_keywords(filepath: str | None = None, stdin: bool = False,
                  args: list[str] | None = None) -> list[str]:
    """Read keywords from file, stdin, or CLI args."""
    keywords = []
    if filepath:
        text = Path(filepath).read_text(encoding="utf-8")
        # Handle CSV (first column) or plain text
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # CSV: take first field
            kw = line.split(",")[0].strip().strip('"')
            if kw:
                keywords.append(kw)
    if stdin:
        for line in sys.stdin:
            kw = line.strip()
            if kw and not kw.startswith("#"):
                keywords.append(kw.split(",")[0].strip().strip('"'))
    if args:
        keywords.extend(args)
    # Deduplicate preserving order
    seen = set()
    return [k for k in keywords if not (k.lower() in seen or seen.add(k.lower()))]


def main():
    p = argparse.ArgumentParser(description="Cluster keywords into semantic topic groups")
    p.add_argument("keywords", nargs="*", help="Keywords (space-separated)")
    p.add_argument("--file", "-f", help="File with keywords (one per line or CSV)")
    p.add_argument("--stdin", action="store_true", help="Read from stdin")
    p.add_argument("--threshold", "-t", type=float, default=0.15,
                   help="Similarity threshold 0-1 (default: 0.15, lower=more grouping)")
    p.add_argument("--min-size", type=int, default=1,
                   help="Minimum cluster size to include (default: 1)")
    p.add_argument("--json", action="store_true", help="JSON output")
    p.add_argument("--csv", help="Export as CSV (cluster_label,keyword)")
    args = p.parse_args()

    keywords = read_keywords(args.file, args.stdin, args.keywords)
    if not keywords:
        p.print_help()
        sys.exit(1)

    clusters = cluster(keywords, args.threshold)
    clusters = [c for c in clusters if c["size"] >= args.min_size]

    if args.json:
        print(json.dumps(clusters, ensure_ascii=False, indent=2))
    else:
        print(f"\n{'='*60}")
        print(f"  Keyword Clustering | {len(keywords)} keywords → {len(clusters)} clusters")
        print(f"  Threshold: {args.threshold}")
        print(f"{'='*60}\n")
        for i, c in enumerate(clusters, 1):
            print(f"  [{i}] {c['label']}  ({c['size']} kw, {c['language']})")
            for m in c["members"][:10]:
                print(f"      {m}")
            if c["size"] > 10:
                print(f"      ... +{c['size'] - 10} more")
            print()

    if args.csv:
        import csv as csvmod
        with open(args.csv, "w", newline="", encoding="utf-8-sig") as f:
            w = csvmod.writer(f)
            w.writerow(["cluster_label", "cluster_size", "keyword", "language"])
            for c in clusters:
                for m in c["members"]:
                    w.writerow([c["label"], c["size"], m, c["language"]])
        print(f"  CSV: {args.csv}")


if __name__ == "__main__":
    main()
