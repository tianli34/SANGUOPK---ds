# 文件名: enums.py
# 用途: 枚举类型定义文件，定义战斗系统中使用的各类枚举常量
from enum import Enum


class DefenseType(Enum):
    """武将可用的防御类型"""

    BLOCK = "block"  # 格挡(硬接)
    PARRY = "parry"  # 招架
    DODGE = "dodge"  # 闪避
    COUNTER = "counter"  # 反击


class AttackPhase(Enum):
    """攻击阶段枚举"""

    WINDUP = "windup"  # 前摇阶段
    ATTACK = "attack"  # 攻击阶段（瞬时）
    BACKSWING = "backswing"  # 后摇阶段


class Terrain(Enum):
    """地形类型"""

    PLAIN = "plain"  # 平地（可通行）
    ROCK = "rock"  # 岩石（不可通行，阻挡视线，绘制石块）
    BOUNDARY = "boundary"  # 禁行边界（不可通行，阻挡视线，不绘制）
