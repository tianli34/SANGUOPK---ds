# 文件名: warrior.py
# 用途: 武将类定义文件，包含武将的属性、状态管理和AI决策逻辑
"""武将对决系统的武将类"""
import math
import random
from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional, Tuple

from src.constants import (
    WINDUP_BAR,
    BACKSWING_BAR,
    COURAGE_CAP,
    SP_EXPANSION_FACTOR,
    HP_COEFFICIENT,
    DEFENDER_AP_LOSS_RATIO,
    ATTACKER_BACKSWING_LOSS_RATIO,
    MOVE_SPEED_BASE,
    MOVE_CELL_PROGRESS,
    SPEAR_BLOCK_WEIGHT_MA_FACTOR,
    SPEAR_BLOCK_WEIGHT_BASE,
)
from src.enums import DefenseType, AttackPhase
from src.weapons import UNARMED_REACH, WeaponCategory

if TYPE_CHECKING:
    from src.skills import Skill
    from src.weapons import Weapon


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
    # 已装备特技的结构化信息（分类、归属、开关状态）
    skill_infos: tuple = ()
    # 兵器
    weapon_name: str = ""
    weapon_category: Optional[int] = None
    weapon_category_label: str = ""
    # 射程与站位（无地图的战斗 position 为 None；有地图时为浮点格坐标）
    reach: int = UNARMED_REACH
    position: Optional[Tuple[float, float]] = None


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
        weapon: Optional["Weapon"] = None,
    ):
        self.name = name
        self.team = team
        self.weapon = weapon

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

        # 空间状态（由战斗引擎布阵/驱动，无地图时保持 None/空）
        self.position: Optional[Tuple[float, float]] = None  # 浮点站位（格为单位）
        self.move_path: List[Tuple[int, int]] = []  # AI 剩余路点（格子），走到格心
        self.manual_moving = False  # 手动连续移动中（没有路点）

        # 初始化武将的运行时状态_基础属性(四维属性)
        self.martialarts_init = max(1, martialarts)  # 武艺，最小值为1
        self.agility_init = max(1, agility)  # 初始敏捷，最小值为1
        self.strength_init = max(1, strength)  # 初始力量，最小值为1
        self.courage = max(1, min(COURAGE_CAP, courage))  # 胆气，限制在 1~上限之间

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
            skill_infos=self.skill_infos,
            weapon_name=self.weapon.name if self.weapon else "",
            weapon_category=self.weapon.category.value if self.weapon else None,
            weapon_category_label=self.weapon.category_label if self.weapon else "",
            reach=self.reach,
            position=self.position,
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
    def reach(self) -> int:
        """攻击射程（格）：兵器射程，无兵器为 1"""
        return self.weapon.effective_reach if self.weapon else UNARMED_REACH

    @property
    def move_speed(self) -> float:
        """移动速度：基础值 + 当前敏捷（随体力衰减）"""
        return MOVE_SPEED_BASE + self.agility

    @property
    def move_speed_cells(self) -> float:
        """移动速度换算为格/秒"""
        return self.move_speed / MOVE_CELL_PROGRESS

    @property
    def is_moving(self) -> bool:
        """是否正在移动（AI 路点或手动连续移动）"""
        return bool(self.move_path) or self.manual_moving

    def begin_move(self, path: List[Tuple[int, int]]) -> bool:
        """开始沿路点移动：起手打断前摇（AP 归零后重新累积）；后摇期间锁定站位不能移动"""
        if not self.is_alive or self.is_in_backswing() or not path:
            return False
        self.ap = 0.0  # 起手移动打断前摇，AP 从零开始重新积累
        self.move_path = list(path)
        self.manual_moving = False
        return True

    def begin_manual_move(self) -> bool:
        """开始手动连续移动：起手打断前摇（AP 归零后重新累积）；后摇期间锁定站位不能移动"""
        if not self.is_alive or self.is_in_backswing():
            return False
        if not self.manual_moving:
            self.ap = 0.0  # 起手移动打断前摇，AP 从零开始重新积累
            self.manual_moving = True
        return True

    def stop_move(self) -> None:
        """停止移动：清空路点与手动移动状态"""
        self.move_path = []
        self.manual_moving = False

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
        """根据攻击速度累积行动点数（移动中同样累积，但移动中仍不能出手）"""
        if self.is_alive:
            self.ap += self.attack_speed * tick_rate

    def gain_ap(self, amount: float) -> None:
        """直接增加行动点数（供特技等效果使用）"""
        self.ap += amount

    def equip_skill(self, skill: "Skill") -> bool:
        """装备特技；同 id 只能装备一个，专属特技只能由归属武将装备"""
        if not skill.can_equip(self):
            return False
        if any(s.skill_id == skill.skill_id for s in self.skills):
            return False
        self.skills.append(skill)
        self.enforce_courage_floor()
        return True

    def unequip_skill(self, skill_id: str) -> bool:
        """卸下指定特技，返回是否卸下成功"""
        for index, skill in enumerate(self.skills):
            if skill.skill_id == skill_id:
                self.skills[index].on_unequip(self)
                del self.skills[index]
                return True
        return False

    @property
    def active_skills(self) -> list:
        """当前开启的特技（关闭的特技不参与任何战斗结算）"""
        return [skill for skill in self.skills if skill.enabled]

    def set_skill_enabled(self, skill_id: str, enabled: bool) -> bool:
        """切换指定特技的开关，返回是否找到该特技"""
        for skill in self.skills:
            if skill.skill_id != skill_id:
                continue
            if skill.enabled != enabled:
                skill.set_enabled(enabled)
                skill.on_toggle(self, enabled)
                self.enforce_courage_floor()
            return True
        return False

    def toggle_skill(self, skill_id: str):
        """翻转指定特技的开关，返回切换后的状态；未装备时返回 None"""
        for skill in self.skills:
            if skill.skill_id == skill_id:
                self.set_skill_enabled(skill_id, not skill.enabled)
                return skill.enabled
        return None

    @property
    def courage_floor(self) -> Optional[int]:
        """所有开启特技提供的胆气下限中的最高值"""
        floors = [
            floor
            for skill in self.active_skills
            if (floor := skill.courage_floor(self)) is not None
        ]
        return max(floors) if floors else None

    def enforce_courage_floor(self) -> bool:
        """把胆气抬升到特技下限，返回是否发生变化"""
        floor = self.courage_floor
        if floor is None:
            return False
        target = max(1, min(COURAGE_CAP, floor))
        if self.courage >= target:
            return False
        self.courage = target
        return True

    def damage_dealt_multiplier(self, round_num: int) -> float:
        """本次造成伤害的总倍率（所有开启特技的倍率相乘）"""
        multiplier = 1.0
        for skill in self.active_skills:
            multiplier *= skill.damage_dealt_multiplier(self, round_num)
        return multiplier

    @property
    def skill_descriptions(self) -> tuple:
        """特技展示文本，用于战报初始属性"""
        return tuple(skill.display_text for skill in self.skills)

    @property
    def skill_infos(self) -> tuple:
        """特技结构化信息，用于网页展示开关状态"""
        return tuple(skill.to_dict() for skill in self.skills)

    @property
    def weapon_description(self) -> str:
        """兵器展示文本（兵器名 + 分类）"""
        return self.weapon.description if self.weapon else ""

    def can_attack(self) -> bool:
        """检查是否可以挥刀（前摇完成；蓄力可在移动中累积，但移动中不能出手）"""
        return (
            self.is_alive
            and not self.is_moving
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
        """在限制范围内修改胆气，并保证不低于特技提供的下限"""
        self.courage = max(1, min(COURAGE_CAP, self.courage + amount))
        self.enforce_courage_floor()

    def choose_defense(self, attacker: Optional["Warrior"] = None) -> DefenseType:
        """AI根据加权属性选择防御类型"""

        weights = {
            DefenseType.BLOCK: self.strength * 0.6 + self.sp_percent * 100 * 0.4,
            DefenseType.PARRY: self.martialarts * 0.7 + self.agility * 0.3,
            DefenseType.DODGE: self.agility * 0.8 + abs(self.courage - 80) * 0.2,
            DefenseType.COUNTER: (self.courage * 0.7 + self.strength * 0.3) * (1 - self.hp_percent),
        }

        # 防守 1 类兵器攻击时，攻方武艺越高，守方越避免硬接格挡
        if (
            attacker is not None
            and attacker.weapon is not None
            and attacker.weapon.category is WeaponCategory.SPEAR
        ):
            multiplier = max(
                0.0,
                SPEAR_BLOCK_WEIGHT_MA_FACTOR * attacker.martialarts
                + SPEAR_BLOCK_WEIGHT_BASE,
            )
            weights[DefenseType.BLOCK] *= multiplier

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
