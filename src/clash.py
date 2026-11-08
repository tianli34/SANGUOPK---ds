# 文件名: clash.py
# 用途: 拼刀系统模块，处理多个武将同时攻击时的拼刀判定和伤害计算
"""拼刀系统"""

import math
from dataclasses import dataclass
from typing import List, TYPE_CHECKING

from src.constants import CLASH_AP_THRESHOLD

if TYPE_CHECKING:
    from src.warrior import Warrior


@dataclass
class ClashResult:
    """武将拼刀的结果"""

    participants: List["Warrior"]  # 参与拼刀的武将
    damages: dict  # 武将名 -> 受到的伤害
    sp_costs: dict  # 武将名 -> 体力消耗


def check_clash_condition(ready_warriors: List["Warrior"]) -> bool:
    """
    检查是否满足拼刀条件
    - 2个或更多武将准备就绪
    - 行动点数差值 <= 20
    """
    if len(ready_warriors) < 2:
        return False

    ap_values = [w.ap for w in ready_warriors]
    return max(ap_values) - min(ap_values) <= CLASH_AP_THRESHOLD


def calculate_clash_damage(warrior_a: "Warrior", warrior_b: "Warrior") -> tuple:
    """
    计算两个武将之间的拼刀伤害

    冲击力 = √(敌方力量 × 己方力量) × 0.5
    受伤 = 冲击力 × (敌方力量 / 己方力量) × 2
    体力消耗 = 受伤 × 0.3

    返回: (武将A受到的伤害, 武将B受到的伤害, A的体力消耗, B的体力消耗)
    """
    impact = math.sqrt(warrior_a.strength * warrior_b.strength) * 0.5

    # A受到B的伤害
    damage_a = impact * (warrior_b.strength / warrior_a.strength) * 2 * 3.0
    # B受到A的伤害
    damage_b = impact * (warrior_a.strength / warrior_b.strength) * 2 * 3.0

    sp_cost_a = damage_a * 0.3
    sp_cost_b = damage_b * 0.3

    return damage_a, damage_b, sp_cost_a, sp_cost_b


def process_clash(warriors: List["Warrior"]) -> ClashResult:
    """
    处理多个武将之间的拼刀
    每对敌人之间都会相互攻击
    """
    damages = {w.name: 0.0 for w in warriors}
    sp_costs = {w.name: 0.0 for w in warriors}

    # 处理所有武将对
    for i, w1 in enumerate(warriors):
        for w2 in warriors[i + 1 :]:
            if w1.team != w2.team:  # 只在敌人之间拼刀
                dmg_1, dmg_2, sp_1, sp_2 = calculate_clash_damage(w1, w2)
                damages[w1.name] += dmg_1
                damages[w2.name] += dmg_2
                sp_costs[w1.name] += sp_1
                sp_costs[w2.name] += sp_2

    return ClashResult(participants=warriors, damages=damages, sp_costs=sp_costs)
