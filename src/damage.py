# 文件名: damage.py
# 用途: 伤害计算模块，负责计算基础伤害、伤害倍率和最终伤害值
"""伤害计算模块"""

import random
from typing import TYPE_CHECKING

from src.constants import ARMOR_PENETRATION

if TYPE_CHECKING:
    from src.warrior import Warrior


def calculate_base_damage(attacker: "Warrior", defender: "Warrior") -> float:
    """
    计算基础物理伤害
    物理伤害 = max(0, 攻击力 - 防御力 × 破甲系数)
    """
    physical = max(
        0, attacker.attack_power - defender.defense_power * ARMOR_PENETRATION
    )
    return physical + attacker.base_impact


def calculate_damage_multiplier(
    attacker: "Warrior", defender: "Warrior", base_multiplier: float = 1.0
) -> float:
    """
    根据条件计算总伤害倍率

    倍率包括:
    - 士气碾压(攻方胆气>80, 守方胆气<30): 1.5×
    """
    multiplier = base_multiplier

    if attacker.courage > 80 and defender.courage < 30:
        multiplier *= 1.5

    return multiplier


def calculate_final_damage(
    attacker: "Warrior", defender: "Warrior", base_multiplier: float = 1.0
) -> float:
    """
    计算包含所有修饰符的最终伤害
    最终伤害 = 基础伤害× 倍率 × 随机浮动(0.95~1.05)
    """
    base = calculate_base_damage(attacker, defender)
    multiplier = calculate_damage_multiplier(attacker, defender, base_multiplier)
    variance = random.uniform(0.95, 1.05)

    return base * multiplier * variance
