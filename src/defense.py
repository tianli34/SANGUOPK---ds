# 文件名: defense.py
# 用途: 防御系统模块，处理格挡、卸力、闪避、反击等防御动作的判定和结果计算
"""对决防御系统"""

import random
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.constants import DEFENSE_PARAMS, RECOIL_CAP_RATIO
from src.enums import DefenseType

if TYPE_CHECKING:
    from src.warrior import Warrior


@dataclass
class DefenseResult:
    """防御动作的结果"""

    defense_type: DefenseType  # 防御类型
    success: bool  # 是否成功
    damage_to_defender: float = 0.0  # 防守方受到的伤害
    damage_to_attacker: float = 0.0  # 攻击方受到的伤害(反击/格挡反震)
    defender_sp_cost: float = 0.0  # 防守方体力消耗
    attacker_sp_cost: float = 0.0  # 攻击方体力消耗
    defender_courage_change: int = 0  # 防守方胆气变化
    damage_multiplier: float = 1.0  # 伤害倍率


def calculate_defense_rate(defense_type: DefenseType, defender: "Warrior", attacker: "Warrior") -> float:
    """计算防御动作的成功率"""
    params = DEFENSE_PARAMS[defense_type.value]
    ap_percent = defender.ap_percent

    if defense_type == DefenseType.BLOCK:
        diff = defender.strength - attacker.strength
        rate = ap_percent * 2.5 + diff * params["rate_factor"]

    elif defense_type == DefenseType.PARRY:
        diff = defender.martialarts - attacker.strength
        rate = ap_percent *2 + diff * params["rate_factor"]

    elif defense_type == DefenseType.DODGE:
        diff = defender.agility - attacker.martialarts
        rate = ap_percent/0.6 + diff * params["rate_factor"]

    elif defense_type == DefenseType.COUNTER:
        defender_composite = defender.martialarts * 0.7 + defender.agility * 0.3
        attacker_composite = attacker.agility * 0.6 + attacker.martialarts * 0.2 + attacker.courage * 0.2
        diff = defender_composite - attacker_composite
        rate = ap_percent + diff * params["rate_factor"]
    else:
        rate = 0.5

    return max(0.05, min(0.95, rate))


def process_block(defender: "Warrior", attacker: "Warrior") -> DefenseResult:
    """处理格挡(硬接)防御"""
    params = DEFENSE_PARAMS["block"]

    # 冲击力 = √(攻方力量 × 守方力量) × impact_k
    impact = math.sqrt(attacker.strength * defender.strength) * params["impact_k"]

    # 原伤害计算
    original_defender_damage = impact * (attacker.strength / defender.strength)
    original_recoil_damage = impact * (defender.strength / attacker.strength) * params["recoil_mult"]
    max_recoil = attacker.attack_power * RECOIL_CAP_RATIO
    original_recoil_damage = min(original_recoil_damage, max_recoil)

    # 格挡成功判定
    success_rate = calculate_defense_rate(DefenseType.BLOCK, defender, attacker)
    success = random.random() < success_rate

    if success:
        defender_damage = original_defender_damage * params["success_damage_mult"]
        recoil_damage = original_recoil_damage
        courage_change = params["success_courage"]
    else:
        defender_damage = original_defender_damage * params["fail_damage_mult"]
        recoil_damage = 0.0
        courage_change = params["fail_courage"]

    # 双方体力消耗 = 受伤值 × sp_cost_ratio
    defender_sp_cost = defender_damage * params["sp_cost_ratio"]
    attacker_sp_cost = recoil_damage * params["sp_cost_ratio"]

    return DefenseResult(
        defense_type=DefenseType.BLOCK,
        success=success,
        damage_to_defender=defender_damage,
        damage_to_attacker=recoil_damage,
        defender_sp_cost=defender_sp_cost,
        attacker_sp_cost=attacker_sp_cost,
        defender_courage_change=courage_change,
        damage_multiplier=params["success_damage_mult"] if success else params["fail_damage_mult"],
    )


def process_defense(
    defense_type: DefenseType,
    defender: "Warrior",
    attacker: "Warrior",
    base_damage: float,
) -> DefenseResult:
    """处理防御动作并返回结果"""
    if defense_type == DefenseType.BLOCK:
        return process_block(defender, attacker)

    params = DEFENSE_PARAMS[defense_type.value]
    success_rate = calculate_defense_rate(defense_type, defender, attacker)
    success = random.random() < success_rate

    if success:
        result = DefenseResult(
            defense_type=defense_type,
            success=True,
            damage_to_defender=0.0,
            damage_to_attacker=0.0,
            defender_sp_cost=params["success_sp_cost"],
            attacker_sp_cost=0.0,
            defender_courage_change=params["success_courage"],
            damage_multiplier=0.0,
        )

        # 反击成功：防守方受到40%伤害，对攻击者造成1.5倍伤害
        if defense_type == DefenseType.COUNTER:
            result.damage_to_defender = base_damage * 0.4
            result.damage_to_attacker = base_damage * 1.5
            result.damage_multiplier = 0.5

        return result
    else:
        result = DefenseResult(
            defense_type=defense_type,
            success=False,
            damage_to_defender=base_damage * params["fail_damage_mult"],
            damage_to_attacker=0.0,
            defender_sp_cost=params["fail_sp_cost"],
            attacker_sp_cost=0.0,
            defender_courage_change=params["fail_courage"],
            damage_multiplier=params["fail_damage_mult"],
        )

        # 反击失败：对攻击者造成20%伤害
        if defense_type == DefenseType.COUNTER:
            result.damage_to_attacker = base_damage * 0.2

        return result
