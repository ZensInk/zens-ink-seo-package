#!/usr/bin/env python3
"""
Search Intent — classify keywords by search intent.

Four standard categories:
  - informational: user wants to learn/know
  - commercial: user is comparing/researching options
  - transactional: user is ready to act (buy/sign up/download)
  - navigational: user is looking for a specific site/page

Special flags layered on top:
  - question: who/what/when/where/why/how patterns
  - buyer: purchase-intent modifiers (buy/price/deal/order)
  - problem: pain-point modifiers (fix/error/problem/solve)

Works for both English and Chinese keywords. Pure stdlib, no API calls.

Usage:
  python3 -m zens_ink_pro.search_intent --file keywords.txt
  python3 -m zens_ink_pro.search_intent --file keywords.txt --json
  python3 -m zens_ink_pro.search_intent "best ai tools" "what is seo" "buy backlinks"
  cat keywords.txt | python3 -m zens_ink_pro.search_intent --stdin
"""

import argparse
import json
import re
import sys
from pathlib import Path

# ── Intent Patterns ────────────────────────────────────────

# Ordered by priority — first match wins within each keyword
_INTENT_RULES = [
    # ── Transactional ──
    ("transactional", [
        # EN
        r"\b(buy|purchase|order|shop|deals?|discount|coupon|sale|sign\s?up|subscribe|download|free\s?trial|hire|get|pricing|plans?|checkout)\b",
        # ZH
        r"(购买|买|订购|下单|优惠|折扣|优惠券|促销|降价|注册|订阅|下载|免费试用|雇佣|开通|充值|付款|价格表|套餐)",
    ]),
    # ── Commercial ──
    ("commercial", [
        r"\b(best|top|review|reviews|comparison|compare|vs|versus|alternative|alternatives|cheap|affordable|cheapest|recommended|ranking|rated)\b",
        r"(最好|最佳|最强|推荐|评测|测评|评价|口碑|对比|比较|区别|差异|替代|平替|便宜|性价比|排行|排名|榜单|哪个好)",
    ]),
    # ── Navigational ──
    ("navigational", [
        r"\b(login|log\s?in|sign\s?in|official\s?(site|website)|dashboard|account|portal)\b",
        r"(登录|登陆|官网|官方|后台|账号|个人中心)",
    ]),
    # ── Informational ──
    ("informational", [
        r"\b(what\s+is|what\s+are|how\s+(to|do|does|can)|why|when|who|where|guide|tutorial|explained|basics|introduction|learn|examples?|meaning|definition|types?\s+of|difference\s+between|examples?\s+of|ideas?|tips?|checklist)\b",
        r"(什么是|什么意思|怎么|如何|为什么|何时|什么时候|谁|哪里|在哪|教程|入门|指南|详解|基础|科普|学习|案例|例子|含义|定义|类型|区别|方法|技巧|清单|攻略|百科)",
    ]),
]

# Compile patterns once
_COMPILED = []
for intent, patterns in _INTENT_RULES:
    compiled = [re.compile(p, re.IGNORECASE) for p in patterns]
    _COMPILED.append((intent, compiled))

# ── Special Flag Patterns ──────────────────────────────────

_QUESTION_PATTERNS = [
    re.compile(r"^(what|why|when|where|who|how|which|can|do|does|is|are|should|will)\b", re.IGNORECASE),
    re.compile(r"\b(what|why|when|where|who|how|which)\b.{0,5}\?$", re.IGNORECASE),
    re.compile(r"(什么是|什么意思|怎么|如何|为什么|何时|什么时候|谁|哪里|在哪|怎么办|是不是|能不能|好不好|多少)"),
]

_BUYER_PATTERNS = [
    re.compile(r"\b(buy|purchase|price|pricing|cost|deal|discount|cheap|affordable|order|shop|sale|coupon|subscription|plans?)\b", re.IGNORECASE),
    re.compile(r"(购买|买|价格|多少钱|费用|优惠|折扣|便宜|性价比|套餐|收费|报价|成本)"),
]

_PROBLEM_PATTERNS = [
    re.compile(r"\b(fix|error|problem|issue|solve|troubleshoot|repair|broken|not\s+working|stuck|fail|crash|bug|debug|resolve)\b", re.IGNORECASE),
    re.compile(r"(修复|解决|错误|报错|问题|故障|无法|不能|失败|崩溃|bug|排错|异常|不工作|卡住)"),
]


def _check_flags(patterns, text):
    """Return True if any pattern matches."""
    return any(p.search(text) for p in patterns)


def classify(keyword: str) -> dict:
    """Classify a single keyword.

    Returns:
        {
            "keyword": str,
            "intent": "informational" | "commercial" | "transactional" | "navigational",
            "confidence": float (0-1),
            "content_type": str (recommended page type),
            "flags": list of "question" | "buyer" | "problem",
        }
    """
    kw_lower = keyword.lower().strip()

    # Determine intent — first match wins
    matched_intent = "informational"  # default
    confidence = 0.5

    for intent, compiled_list in _COMPILED:
        for pat in compiled_list:
            if pat.search(kw_lower):
                matched_intent = intent
                confidence = 0.85
                break
        if confidence > 0.5:
            break

    # Boost confidence if multiple signals agree
    match_count = 0
    for _, compiled_list in _COMPILED:
        for pat in compiled_list:
            if pat.search(kw_lower):
                match_count += 1
                break
    if match_count > 1:
        confidence = min(0.95, confidence + 0.1)

    # Special flags
    flags = []
    if _check_flags(_QUESTION_PATTERNS, kw_lower):
        flags.append("question")
    if _check_flags(_BUYER_PATTERNS, kw_lower):
        flags.append("buyer")
    if _check_flags(_PROBLEM_PATTERNS, kw_lower):
        flags.append("problem")

    # Recommended content type based on intent + flags
    content_type = _recommend_content_type(matched_intent, flags, kw_lower)

    return {
        "keyword": keyword,
        "intent": matched_intent,
        "confidence": round(confidence, 2),
        "content_type": content_type,
        "flags": flags,
    }


_CONTENT_TYPE_MAP = {
    "informational": "Guide / blog post",
    "commercial": "Comparison / listicle / review",
    "transactional": "Product / pricing / landing page",
    "navigational": "Existing page (optimize for brand)",
}


def _recommend_content_type(intent: str, flags: list, kw: str) -> str:
    """Recommend a page type from intent + flags."""
    if "problem" in flags:
        return "Troubleshooting guide / FAQ"
    if "question" in flags and intent == "informational":
        return "BLUF guide (answer first, then elaborate)"
    if "vs" in kw or "比较" in kw or "对比" in kw or "versus" in kw:
        return "Side-by-side comparison table"
    if "best" in kw or "top" in kw or "推荐" in kw or "排行" in kw:
        return "Ranked list / top-N listicle"
    return _CONTENT_TYPE_MAP.get(intent, "Article / blog post")


def classify_batch(keywords: list[str]) -> list[dict]:
    """Classify a batch of keywords."""
    return [classify(kw) for kw in keywords]


def intent_summary(results: list[dict]) -> dict:
    """Summarize classification results."""
    total = len(results)
    if total == 0:
        return {"total": 0}

    counts = {}
    flag_counts = {}
    for r in results:
        i = r["intent"]
        counts[i] = counts.get(i, 0) + 1
        for f in r.get("flags", []):
            flag_counts[f] = flag_counts.get(f, 0) + 1

    return {
        "total": total,
        "by_intent": {k: v for k, v in sorted(counts.items(), key=lambda x: -x[1])},
        "by_flag": dict(sorted(flag_counts.items(), key=lambda x: -x[1])),
        "pct": {k: round(v / total * 100) for k, v in counts.items()},
    }


def render_report(results: list[dict]) -> str:
    """Render a human-readable text report."""
    summary = intent_summary(results)
    lines = [
        "=" * 60,
        "  Search Intent Analysis",
        "=" * 60,
        "",
        f"  Total keywords: {summary['total']}",
        "",
        "  By Intent:",
    ]
    for intent, count in summary.get("by_intent", {}).items():
        pct = summary["pct"].get(intent, 0)
        bar = "#" * (pct // 5)
        lines.append(f"    {intent:15s} {count:4d}  ({pct:2d}%)  {bar}")
    lines.append("")

    if summary.get("by_flag"):
        lines.append("  Special Flags:")
        for flag, count in summary["by_flag"].items():
            lines.append(f"    {flag:15s} {count:4d}")
        lines.append("")

    # Group by intent
    by_intent = {}
    for r in results:
        by_intent.setdefault(r["intent"], []).append(r)

    for intent in ["transactional", "commercial", "informational", "navigational"]:
        items = by_intent.get(intent, [])
        if not items:
            continue
        lines.append(f"  ── {intent.upper()} ({len(items)}) ──")
        for r in items[:15]:
            flags_str = f"  [{', '.join(r['flags'])}]" if r["flags"] else ""
            lines.append(f"    {r['keyword']}{flags_str}")
        if len(items) > 15:
            lines.append(f"    ... and {len(items) - 15} more")
        lines.append("")

    return "\n".join(lines)


# ── CLI ────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="Classify keywords by search intent")
    p.add_argument("keywords", nargs="*", help="Keywords to classify")
    p.add_argument("--file", "-f", help="File with one keyword per line")
    p.add_argument("--stdin", action="store_true", help="Read keywords from stdin")
    p.add_argument("--json", action="store_true", help="Output as JSON")
    p.add_argument("--output", "-o", help="Write to file instead of stdout")
    args = p.parse_args()

    # Gather keywords
    keywords = list(args.keywords)
    if args.file:
        keywords.extend(Path(args.file).read_text(encoding="utf-8-sig").splitlines())
    if args.stdin:
        keywords.extend(sys.stdin.read().splitlines())
    keywords = [k.strip() for k in keywords if k.strip()]

    if not keywords:
        p.error("No keywords provided. Use --file, --stdin, or pass keywords directly.")

    results = classify_batch(keywords)

    if args.json:
        output = json.dumps(
            {"results": results, "summary": intent_summary(results)},
            ensure_ascii=False, indent=2,
        )
    else:
        output = render_report(results)

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"Written to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
