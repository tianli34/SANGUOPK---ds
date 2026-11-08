# 文件名: battle_statistics.py
# 用途: 战斗数据统计模块，负责从战斗日志中提取、分析和汇总各类战斗数据
"""战斗数据统计模块 - 负责从战斗日志中提取和汇总数据"""

from typing import List, Dict, TYPE_CHECKING
from dataclasses import dataclass, field
from collections import defaultdict

if TYPE_CHECKING:
    from src.battle_engine import BattleResult, BattleLog

# 所有防御类型
ALL_DEFENSE_TYPES = ["block", "parry", "dodge", "counter"]

# 防御类型中文映射 (View层可能用到，但定义在这里方便统一)
DEFENSE_TYPE_CN = {"block": "格挡", "parry": "卸力", "dodge": "闪避", "counter": "反击"}


@dataclass
class DefenseStats:
    """单个防御类型的统计数据"""

    use_count: int = 0  # 使用次数
    success_count: int = 0  # 成功次数
    total_damage_taken: float = 0.0  # 防御时受到的总伤害
    total_damage_dealt: float = 0.0  # 防御时造成的总伤害（反击/反震）


@dataclass
class ClashRecord:
    """单次拼刀记录"""

    round_num: int
    tick: int
    participants: List[str]
    damages: Dict[str, float]
    sp_costs: Dict[str, float]


@dataclass
class BattleStats:
    """战斗统计核心类 - 既可用于单场也可用于多场汇总"""

    # --- 基础计数 ---
    total_battles: int = 0
    total_rounds: int = 0
    total_ticks: int = 0

    # 胜负统计
    team_a_wins: int = 0
    team_b_wins: int = 0
    draws: int = 0

    # --- 详细统计 ---

    # 防御统计: {武将名: {防御类型: DefenseStats}}
    # 注意：这里使用 nested defaultdict 方便自动初始化
    defense_stats: Dict[str, Dict[str, DefenseStats]] = field(
        default_factory=lambda: defaultdict(
            lambda: {dt: DefenseStats() for dt in ALL_DEFENSE_TYPES}
        )
    )

    # 伤害统计 {武将名: 总受伤}
    warrior_total_damage: Dict[str, float] = field(
        default_factory=lambda: defaultdict(float)
    )

    # 攻击时受到的伤害（反击/反震） {武将名: 数值}
    warrior_attack_damage_taken: Dict[str, float] = field(
        default_factory=lambda: defaultdict(float)
    )

    # 单次攻击伤害统计（不含拼刀）{武将名: [最高伤害, 最低伤害]}
    warrior_attack_damage_range: Dict[str, List[float]] = field(
        default_factory=lambda: defaultdict(lambda: [0.0, float("inf")])
    )

    # 拼刀统计
    total_clashes: int = 0
    clash_records: List[ClashRecord] = field(default_factory=list)  # 仅单场保留详细记录
    warrior_clash_count: Dict[str, int] = field(
        default_factory=lambda: defaultdict(int)
    )
    warrior_clash_damage: Dict[str, float] = field(
        default_factory=lambda: defaultdict(float)
    )
    warrior_clash_sp_cost: Dict[str, float] = field(
        default_factory=lambda: defaultdict(float)
    )

    # --- 攻击频率 (仅单场分析使用) ---
    # {武将名: [tick1, tick2...]}
    attack_ticks: Dict[str, List[int]] = field(
        default_factory=lambda: defaultdict(list)
    )

    # --- 极值与分布 (多场汇总使用) ---
    min_rounds: int = 999999
    max_rounds: int = 0
    multi_attack_rounds: int = 0  # 同一武将回合内多次攻击的次数

    # 胜方/负方状态记录 (Lists)
    team_a_winner_hp: List[float] = field(default_factory=list)
    team_a_winner_sp: List[float] = field(default_factory=list)
    team_a_winner_courage: List[int] = field(default_factory=list)

    team_b_winner_hp: List[float] = field(default_factory=list)
    team_b_winner_sp: List[float] = field(default_factory=list)
    team_b_winner_courage: List[int] = field(default_factory=list)

    team_a_loser_sp: List[float] = field(default_factory=list)
    team_a_loser_courage: List[int] = field(default_factory=list)
    team_b_loser_sp: List[float] = field(default_factory=list)
    team_b_loser_courage: List[int] = field(default_factory=list)

    def analyze_result(self, result: "BattleResult") -> None:
        """解析一场战斗结果并更新统计"""
        self.total_battles += 1
        self.total_rounds += result.rounds
        self.total_ticks += result.ticks

        # 1. 更新胜负及极值
        self._update_outcome_stats(result)

        # 2. 遍历日志更新战斗细节
        self._process_logs(result.logs)

    def _update_outcome_stats(self, result: "BattleResult") -> None:
        # 回合数极值
        if result.rounds < self.min_rounds:
            self.min_rounds = result.rounds
        if result.rounds > self.max_rounds:
            self.max_rounds = result.rounds

        # 胜负判断
        if result.winner_team == "A":
            self.team_a_wins += 1
            self._record_survivor_stats(
                result.team_a_survivors,
                self.team_a_winner_hp,
                self.team_a_winner_sp,
                self.team_a_winner_courage,
            )
            self._record_loser_stats(
                result.team_b, self.team_b_loser_sp, self.team_b_loser_courage
            )
        elif result.winner_team == "B":
            self.team_b_wins += 1
            self._record_survivor_stats(
                result.team_b_survivors,
                self.team_b_winner_hp,
                self.team_b_winner_sp,
                self.team_b_winner_courage,
            )
            self._record_loser_stats(
                result.team_a, self.team_a_loser_sp, self.team_a_loser_courage
            )
        else:
            self.draws += 1

    def _record_survivor_stats(self, survivors, hp_list, sp_list, courage_list):
        for w in survivors:
            hp_list.append(w.hp)
            sp_list.append(w.sp)
            courage_list.append(w.courage)

    def _record_loser_stats(self, all_warriors, sp_list, courage_list):
        for w in all_warriors:
            sp_list.append(w.sp)
            courage_list.append(w.courage)

    def _process_logs(self, logs: List["BattleLog"]) -> None:
        round_attacks = defaultdict(int)

        for log in logs:
            if log.event_type == "attack":
                self._process_attack_log(log, round_attacks)
            elif log.event_type == "clash":
                self._process_clash_log(log)

        # 统计多次攻击的回合
        for _, count in round_attacks.items():
            if count > 1:
                self.multi_attack_rounds += 1

    def _process_attack_log(self, log: "BattleLog", round_attacks: Dict) -> None:
        details = log.details
        attacker = details.get("attacker", "")
        defender = details.get("defender", "")
        defense_type = details.get("defense", "block")
        success = details.get("success", False)

        # 记录攻击频率
        if attacker:
            round_attacks[(log.round_num, attacker)] += 1
            self.attack_ticks[attacker].append(log.tick)

        # 计算伤害
        target_hp_before = details.get("target_hp_before", 0)
        target_hp_after = details.get("target_hp_after", 0)
        attacker_hp_before = details.get("attacker_hp_before", 0)
        attacker_hp_after = details.get("attacker_hp_after", 0)

        damage_to_defender = max(0, target_hp_before - target_hp_after)
        damage_to_attacker = max(0, attacker_hp_before - attacker_hp_after)

        # 更新防御统计
        if defender:
            stats = self.defense_stats[defender][defense_type]
            stats.use_count += 1
            if success:
                stats.success_count += 1
            stats.total_damage_taken += damage_to_defender
            stats.total_damage_dealt += damage_to_attacker

            self.warrior_total_damage[defender] += damage_to_defender

        # 更新攻击方统计
        if attacker:
            self.warrior_total_damage[attacker] += damage_to_attacker
            self.warrior_attack_damage_taken[attacker] += damage_to_attacker

            # 单次伤害极值
            if damage_to_defender > 0:
                rng = self.warrior_attack_damage_range[attacker]
                if damage_to_defender > rng[0]:
                    rng[0] = damage_to_defender
                if damage_to_defender < rng[1]:
                    rng[1] = damage_to_defender

    def _process_clash_log(self, log: "BattleLog") -> None:
        details = log.details
        participants = details.get("participants", [])
        damages = details.get("damages", {})
        sp_costs = details.get("sp_costs", {})

        self.total_clashes += 1

        # 记录详情 (如果是大量战斗汇总，可能需要考虑是否记录这么多详情，但为了兼容单场报告先记录)
        # 优化：如果是单场分析（从外部判断），记录；如果是汇总，可能不保留 record。
        # 这里简单起见，始终记录 record，但在汇总 merge 时不合并 record 列表以节省内存。
        self.clash_records.append(
            ClashRecord(
                round_num=log.round_num,
                tick=log.tick,
                participants=participants,
                damages=damages,
                sp_costs=sp_costs,
            )
        )

        for name in participants:
            self.warrior_clash_count[name] += 1
            self.warrior_clash_damage[name] += damages.get(name, 0)
            self.warrior_clash_sp_cost[name] += sp_costs.get(name, 0)

    def merge(self, other: "BattleStats") -> None:
        """合并另一个 Stats 对象的数据到当前对象"""
        self.total_battles += other.total_battles
        self.total_rounds += other.total_rounds
        self.total_ticks += other.total_ticks

        self.team_a_wins += other.team_a_wins
        self.team_b_wins += other.team_b_wins
        self.draws += other.draws

        self.min_rounds = min(self.min_rounds, other.min_rounds)
        self.max_rounds = max(self.max_rounds, other.max_rounds)
        self.multi_attack_rounds += other.multi_attack_rounds
        self.total_clashes += other.total_clashes

        # 合并列表
        self.team_a_winner_hp.extend(other.team_a_winner_hp)
        self.team_a_winner_sp.extend(other.team_a_winner_sp)
        self.team_a_winner_courage.extend(other.team_a_winner_courage)
        self.team_b_winner_hp.extend(other.team_b_winner_hp)
        self.team_b_winner_sp.extend(other.team_b_winner_sp)
        self.team_b_winner_courage.extend(other.team_b_winner_courage)
        self.team_a_loser_sp.extend(other.team_a_loser_sp)
        self.team_a_loser_courage.extend(other.team_a_loser_courage)
        self.team_b_loser_sp.extend(other.team_b_loser_sp)
        self.team_b_loser_courage.extend(other.team_b_loser_courage)

        # 合并字典 (数值累加)
        for d_key, val in other.warrior_total_damage.items():
            self.warrior_total_damage[d_key] += val

        for d_key, val in other.warrior_attack_damage_taken.items():
            self.warrior_attack_damage_taken[d_key] += val

        for d_key, val in other.warrior_clash_count.items():
            self.warrior_clash_count[d_key] += val

        for d_key, val in other.warrior_clash_damage.items():
            self.warrior_clash_damage[d_key] += val

        for d_key, val in other.warrior_clash_sp_cost.items():
            self.warrior_clash_sp_cost[d_key] += val

        # 合并伤害范围 (取极值)
        for w, rng in other.warrior_attack_damage_range.items():
            self_rng = self.warrior_attack_damage_range[w]
            self_rng[0] = max(self_rng[0], rng[0])
            self_rng[1] = min(self_rng[1], rng[1])

        # 合并防御统计
        for w, def_dict in other.defense_stats.items():
            for dt, stats in def_dict.items():
                target = self.defense_stats[w][dt]
                target.use_count += stats.use_count
                target.success_count += stats.success_count
                target.total_damage_taken += stats.total_damage_taken
                target.total_damage_dealt += stats.total_damage_dealt

        # 注意：不合并 clash_records 和 attack_ticks，这些是单场详情，汇总报告不需要
