# 文件名: warrior.py
# 用途: 武将类定义文件，包含武将的属性、状态管理和AI决策逻辑
"""武将对决系统的武将类"""
import math
import random
from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.constants import (
    WINDUP_BAR,
    BACKSWING_BAR,
    COURAGE_CAP,
    SP_EXPANSION_FACTOR,
    HP_COEFFICIENT,
    DEFENDER_AP_LOSS_RATIO,
    ATTACKER_BACKSWING_LOSS_RATIO,
)
from src.enums import DefenseType, AttackPhase

if TYPE_CHECKING:
    from src.skills import Skill


@dataclass
class WarriorSnapshot:
    """武将状态快照"""

    name: str
    team: str
    hp: float
    hp_real: float
    hp_percent: float
    sp: float
    sp_real: int
    sp_percent: float
    courage: int
    is_alive: bool
    # 基础属性
    martialarts: int
    agility: int
    strength: int
    # 衍生属性
    attack_power: float
    defense_power: float
    attack_speed: float
    # 攻击阶段
    attack_phase: AttackPhase
    ap: float
    # 已装备特技（名称+效果描述）
    skills: tuple = ()


class Warrior:
    """武将对决系统中的武将"""

    def __init__(
        self,
        name: str,
        team: str,
        martialarts: int = 50,
        agility: int = 50,
        strength: int = 50,
        courage: int = 50,
        sp: int = 50,
    ):
        self.name = name
        self.team = team

        # 初始化武将的运行时状态
        self.init_sp = sp  # 初始体力
        self.sp_real = sp * SP_EXPANSION_FACTOR  # 体力上限
        self.sp = self.sp_real  # 当前体力
        self.hp_real = self.sp_real * HP_COEFFICIENT  # 最大生命值
        self.hp = self.hp_real  # 当前生命值
        self.ap = 0.0  # 行动点数
        self.backswing_extra = 0.0  # 攻方受伤后追加的后摇阈值
        self.is_alive = True  # 存活状态
        self.attack_count = 0  # 攻击次数
        self.ap_bonus_count = 0  # 后手AP基准加成的生效次数（每场至多1次）
        self.skills: list = []  # 已装备特技
        
        # 攻击阶段状态
        self.attack_phase = AttackPhase.WINDUP  # 初始为前摇阶段

        # 初始化武将的运行时状态_基础属性(四维属性)
        self.martialarts_init = max(1, martialarts)  # 武艺，最小值为1
        self.agility_init = max(1, agility)  # 初始敏捷，最小值为1
        self.strength_init = max(1, strength)  # 初始力量，最小值为1
        self.courage = max(1, courage)  # 胆气，最小值为1

    def snapshot(self) -> WarriorSnapshot:
        """获取武将当前状态快照"""
        return WarriorSnapshot(
            name=self.name,
            team=self.team,
            hp=self.hp,
            hp_real=self.hp_real,
            hp_percent=self.hp_percent,
            sp=self.sp,
            sp_real=self.sp_real,
            sp_percent=self.sp_percent,
            courage=self.courage,
            is_alive=self.is_alive,
            martialarts=self.martialarts,
            agility=self.agility,
            strength=self.strength,
            attack_power=self.attack_power,
            defense_power=self.defense_power,
            attack_speed=self.attack_speed,
            attack_phase=self.attack_phase,
            ap=self.ap,
            skills=self.skill_descriptions,
        )
    
    @property
    def martialarts(self) -> int:
        """根据体力百分比动态计算武艺,每次都要基于初始武艺和当前体力计算当前武艺"""
        return max(1, int(self.martialarts_init *(0.6+ (min(self.sp_percent, 0.8)/0.8)*0.4)))

    @property
    def strength(self) -> int:
        """根据体力百分比动态计算力量,每次都要基于初始力量和当前体力计算当前力量"""
        return max(1, int(self.strength_init *(0.3+0.7*math.sqrt(self.sp_percent))))
    
    @property
    def agility(self) -> int:
        """根据体力百分比动态计算敏捷,每次都要基于初始敏捷和当前体力计算当前敏捷"""
        return max(1, int(self.agility_init *(0.1+0.9*math.sqrt(self.sp_percent))))

    @property
    def attack_speed(self) -> float:
        """根据敏捷和体力比例计算攻击速度"""
        return 50 + self.agility * 2

    @property
    def attack_power(self) -> float:
        """计算攻击力: 力量×武艺"""
        return math.sqrt(self.strength * self.martialarts)*2

    @property
    def defense_power(self) -> float:
        """计算防御力: 力量×初始体力"""
        return math.sqrt(self.strength * self.init_sp)

    @property
    def base_impact(self) -> float:
        """计算基础冲击力: 力量×0.1"""
        return self.strength * 0.1

    @property
    def sp_percent(self) -> float:
        """当前体力百分比"""
        return self.sp / self.sp_real

    @property
    def sp_raw(self) -> float:
        """当前体力原始值（未膨胀）"""
        return self.sp / SP_EXPANSION_FACTOR

    @property
    def hp_percent(self) -> float:
        """当前生命值百分比"""
        return self.hp / self.hp_real

    @property
    def ap_percent(self) -> float:
        """当前行动点数百分比（前摇+后摇统一归一化；未攻击且加成未生效过时附加后摇基准）"""
        denominator = WINDUP_BAR + BACKSWING_BAR
        has_bonus = self.attack_count == 0 and self.ap_bonus_count == 0
        offset = BACKSWING_BAR if has_bonus else 0.0
        return (self.ap + offset) / denominator

    def consume_ap_bonus(self) -> None:
        """结算一次后手AP基准加成：未攻击过且未生效过才计数，本场至多一次"""
        if self.attack_count == 0 and self.ap_bonus_count == 0:
            self.ap_bonus_count = 1

    def tick_ap(self, tick_rate: float) -> None:
        """根据攻击速度累积行动点数"""
        if self.is_alive:
            self.ap += self.attack_speed * tick_rate

    def gain_ap(self, amount: float) -> None:
        """直接增加行动点数（供特技等效果使用）"""
        self.ap += amount

    def equip_skill(self, skill: "Skill") -> bool:
        """装备特技；同 id 特技只能装备一个"""
        if any(s.skill_id == skill.skill_id for s in self.skills):
            return False
        self.skills.append(skill)
        return True

    def unequip_skill(self, skill_id: str) -> bool:
        """卸下指定特技，返回是否卸下成功"""
        for index, skill in enumerate(self.skills):
            if skill.skill_id == skill_id:
                del self.skills[index]
                return True
        return False

    @property
    def skill_descriptions(self) -> tuple:
        """特技展示文本，用于战报初始属性"""
        return tuple(f"{s.name}（{s.description}）" for s in self.skills)

    def can_attack(self) -> bool:
        """检查是否可以发起攻击（前摇阶段且达到前摇阈值）"""
        return (
            self.is_alive
            and self.attack_phase == AttackPhase.WINDUP
            and self.ap >= WINDUP_BAR
        )

    def is_in_backswing(self) -> bool:
        """检查是否处于后摇阶段"""
        return self.attack_phase == AttackPhase.BACKSWING

    def start_attack(self) -> None:
        """开始攻击，进入攻击阶段"""
        self.attack_phase = AttackPhase.ATTACK
        self.ap = 0.0  # 重置AP，开始累积后摇
        self.attack_count += 1

    def finish_attack(self) -> None:
        """攻击完成，进入后摇阶段"""
        self.attack_phase = AttackPhase.BACKSWING

    def finish_backswing(self) -> None:
        """后摇完成，进入前摇阶段"""
        self.attack_phase = AttackPhase.WINDUP
        self.ap = 0.0  # 重置AP，开始累积前摇
        self.backswing_extra = 0.0  # 后摇结束，追加阈值失效

    def check_backswing_complete(self) -> bool:
        """检查后摇是否完成"""
        return (
            self.attack_phase == AttackPhase.BACKSWING
            and self.ap >= BACKSWING_BAR + self.backswing_extra
        )

    def apply_defender_damage_penalty(self, damage: float) -> None:
        """守方受伤：按受伤值扣除当前AP"""
        self.ap = max(0.0, self.ap - damage * DEFENDER_AP_LOSS_RATIO)

    def apply_attacker_damage_penalty(self, damage: float) -> None:
        """攻方受伤：延长本次后摇的AP阈值（同一后摇周期内多次受伤累加）"""
        self.backswing_extra += damage * ATTACKER_BACKSWING_LOSS_RATIO

    def reset_ap(self) -> None:
        """攻击后重置行动点数（兼容旧代码）"""
        self.ap = 0.0

    def take_damage(self, damage: float) -> None:
        """对武将造成伤害"""
        self.hp = max(0, self.hp - damage)
        if self.hp <= 0:
            self.is_alive = False

    def consume_sp(self, amount: float) -> None:
        """消耗体力"""
        self.sp = max(0, self.sp - amount)

    def attack_sp_cost(self) -> int:
        return int(((10 + self.strength * 0.1) / (1 + self.martialarts * 0.01 + self.agility * 0.005) * (1.6 - self.courage* 0.8/120))/math.sqrt(max(0.001, self.hp_percent)))

    def modify_courage(self, amount: int) -> None:
        """在限制范围内修改胆气"""
        self.courage = max(1, min(COURAGE_CAP, self.courage + amount))

    def choose_defense(self) -> DefenseType:
        """AI根据加权属性选择防御类型"""

        weights = {
            DefenseType.BLOCK: self.strength * 0.6 + self.sp_percent * 100 * 0.4,
            DefenseType.PARRY: self.martialarts * 0.7 + self.agility * 0.3,
            DefenseType.DODGE: self.agility * 0.7 + self.martialarts * 0.2 + abs(self.courage - 80) * 0.2,
            DefenseType.COUNTER: (self.courage * 0.7 + self.martialarts * 0.3) * (1 - self.hp_percent),
        }

        total = sum(weights.values())
        roll = random.uniform(0, total)
        cumulative = 0.0

        for defense_type, weight in weights.items():
            cumulative += weight
            if roll <= cumulative:
                return defense_type

        return DefenseType.BLOCK

    def __repr__(self) -> str:
        return f"Warrior({self.name}, HP={self.hp:.0f}, SP={self.sp:.0f}, AP={self.ap:.0f})"
