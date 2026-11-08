# 文件名: seed_history.py
# 用途: 记录最近若干场战斗的随机种子与结果标识，便于复盘与复现
"""战斗种子历史模块

每场战斗保存实际使用的随机种子，并附带回合总数与胜者剩余血量，
既可用种子单独复现某一场战斗，也可凭回合数与剩余血量快速辨认种子。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional, TYPE_CHECKING, Union

if TYPE_CHECKING:
    from src.battle_engine import BattleResult


HISTORY_LIMIT = 100
DEFAULT_HISTORY_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "seed_history.json"
)


@dataclass
class SeedRecord:
    """一场战斗的种子与结果标识"""

    seed: int
    rounds: int
    ticks: int
    outcome: str
    winner_side: Optional[str]
    winner_name: Optional[str]
    winner_hp: Optional[float]
    winner_hp_max: Optional[float]
    winner_hp_percent: Optional[float]
    recorded_at: str = field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds")
    )

    @classmethod
    def from_result(cls, seed: int, result: "BattleResult") -> "SeedRecord":
        """从战斗结果提取种子标识；平局等无胜者的情况字段留空"""
        survivors = []
        if result.winner_team == "A":
            survivors = result.team_a_survivors
        elif result.winner_team == "B":
            survivors = result.team_b_survivors

        if survivors:
            winner_hp = round(sum(w.hp for w in survivors), 2)
            winner_hp_max = round(sum(w.hp_real for w in survivors), 2)
            winner_hp_percent = (
                round(winner_hp / winner_hp_max, 4) if winner_hp_max > 0 else None
            )
            winner_name = "、".join(w.name for w in survivors)
        else:
            winner_hp = None
            winner_hp_max = None
            winner_hp_percent = None
            winner_name = None

        return cls(
            seed=seed,
            rounds=result.rounds,
            ticks=result.ticks,
            outcome=result.outcome.value,
            winner_side=result.winner_team,
            winner_name=winner_name,
            winner_hp=winner_hp,
            winner_hp_max=winner_hp_max,
            winner_hp_percent=winner_hp_percent,
        )

    def to_dict(self) -> dict:
        return {
            "seed": self.seed,
            "rounds": self.rounds,
            "ticks": self.ticks,
            "outcome": self.outcome,
            "winnerSide": self.winner_side,
            "winnerName": self.winner_name,
            "winnerHp": self.winner_hp,
            "winnerHpMax": self.winner_hp_max,
            "winnerHpPercent": self.winner_hp_percent,
            "recordedAt": self.recorded_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SeedRecord":
        return cls(
            seed=int(data["seed"]),
            rounds=int(data["rounds"]),
            ticks=int(data.get("ticks", 0)),
            outcome=str(data.get("outcome", "")),
            winner_side=data.get("winnerSide"),
            winner_name=data.get("winnerName"),
            winner_hp=data.get("winnerHp"),
            winner_hp_max=data.get("winnerHpMax"),
            winner_hp_percent=data.get("winnerHpPercent"),
            recorded_at=str(data.get("recordedAt", "")),
        )


class SeedHistory:
    """滚动保存最近 limit 场战斗的种子记录"""

    def __init__(
        self,
        path: Union[Path, str] = DEFAULT_HISTORY_PATH,
        limit: int = HISTORY_LIMIT,
    ):
        self.path = Path(path)
        self.limit = limit
        self.records: List[SeedRecord] = self._load()

    def _load(self) -> List[SeedRecord]:
        """读取历史文件；文件缺失或损坏时视为空历史"""
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []

        entries = data.get("records", []) if isinstance(data, dict) else data
        if not isinstance(entries, list):
            return []

        records: List[SeedRecord] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            try:
                records.append(SeedRecord.from_dict(entry))
            except (KeyError, TypeError, ValueError):
                continue
        return records[-self.limit :]

    def append(self, record: SeedRecord) -> None:
        """追加一条记录，只保留最近 limit 条"""
        self.records.append(record)
        if len(self.records) > self.limit:
            del self.records[: len(self.records) - self.limit]

    def save(self) -> Path:
        """原子写入历史文件"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        document = {
            "limit": self.limit,
            "updatedAt": datetime.now().isoformat(timespec="seconds"),
            "records": [record.to_dict() for record in self.records],
        }
        temp_path = self.path.with_name(self.path.name + ".tmp")
        temp_path.write_text(
            json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temp_path.replace(self.path)
        return self.path
