# 文件名: constants.py
# 用途: 全局常量定义文件，存储战斗系统中使用的各类数值参数和配置常量

# 生命值与体力值
HP_COEFFICIENT = 2  # HP系数
SP_EXPANSION_FACTOR = 50  # 体力膨胀系数

# 行动点数
WINDUP_BAR = 100  # 前摇行动点数阈值
BACKSWING_BAR = 200  # 后摇行动点数阈值

TICK_RATE = 0.05  # 时间流逝速率

# 拼刀系统
CLASH_AP_THRESHOLD = 20  # 拼刀AP差值阈值

# 受伤对行动点数的惩罚
DEFENDER_AP_LOSS_RATIO = 0.5  # 守方受伤时：AP 扣除 受伤值 × 该比例
ATTACKER_BACKSWING_LOSS_RATIO = 0.5  # 攻方受伤时：后摇阈值增加 受伤值 × 该比例

# 格挡系统
BLOCK_K = 0.5  # 格挡冲击力系数

# 体力消耗
BASE_SP_COST = 5  # 基础体力消耗

# 胆气系统
COURAGE_CAP = 120  # 胆气上限值

# 伤害计算
RECOIL_CAP_RATIO = 0.5  # 反震伤害上限比例
ARMOR_PENETRATION = 1.0  # 破甲系数

# 战斗规则
MAX_ROUNDS = 300  # 最大回合数
MAX_TICKS = 30000  # 最大时间刻度（防止无限循环）

# 防御参数
DEFENSE_PARAMS = {
    "block": {  # 格挡
        "base_rate": 0.70,  # 基础成功率
        "rate_factor": 0.01,  # 属性差异系数
        "impact_k": 0.5,  # 冲击力系数
        "success_damage_mult": 0.3,  # 成功伤害倍率
        "fail_damage_mult": 2.0,  # 失败伤害倍率
        "recoil_mult": 0.3,  # 反震倍率
        "sp_cost_ratio": 0.3,  # 体力消耗比例
        "success_courage": 10,  # 成功胆气变化
        "fail_courage": -30,  # 失败胆气变化
    },
    "parry": {  # 卸力
        "base_rate": 0.50,  # 基础成功率
        "rate_factor": 0.01,  # 属性差异系数
        "success_sp_cost": 10,  # 成功体力消耗
        "success_courage": 20,  # 成功胆气变化
        "fail_sp_cost": 20,  # 失败体力消耗
        "fail_courage": -10,  # 失败胆气变化
        "fail_damage_mult": 1.0,  # 失败伤害倍率
    },
    "dodge": {  # 闪避
        "base_rate": 0.1,  # 基础成功率
        "rate_factor": 0.01,  # 属性差异系数
        "success_sp_cost": 20,  # 成功体力消耗
        "success_courage": 30,  # 成功胆气变化
        "fail_sp_cost": 40,  # 失败体力消耗
        "fail_courage": -15,  # 失败胆气变化
        "fail_damage_mult": 1.2,  # 失败伤害倍率
    },
    "counter": {  # 反击
        "base_rate": 0.60,  # 基础成功率
        "rate_factor": 0.01,  # 属性差异系数
        "success_sp_cost": 30,  # 成功体力消耗
        "success_courage": 40,  # 成功胆气变化
        "fail_sp_cost": 50,  # 失败体力消耗
        "fail_courage": 0,  # 失败胆气变化
        "fail_damage_mult": 0.8,  # 失败伤害倍率
    },
}
