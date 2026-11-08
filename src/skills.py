# 文件名: skills.py
# 用途: 特技系统模块，定义可装备/卸下的特技及其触发时机
"""特技系统"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, Optional, Type

if TYPE_CHECKING:
    from src.battle_engine import BattleEngine
    from src.warrior import Warrior


@dataclass
class SkillEffect:
    """特技发动结果，description 会直接写入战报"""

    description: str
    details: dict = field(default_factory=dict)


class Skill:
    """特技基类

    特技可随时通过 Warrior.equip_skill() 装备、Warrior.unequip_skill() 卸下。
    战斗引擎在对应时机调用钩子，钩子返回 SkillEffect 即代表特技起了作用，
    该效果会被记录进战报。
    """

    skill_id: str = ""
    name: str = ""
    description: str = ""

    def on_battle_start(
        self, warrior: "Warrior", engine: "BattleEngine"
    ) -> Optional[SkillEffect]:
        """战斗正式开始（第 1 回合第一次行动前）触发"""
        return None


class OpeningApBoost(Skill):
    """开局AP+50"""

    skill_id = "opening_ap_50"
    name = "先声夺人"
    description = "开局行动点数 +50"

    def __init__(self, amount: int = 50):
        self.amount = amount

    def on_battle_start(self, warrior: "Warrior", engine: "BattleEngine"):
        ap_before = warrior.ap
        warrior.gain_ap(self.amount)
        return SkillEffect(
            f"{warrior.name} 的特技【{self.name}】发动：AP {ap_before:.0f} → "
            f"{warrior.ap:.0f}（+{self.amount}）",
            {
                "skill_id": self.skill_id,
                "skill": self.name,
                "warrior": warrior.name,
                "amount": self.amount,
                "ap_before": ap_before,
                "ap_after": warrior.ap,
            },
        )


# 特技注册表：skill_id -> 特技类
SKILL_REGISTRY: Dict[str, Type[Skill]] = {
    OpeningApBoost.skill_id: OpeningApBoost,
}


def get_skill(skill_id: str) -> Skill:
    """按 skill_id 创建特技实例"""
    try:
        return SKILL_REGISTRY[skill_id]()
    except KeyError:
        raise ValueError(f"未知特技: {skill_id}") from None
