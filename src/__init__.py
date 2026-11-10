# 文件名: __init__.py
# 用途: 武将对决系统的包初始化文件，导出核心类、函数和常量供外部使用

from src.warrior import Warrior
from src.battle_engine import BattleEngine, BattleResult, BattleOutcome
from src.defense import DefenseResult, process_defense
from src.damage import calculate_base_damage, calculate_final_damage
from src.clash import process_clash, check_clash_condition
from src.skills import Skill, SkillEffect, OpeningApBoost, SKILL_REGISTRY, get_skill
from src.weapons import (
    Weapon,
    WeaponCategory,
    WEAPON_REGISTRY,
    get_weapon,
    is_defense_forbidden,
    CATEGORY_DEFAULT_REACH,
    UNARMED_REACH,
)
from src.map import (
    BattleMap,
    MAP_REGISTRY,
    DEFAULT_MAP_NAME,
    get_map,
    get_default_map,
    register_map,
    chebyshev_distance,
)
from src.enums import DefenseType, Terrain
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
    "Weapon",
    "WeaponCategory",
    "WEAPON_REGISTRY",
    "get_weapon",
    "is_defense_forbidden",
    "CATEGORY_DEFAULT_REACH",
    "UNARMED_REACH",
    "BattleMap",
    "MAP_REGISTRY",
    "DEFAULT_MAP_NAME",
    "get_map",
    "get_default_map",
    "register_map",
    "chebyshev_distance",
    "Terrain",
    "BACKSWING_BAR",
    "TICK_RATE",
    "CLASH_AP_THRESHOLD",
    "BLOCK_K",
    "BASE_SP_COST",
    "COURAGE_CAP",
    "RECOIL_CAP_RATIO",
    "MAX_ROUNDS",
]
