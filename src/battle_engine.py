# 文件名: battle_engine.py
# 用途: 战斗引擎核心模块，负责管理战斗流程、回合控制、攻击判定和战斗结果输出
"""武将对决系统的战斗引擎"""

import math
from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum

from src.constants import (
    MAX_ROUNDS,
    MAX_TICKS,
    TICK_RATE,
    UNIT_RADIUS,
    UNIT_SEPARATION,
    WHIFF_SP_COST_RATIO,
)
from src.map import BattleMap, cell_at, cell_center, chebyshev_distance
from src.warrior import Warrior
from src.defense import process_defense
from src.damage import calculate_final_damage
from src.clash import check_clash_condition, process_clash


class BattleOutcome(Enum):
    """可能的战斗结果"""

    TEAM_A_WIN = "team_a_win"  # A队胜利
    TEAM_B_WIN = "team_b_win"  # B队胜利
    DRAW = "draw"  # 平局
    TIMEOUT = "timeout"  # 超时


@dataclass
class BattleLog:
    """战斗事件日志条目"""

    tick: int  # 时间刻度
    round_num: int  # 回合数
    event_type: str  # 事件类型
    description: str  # 事件描述
    details: dict = field(default_factory=dict)  # 详细信息
    warrior_states: list = field(default_factory=list)  # 事件发生后的全体武将状态快照


@dataclass
class BattleResult:
    """战斗最终结果"""

    outcome: BattleOutcome  # 战斗结果
    winner_team: Optional[str]  # 获胜队伍
    rounds: int  # 总回合数
    ticks: int  # 总时间刻度数
    team_a_survivors: List[Warrior]  # A队幸存者
    team_b_survivors: List[Warrior]  # B队幸存者
    logs: List[BattleLog]  # 战斗日志
    team_a: List[Warrior] = field(default_factory=list)  # A队所有武将
    team_b: List[Warrior] = field(default_factory=list)  # B队所有武将
    sp_leader_changes: List[tuple] = field(default_factory=list)  # 体力领先者变更历史 [(round_num, leader)]
    leader_history: List[dict] = field(default_factory=list)  # 每回合 HP/SP 领先快照
    battle_map: Optional[BattleMap] = None  # 本场使用的地图（无地图战斗为 None）


class BattleEngine:
    """运行武将对决模拟的主要战斗引擎"""

    def __init__(
        self,
        team_a: List[Warrior],
        team_b: List[Warrior],
        battle_map: Optional[BattleMap] = None,
    ):
        self.team_a = team_a
        self.team_b = team_b
        self.all_warriors = team_a + team_b
        self.battle_map = battle_map  # 不传地图时行为与纯数值模拟完全一致

        self.tick_count = 0  # 时间刻度计数器
        self.round_count = 0  # 回合计数器
        self.attack_count = 0  # 攻击次数计数器
        self.logs: List[BattleLog] = []  # 战斗日志
        self.last_attack_tick = {}  # 记录每个武将上次攻击的tick
        self.last_any_attack_tick = 0  # 记录任何武将上次攻击的tick
        self.sp_leader = None  # 当前体力领先者（"A" 或 "B"）
        self.sp_leader_changes = []  # 体力领先者变更历史 [(round_num, leader)]
        self.hp_leader = None  # 当前生命领先者（"A" 或 "B"）
        self.leader_history = []  # 每回合结束时的 HP/SP 领先快照
        # 实时操控覆盖项：武将名 -> {"mode": auto/manual, "move": 方向或None, "attack": 攻击意图}
        # 缺省为空字典，行为与纯 AI 模拟完全一致
        self.overrides: dict = {}
        # 连续移动的事件记账：一次移动段从何处开始、手动方向与所在格是否变化
        self._move_origin: dict = {}
        self._manual_dir: dict = {}
        self._move_cell: dict = {}

        self._validate_teams()

    def _validate_teams(self) -> None:
        """确保队伍正确设置"""
        for w in self.team_a:
            w.team = "A"
        for w in self.team_b:
            w.team = "B"

    def _capture_warrior_states(self) -> list:
        """记录当前全体武将的数值快照，供战报与网页演出重建状态"""
        states = []
        for w in self.all_warriors:
            entry = {
                "name": w.name,
                "team": w.team,
                "hp": w.hp,
                "hp_real": w.hp_real,
                "sp": w.sp,
                "sp_real": w.sp_real,
                "courage": w.courage,
                "ap": w.ap,
                "alive": w.is_alive,
            }
            if self.battle_map is not None:
                entry["position"] = list(w.position) if w.position is not None else None
            states.append(entry)
        return states

    def _log(self, event_type: str, description: str, **details) -> None:
        """添加日志条目"""
        self.logs.append(
            BattleLog(
                tick=self.tick_count,
                round_num=self.round_count,
                event_type=event_type,
                description=description,
                details=details,
                warrior_states=self._capture_warrior_states(),
            )
        )

    def _get_alive(self, team: str) -> List[Warrior]:
        """获取指定队伍存活的武将"""
        warriors = self.team_a if team == "A" else self.team_b
        return [w for w in warriors if w.is_alive]

    def _get_all_alive(self) -> List[Warrior]:
        """获取所有存活的武将"""
        return [w for w in self.all_warriors if w.is_alive]

    def _get_team_sp_percent(self, team: str) -> float:
        """计算指定队伍的总体力百分比"""
        warriors = self.team_a if team == "A" else self.team_b
        total_sp = sum(w.sp for w in warriors)
        total_sp_real = sum(w.sp_real for w in warriors)
        return total_sp / total_sp_real if total_sp_real > 0 else 0.0

    def _get_team_hp_percent(self, team: str) -> float:
        """计算指定队伍的总生命百分比"""
        warriors = self.team_a if team == "A" else self.team_b
        total_hp = sum(w.hp for w in warriors)
        total_hp_real = sum(w.hp_real for w in warriors)
        return total_hp / total_hp_real if total_hp_real > 0 else 0.0

    def _record_leadership(self, round_num: int) -> None:
        """记录该回合结束时的 HP/SP 领先快照（持平则延续上一位领先者）"""
        hp_a = self._get_team_hp_percent("A")
        hp_b = self._get_team_hp_percent("B")
        sp_a = self._get_team_sp_percent("A")
        sp_b = self._get_team_sp_percent("B")

        if hp_a > hp_b:
            self.hp_leader = "A"
        elif hp_b > hp_a:
            self.hp_leader = "B"

        if sp_a > sp_b:
            self.sp_leader = "A"
        elif sp_b > sp_a:
            self.sp_leader = "B"

        self.leader_history.append(
            {
                "round": round_num,
                "hp": {
                    "A": hp_a,
                    "B": hp_b,
                    "leader": self.hp_leader,
                    "gap": abs(hp_a - hp_b),
                },
                "sp": {
                    "A": sp_a,
                    "B": sp_b,
                    "leader": self.sp_leader,
                    "gap": abs(sp_a - sp_b),
                },
            }
        )

    def _record_final_leadership(self) -> None:
        """战斗在回合中途结束时，补记当前回合的最终领先状态"""
        if self.leader_history and self.leader_history[-1]["round"] >= self.round_count:
            return

        hp_a = self._get_team_hp_percent("A")
        hp_b = self._get_team_hp_percent("B")
        sp_a = self._get_team_sp_percent("A")
        sp_b = self._get_team_sp_percent("B")

        if self.leader_history:
            last = self.leader_history[-1]
            unchanged = (
                abs(last["hp"]["A"] - hp_a) < 1e-9
                and abs(last["hp"]["B"] - hp_b) < 1e-9
                and abs(last["sp"]["A"] - sp_a) < 1e-9
                and abs(last["sp"]["B"] - sp_b) < 1e-9
            )
            if unchanged:
                return

        self._record_leadership(max(1, self.round_count))

    def _find_target(self, attacker: Warrior) -> Optional[Warrior]:
        """寻找目标：生命值最低的敌人"""
        enemy_team = "B" if attacker.team == "A" else "A"
        enemies = self._get_alive(enemy_team)
        if not enemies:
            return None
        return min(enemies, key=lambda w: w.hp)

    def _check_battle_end(self) -> Optional[BattleResult]:
        """检查战斗是否应该结束"""
        alive_a = self._get_alive("A")
        alive_b = self._get_alive("B")

        # 双方全灭 - 平局
        if not alive_a and not alive_b:
            self._log("battle_end", "双方同归于尽！平局！")
            return BattleResult(
                outcome=BattleOutcome.DRAW,
                winner_team=None,
                rounds=self.round_count,
                ticks=self.tick_count,
                team_a_survivors=[],
                team_b_survivors=[],
                logs=self.logs,
                team_a=self.team_a,
                team_b=self.team_b,
                sp_leader_changes=self.sp_leader_changes,
                leader_history=self.leader_history,
            )

        # A队全灭
        if not alive_a:
            self._log("battle_end", "A队全灭，B队获胜！")
            return BattleResult(
                outcome=BattleOutcome.TEAM_B_WIN,
                winner_team="B",
                rounds=self.round_count,
                ticks=self.tick_count,
                team_a_survivors=[],
                team_b_survivors=alive_b,
                logs=self.logs,
                team_a=self.team_a,
                team_b=self.team_b,
                sp_leader_changes=self.sp_leader_changes,
                leader_history=self.leader_history,
            )

        # B队全灭
        if not alive_b:
            self._log("battle_end", "B队全灭，A队获胜！")
            return BattleResult(
                outcome=BattleOutcome.TEAM_A_WIN,
                winner_team="A",
                rounds=self.round_count,
                ticks=self.tick_count,
                team_a_survivors=alive_a,
                team_b_survivors=[],
                logs=self.logs,
                team_a=self.team_a,
                team_b=self.team_b,
                sp_leader_changes=self.sp_leader_changes,
                leader_history=self.leader_history,
            )

        return None

    def _check_timeout(self) -> Optional[BattleResult]:
        """检查超时并根据生命值百分比决定胜者"""
        # 优先检查时间刻度超时（防止无限循环）
        if self.tick_count < MAX_TICKS and self.round_count < MAX_ROUNDS:
            return None

        alive_a = self._get_alive("A")
        alive_b = self._get_alive("B")

        # 计算生命值百分比
        total_max_a = sum(w.hp_real for w in self.team_a)
        total_max_b = sum(w.hp_real for w in self.team_b)

        current_hp_a = sum(w.hp for w in alive_a)
        current_hp_b = sum(w.hp for w in alive_b)

        pct_a = current_hp_a / total_max_a if total_max_a > 0 else 0
        pct_b = current_hp_b / total_max_b if total_max_b > 0 else 0

        reason = "达到最大时间刻度" if self.tick_count >= MAX_TICKS else "达到最大回合数"
        self._log("timeout", f"{reason}！A队血量{pct_a:.1%}，B队血量{pct_b:.1%}")

        if pct_a > pct_b:
            return BattleResult(
                outcome=BattleOutcome.TIMEOUT,
                winner_team="A",
                rounds=self.round_count,
                ticks=self.tick_count,
                team_a_survivors=alive_a,
                team_b_survivors=alive_b,
                logs=self.logs,
                team_a=self.team_a,
                team_b=self.team_b,
                sp_leader_changes=self.sp_leader_changes,
                leader_history=self.leader_history,
            )
        elif pct_b > pct_a:
            return BattleResult(
                outcome=BattleOutcome.TIMEOUT,
                winner_team="B",
                rounds=self.round_count,
                ticks=self.tick_count,
                team_a_survivors=alive_a,
                team_b_survivors=alive_b,
                logs=self.logs,
                team_a=self.team_a,
                team_b=self.team_b,
                sp_leader_changes=self.sp_leader_changes,
                leader_history=self.leader_history,
            )
        else:
            return BattleResult(
                outcome=BattleOutcome.DRAW,
                winner_team=None,
                rounds=self.round_count,
                ticks=self.tick_count,
                team_a_survivors=alive_a,
                team_b_survivors=alive_b,
                logs=self.logs,
                team_a=self.team_a,
                team_b=self.team_b,
                sp_leader_changes=self.sp_leader_changes,
                leader_history=self.leader_history,
            )

    def _log_skill_effect(self, skill, warrior: Warrior, effect) -> None:
        """把特技发动结果写入战报"""
        if effect is None:
            return
        details = dict(effect.details)
        details.setdefault("skill_id", skill.skill_id)
        details.setdefault("skill", skill.name)
        details.setdefault("category", skill.category)
        details.setdefault("warrior", warrior.name)
        self._log("skill_trigger", effect.description, **details)

    def _apply_battle_start_skills(self) -> None:
        """第 1 回合首次行动前触发所有开启的特技"""
        for warrior in self.all_warriors:
            for skill in warrior.active_skills:
                effect = skill.on_battle_start(warrior, self)
                self._log_skill_effect(skill, warrior, effect)

    def _apply_round_start_skills(self) -> None:
        """每个回合开始时触发所有开启的特技（含第 1 回合）"""
        for warrior in self.all_warriors:
            if not warrior.is_alive:
                continue
            for skill in warrior.active_skills:
                effect = skill.on_round_start(warrior, self, self.round_count)
                self._log_skill_effect(skill, warrior, effect)

    def _process_single_attack(self, attacker: Warrior) -> None:
        """处理单个攻击动作"""
        target = self._find_target(attacker)
        if not target:
            attacker.finish_attack()
            attacker.finish_backswing()
            return

        # 射程外（或视线被挡）同样允许挥刀，但只是空挥：不进入攻防判定
        if self.battle_map is not None and not self._can_reach(attacker, target):
            self._process_whiff(attacker, target)
            return

        # 进入攻击阶段
        attacker.start_attack()

        # 记录攻击前状态
        attacker_hp_before = attacker.hp
        attacker_sp_before = attacker.sp
        attacker_sp_percent_before = attacker.sp_percent  # 攻击方SP百分比
        target_hp_before = target.hp
        target_sp_before = target.sp
        target_sp_percent_before = target.sp_percent  # 防守方SP百分比
        target_courage_before = target.courage
        target_ap_percent = target.ap_percent  # 记录防守方AP百分比

        # 防守方选择防御方式
        defense_type = target.choose_defense(attacker)
        base_damage = calculate_final_damage(attacker, target)

        # 计算防御成功率
        from src.defense import calculate_defense_rate
        defense_rate = calculate_defense_rate(defense_type, target, attacker)

        # 处理防御
        result = process_defense(defense_type, target, attacker, base_damage)

        # 特技伤害倍率：攻方打出的伤害与守方反击/反震打出的伤害分别结算
        attacker_damage_multiplier = 1.0
        defender_damage_multiplier = 1.0
        if result.damage_to_defender > 0:
            attacker_damage_multiplier = attacker.damage_dealt_multiplier(
                self.round_count
            )
            result.damage_to_defender *= attacker_damage_multiplier
        if result.damage_to_attacker > 0:
            defender_damage_multiplier = target.damage_dealt_multiplier(
                self.round_count
            )
            result.damage_to_attacker *= defender_damage_multiplier

        # 本次防守结算后，后手AP基准加成不再重复生效
        target.consume_ap_bonus()

        # 应用结果：守方受伤扣AP，攻方受伤延长后摇
        if result.damage_to_defender > 0:
            target.take_damage(result.damage_to_defender)
            target.apply_defender_damage_penalty(result.damage_to_defender)
        if result.damage_to_attacker > 0:
            attacker.take_damage(result.damage_to_attacker)
            attacker.apply_attacker_damage_penalty(result.damage_to_attacker)

        # 攻击体力消耗依赖当前 SP/HP 百分比，必须在扣减前只计算一次并复用，
        # 否则日志记录值会与实际扣减不一致
        attack_cost = attacker.attack_sp_cost()

        target.consume_sp(result.defender_sp_cost)
        attacker_sp_before_deduction = attacker.sp
        attacker.consume_sp(result.attacker_sp_cost + attack_cost)
        attacker_actual_sp_cost = attacker_sp_before_deduction - attacker.sp
        target.modify_courage(result.defender_courage_change)

        # 计算攻击间隔（第一次攻击间隔为从战斗开始到现在）
        attack_interval_ticks = self.tick_count - self.last_attack_tick.get(attacker.name, 0)
        global_attack_interval_ticks = self.tick_count - self.last_any_attack_tick
        self.last_attack_tick[attacker.name] = self.tick_count
        self.last_any_attack_tick = self.tick_count

        # 记录攻击日志（包含详细状态变化）
        range_details = {}
        if self.battle_map is not None:
            range_details = {
                "attack_distance": chebyshev_distance(attacker.position, target.position),
                "attacker_reach": attacker.reach,
            }
        self._log(
            "attack",
            f"{attacker.name} 攻击 {target.name}，{target.name} 选择 {defense_type.value}",
            attacker=attacker.name,
            defender=target.name,
            defense=defense_type.value,
            success=result.success,
            defense_rate=defense_rate,  # 记录防御成功率
            defender_ap_percent=target_ap_percent,  # 记录防守方AP百分比
            attack_interval_ticks=attack_interval_ticks,  # 记录该武将的攻击间隔
            global_attack_interval_ticks=global_attack_interval_ticks,  # 记录距离任何攻击的间隔
            damage_to_defender=result.damage_to_defender,
            damage_to_attacker=result.damage_to_attacker,
            defender_sp_cost=result.defender_sp_cost,
            attacker_sp_cost=attacker_actual_sp_cost,  # 记录实际扣减量（SP 不足时会被钳到 0）
            defender_courage_change=result.defender_courage_change,
            # 状态变化记录
            attacker_hp_before=attacker_hp_before,
            attacker_hp_after=attacker.hp,
            attacker_sp_before=attacker_sp_before,
            attacker_sp_after=attacker.sp,
            attacker_sp_percent_before=attacker_sp_percent_before,
            attacker_sp_percent_after=attacker.sp_percent,
            target_hp_before=target_hp_before,
            target_hp_after=target.hp,
            target_sp_before=target_sp_before,
            target_sp_after=target.sp,
            target_sp_percent_before=target_sp_percent_before,
            target_sp_percent_after=target.sp_percent,
            target_courage_before=target_courage_before,
            target_courage_after=target.courage,
            target_alive=target.is_alive,
            attacker_alive=attacker.is_alive,
            attacker_damage_multiplier=attacker_damage_multiplier,
            defender_damage_multiplier=defender_damage_multiplier,
            **range_details,
        )

        # 攻击完成，进入后摇阶段
        attacker.finish_attack()
        self.attack_count += 1

    def _process_whiff(self, attacker: Warrior, target: Warrior) -> None:
        """射程外挥刀：只结算自身出招消耗与后摇，不产生任何攻防判定

        出手即消耗一次前摇并付出一份攻击体力，对手既不掉血也不进入防守选择，
        空挥之后同样进入后摇（不可移动、不可出手），用来限制无脑乱挥。
        """
        attacker.start_attack()

        attack_cost = attacker.attack_sp_cost() * WHIFF_SP_COST_RATIO
        sp_before = attacker.sp
        attacker.consume_sp(attack_cost)
        actual_cost = sp_before - attacker.sp

        attack_interval_ticks = self.tick_count - self.last_attack_tick.get(attacker.name, 0)
        global_attack_interval_ticks = self.tick_count - self.last_any_attack_tick
        self.last_attack_tick[attacker.name] = self.tick_count
        self.last_any_attack_tick = self.tick_count

        distance = chebyshev_distance(attacker.position, target.position)
        out_of_range = distance > attacker.reach
        reason = "range" if out_of_range else "los"
        distance_text = (
            f"{target.name} 尚在射程外（相距 {distance:.1f} 格，射程 {attacker.reach} 格）"
            if out_of_range
            else "视线被地形遮挡"
        )
        self._log(
            "whiff",
            f"{attacker.name} 挥刀落空：{distance_text}",
            attacker=attacker.name,
            defender=target.name,
            out_of_range=out_of_range,
            whiff_reason=reason,
            attack_distance=distance,
            attacker_reach=attacker.reach,
            attacker_sp_before=sp_before,
            attacker_sp_after=attacker.sp,
            attacker_sp_cost=actual_cost,
            attack_interval_ticks=attack_interval_ticks,
            global_attack_interval_ticks=global_attack_interval_ticks,
        )

        # 空挥同样进入后摇
        attacker.finish_attack()
        self.attack_count += 1

    def _process_clash(self, ready_warriors: List[Warrior]) -> None:
        """处理多个武将之间的拼刀"""
        clash_result = process_clash(ready_warriors, self.round_count)

        # 应用伤害和体力消耗
        for warrior in ready_warriors:
            damage = clash_result.damages[warrior.name]
            sp_cost = clash_result.sp_costs[warrior.name]
            warrior.take_damage(damage)
            warrior.apply_attacker_damage_penalty(damage)
            warrior.consume_sp(sp_cost)
            # 拼刀后进入后摇阶段
            warrior.start_attack()
            warrior.finish_attack()

        self._log(
            "clash",
            f"拼刀！参与者: {', '.join(w.name for w in ready_warriors)}",
            participants=[w.name for w in ready_warriors],
            damages=clash_result.damages,
            sp_costs=clash_result.sp_costs,
        )

        self.attack_count += len(ready_warriors)

    def _check_round_end(self) -> None:
        """检查回合是否应该结束"""
        alive_count = len(self._get_all_alive())
        if alive_count > 0 and self.attack_count >= alive_count:
            completed_round = self.round_count

            # 检查体力领先者
            sp_a = self._get_team_sp_percent("A")
            sp_b = self._get_team_sp_percent("B")
            new_leader = None

            if sp_a > sp_b:
                new_leader = "A"
            elif sp_b > sp_a:
                new_leader = "B"
            # 如果相等，保持当前领先者不变

            # 记录变更（初始 leader 为 None，同样会进入此分支）
            if new_leader is not None and new_leader != self.sp_leader:
                self.sp_leader = new_leader
                self.sp_leader_changes.append((completed_round, new_leader))
                self._log(
                    "sp_leader_change",
                    f"体力领先者变更: {new_leader}队",
                    leader=new_leader,
                    round_num=completed_round,
                )

            self._record_leadership(completed_round)
            self._log("round_end", f"第 {completed_round} 回合结束")

            self.round_count += 1
            self.attack_count = 0
            self._apply_round_start_skills()

    def _deploy(self) -> None:
        """布阵：双方依次落在出生点格心（多武将时落在最近空闲格）"""
        for team, side in ((self.team_a, "A"), (self.team_b, "B")):
            occupied = {
                cell_at(w.position) for w in self.all_warriors if w.position is not None
            }
            for warrior in team:
                cell = self.battle_map.nearest_free(self.battle_map.spawn(side), occupied)
                warrior.position = cell_center(cell)
                occupied.add(cell)

    def _can_reach(self, attacker: Warrior, target: Warrior) -> bool:
        """目标是否在射程内且视线通畅（按双方实际浮点站位判定）"""
        return (
            chebyshev_distance(attacker.position, target.position) <= attacker.reach
            and self.battle_map.has_line_of_sight_points(
                attacker.position, target.position
            )
        )

    def _update_movement(self) -> None:
        """移动阶段：推进在途移动；射程外且不在后摇的武将向目标寻路接近

        手动移动指令优先于 AI 寻路（无论自动/手动模式）；
        手动模式下没有指令时原地待命，不自动接近目标。
        双方都按浮点坐标连续移动，可在任意可走位置停下。
        """
        if self.battle_map is None:
            return
        alive = self._get_all_alive()
        for warrior in alive:
            if warrior.is_in_backswing():
                if warrior.is_moving:
                    warrior.stop_move()
                self._end_move_leg(warrior)
                continue  # 后摇期间锁定站位

            others = [
                other
                for other in alive
                if other is not warrior and other.position is not None
            ]
            override = self.overrides.get(warrior.name)
            manual_dir = override.get("move") if override else None

            if manual_dir is not None:
                self._step_manual_move(warrior, manual_dir, others)
                continue

            if self._manual_dir.get(warrior.name) is not None:
                # 松开方向键：结束本段手动移动
                if warrior.manual_moving:
                    warrior.stop_move()
                self._end_move_leg(warrior)

            if override and override.get("mode") == "manual":
                if warrior.is_moving:
                    warrior.stop_move()
                self._end_move_leg(warrior)
                continue

            target = self._find_target(warrior)
            if target is None:
                if warrior.is_moving:
                    warrior.stop_move()
                self._end_move_leg(warrior)
                continue

            if warrior.is_moving:
                self._advance_ai_move(warrior, target, others)
                continue

            if self._can_reach(warrior, target):
                continue

            occupied = {cell_at(other.position) for other in others}
            start_cell = cell_at(warrior.position)
            path = self.battle_map.find_path_to_point_range(
                start_cell, target.position, warrior.reach, occupied=occupied
            )
            if path:
                warrior.begin_move(path)
                self._move_origin.setdefault(warrior.name, warrior.position)
                self._clear_attack_intent(warrior)
            elif path == []:
                # 当前格心已在射程内，但实际站位还差一点：走回格心
                center = cell_center(start_cell)
                if math.hypot(
                    center[0] - warrior.position[0], center[1] - warrior.position[1]
                ) > 1e-3:
                    warrior.begin_move([start_cell])
                    self._move_origin.setdefault(warrior.name, warrior.position)

    def _advance_ai_move(self, warrior: Warrior, target: Warrior, others) -> None:
        """沿 AI 路点连续推进；进入射程后立即停下"""
        if self._can_reach(warrior, target):
            warrior.stop_move()
            self._end_move_leg(warrior)
            return

        remaining = warrior.move_speed_cells * TICK_RATE
        while remaining > 1e-9 and warrior.move_path:
            waypoint = cell_center(warrior.move_path[0])
            x, y = warrior.position
            distance = math.hypot(waypoint[0] - x, waypoint[1] - y)
            if distance <= 1e-9:
                warrior.move_path.pop(0)
                self._flush_move(warrior)
                if self._can_reach(warrior, target):
                    warrior.stop_move()
                    self._end_move_leg(warrior)
                    return
                continue

            travel = min(remaining, distance)
            moved = self._move_position(
                warrior,
                x + (waypoint[0] - x) / distance * travel,
                y + (waypoint[1] - y) / distance * travel,
                others,
            )
            if moved is None:
                warrior.stop_move()  # 前方被挡，停下重新规划
                self._end_move_leg(warrior)
                return
            remaining -= math.hypot(moved[0] - x, moved[1] - y)
            if math.hypot(waypoint[0] - moved[0], waypoint[1] - moved[1]) <= 1e-6:
                warrior.move_path.pop(0)
                self._flush_move(warrior)
                if self._can_reach(warrior, target):
                    warrior.stop_move()
                    self._end_move_leg(warrior)
                    return

        if not warrior.move_path:
            warrior.stop_move()
            self._end_move_leg(warrior)

    def _step_manual_move(self, warrior: Warrior, direction, others) -> None:
        """手动移动：按方向连续推进，可停在任意可走位置；方向变化即切段"""
        dx, dy = direction
        length = math.hypot(dx, dy)
        if length <= 0:
            return

        previous = self._manual_dir.get(warrior.name)
        if previous is not None and previous != (dx, dy):
            self._flush_move(warrior)
        self._manual_dir[warrior.name] = (dx, dy)

        if warrior.move_path:
            warrior.stop_move()  # 手动优先，丢弃 AI 路点

        step = warrior.move_speed_cells * TICK_RATE
        before = warrior.position
        moved = self._move_position(
            warrior,
            before[0] + dx / length * step,
            before[1] + dy / length * step,
            others,
        )
        if moved is None:
            if warrior.manual_moving:
                warrior.stop_move()
                self._end_move_leg(warrior)
            return

        if not warrior.manual_moving:
            warrior.begin_manual_move()
            self._move_origin[warrior.name] = before
            self._move_cell[warrior.name] = cell_at(before)
            self._clear_attack_intent(warrior)
        elif cell_at(warrior.position) != self._move_cell.get(warrior.name):
            # 跨入新格时记一段，保证回放能连续演出手动移动
            self._flush_move(warrior)
            self._move_cell[warrior.name] = cell_at(warrior.position)

    def _move_position(self, warrior: Warrior, x: float, y: float, others) -> Optional[tuple]:
        """按地图碰撞与单位间距推进到目标点；完全无法移动时返回 None"""
        start = warrior.position
        moved = self.battle_map.move_point(
            start[0], start[1], x - start[0], y - start[1], UNIT_RADIUS
        )
        if math.hypot(moved[0] - start[0], moved[1] - start[1]) < 1e-9:
            return None
        if others:
            before_gap = min(
                math.hypot(start[0] - other.position[0], start[1] - other.position[1])
                for other in others
            )
            after_gap = min(
                math.hypot(moved[0] - other.position[0], moved[1] - other.position[1])
                for other in others
            )
            if after_gap < UNIT_SEPARATION and after_gap < before_gap - 1e-9:
                return None
        warrior.position = moved
        return moved

    def _flush_move(self, warrior: Warrior) -> None:
        """结算一段移动事件：从上次事件位置到当前浮点位置"""
        origin = self._move_origin.get(warrior.name)
        position = warrior.position
        if origin is None or position is None:
            return
        distance = math.hypot(position[0] - origin[0], position[1] - origin[1])
        if distance < 1e-4:
            return
        duration = max(80, round(distance / warrior.move_speed_cells * 1000))
        self._log(
            "move",
            f"{warrior.name} 移动 ({origin[0]:.1f},{origin[1]:.1f}) → "
            f"({position[0]:.1f},{position[1]:.1f})",
            warrior=warrior.name,
            duration=duration,
            **{"from": list(origin), "to": list(position)},
        )
        self._move_origin[warrior.name] = position

    def _end_move_leg(self, warrior: Warrior) -> None:
        """结束移动段：补一条收尾事件并清空记账"""
        self._flush_move(warrior)
        self._move_origin.pop(warrior.name, None)
        self._manual_dir.pop(warrior.name, None)
        self._move_cell.pop(warrior.name, None)

    def _attack_allowed(self, warrior: Warrior) -> bool:
        """手动模式必须收到攻击指令才出手；自动模式始终允许"""
        override = self.overrides.get(warrior.name)
        if override and override.get("mode") == "manual":
            return bool(override.get("attack"))
        return True

    def _clear_attack_intent(self, warrior: Warrior) -> None:
        override = self.overrides.get(warrior.name)
        if override:
            override["attack"] = False

    def run_tick(self) -> Optional[BattleResult]:
        """运行战斗的一个时间刻度"""
        self.tick_count += 1

        # 移动阶段（无地图时为空操作）
        self._update_movement()

        # 为所有存活武将累积行动点数（移动中的武将内部跳过）
        for warrior in self._get_all_alive():
            warrior.tick_ap(TICK_RATE)

        # 检查后摇完成的武将，让他们进入前摇阶段
        for warrior in self._get_all_alive():
            if warrior.check_backswing_complete():
                warrior.finish_backswing()

        # 获取前摇完成的武将：射程外也允许挥刀（落空），由 _process_single_attack 分流
        ready = [w for w in self._get_all_alive() if w.can_attack()]
        ready = [w for w in ready if self._attack_allowed(w)]

        # 拼刀只在真正能交手（双方射程内且视线通畅）的武将之间成立
        clash_ready = ready
        if self.battle_map is not None:
            clash_ready = [
                w
                for w in ready
                if (target := self._find_target(w)) is not None
                and self._can_reach(w, target)
            ]

        if len(clash_ready) >= 2 and check_clash_condition(clash_ready):
            # 拼刀！
            self._process_clash(clash_ready)
            for warrior in clash_ready:
                self._clear_attack_intent(warrior)
            # 同一 tick 内够不着的武将各自空挥
            for attacker in [w for w in ready if w not in clash_ready]:
                if attacker.is_alive:
                    self._process_single_attack(attacker)
                    self._clear_attack_intent(attacker)
        elif ready:
            # 按顺序进行单个攻击（射程外的会落空）
            for attacker in ready:
                if attacker.is_alive:
                    self._process_single_attack(attacker)
                    self._clear_attack_intent(attacker)

        # 检查战斗是否结束（在所有伤害应用后）
        result = self._check_battle_end()
        if result:
            return result

        # 检查回合是否结束
        self._check_round_end()

        # 检查是否超时
        return self._check_timeout()

    def begin(self) -> None:
        """开战布置：布阵、开场日志与第 1 回合特技（run 与实时会话共用）"""
        if self.battle_map is not None:
            self._deploy()
        self._log("battle_start", "战斗开始！")
        self.round_count = 1
        self._apply_battle_start_skills()
        self._apply_round_start_skills()

    def run(self) -> BattleResult:
        """运行完整战斗直到结束"""
        self.begin()

        while True:
            result = self.run_tick()
            if result:
                self._record_final_leadership()
                result.battle_map = self.battle_map
                return result
