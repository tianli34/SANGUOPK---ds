# 文件名: skills.py
# 用途: 特技系统模块，定义通用/专属特技及其触发时机与开关
"""特技系统

特技分为两类：
- 通用特技：任何武将都可以装备；
- 专属特技：带有 owner，只有对应武将可以装备。

每个特技实例都带 enabled 开关。关闭后的特技仍保留在装备栏中，
但战斗引擎不会再调用它的任何钩子，效果等同于未装备。
"""

import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, Optional, Tuple, Type

if TYPE_CHECKING:
    from src.battle_engine import BattleEngine
    from src.warrior import Warrior

GENERIC = "通用"
EXCLUSIVE = "专属"


@dataclass
class SkillEffect:
    """特技发动结果，description 会直接写入战报"""

    description: str
    details: dict = field(default_factory=dict)


class Skill:
    """特技基类

    特技可随时通过 Warrior.equip_skill() 装备、Warrior.unequip_skill() 卸下，
    并通过 Warrior.set_skill_enabled() / Warrior.toggle_skill() 切换开关。
    战斗引擎只对开启状态的特技调用钩子，钩子返回 SkillEffect 即代表特技起了作用，
    该效果会被记录进战报。
    """

    skill_id: str = ""
    name: str = ""
    description: str = ""
    category: str = GENERIC
    owner: Optional[str] = None  # 专属特技归属武将；通用特技为 None

    def __init__(self) -> None:
        self.enabled = True

    @property
    def is_exclusive(self) -> bool:
        return self.category == EXCLUSIVE

    @property
    def display_text(self) -> str:
        """战报/面板展示文本"""
        state = "" if self.enabled else "，已关闭"
        return f"[{self.category}] {self.name}（{self.description}{state}）"

    def to_dict(self) -> dict:
        """结构化展示信息（供网页导出）"""
        return {
            "id": self.skill_id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "owner": self.owner,
            "enabled": self.enabled,
        }

    def can_equip(self, warrior: "Warrior") -> bool:
        """专属特技只能由归属武将装备"""
        return self.owner is None or self.owner == warrior.name

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)

    def toggle(self) -> bool:
        self.enabled = not self.enabled
        return self.enabled

    def on_battle_start(
        self, warrior: "Warrior", engine: "BattleEngine"
    ) -> Optional[SkillEffect]:
        """战斗正式开始（第 1 回合第一次行动前）触发"""
        return None

    def on_round_start(
        self, warrior: "Warrior", engine: "BattleEngine", round_num: int
    ) -> Optional[SkillEffect]:
        """每个回合开始时触发（含第 1 回合）"""
        return None

    def on_toggle(self, warrior: "Warrior", enabled: bool) -> None:
        """开关状态变化时触发，供需要即时生效/撤销的特技覆写"""
        return None

    def on_unequip(self, warrior: "Warrior") -> None:
        """卸下特技时触发，供需要清理临时状态的特技覆写"""
        return None

    def damage_dealt_multiplier(self, warrior: "Warrior", round_num: int) -> float:
        """本次造成伤害的倍率（只作用于该武将打出的伤害）"""
        return 1.0

    def courage_floor(self, warrior: "Warrior") -> Optional[int]:
        """胆气下限；返回 None 表示不限制"""
        return None


class CourageFloor80(Skill):
    """胆气维持不低于 80"""

    skill_id = "courage_floor_80"
    name = "临危不惧"
    description = "胆气始终不低于 80"
    category = GENERIC
    floor = 80

    def courage_floor(self, warrior: "Warrior") -> Optional[int]:
        return self.floor

    def on_battle_start(self, warrior: "Warrior", engine: "BattleEngine"):
        courage_before = warrior.courage
        if not warrior.enforce_courage_floor():
            return None
        return SkillEffect(
            f"{warrior.name} 的特技【{self.name}】发动：胆气 {courage_before} → "
            f"{warrior.courage}（下限 {self.floor}）",
            {
                "skill_id": self.skill_id,
                "skill": self.name,
                "warrior": warrior.name,
                "courage_before": courage_before,
                "courage_after": warrior.courage,
                "floor": self.floor,
            },
        )


class GuanYuWusheng(Skill):
    """关羽专属：武圣

    开局行动点数 +80；前 5 回合：力量×2、敏捷×1.5、武艺=100，
    造成伤害在 1.5~2.5 倍间浮动；第 6 回合开始时恢复原有属性。
    """

    skill_id = "guan_yu_wusheng"
    name = "武圣"
    description = (
        "开局行动点数 +80；前 5 回合力量×2、敏捷×1.5、武艺=100，"
        "造成伤害×1.5~2.5；第 6 回合起恢复常态"
    )
    category = EXCLUSIVE
    owner = "关羽"
    buff_rounds = 5
    ap_boost = 80

    def __init__(self) -> None:
        super().__init__()
        self._originals: Optional[Tuple[int, int, int]] = None

    def on_battle_start(self, warrior: "Warrior", engine: "BattleEngine"):
        ap_before = warrior.ap
        warrior.gain_ap(self.ap_boost)
        return SkillEffect(
            f"{warrior.name} 的特技【{self.name}】发动：AP {ap_before:.0f} → "
            f"{warrior.ap:.0f}（+{self.ap_boost}）",
            {
                "skill_id": self.skill_id,
                "skill": self.name,
                "warrior": warrior.name,
                "amount": self.ap_boost,
                "ap_before": ap_before,
                "ap_after": warrior.ap,
            },
        )

    @property
    def is_active(self) -> bool:
        return self._originals is not None

    def _apply(self, warrior: "Warrior") -> None:
        self._originals = (
            warrior.strength_init,
            warrior.agility_init,
            warrior.martialarts_init,
        )
        warrior.strength_init = self._originals[0] * 2
        warrior.agility_init = int(round(self._originals[1] * 1.5))
        warrior.martialarts_init = 100

    def _restore(self, warrior: "Warrior") -> None:
        if self._originals is None:
            return
        (
            warrior.strength_init,
            warrior.agility_init,
            warrior.martialarts_init,
        ) = self._originals
        self._originals = None

    def on_round_start(
        self, warrior: "Warrior", engine: "BattleEngine", round_num: int
    ) -> Optional[SkillEffect]:
        if round_num <= self.buff_rounds:
            if self.is_active:
                return None
            strength_before = warrior.strength_init
            agility_before = warrior.agility_init
            martialarts_before = warrior.martialarts_init
            self._apply(warrior)
            return SkillEffect(
                f"{warrior.name} 的特技【{self.name}】发动：力量 "
                f"{strength_before:g}→{warrior.strength_init:g}、敏捷 "
                f"{agility_before:g}→{warrior.agility_init:g}、武艺 "
                f"{martialarts_before:g}→{warrior.martialarts_init:g}，"
                f"造成伤害 ×1.5~2.5（前 {self.buff_rounds} 回合）",
                {
                    "skill_id": self.skill_id,
                    "skill": self.name,
                    "warrior": warrior.name,
                    "strength_before": strength_before,
                    "strength_after": warrior.strength_init,
                    "agility_before": agility_before,
                    "agility_after": warrior.agility_init,
                    "martialarts_before": martialarts_before,
                    "martialarts_after": warrior.martialarts_init,
                    "buff_rounds": self.buff_rounds,
                },
            )

        if not self.is_active:
            return None

        strength_before = warrior.strength_init
        agility_before = warrior.agility_init
        martialarts_before = warrior.martialarts_init
        self._restore(warrior)
        return SkillEffect(
            f"{warrior.name} 的特技【{self.name}】结束：第 {round_num} 回合起"
            f"恢复常态（力量 {strength_before:g}→{warrior.strength_init:g}、敏捷 "
            f"{agility_before:g}→{warrior.agility_init:g}、武艺 "
            f"{martialarts_before:g}→{warrior.martialarts_init:g}）",
            {
                "skill_id": self.skill_id,
                "skill": self.name,
                "warrior": warrior.name,
                "strength_before": strength_before,
                "strength_after": warrior.strength_init,
                "agility_before": agility_before,
                "agility_after": warrior.agility_init,
                "martialarts_before": martialarts_before,
                "martialarts_after": warrior.martialarts_init,
            },
        )

    def damage_dealt_multiplier(self, warrior: "Warrior", round_num: int) -> float:
        if self.is_active and round_num <= self.buff_rounds:
            return random.uniform(1.5, 2.5)
        return 1.0

    def on_toggle(self, warrior: "Warrior", enabled: bool) -> None:
        if not enabled:
            self._restore(warrior)

    def on_unequip(self, warrior: "Warrior") -> None:
        self._restore(warrior)


# 特技注册表：skill_id -> 特技类
SKILL_REGISTRY: Dict[str, Type[Skill]] = {
    CourageFloor80.skill_id: CourageFloor80,
    GuanYuWusheng.skill_id: GuanYuWusheng,
}


def get_skill(skill_id: str) -> Skill:
    """按 skill_id 创建特技实例"""
    try:
        return SKILL_REGISTRY[skill_id]()
    except KeyError:
        raise ValueError(f"未知特技: {skill_id}") from None
