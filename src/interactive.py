# 文件名: interactive.py
# 用途: 实时操控会话 —— 包装战斗引擎，支持逐批推进 tick 并接收手动指令
"""实时操控会话

网页端以固定节奏请求推进若干 tick，并附带键盘指令（控制模式/移动方向/攻击意图）。
所有命中、伤害与体力判定仍由 BattleEngine 完成，本模块只负责会话管理、
指令落地与事件增量导出，事件格式与回放导出完全一致。
"""

import secrets
import threading
import time
from datetime import datetime
from typing import Optional

from src.battle_engine import BattleEngine, BattleResult
from src.constants import BACKSWING_BAR, WINDUP_BAR
from src.enums import AttackPhase
from src.event_exporter import (
    build_battle_summary,
    build_event,
    snapshot_state,
    snapshot_warrior,
)
from src.warrior import WarriorSnapshot

# 单批推进的 tick 上限：约 3 秒游戏时间，防止请求异常时引擎空转
MAX_STEP_TICKS = 60


class BattleSession:
    """一场可交互的实时战斗：持有引擎实例，按需推进并吐出增量事件"""

    def __init__(
        self,
        engine: BattleEngine,
        snapshot_a: WarriorSnapshot,
        snapshot_b: WarriorSnapshot,
        seed: Optional[int] = None,
        backdrop: Optional[dict] = None,
    ):
        self.engine = engine
        self.snapshots = {"A": snapshot_a, "B": snapshot_b}
        self.side_by_name = {snapshot_a.name: "A", snapshot_b.name: "B"}
        self.seed = seed
        self.backdrop = backdrop
        self.log_cursor = 0
        self.previous_state = self._initial_state()
        self.finished = False
        self.result: Optional[BattleResult] = None
        self.last_access = time.monotonic()
        engine.begin()

    def _initial_state(self) -> dict:
        state = {
            side: snapshot_state(snapshot, side)
            for side, snapshot in self.snapshots.items()
        }
        if self.engine.battle_map is not None:
            for side in ("A", "B"):
                state[side]["position"] = list(self.engine.battle_map.spawn_point(side))
        return state

    def initial_document(self) -> dict:
        """会话创建时返回的文档骨架：武将/地图/开场事件，供网页初始化场景"""
        battle_map = self.engine.battle_map
        document = {
            "meta": {
                "version": 2 if battle_map is not None else 1,
                "generatedAt": datetime.now().isoformat(timespec="seconds"),
                "seed": self.seed,
                "source": "src.battle_engine",
                "live": True,
            },
            "warriors": {
                side: snapshot_warrior(
                    snapshot, side, with_reach=battle_map is not None
                )
                for side, snapshot in self.snapshots.items()
            },
            "events": self._collect_events(),
        }
        if battle_map is not None:
            document["map"] = battle_map.to_dict()
            if self.backdrop:
                document["map"]["backdrop"] = self.backdrop
        return document

    def apply_commands(self, commands: dict) -> None:
        """落地网页指令：mode 切换控制模式，move 为持续方向，attack 为一次性意图"""
        for side, team in (("A", self.engine.team_a), ("B", self.engine.team_b)):
            command = commands.get(side) or {}
            warrior = team[0]
            override = self.engine.overrides.setdefault(
                warrior.name, {"mode": "auto", "move": None, "attack": False}
            )
            mode = command.get("mode")
            if mode in ("auto", "manual"):
                override["mode"] = mode
            move = command.get("move")
            if move is None:
                override["move"] = None
            else:
                dx = max(-1, min(1, int(move[0])))
                dy = max(-1, min(1, int(move[1])))
                override["move"] = (dx, dy) if (dx or dy) else None
            if command.get("attack"):
                override["attack"] = True

    def step(self, ticks: int, commands: Optional[dict] = None) -> dict:
        """推进至多 ticks 个时间刻度，返回增量事件与最新状态"""
        self.last_access = time.monotonic()
        if commands:
            self.apply_commands(commands)
        ticks = max(1, min(int(ticks), MAX_STEP_TICKS))
        if not self.finished:
            for _ in range(ticks):
                result = self.engine.run_tick()
                if result:
                    self.engine._record_final_leadership()
                    result.battle_map = self.engine.battle_map
                    self.result = result
                    self.finished = True
                    break
        response = {
            "events": self._collect_events(),
            "state": self._live_state(),
            "tick": self.engine.tick_count,
            "round": max(1, self.engine.round_count),
            "finished": self.finished,
        }
        if self.finished:
            response["battle"] = build_battle_summary(
                self.result,
                {side: snapshot.name for side, snapshot in self.snapshots.items()},
            )
        return response

    def _collect_events(self) -> list:
        events = []
        logs = self.engine.logs
        while self.log_cursor < len(logs):
            event, self.previous_state = build_event(
                logs[self.log_cursor],
                self.log_cursor,
                self.previous_state,
                self.side_by_name,
            )
            events.append(event)
            self.log_cursor += 1
        return events

    def _live_state(self) -> dict:
        """最新状态快照：附带蓄力进度，供网页显示手动攻击时机"""
        state = {}
        for side, team in (("A", self.engine.team_a), ("B", self.engine.team_b)):
            warrior = team[0]
            entry = {
                "name": warrior.name,
                "hp": round(warrior.hp, 2),
                "sp": round(warrior.sp, 2),
                "courage": warrior.courage,
                "alive": warrior.is_alive,
            }
            if warrior.position is not None:
                entry["position"] = list(warrior.position)
                entry["moving"] = warrior.is_moving
            if warrior.attack_phase == AttackPhase.BACKSWING:
                bar = BACKSWING_BAR + warrior.backswing_extra
                percent = min(1.0, warrior.ap / bar) if bar > 0 else 1.0
                phase = "backswing"
                ready = False
            else:
                percent = min(1.0, warrior.ap / WINDUP_BAR)
                phase = "windup"
                target = self.engine._find_target(warrior)
                ready = warrior.can_attack() and (
                    self.engine.battle_map is None
                    or (target is not None and self.engine._can_reach(warrior, target))
                )
            entry["ap"] = {
                "percent": round(percent, 3),
                "phase": phase,
                "ready": bool(ready),
            }
            state[side] = entry
        return state


class SessionStore:
    """会话注册表：线程安全，按最后访问时间淘汰过期会话"""

    TTL_SECONDS = 1800
    LIMIT = 32

    def __init__(self):
        self._sessions: dict = {}
        self._lock = threading.Lock()

    def create(self, session: BattleSession) -> str:
        with self._lock:
            self._evict()
            session_id = secrets.token_hex(8)
            self._sessions[session_id] = session
            return session_id

    def step(self, session_id: str, ticks: int, commands: Optional[dict]) -> Optional[dict]:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            return session.step(ticks, commands)

    def close(self, session_id: str) -> bool:
        with self._lock:
            return self._sessions.pop(session_id, None) is not None

    def _evict(self) -> None:
        now = time.monotonic()
        expired = [
            key
            for key, session in self._sessions.items()
            if now - session.last_access > self.TTL_SECONDS
        ]
        for key in expired:
            del self._sessions[key]
        while len(self._sessions) >= self.LIMIT:
            oldest = min(
                self._sessions, key=lambda key: self._sessions[key].last_access
            )
            del self._sessions[oldest]