# 文件名: battle_report.py
# 用途: 战报输出模块，负责将战斗统计数据格式化并渲染为可读的文本报告
"战报输出模块 - 负责将统计数据渲染为文本报告"

from typing import List, TYPE_CHECKING
from src.warrior import WarriorSnapshot
from src.battle_statistics import BattleStats, ALL_DEFENSE_TYPES, DEFENSE_TYPE_CN
from src.lead_analysis import build_lead_records

if TYPE_CHECKING:
    from src.warrior import Warrior
    from src.battle_engine import BattleResult, BattleLog


def format_warrior_initial_stats(snapshot: WarriorSnapshot) -> str:
    """格式化武将初始属性（从快照）"""
    from src.constants import SP_EXPANSION_FACTOR

    # 直接从快照获取计算属性，避免逻辑重复
    sp_display = snapshot.sp_real / SP_EXPANSION_FACTOR

    text = (
        f"  【{snapshot.name}】\n"
        f"    四维属性: 武艺={snapshot.martialarts} 敏捷={snapshot.agility} "
        f"力量={snapshot.strength} 胆气={snapshot.courage} 体力={sp_display:.0f}\n"
        f"    战斗属性: HP={snapshot.hp:.0f} SP={snapshot.sp:.0f}/{snapshot.sp_real}\n"
        f"    计算属性: 攻击力={snapshot.attack_power:.1f} 防御力={snapshot.defense_power:.1f} "
        f"攻速={snapshot.attack_speed:.1f}"
    )
    if snapshot.weapon_name:
        text += f"\n    兵器: {snapshot.weapon_name} · {snapshot.weapon_category_label}"
    if snapshot.skills:
        text += f"\n    特技: {'；'.join(snapshot.skills)}"
    return text


def format_warrior_current_stats(warrior: "Warrior") -> str:
    """格式化武将当前属性"""
    status = "阵亡" if not warrior.is_alive else "存活"
    return (
        f"  【{warrior.name}】[{status}]\n"
        f"    HP={warrior.hp:.0f}/{warrior.hp_real:.0f} ({warrior.hp_percent * 100:.1f}%)\n"
        f"    SP={warrior.sp:.0f}/{warrior.sp_real} ({warrior.sp_percent * 100:.1f}%)\n"
        f"    胆气={warrior.courage}"
    )


class BattleReporter:
    """单场战斗战报生成器"""

    def __init__(self, team_a: List["Warrior"], team_b: List["Warrior"]):
        self.team_a = team_a
        self.team_b = team_b
        self.initial_snapshots_a = [w.snapshot() for w in team_a]
        self.initial_snapshots_b = [w.snapshot() for w in team_b]

    def generate_initial_report(self) -> str:
        lines = []
        lines.append("=" * 70)
        lines.append("【战斗开始 - 双方武将初始属性】")
        lines.append("=" * 70)

        lines.append("\n▶ A队阵容:")
        for snapshot in self.initial_snapshots_a:
            lines.append(format_warrior_initial_stats(snapshot))

        lines.append("\n▶ B队阵容:")
        for snapshot in self.initial_snapshots_b:
            lines.append(format_warrior_initial_stats(snapshot))

        lines.append("=" * 70)
        return "\n".join(lines)

    def generate_round_report(
        self, round_logs: List["BattleLog"], round_num: int
    ) -> str:
        """生成单个回合的详细流水账"""
        if not round_logs:
            return ""

        lines = []
        lines.append(f"\n{'─' * 70}")
        lines.append(f"【第 {round_num} 回合】")
        lines.append("─" * 70)

        # 显示该回合的体力领先者变更
        for log in round_logs:
            if log.event_type == "sp_leader_change":
                leader = log.details.get("leader", "")
                lines.append(f"  体力领先者: {leader}队")
                break

        # 特技在行动前生效，先于攻击展示
        for log in round_logs:
            if log.event_type == "skill_trigger":
                lines.append(f"    ✦ {log.description}")

        for log in round_logs:
            if log.event_type == "attack":
                lines.append(self._format_attack_log(log))
            elif log.event_type == "clash":
                lines.append(self._format_clash_log(log))

        return "\n".join(lines)

    def _format_stat_change(
        self,
        details: dict,
        name: str,
        name_key: str,
        stat: str,
        label: str,
        fmt: str = ".0f",
    ) -> str:
        before = details.get(f"{name_key}_{stat}_before")
        after = details.get(f"{name_key}_{stat}_after")

        if before is None or after is None or before == after:
            return ""

        diff = after - before
        sign = "+" if diff > 0 else ""

        # 对于 HP/SP, 通常显示减少值，所以保持原逻辑 (before - after) 为正数表示减少
        if stat in ("hp", "sp"):
            display_diff = before - after
            result = f"{name} {label}: {before:{fmt}}→{after:{fmt}} (-{display_diff:{fmt}})"
            # 如果是SP，直接从快照获取百分比
            if stat == "sp":
                pct_before = details.get(f"{name_key}_sp_percent_before")
                pct_after = details.get(f"{name_key}_sp_percent_after")
                if pct_before is not None and pct_after is not None:
                    result += f" ({pct_before * 100:.1f}%→{pct_after * 100:.1f}%)"
            return result
        else:
            return f"{name} {label}: {before:{fmt}}→{after:{fmt}} ({sign}{diff:{fmt}})"

    def _format_attack_log(self, log: "BattleLog") -> str:
        details = log.details
        attacker = details.get("attacker", "未知")
        defender = details.get("defender", "未知")
        defense = details.get("defense", "block")
        success = details.get("success", False)
        defense_rate = details.get("defense_rate")
        defender_ap_percent = details.get("defender_ap_percent")

        defense_cn = DEFENSE_TYPE_CN.get(defense, defense)
        success_text = "成功" if success else "失败"

        lines = []
        lines.append(f"\n  ⚔ {attacker} → {defender}")
        
        # 显示攻击间隔
        attack_interval_ticks = details.get("attack_interval_ticks")
        global_attack_interval_ticks = details.get("global_attack_interval_ticks")
        if attack_interval_ticks is not None:
            interval_seconds = attack_interval_ticks / 20.0
            lines.append(f"    该武将攻击间隔: {interval_seconds:.2f}秒 ({attack_interval_ticks}tick)")
        if global_attack_interval_ticks is not None:
            global_interval_seconds = global_attack_interval_ticks / 20.0
            lines.append(f"    距上次攻击间隔: {global_interval_seconds:.2f}秒 ({global_attack_interval_ticks}tick)")
        
        lines.append(f"    防御方式: {defense_cn}")
        if defender_ap_percent is not None:
            lines.append(f"    防守方AP: {defender_ap_percent * 100:.1f}%")
        if defense_rate is not None:
            lines.append(f"    成功率: {defense_rate * 100:.1f}%")
        lines.append(f"    判定结果: {success_text}")

        changes = []
        for char_type, name_key in [("defender", "target"), ("attacker", "attacker")]:
            name = details.get(char_type)
            if not name:
                continue

            for stat, label in [("hp", "HP"), ("sp", "SP"), ("courage", "胆气")]:
                fmt = ".0f" if stat != "courage" else "d"
                change_str = self._format_stat_change(
                    details, name, name_key, stat, label, fmt
                )
                if change_str:
                    changes.append(change_str)

        if changes:
            lines.append("    属性变化:")
            for change in changes:
                lines.append(f"      • {change}")

        if not details.get("target_alive", True):
            lines.append(f"    ☠ {defender} 阵亡!")
        if not details.get("attacker_alive", True):
            lines.append(f"    ☠ {attacker} 阵亡!")

        return "\n".join(lines)

    def _format_clash_log(self, log: "BattleLog") -> str:
        details = log.details
        participants = details.get("participants", [])
        damages = details.get("damages", {})
        sp_costs = details.get("sp_costs", {})

        lines = []
        lines.append(f"\n  ⚔⚔ 拼刀! 参与者: {', '.join(participants)}")
        for name in participants:
            dmg = damages.get(name, 0)
            sp = sp_costs.get(name, 0)
            if dmg > 0 or sp > 0:
                lines.append(f"    {name}: HP-{dmg:.0f}, SP-{sp:.0f}")
        return "\n".join(lines)

    def generate_final_report(self, result: "BattleResult") -> str:
        lines = []
        lines.append("\n" + "=" * 70)
        lines.append("【战斗结束 - 双方武将当前属性】")
        lines.append("=" * 70)

        outcome_text = {
            "team_a_win": "A队胜利",
            "team_b_win": "B队胜利",
            "draw": "平局",
            "timeout": "超时判定",
        }
        lines.append(
            f"\n战斗结果: {outcome_text.get(result.outcome.value, result.outcome.value)}"
        )
        lines.append(f"获胜方: {result.winner_team or '无'}")
        lines.append(f"总回合数: {result.rounds}")

        # 显示 HP/SP 领先记录
        lead_section = self._format_lead_records(result)
        if lead_section:
            lines.append(lead_section)

        lines.append("\n▶ A队武将状态:")
        for w in self.team_a:
            lines.append(format_warrior_current_stats(w))
        lines.append("\n▶ B队武将状态:")
        for w in self.team_b:
            lines.append(format_warrior_current_stats(w))

        lines.append("=" * 70)
        return "\n".join(lines)

    def _format_lead_records(self, result: "BattleResult") -> str:
        """渲染 HP/SP 领先记录"""
        if not result.leader_history:
            return ""

        records = build_lead_records(result.leader_history)
        names = {
            "A": self.team_a[0].name if len(self.team_a) == 1 else "A队",
            "B": self.team_b[0].name if len(self.team_b) == 1 else "B队",
        }

        lines = ["\n【领先记录】"]
        for key, label in (("hp", "HP"), ("sp", "SP")):
            data = records[key]
            lines.append(f"\n▶ {label}")
            if data["changes"]:
                for change in data["changes"]:
                    lines.append(
                        f"  第 {change['round']} 回合    {names[change['side']]}领先"
                    )
            else:
                lines.append("  全程持平")

            longest = data["longest"]
            max_gap = data["maxGap"]
            lines.append(
                f"  最长持续领先: {names['A']} {longest['A']} 回合 · "
                f"{names['B']} {longest['B']} 回合"
            )
            lines.append(
                f"  最大领先幅度: {names['A']} {max_gap['A'] * 100:.1f}% · "
                f"{names['B']} {max_gap['B'] * 100:.1f}%"
            )

        return "\n".join(lines)

    def generate_full_report(self, result: "BattleResult") -> str:
        """生成完整战报"""
        # 先使用 Analyzer 获取统计数据
        stats = BattleStats()
        stats.analyze_result(result)

        # 预先按回合分组日志，提高效率
        from collections import defaultdict

        logs_by_round = defaultdict(list)
        for log in result.logs:
            logs_by_round[log.round_num].append(log)

        lines = []
        # 1. 初始
        lines.append(self.generate_initial_report())
        # 2. 回合流水
        for round_num in range(1, result.rounds + 1):
            round_logs = logs_by_round.get(round_num, [])
            report = self.generate_round_report(round_logs, round_num)
            if report:
                lines.append(report)
        # 3. 结果
        lines.append(self.generate_final_report(result))
        # 4. 统计表格
        lines.append(self._format_attack_stats(stats))
        lines.append(self._format_defense_stats(stats))
        lines.append(self._format_clash_stats(stats))

        return "\n".join(lines)

    def _format_attack_stats(self, stats: BattleStats) -> str:
        if not stats.attack_ticks:
            return ""
        lines = []
        lines.append("\n" + "=" * 70)
        lines.append("【攻击频率统计】")
        lines.append("=" * 70)
        lines.append(f"\n  {'武将':<10} {'攻击次数':<10} {'平均攻击间隔(tick)':<20}")
        lines.append(f"  {'-' * 10} {'-' * 10} {'-' * 20}")

        for name, ticks in stats.attack_ticks.items():
            count = len(ticks)
            avg = 0.0
            if count > 1:
                intervals = [ticks[i + 1] - ticks[i] for i in range(count - 1)]
                avg = sum(intervals) / len(intervals)
            lines.append(f"  {name:<10} {count:<10} {avg:>10.1f}")
        lines.append("=" * 70)
        return "\n".join(lines)

    def _format_defense_stats(self, stats: BattleStats) -> str:
        if not stats.defense_stats:
            return ""
        lines = []
        lines.append("\n" + "=" * 70)
        lines.append("【防御统计】")
        lines.append("=" * 70)

        total_rounds = stats.total_rounds or 1

        for name, warrior_stats in stats.defense_stats.items():
            total_defs = sum(s.use_count for s in warrior_stats.values())
            lines.append(f"\n▶ {name} 防御统计:")
            lines.append(f"  总防御次数: {total_defs}")
            lines.append(
                f"  {'防御方式':<8} {'次数':<10} {'占比':<10} {'成功率':<10} {'防御受伤':<12} {'反伤敌方':<12} {'受伤/回合':<10}"
            )
            lines.append(
                f"  {'-' * 8} {'-' * 10} {'-' * 10} {'-' * 10} {'-' * 12} {'-' * 12} {'-' * 10}"
            )

            for dt in ALL_DEFENSE_TYPES:
                ds = warrior_stats[dt]
                use_pct = (ds.use_count / total_defs * 100) if total_defs > 0 else 0
                succ_rate = (
                    (ds.success_count / ds.use_count * 100) if ds.use_count > 0 else 0
                )
                avg_dmg = ds.total_damage_taken / total_rounds

                lines.append(
                    f"  {DEFENSE_TYPE_CN[dt]:<8} {ds.use_count:<10} {use_pct:>6.1f}%   "
                    f"{succ_rate:>6.1f}%   {ds.total_damage_taken:>10.1f}  {ds.total_damage_dealt:>10.1f}  {avg_dmg:>8.1f}"
                )

            # 汇总
            all_dmg_taken = sum(s.total_damage_taken for s in warrior_stats.values())
            all_dmg_dealt = sum(s.total_damage_dealt for s in warrior_stats.values())

            lines.append(
                f"  {'-' * 8} {'-' * 10} {'-' * 10} {'-' * 10} {'-' * 12} {'-' * 12} {'-' * 10}"
            )
            lines.append(
                f"  {'合计':<8} {total_defs:<10} {'100.0%':<10} {'':<10} {all_dmg_taken:>10.1f}  {all_dmg_dealt:>10.1f}  {all_dmg_taken / total_rounds:>8.1f}"
            )

            # 总受伤 (含攻击时)
            total_dmg = stats.warrior_total_damage.get(name, 0)
            att_dmg = total_dmg - all_dmg_taken
            if att_dmg > 0:
                lines.append(f"\n  攻击时受伤(反击/反震): {att_dmg:.1f}")
            lines.append(
                f"  总受伤: {total_dmg:.1f}  (受伤/回合: {total_dmg / total_rounds:.1f})"
            )

        lines.append("=" * 70)
        return "\n".join(lines)

    def _format_clash_stats(self, stats: BattleStats) -> str:
        if stats.total_clashes == 0:
            return ""
        lines = []
        lines.append("\n" + "=" * 70)
        lines.append("【拼刀统计】")
        lines.append("=" * 70)
        lines.append(f"\n总拼刀次数: {stats.total_clashes}")

        lines.append("\n▶ 拼刀详情:")
        for i, rec in enumerate(stats.clash_records, 1):
            lines.append(f"\n  第{i}次拼刀 (回合{rec.round_num}, tick={rec.tick})")
            lines.append(f"    参与者: {', '.join(rec.participants)}")
            for name in rec.participants:
                d = rec.damages.get(name, 0)
                s = rec.sp_costs.get(name, 0)
                lines.append(f"    {name}: HP-{d:.1f}, SP-{s:.1f}")

        lines.append("\n▶ 武将拼刀汇总:")
        lines.append(
            f"  {'武将':<10} {'参与次数':<10} {'总受伤':<12} {'总体力消耗':<12} {'平均受伤/次':<12}"
        )
        lines.append(f"  {'-' * 10} {'-' * 10} {'-' * 12} {'-' * 12} {'-' * 12}")
        for name in stats.warrior_clash_count:
            cnt = stats.warrior_clash_count[name]
            dmg = stats.warrior_clash_damage[name]
            sp = stats.warrior_clash_sp_cost[name]
            avg = dmg / cnt if cnt > 0 else 0
            lines.append(
                f"  {name:<10} {cnt:<10} {dmg:>10.1f}  {sp:>10.1f}  {avg:>10.1f}"
            )

        lines.append("=" * 70)
        return "\n".join(lines)


class AggregateReporter:
    """多场战斗汇总报告生成器"""

    def __init__(self, warrior_a_name: str = "A队", warrior_b_name: str = "B队"):
        self.warrior_a_name = warrior_a_name
        self.warrior_b_name = warrior_b_name
        self.stats = BattleStats()

    def add_battle_result(self, result: "BattleResult") -> None:
        single_stats = BattleStats()
        single_stats.analyze_result(result)
        self.stats.merge(single_stats)

    def generate_aggregate_report(
        self, snapshots_a: List[WarriorSnapshot], snapshots_b: List[WarriorSnapshot]
    ) -> str:
        lines = []
        s = self.stats
        total = s.total_battles
        if total == 0:
            return "无战斗数据"

        lines.append("=" * 70)
        lines.append(f"【{total}次单挑总战报】")
        lines.append("=" * 70)

        # 阵容
        lines.append("\n▶ 对战双方:")
        for ss in snapshots_a:
            lines.append(format_warrior_initial_stats(ss))
        lines.append("  VS")
        for ss in snapshots_b:
            lines.append(format_warrior_initial_stats(ss))

        # 胜负
        lines.append("\n" + "=" * 70)
        lines.append("【胜负统计】")
        lines.append("=" * 70)
        lines.append(f"\n  总场次: {total}")
        lines.append(
            f"  {self.warrior_a_name} 胜: {s.team_a_wins} ({s.team_a_wins / total * 100:.1f}%)"
        )
        lines.append(
            f"  {self.warrior_b_name} 胜: {s.team_b_wins} ({s.team_b_wins / total * 100:.1f}%)"
        )
        lines.append(f"  平局: {s.draws} ({s.draws / total * 100:.1f}%)")
        lines.append(f"\n  平均回合数: {s.total_rounds / total:.1f}")
        lines.append(f"  平均tick数: {s.total_ticks / total:.1f}")

        # 防御统计
        self._append_defense_section(lines, s)
        # 拼刀统计
        self._append_clash_section(lines, s)
        # 伤害统计
        self._append_damage_section(lines, s)
        # 其他统计
        self._append_misc_stats(lines, s)

        return "\n".join(lines)

    def _append_defense_section(self, lines: List[str], s: BattleStats):
        lines.append("\n" + "=" * 70)
        lines.append("【防御方式统计】")
        lines.append("=" * 70)

        all_warriors = sorted(s.defense_stats.keys())
        for name in all_warriors:
            w_stats = s.defense_stats[name]
            total_uses = sum(d.use_count for d in w_stats.values())
            if total_uses == 0:
                continue

            lines.append(f"\n▶ {name} 防御统计 (总次数: {total_uses}):")
            lines.append(
                f"  {'防御方式':<8} {'使用次数':<10} {'占比':<10} {'成功次数':<10} {'成功率':<10}"
            )
            lines.append(f"  {'-' * 8} {'-' * 10} {'-' * 10} {'-' * 10} {'-' * 10}")

            for dt in ALL_DEFENSE_TYPES:
                ds = w_stats[dt]
                use_pct = ds.use_count / total_uses * 100
                succ_rate = (
                    (ds.success_count / ds.use_count * 100) if ds.use_count > 0 else 0
                )
                lines.append(
                    f"  {DEFENSE_TYPE_CN[dt]:<8} {ds.use_count:<10} {use_pct:>6.1f}%   {ds.success_count:<10} {succ_rate:>6.1f}%"
                )

    def _append_clash_section(self, lines: List[str], s: BattleStats):
        if s.total_clashes == 0:
            return
        lines.append("\n" + "=" * 70)
        lines.append("【拼刀统计】")
        lines.append("=" * 70)
        lines.append(f"\n  总拼刀次数: {s.total_clashes}")
        lines.append(f"  平均每场拼刀: {s.total_clashes / s.total_battles:.2f}次")

        lines.append(
            f"\n  {'武将':<10} {'参与次数':<10} {'总受伤':<12} {'总体力消耗':<12} {'平均受伤/次':<12}"
        )
        lines.append(f"  {'-' * 10} {'-' * 10} {'-' * 12} {'-' * 12} {'-' * 12}")
        for name in sorted(s.warrior_clash_count):
            cnt = s.warrior_clash_count[name]
            dmg = s.warrior_clash_damage[name]
            sp = s.warrior_clash_sp_cost[name]
            avg = dmg / cnt if cnt > 0 else 0
            lines.append(
                f"  {name:<10} {cnt:<10} {dmg:>10.1f}  {sp:>10.1f}  {avg:>10.1f}"
            )

    def _append_damage_section(self, lines: List[str], s: BattleStats):
        lines.append("\n" + "=" * 70)
        lines.append("【伤害统计】")
        lines.append("=" * 70)

        # 总受伤
        lines.append(f"\n  {'武将':<10} {'总受伤':<12} {'平均受伤/场':<12}")
        lines.append(f"  {'-' * 10} {'-' * 12} {'-' * 12}")
        for name in sorted(s.warrior_total_damage):
            dmg = s.warrior_total_damage[name]
            lines.append(f"  {name:<10} {dmg:>10.1f}  {dmg / s.total_battles:>10.1f}")

        # 攻防受伤分布
        lines.append("\n  攻击/防御受伤比例:")
        lines.append(
            f"  {'武将':<10} {'攻击时受伤':<12} {'防御时受伤':<12} {'攻击受伤占比':<12}"
        )
        lines.append(f"  {'-' * 10} {'-' * 12} {'-' * 12} {'-' * 12}")

        all_names = set(s.warrior_attack_damage_taken.keys()) | set(
            s.defense_stats.keys()
        )
        for name in sorted(all_names):
            att_dmg = s.warrior_attack_damage_taken.get(name, 0)
            def_dmg = sum(d.total_damage_taken for d in s.defense_stats[name].values())
            total = att_dmg + def_dmg
            if total > 0:
                lines.append(
                    f"  {name:<10} {att_dmg:>10.1f}  {def_dmg:>10.1f}  {att_dmg / total * 100:>8.1f}%"
                )

    def _append_misc_stats(self, lines: List[str], s: BattleStats):
        # 回合数统计
        lines.append("\n" + "=" * 70)
        lines.append("【回合数统计】")
        lines.append("=" * 70)
        min_r = s.min_rounds if s.min_rounds != 999999 else 0
        lines.append(f"\n  最多回合数: {s.max_rounds}")
        lines.append(f"  最少回合数: {min_r}")

        # 胜方状态 (只取部分示例)
        lines.append("\n" + "=" * 70)
        lines.append("【获胜状态统计 (平均值)】")
        lines.append("=" * 70)
        if s.team_a_winner_hp:
            avg_hp = sum(s.team_a_winner_hp) / len(s.team_a_winner_hp)
            lines.append(f"  A队获胜平均剩余HP: {avg_hp:.1f}")
        if s.team_b_winner_hp:
            avg_hp = sum(s.team_b_winner_hp) / len(s.team_b_winner_hp)
            lines.append(f"  B队获胜平均剩余HP: {avg_hp:.1f}")

        lines.append("\n" + "=" * 70)
