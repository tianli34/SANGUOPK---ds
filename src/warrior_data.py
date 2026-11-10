# 文件名: warrior_data.py
# 用途: 武将数据文件，集中存放名将预设、默认武将配置与属性字段定义
"""武将数据：名将预设、默认出战配置与属性字段"""

# 名将预设：综合《三国演义》战绩与兵器特点设定，五维基准对照马超、许褚。
# 马超以枪法迅捷见长；许褚力大体壮、体力深厚；
# 关羽的青龙偃月刀势大力沉，武艺与胆气最高，力量略逊许褚，敏捷不及马超。
WARRIOR_PRESETS = {
    "马超": {
        "name": "马超",
        "martialarts": 96,
        "agility": 98,
        "strength": 91,
        "courage": 90,
        "sp": 95,
        "skill": "none",
        "weapon": "虎头湛金枪",
    },
    "许褚": {
        "name": "许褚",
        "martialarts": 91,
        "agility": 88,
        "strength": 99,
        "courage": 91,
        "sp": 99,
        "skill": "none",
        "weapon": "血煞虎头刀",
    },
    "关羽": {
        "name": "关羽",
        "martialarts": 97,
        "agility": 88,
        "strength": 97,
        "courage": 96,
        "sp": 97,
        "skill": "none",
        "weapon": "青龙偃月刀",
    },
}

# 双方武将的默认配置
DEFAULT_WARRIORS = {
    "a": dict(WARRIOR_PRESETS["马超"]),
    "b": dict(WARRIOR_PRESETS["许褚"]),
}

STAT_FIELDS = ("martialarts", "agility", "strength", "courage", "sp")

STAT_LABELS = {
    "martialarts": "武艺",
    "agility": "敏捷",
    "strength": "力量",
    "courage": "胆气",
    "sp": "体力",
}
