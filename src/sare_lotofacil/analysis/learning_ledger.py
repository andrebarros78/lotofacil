from __future__ import annotations

from collections.abc import Mapping
from typing import Any

LEARNING_LEDGER_VERSION = "post-contest-learning-v1"
TARGET_HITS = 15


def build_learning_ledger(reports: Mapping[str, Any]) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    miss_frequency: dict[int, int] = {}
    omitted_frequency: dict[int, int] = {}

    for report in reports.get("reports", []):
        if not isinstance(report, Mapping):
            continue
        hits = report.get("hits")
        if type(hits) is not int:
            continue
        if hits < 0 or hits > TARGET_HITS:
            raise ValueError("LEARNING_LEDGER_HITS_OUT_OF_RANGE")
        selected_misses = [int(x) for x in report.get("selected_misses", [])]
        omitted_winners = [int(x) for x in report.get("omitted_winners", [])]
        for number in selected_misses:
            miss_frequency[number] = miss_frequency.get(number, 0) + 1
        for number in omitted_winners:
            omitted_frequency[number] = omitted_frequency.get(number, 0) + 1
        entries.append({
            "contest_number": int(report["contest_number"]),
            "hits": hits,
            "target_hits": TARGET_HITS,
            "gap_to_15": TARGET_HITS - hits,
            "selected_misses": selected_misses,
            "omitted_winners": omitted_winners,
            "primary_delta_brier_vs_uniform": report.get("primary_delta_brier_vs_uniform"),
            "process_findings": list(report.get("self_analysis", {}).get("process_findings", [])),
            "adjustments_suggested": list(report.get("self_analysis", {}).get("adjustments_suggested", [])),
        })

    entries.sort(key=lambda item: item["contest_number"])
    mean_hits = sum(item["hits"] for item in entries) / len(entries) if entries else None
    best_hits = max((item["hits"] for item in entries), default=None)
    latest = entries[-1] if entries else None
    recurring_misses = sorted(miss_frequency.items(), key=lambda item: (-item[1], item[0]))
    recurring_omissions = sorted(omitted_frequency.items(), key=lambda item: (-item[1], item[0]))

    return {
        "schema_version": 1,
        "learning_ledger_version": LEARNING_LEDGER_VERSION,
        "objective": {"metric": "hits_on_frozen_15_number_card", "target": TARGET_HITS},
        "entries": entries,
        "entry_count": len(entries),
        "latest_entry": latest,
        "summary": {
            "mean_hits": mean_hits,
            "best_hits": best_hits,
            "latest_gap_to_15": latest["gap_to_15"] if latest else None,
            "selected_miss_frequency": [{"number": n, "count": c} for n, c in recurring_misses],
            "omitted_winner_frequency": [{"number": n, "count": c} for n, c in recurring_omissions],
        },
        "learning_policy": {
            "report_is_learning_input": True,
            "single_contest_retuning_allowed": False,
            "retroactive_rewrite_allowed": False,
            "champion_auto_promotion_allowed": False,
            "challenger_requires_predeclared_prospective_validation": True,
        },
    }
