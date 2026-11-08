# 文件名: lead_analysis.py
# 用途: 根据逐回合 HP/SP 领先快照，整理领先变更、最长持续领先与最大领先幅度
"""领先记录分析模块"""

from typing import Dict, List

METRICS = ("hp", "sp")
SIDES = ("A", "B")


def _analyze_metric(history: List[dict], metric: str) -> dict:
    changes = []
    longest = {side: 0 for side in SIDES}
    max_gap = {side: 0.0 for side in SIDES}

    previous_leader = None
    streak_side = None
    streak_rounds = 0

    for entry in history:
        snapshot = entry.get(metric) or {}
        leader = snapshot.get("leader")
        gap = abs(float(snapshot.get("A", 0.0)) - float(snapshot.get("B", 0.0)))

        if leader != previous_leader:
            if leader is not None:
                changes.append({"round": entry["round"], "side": leader})
            previous_leader = leader

        if leader is None:
            streak_side = None
            streak_rounds = 0
        elif leader == streak_side:
            streak_rounds += 1
        else:
            streak_side = leader
            streak_rounds = 1

        if streak_side is not None:
            longest[streak_side] = max(longest[streak_side], streak_rounds)

        if leader is not None:
            max_gap[leader] = max(max_gap[leader], gap)

    return {
        "changes": changes,
        "longest": longest,
        "maxGap": max_gap,
        "rounds": len(history),
    }


def build_lead_records(history: List[dict]) -> Dict[str, dict]:
    """把引擎的逐回合领先快照整理成 HP/SP 两份领先记录"""
    return {metric: _analyze_metric(history, metric) for metric in METRICS}
