# 文件名: tests/test_combat.py
# 用途: 战斗系统核心公式与流程的单元测试

import json
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# 支持直接运行 python tests/test_combat.py
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src import (
    BattleEngine,
    BattleOutcome,
    DefenseType,
    Warrior,
    WeaponCategory,
    calculate_base_damage,
    check_clash_condition,
    get_skill,
    get_weapon,
)
import src.defense as defense_module
from src.battle_report import BattleReporter
from src.clash import calculate_clash_damage
from src.constants import BACKSWING_BAR, MAX_ROUNDS, MAX_TICKS, WINDUP_BAR
from src.defense import calculate_defense_rate
from src.event_exporter import build_battle_document
from src.lead_analysis import build_lead_records
from src.seed_history import SeedHistory, SeedRecord


def make_warrior(name="测试", team="A", **overrides):
    """创建带默认属性的测试武将"""
    stats = dict(martialarts=90, agility=90, strength=90, courage=80, sp=90)
    stats.update(overrides)
    return Warrior(name, team, **stats)


class WarriorTest(unittest.TestCase):
    def test_attributes_decay_with_stamina(self):
        warrior = make_warrior()
        full = (warrior.martialarts, warrior.agility, warrior.strength)

        warrior.sp *= 0.3
        low = (warrior.martialarts, warrior.agility, warrior.strength)

        for low_value, full_value in zip(low, full):
            self.assertLessEqual(low_value, full_value)
        self.assertLess(low[1], full[1])

    def test_attack_sp_cost_is_positive(self):
        self.assertGreater(make_warrior().attack_sp_cost(), 0)

    def test_ap_percent_bonus_once_before_any_attack(self):
        denominator = WINDUP_BAR + BACKSWING_BAR

        warrior = make_warrior()
        self.assertAlmostEqual(warrior.ap_percent, BACKSWING_BAR / denominator)

        # 首次防守结算后不再附加
        warrior.consume_ap_bonus()
        self.assertAlmostEqual(warrior.ap_percent, 0.0)
        warrior.consume_ap_bonus()
        self.assertAlmostEqual(warrior.ap_percent, 0.0)

        # 攻击过的武将没有加成
        attacked = make_warrior()
        attacked.start_attack()
        attacked.consume_ap_bonus()
        attacked.ap = WINDUP_BAR
        self.assertAlmostEqual(attacked.ap_percent, WINDUP_BAR / denominator)

        # 特技加AP不影响加成资格
        boosted = make_warrior()
        boosted.gain_ap(50)
        self.assertAlmostEqual(
            boosted.ap_percent, (50 + BACKSWING_BAR) / denominator
        )


class DamageTest(unittest.TestCase):
    def test_stronger_attacker_deals_more_damage(self):
        strong = make_warrior("强", "A", martialarts=100, strength=100)
        weak = make_warrior("弱", "B", martialarts=20, strength=20)

        self.assertGreater(
            calculate_base_damage(strong, weak),
            calculate_base_damage(weak, strong),
        )


class DefenseTest(unittest.TestCase):
    def test_defense_rate_within_bounds(self):
        defender = make_warrior(
            "守", "A", martialarts=100, agility=100, strength=100, courage=120
        )
        attacker = make_warrior(
            "攻", "B", martialarts=1, agility=1, strength=1, courage=1
        )

        for defense_type in DefenseType:
            for ap in (0, 150, 300):
                defender.ap = ap
                rate = calculate_defense_rate(defense_type, defender, attacker)
                self.assertGreaterEqual(rate, 0.05)
                self.assertLessEqual(rate, 0.95)

    def test_block_weight_reduced_against_spear(self):
        # 守方格挡权重 70；若按守方武艺(50)算 x=0.5，权重 35 会选中格挡
        defender = make_warrior("守", "A", martialarts=50)
        spear = make_warrior("枪", "B", weapon=get_weapon("虎头湛金枪"))
        heavy = make_warrior("刀", "B", weapon=get_weapon("血煞虎头刀"))

        # 攻方武艺 90 时 x = 0.85 - 0.007×90 = 0.22，格挡权重降为 15.4
        with patch("src.warrior.random.uniform", return_value=25.0):
            self.assertIs(defender.choose_defense(heavy), DefenseType.BLOCK)
            self.assertIs(defender.choose_defense(spear), DefenseType.PARRY)

    def test_ap_bonus_consumed_once_after_all_reads(self):
        """同一次攻击内多次读取 ap_percent 都应看到加成，结算只发生一次"""
        attacker = make_warrior("攻", "A", agility=120)
        defender = make_warrior("守", "B", agility=40)
        attacker.ap = WINDUP_BAR

        engine = BattleEngine([attacker], [defender])
        engine.round_count = 1

        observed = []
        original = defense_module.calculate_defense_rate

        def spy(defense_type, defender, attacker):
            observed.append((defender.ap_percent, defender.ap_bonus_count))
            return original(defense_type, defender, attacker)

        defense_module.calculate_defense_rate = spy
        try:
            engine.run_tick()
        finally:
            defense_module.calculate_defense_rate = original

        attack_logs = [l for l in engine.logs if l.event_type == "attack"]
        self.assertEqual(len(attack_logs), 1)
        logged_percent = attack_logs[0].details["defender_ap_percent"]

        self.assertGreater(len(observed), 1)
        for percent, count in observed:
            self.assertEqual(count, 0)  # 所有读取都发生在结算之前
            self.assertAlmostEqual(percent, logged_percent)

        # 整次攻击只结算一次，而不是每次读取 +1
        self.assertEqual(defender.ap_bonus_count, 1)


class WeaponTest(unittest.TestCase):
    def test_default_roster_equips_weapons(self):
        from main import build_parser, create_warrior

        args = build_parser().parse_args([])
        ma_chao = create_warrior(args, "a")
        xu_chu = create_warrior(args, "b")

        self.assertEqual(ma_chao.weapon.name, "虎头湛金枪")
        self.assertIs(ma_chao.weapon.category, WeaponCategory.SPEAR)
        self.assertEqual(ma_chao.weapon.category.value, 1)

        self.assertEqual(xu_chu.weapon.name, "血煞虎头刀")
        self.assertIs(xu_chu.weapon.category, WeaponCategory.HEAVY)
        self.assertEqual(xu_chu.weapon.category.value, 4)

        snapshot = ma_chao.snapshot()
        self.assertEqual(snapshot.weapon_name, "虎头湛金枪")
        self.assertEqual(snapshot.weapon_category, 1)
        self.assertEqual(snapshot.weapon_category_label, "枪与矛（刺击类）")

    def test_report_and_export_include_weapon(self):
        random.seed(7)
        warrior_a = make_warrior(
            "马超", "A", weapon=get_weapon("虎头湛金枪")
        )
        warrior_b = make_warrior(
            "许褚", "B", weapon=get_weapon("血煞虎头刀")
        )
        snapshot_a = warrior_a.snapshot()
        snapshot_b = warrior_b.snapshot()
        reporter = BattleReporter([warrior_a], [warrior_b])

        result = BattleEngine([warrior_a], [warrior_b]).run()
        report = reporter.generate_full_report(result)
        self.assertIn("兵器: 虎头湛金枪 · 枪与矛（刺击类）", report)
        self.assertIn("兵器: 血煞虎头刀 · 大斧与长柄锤（重型破甲类）", report)

        document = build_battle_document(result, [snapshot_a], [snapshot_b])
        self.assertEqual(
            document["warriors"]["A"]["weapon"],
            {
                "name": "虎头湛金枪",
                "category": 1,
                "categoryLabel": "枪与矛（刺击类）",
            },
        )
        self.assertEqual(document["warriors"]["B"]["weapon"]["category"], 4)


class WarriorPresetTest(unittest.TestCase):
    def test_guan_yu_preset_matches_design(self):
        from src.warrior_data import WARRIOR_PRESETS

        preset = WARRIOR_PRESETS["关羽"]
        self.assertEqual(
            (
                preset["martialarts"],
                preset["agility"],
                preset["strength"],
                preset["courage"],
                preset["sp"],
            ),
            (97, 88, 97, 96, 97),
        )
        self.assertEqual(preset["weapon"], "青龙偃月刀")
        self.assertEqual(preset["skill"], "none")

    def test_guan_yu_preset_is_playable_from_cli(self):
        from main import build_parser, create_warrior

        args = build_parser().parse_args(["--a-warrior", "关羽"])
        guan_yu = create_warrior(args, "a")

        self.assertEqual(guan_yu.name, "关羽")
        self.assertEqual(guan_yu.martialarts_init, 97)
        self.assertEqual(guan_yu.agility_init, 88)
        self.assertEqual(guan_yu.strength_init, 97)
        self.assertEqual(guan_yu.courage, 96)
        self.assertEqual(guan_yu.init_sp, 97)
        self.assertEqual(guan_yu.weapon.name, "青龙偃月刀")
        self.assertIs(guan_yu.weapon.category, WeaponCategory.GREAT_BLADE)
        self.assertEqual(guan_yu.weapon.effective_reach, 1)
        self.assertEqual(guan_yu.skills, [])


class ClashTest(unittest.TestCase):
    def test_equal_warriors_take_equal_damage(self):
        damage_a, damage_b, sp_a, sp_b = calculate_clash_damage(
            make_warrior("甲", "A"), make_warrior("乙", "B")
        )

        self.assertAlmostEqual(damage_a, damage_b)
        self.assertAlmostEqual(sp_a, sp_b)
        self.assertGreater(damage_a, 0)

    def test_clash_requires_close_ap(self):
        first = make_warrior("甲", "A")
        second = make_warrior("乙", "B")

        first.ap, second.ap = 100, 110
        self.assertTrue(check_clash_condition([first, second]))

        second.ap = 200
        self.assertFalse(check_clash_condition([first, second]))


class BattleEngineTest(unittest.TestCase):
    def test_battle_terminates(self):
        random.seed(42)
        warrior_a = make_warrior(
            "马超", "A", martialarts=98, agility=95, strength=92, courage=94, sp=98
        )
        warrior_b = make_warrior(
            "许褚", "B", martialarts=95, agility=80, strength=99, courage=96, sp=100
        )

        result = BattleEngine([warrior_a], [warrior_b]).run()

        self.assertIn(result.outcome, set(BattleOutcome))
        self.assertLessEqual(result.rounds, MAX_ROUNDS)
        self.assertLessEqual(result.ticks, MAX_TICKS)
        self.assertTrue(result.logs)

    def test_full_report_renders(self):
        random.seed(7)
        warrior_a = make_warrior("甲", "A")
        warrior_b = make_warrior("乙", "B")
        reporter = BattleReporter([warrior_a], [warrior_b])

        result = BattleEngine([warrior_a], [warrior_b]).run()
        report = reporter.generate_full_report(result)

        self.assertIn("甲", report)
        self.assertIn("乙", report)
        self.assertIn("战斗结果", report)

    def test_attack_log_sp_cost_matches_actual_deduction(self):
        """战报记录的攻击体力消耗必须等于真实扣减量

        attack_sp_cost() 依赖当前 SP 百分比，若在扣减后重复计算会得到不同结果。
        """
        random.seed(42)
        warrior_a = make_warrior(
            "马超", "A", martialarts=98, agility=95, strength=92, courage=94, sp=98
        )
        warrior_b = make_warrior(
            "许褚", "B", martialarts=95, agility=80, strength=99, courage=96, sp=100
        )

        result = BattleEngine([warrior_a], [warrior_b]).run()
        attack_logs = [log for log in result.logs if log.event_type == "attack"]
        self.assertTrue(attack_logs)

        for log in attack_logs:
            details = log.details
            actual = details["attacker_sp_before"] - details["attacker_sp_after"]
            self.assertAlmostEqual(
                details["attacker_sp_cost"],
                actual,
                places=6,
                msg=f"tick={log.tick} 战报体力消耗与实际扣减不一致",
            )


class LeadRecordTest(unittest.TestCase):
    def test_analyze_changes_streaks_and_max_gap(self):
        history = [
            {
                "round": 1,
                "hp": {"A": 0.60, "B": 0.50, "leader": "A"},
                "sp": {"A": 0.40, "B": 0.40, "leader": None},
            },
            {
                "round": 2,
                "hp": {"A": 0.58, "B": 0.50, "leader": "A"},
                "sp": {"A": 0.50, "B": 0.40, "leader": "A"},
            },
            {
                "round": 3,
                "hp": {"A": 0.45, "B": 0.55, "leader": "B"},
                "sp": {"A": 0.45, "B": 0.42, "leader": "A"},
            },
            {
                "round": 4,
                "hp": {"A": 0.40, "B": 0.60, "leader": "B"},
                "sp": {"A": 0.30, "B": 0.60, "leader": "B"},
            },
        ]

        records = build_lead_records(history)

        self.assertEqual(
            records["hp"]["changes"],
            [{"round": 1, "side": "A"}, {"round": 3, "side": "B"}],
        )
        self.assertEqual(records["hp"]["longest"], {"A": 2, "B": 2})
        self.assertAlmostEqual(records["hp"]["maxGap"]["A"], 0.10)
        self.assertAlmostEqual(records["hp"]["maxGap"]["B"], 0.20)

        self.assertEqual(
            records["sp"]["changes"],
            [{"round": 2, "side": "A"}, {"round": 4, "side": "B"}],
        )
        self.assertEqual(records["sp"]["longest"], {"A": 2, "B": 1})
        self.assertAlmostEqual(records["sp"]["maxGap"]["A"], 0.10)
        self.assertAlmostEqual(records["sp"]["maxGap"]["B"], 0.30)

    def test_engine_records_leader_history_each_round(self):
        random.seed(42)
        warrior_a = make_warrior("马超", "A", sp=98)
        warrior_b = make_warrior("许褚", "B", sp=100)

        result = BattleEngine([warrior_a], [warrior_b]).run()

        self.assertTrue(result.leader_history)
        rounds = [entry["round"] for entry in result.leader_history]
        self.assertEqual(rounds, list(range(1, len(rounds) + 1)))
        self.assertLessEqual(rounds[-1], result.rounds)

        for entry in result.leader_history:
            self.assertIn(entry["hp"]["leader"], ("A", "B", None))
            self.assertIn(entry["sp"]["leader"], ("A", "B", None))
            self.assertGreaterEqual(entry["hp"]["gap"], 0)
            self.assertGreaterEqual(entry["sp"]["gap"], 0)

    def test_report_and_export_include_lead_records(self):
        random.seed(7)
        warrior_a = make_warrior("甲", "A")
        warrior_b = make_warrior("乙", "B")
        snapshot_a = warrior_a.snapshot()
        snapshot_b = warrior_b.snapshot()
        reporter = BattleReporter([warrior_a], [warrior_b])

        result = BattleEngine([warrior_a], [warrior_b]).run()
        report = reporter.generate_full_report(result)

        self.assertIn("【领先记录】", report)
        self.assertIn("最长持续领先", report)
        self.assertIn("最大领先幅度", report)

        document = build_battle_document(result, [snapshot_a], [snapshot_b])
        lead_records = document["battle"]["leadRecords"]

        for metric in ("hp", "sp"):
            self.assertIn("changes", lead_records[metric])
            self.assertIn("longest", lead_records[metric])
            self.assertIn("maxGap", lead_records[metric])
            self.assertEqual(
                set(lead_records[metric]["longest"]), {"A", "B"}
            )
            self.assertEqual(set(lead_records[metric]["maxGap"]), {"A", "B"})


class SkillTest(unittest.TestCase):
    def test_equip_and_unequip(self):
        warrior = make_warrior()
        self.assertTrue(warrior.equip_skill(get_skill("opening_ap_50")))
        # 同 id 特技不可重复装备
        self.assertFalse(warrior.equip_skill(get_skill("opening_ap_50")))
        self.assertIn("先声夺人", warrior.skill_descriptions[0])

        self.assertTrue(warrior.unequip_skill("opening_ap_50"))
        self.assertFalse(warrior.unequip_skill("opening_ap_50"))
        self.assertEqual(warrior.skills, [])

    def test_opening_ap_skill_triggers_once_and_logs(self):
        random.seed(11)
        warrior_a = make_warrior("甲", "A")
        warrior_a.equip_skill(get_skill("opening_ap_50"))
        warrior_b = make_warrior("乙", "B")

        result = BattleEngine([warrior_a], [warrior_b]).run()

        skill_logs = [log for log in result.logs if log.event_type == "skill_trigger"]
        self.assertEqual(len(skill_logs), 1)
        details = skill_logs[0].details
        self.assertEqual(details["warrior"], "甲")
        self.assertEqual(details["skill"], "先声夺人")
        self.assertEqual(details["ap_before"], 0)
        self.assertEqual(details["ap_after"], 50)
        self.assertEqual(skill_logs[0].round_num, 1)

    def test_no_trigger_without_equipped_skill(self):
        random.seed(11)
        result = BattleEngine(
            [make_warrior("甲", "A")], [make_warrior("乙", "B")]
        ).run()

        self.assertFalse(
            [log for log in result.logs if log.event_type == "skill_trigger"]
        )

    def test_report_shows_equipped_skill_and_trigger(self):
        random.seed(7)
        warrior_a = make_warrior("甲", "A")
        warrior_a.equip_skill(get_skill("opening_ap_50"))
        warrior_b = make_warrior("乙", "B")
        reporter = BattleReporter([warrior_a], [warrior_b])

        result = BattleEngine([warrior_a], [warrior_b]).run()
        report = reporter.generate_full_report(result)

        self.assertIn("特技: 先声夺人", report)
        self.assertIn("特技【先声夺人】发动", report)
        self.assertIn("AP 0 → 50", report)


class SeedTest(unittest.TestCase):
    def test_apply_seed_is_deterministic(self):
        from main import apply_seed

        apply_seed(123, 0)
        first = [random.random() for _ in range(5)]
        apply_seed(123, 0)
        second = [random.random() for _ in range(5)]

        self.assertEqual(first, second)

    def test_apply_seed_varies_by_battle_index(self):
        from main import apply_seed

        apply_seed(123, 0)
        first = random.random()
        apply_seed(123, 1)
        second = random.random()

        self.assertNotEqual(first, second)

    def test_apply_seed_none_generates_reproducible_seed(self):
        from main import apply_seed

        generated = apply_seed(None, 3)
        first = [random.random() for _ in range(5)]

        self.assertEqual(apply_seed(generated, 0), generated)
        second = [random.random() for _ in range(5)]

        self.assertEqual(first, second)


class SeedHistoryTest(unittest.TestCase):
    def test_record_captures_rounds_and_winner_hp(self):
        random.seed(11)
        result = BattleEngine(
            [make_warrior("马超", "A")], [make_warrior("许褚", "B")]
        ).run()

        record = SeedRecord.from_result(2024, result)

        self.assertEqual(record.seed, 2024)
        self.assertEqual(record.rounds, result.rounds)
        if result.winner_team is None:
            self.assertIsNone(record.winner_hp)
            self.assertIsNone(record.winner_name)
        else:
            self.assertEqual(record.winner_side, result.winner_team)
            self.assertIsNotNone(record.winner_hp)
            self.assertIsNotNone(record.winner_hp_percent)

    def test_history_keeps_latest_records_and_persists(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "seed_history.json"
            history = SeedHistory(path)
            for i in range(105):
                history.append(
                    SeedRecord(
                        seed=i,
                        rounds=10 + i,
                        ticks=100 + i,
                        outcome="team_a_win",
                        winner_side="A",
                        winner_name="甲",
                        winner_hp=120.5,
                        winner_hp_max=200.0,
                        winner_hp_percent=0.6025,
                        recorded_at="2026-01-01T00:00:00",
                    )
                )
            history.save()

            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["limit"], 100)
            self.assertEqual(len(data["records"]), 100)
            self.assertEqual(data["records"][-1]["rounds"], 114)
            self.assertEqual(data["records"][-1]["winnerHp"], 120.5)

            reloaded = SeedHistory(path)
            self.assertEqual([r.seed for r in reloaded.records[:2]], [5, 6])
            self.assertEqual(reloaded.records[-1].seed, 104)


class CliSeedTest(unittest.TestCase):
    def test_same_seed_produces_identical_output(self):
        cmd = [
            sys.executable,
            str(PROJECT_ROOT / "main.py"),
            "--seed",
            "123",
            "-n",
            "3",
        ]
        first = subprocess.run(
            cmd, cwd=str(PROJECT_ROOT), capture_output=True, timeout=60
        )
        second = subprocess.run(
            cmd, cwd=str(PROJECT_ROOT), capture_output=True, timeout=60
        )

        self.assertEqual(first.returncode, 0, first.stderr.decode("utf-8", "replace"))
        self.assertEqual(second.returncode, 0, second.stderr.decode("utf-8", "replace"))
        self.assertIn("随机种子: 123".encode("utf-8"), first.stdout)
        self.assertEqual(first.stdout, second.stdout)


class WebBattleApiTest(unittest.TestCase):
    def test_random_document_is_playable(self):
        import main

        args = main.build_parser().parse_args([])
        state = random.getstate()
        try:
            document = main.build_random_document(args)
        finally:
            random.setstate(state)

        self.assertIsInstance(document["meta"]["seed"], int)
        self.assertTrue(document["events"])
        self.assertTrue(document["events"][0]["state"])
        self.assertIn("A", document["warriors"])
        self.assertIn("B", document["warriors"])
        self.assertGreaterEqual(document["battle"]["rounds"], 1)


if __name__ == "__main__":
    unittest.main()
