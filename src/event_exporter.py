# 文件名: event_exporter.py
# 用途: 把 BattleResult 转换为网页演出可直接消费的结构化 JSON 事件文档
"""战斗事件导出模块

只做“读取与整理”，不参与任何战斗判定：
事件顺序、伤害、体力与胆气变化全部来自战斗引擎写入的日志与状态快照。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from src.battle_engine import BattleResult
from src.battle_statistics import DEFENSE_TYPE_CN
from src.lead_analysis import build_lead_records
from src.warrior import WarriorSnapshot


OUTCOME_CN = {
    "team_a_win": "A队胜利",
    "team_b_win": "B队胜利",
    "draw": "平局",
    "timeout": "超时判定",
}


def _snapshot_warrior(snapshot: WarriorSnapshot, side: str, with_reach: bool = False) -> dict:
    """战前快照 → 网页初始武将数据"""
    weapon = None
    if snapshot.weapon_name:
        weapon = {
            "name": snapshot.weapon_name,
            "category": snapshot.weapon_category,
            "categoryLabel": snapshot.weapon_category_label,
        }
        if with_reach:
            weapon["reach"] = snapshot.reach
    return {
        "name": snapshot.name,
        "team": side,
        "hp": round(snapshot.hp, 2),
        "hpMax": snapshot.hp_real,
        "sp": round(snapshot.sp, 2),
        "spMax": snapshot.sp_real,
        "courage": snapshot.courage,
        "stats": {
            "martialarts": snapshot.martialarts,
            "agility": snapshot.agility,
            "strength": snapshot.strength,
            "courage": snapshot.courage,
            "sp": round(snapshot.sp_real / 50),
        },
        "skills": list(snapshot.skills),
        "weapon": weapon,
    }


def _snapshot_state(snapshot: WarriorSnapshot, side: str) -> dict:
    return {
        "name": snapshot.name,
        "hp": round(snapshot.hp, 2),
        "sp": round(snapshot.sp, 2),
        "courage": snapshot.courage,
        "alive": snapshot.is_alive,
    }


def _state_from_log(log, side_by_name: dict) -> dict:
    """把日志里的全体快照整理成 {A:..., B:...}（1v1 取每队首位武将）"""
    state: dict = {}
    for entry in log.warrior_states:
        side = side_by_name.get(entry["name"])
        if side is None or side in state:
            continue
        state[side] = {
            "name": entry["name"],
            "hp": round(entry["hp"], 2),
            "sp": round(entry["sp"], 2),
            "courage": entry["courage"],
            "alive": entry["alive"],
        }
        if entry.get("position") is not None:
            state[side]["position"] = entry["position"]
    return state


def _effects(before: dict, after: dict) -> dict:
    """按事件前后快照计算实际数值变化"""
    effects: dict = {}
    for side in ("A", "B"):
        prev = before.get(side)
        cur = after.get(side)
        if not prev or not cur:
            continue
        effects[side] = {
            "hp": round(cur["hp"] - prev["hp"], 2),
            "sp": round(cur["sp"] - prev["sp"], 2),
            "courage": cur["courage"] - prev["courage"],
        }
    return effects


def _alive_map(state: dict) -> dict:
    return {side: bool(value.get("alive", True)) for side, value in state.items()}


def _event_text(log, defense_cn: Optional[str]) -> str:
    details = log.details
    if log.event_type == "attack":
        attacker = details.get("attacker", "?")
        defender = details.get("defender", "?")
        success = "成功" if details.get("success") else "失败"
        return f"{attacker} 进攻 → {defender} · {defense_cn or ''}{success}"
    if log.event_type == "clash":
        participants = details.get("participants", [])
        return f"拼刀！{' / '.join(participants)}"
    if log.event_type == "sp_leader_change":
        leader = details.get("leader")
        return f"体力领先 → {leader}队"
    return log.description


def build_battle_document(
    result: BattleResult,
    snapshots_a: List[WarriorSnapshot],
    snapshots_b: List[WarriorSnapshot],
    seed: Optional[int] = None,
) -> dict:
    """构建网页消费的完整战斗文档"""
    snapshot_a = snapshots_a[0]
    snapshot_b = snapshots_b[0]
    side_by_name = {snapshot_a.name: "A", snapshot_b.name: "B"}
    battle_map = result.battle_map

    initial_state = {
        "A": _snapshot_state(snapshot_a, "A"),
        "B": _snapshot_state(snapshot_b, "B"),
    }
    if battle_map is not None:
        initial_state["A"]["position"] = list(battle_map.spawn("A"))
        initial_state["B"]["position"] = list(battle_map.spawn("B"))
    previous = initial_state

    events: list = []
    for index, log in enumerate(result.logs):
        after = _state_from_log(log, side_by_name)
        # battle_start 等事件发生在快照之前时，使用初始状态兜底
        if len(after) < 2:
            after = {**previous, **after}
        if not after:
            after = previous

        details = log.details
        defense_cn = DEFENSE_TYPE_CN.get(details.get("defense", ""), None)
        actor_side = side_by_name.get(details.get("attacker"))
        defender_side = side_by_name.get(details.get("defender"))

        event = {
            "index": index,
            "tick": log.tick,
            "round": max(1, log.round_num),
            "type": log.event_type,
            "text": _event_text(log, defense_cn),
            "effects": _effects(previous, after),
            "alive": _alive_map(after),
            "state": after,
        }

        if log.event_type == "attack":
            event["actor"] = {
                "name": details.get("attacker"),
                "side": actor_side,
            }
            event["defender"] = {
                "name": details.get("defender"),
                "side": defender_side,
            }
            event["defense"] = {
                "type": details.get("defense"),
                "label": defense_cn,
                "success": bool(details.get("success")),
                "rate": round(float(details.get("defense_rate", 0)), 4),
            }
            event["damage"] = {
                "toDefender": round(details.get("damage_to_defender", 0), 2),
                "toAttacker": round(details.get("damage_to_attacker", 0), 2),
            }
        elif log.event_type == "clash":
            event["clash"] = {
                "participants": details.get("participants", []),
                "damages": {k: round(v, 2) for k, v in details.get("damages", {}).items()},
                "spCosts": {k: round(v, 2) for k, v in details.get("sp_costs", {}).items()},
            }
        elif log.event_type == "skill_trigger":
            event["skill"] = {
                "id": details.get("skill_id"),
                "name": details.get("skill"),
                "warrior": details.get("warrior"),
                "amount": details.get("amount"),
                "apBefore": details.get("ap_before"),
                "apAfter": details.get("ap_after"),
            }
        elif log.event_type == "sp_leader_change":
            event["leader"] = details.get("leader")
        elif log.event_type == "move":
            mover = details.get("warrior")
            event["move"] = {
                "warrior": mover,
                "side": side_by_name.get(mover),
                "from": details.get("from"),
                "to": details.get("to"),
            }

        events.append(event)
        previous = after

    outcome_value = result.outcome.value
    lead_records = build_lead_records(result.leader_history)
    side_names = {"A": snapshot_a.name, "B": snapshot_b.name}
    lead_document = {
        metric: {
            "changes": [
                {
                    "round": change["round"],
                    "side": change["side"],
                    "name": side_names[change["side"]],
                }
                for change in section["changes"]
            ],
            "longest": section["longest"],
            "maxGap": section["maxGap"],
            "rounds": section["rounds"],
        }
        for metric, section in lead_records.items()
    }

    document = {
        "meta": {
            "version": 2 if battle_map is not None else 1,
            "generatedAt": datetime.now().isoformat(timespec="seconds"),
            "seed": seed,
            "source": "src.battle_engine",
        },
        "battle": {
            "outcome": outcome_value,
            "outcomeText": OUTCOME_CN.get(outcome_value, outcome_value),
            "winnerSide": result.winner_team,
            "rounds": result.rounds,
            "ticks": result.ticks,
            "spLeaderChanges": [
                {"round": round_num, "side": leader}
                for round_num, leader in result.sp_leader_changes
            ],
            "leadRecords": lead_document,
        },
        "warriors": {
            "A": _snapshot_warrior(snapshot_a, "A", with_reach=battle_map is not None),
            "B": _snapshot_warrior(snapshot_b, "B", with_reach=battle_map is not None),
        },
        "events": events,
    }
    if battle_map is not None:
        document["map"] = battle_map.to_dict()
    return document


def write_battle_json(document: dict, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return path


def write_battle_js(document: dict, path: Path, variable: str = "BATTLE_DATA") -> Path:
    """额外输出 JS 版本，便于直接双击 index.html（file:// 无法 fetch JSON）"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(document, ensure_ascii=False)
    path.write_text(f"window.{variable} = {payload};\n", encoding="utf-8")
    return path
