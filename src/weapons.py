# 文件名: weapons.py
# 用途: 兵器分类系统，定义兵器类别、兵器注册表与兵器相关的攻防规则
"""兵器分类系统"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, FrozenSet, Optional, Tuple

from src.enums import DefenseType


class WeaponCategory(Enum):
    """兵器分类"""

    SPEAR = 1  # 枪与矛（刺击类）
    GREAT_BLADE = 2  # 长柄大刀（劈砍类）
    HALBERD = 3  # 戟（勾刺兼备类）
    HEAVY = 4  # 大斧与长柄锤（重型破甲类）

    @property
    def name_cn(self) -> str:
        return _CATEGORY_NAMES[self]

    @property
    def style_cn(self) -> str:
        return _CATEGORY_STYLES[self]

    @property
    def label(self) -> str:
        return f"{self.name_cn}（{self.style_cn}）"


_CATEGORY_NAMES = {
    WeaponCategory.SPEAR: "枪与矛",
    WeaponCategory.GREAT_BLADE: "长柄大刀",
    WeaponCategory.HALBERD: "戟",
    WeaponCategory.HEAVY: "大斧与长柄锤",
}

_CATEGORY_STYLES = {
    WeaponCategory.SPEAR: "刺击类",
    WeaponCategory.GREAT_BLADE: "劈砍类",
    WeaponCategory.HALBERD: "勾刺兼备类",
    WeaponCategory.HEAVY: "重型破甲类",
}


@dataclass(frozen=True)
class Weapon:
    """具体兵器：名称 + 所属分类 + 可选的单件射程配置"""

    name: str
    category: WeaponCategory
    reach: Optional[int] = None

    @property
    def effective_reach(self) -> int:
        """实际射程：单件配置优先，否则按类别默认"""
        if self.reach is not None:
            return self.reach
        return CATEGORY_DEFAULT_REACH[self.category]

    @property
    def category_label(self) -> str:
        return self.category.label

    @property
    def description(self) -> str:
        return f"{self.name} · {self.category_label}"


# 类别默认射程（格）：枪矛=3 / 长柄刀=2 / 戟=2 / 重型=1
CATEGORY_DEFAULT_REACH: Dict[WeaponCategory, int] = {
    WeaponCategory.SPEAR: 3,
    WeaponCategory.GREAT_BLADE: 2,
    WeaponCategory.HALBERD: 2,
    WeaponCategory.HEAVY: 1,
}

UNARMED_REACH = 1  # 无兵器射程


# 兵器注册表：兵器名 -> 兵器实例
WEAPON_REGISTRY: Dict[str, Weapon] = {
    weapon.name: weapon
    for weapon in (
        Weapon("虎头湛金枪", WeaponCategory.SPEAR),
        Weapon("血煞虎头刀", WeaponCategory.HEAVY),
    )
}


def get_weapon(name: str) -> Weapon:
    """按兵器名获取兵器实例"""
    try:
        return WEAPON_REGISTRY[name]
    except KeyError:
        raise ValueError(f"未知兵器: {name}") from None


# 防守方兵器类别 -> 无条件禁用的防御方式
ALWAYS_FORBIDDEN_DEFENSES: Dict[WeaponCategory, FrozenSet[DefenseType]] = {
    WeaponCategory.SPEAR: frozenset({DefenseType.BLOCK}),
}

# (防守方类别, 攻击方类别) -> 该对阵下禁用的防御方式
MATCHUP_FORBIDDEN_DEFENSES: Dict[
    Tuple[WeaponCategory, WeaponCategory], FrozenSet[DefenseType]
] = {
    (WeaponCategory.HEAVY, WeaponCategory.SPEAR): frozenset({DefenseType.BLOCK}),
}


def is_defense_forbidden(
    defender_weapon: Optional[Weapon],
    attacker_weapon: Optional[Weapon],
    defense_type: DefenseType,
) -> bool:
    """判断当前兵器对阵是否禁用某种防御方式

    规则：
    - 1 类（枪与矛）不能格挡；
    - 4 类（大斧与长柄锤）不能格挡 1 类的攻击。
    未装备兵器的武将不受兵器规则限制。
    """
    if defender_weapon is None:
        return False

    forbidden = ALWAYS_FORBIDDEN_DEFENSES.get(defender_weapon.category)
    if forbidden and defense_type in forbidden:
        return True

    if attacker_weapon is not None:
        matchup = MATCHUP_FORBIDDEN_DEFENSES.get(
            (defender_weapon.category, attacker_weapon.category)
        )
        if matchup and defense_type in matchup:
            return True

    return False
