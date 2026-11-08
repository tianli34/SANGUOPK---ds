# 文件名: __init__.py
# 用途: 武将对决系统的包初始化文件，导出核心类、函数和常量供外部使用

from src.warrior import Warrior
from src.battle_engine import BattleEngine, BattleResult, BattleOutcome
from src.defense import DefenseResult, process_defense
from src.damage import calculate_base_damage, calculate_final_damage
from src.clash import process_clash, check_clash_condition
from src.skills import Skill, SkillEffect, OpeningApBoost, SKILL_REGISTRY, get_skill
from src.enums import DefenseType
from src.constants import (
    BACKSWING_BAR,
    TICK_RATE,
    CLASH_AP_THRESHOLD,
    BLOCK_K,
    BASE_SP_COST,
    COURAGE_CAP,
    RECOIL_CAP_RATIO,
    MAX_ROUNDS,
)

__all__ = [
    "Warrior",
    "BattleEngine",
    "BattleResult",
    "BattleOutcome",
    "DefenseType",
    "DefenseResult",
    "process_defense",
    "calculate_base_damage",
    "calculate_final_damage",
    "process_clash",
    "check_clash_condition",
    "Skill",
    "SkillEffect",
    "OpeningApBoost",
    "SKILL_REGISTRY",
    "get_skill",
    "BACKSWING_BAR",
    "TICK_RATE",
    "CLASH_AP_THRESHOLD",
    "BLOCK_K",
    "BASE_SP_COST",
    "COURAGE_CAP",
    "RECOIL_CAP_RATIO",
    "MAX_ROUNDS",
]
