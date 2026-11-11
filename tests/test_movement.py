# 文件名: tests/test_movement.py
# 用途: 地图、寻路、射程、移动、引擎集成、事件导出与确定性的单元测试

import random
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src import (
    BattleEngine,
    BattleMap,
    Warrior,
    Weapon,
    WeaponCategory,
    chebyshev_distance,
    get_default_map,
    get_map,
    get_weapon,
)
from src.constants import TICK_RATE, UNIT_RADIUS, WINDUP_BAR
from src.event_exporter import build_battle_document
from src.map import bresenham_cells, cell_at, cell_center


def make_warrior(name="测试", team="A", **overrides):
    attrs = dict(
        martialarts=90, agility=90, strength=90, courage=80, sp=90
    )
    attrs.update(overrides)
    return Warrior(name=name, team=team, **attrs)


def positions_from_states(states):
    return {entry["team"]: tuple(entry["position"]) for entry in states}


def make_battle(with_map=True, seed=123):
    random.seed(seed)
    warrior_a = make_warrior(
        "马超", "A", agility=98, weapon=get_weapon("虎头湛金枪")
    )
    warrior_b = make_warrior(
        "许褚", "B", strength=99, weapon=get_weapon("血煞虎头刀")
    )
    snapshot_a = warrior_a.snapshot()
    snapshot_b = warrior_b.snapshot()
    engine = BattleEngine(
        [warrior_a], [warrior_b],
        battle_map=get_default_map() if with_map else None,
    )
    result = engine.run()
    return result, warrior_a, warrior_b, snapshot_a, snapshot_b


class MapTest(unittest.TestCase):
    def test_builtin_layout_and_registry(self):
        battle_map = get_default_map()
        self.assertEqual(battle_map.name, "演武场")
        self.assertEqual((battle_map.width, battle_map.height), (13, 7))
        self.assertEqual(battle_map.spawn("A"), (2, 3))
        self.assertEqual(battle_map.spawn("B"), (10, 3))
        self.assertTrue(battle_map.is_walkable((2, 3)))
        self.assertTrue(battle_map.is_walkable((10, 3)))
        self.assertIs(get_map("演武场"), battle_map)
        with self.assertRaises(ValueError):
            get_map("不存在的地图")

    def test_builtin_layout_matches_design(self):
        battle_map = get_default_map()
        expected = {(x, 0) for x in range(13)}
        expected |= {(x, 1) for x in range(4)}
        expected |= {(0, 2), (0, 3), (12, 3)}
        expected |= {(11, 4), (12, 4)}
        expected |= {(x, 5) for x in range(10, 13)}
        expected |= {(x, 6) for x in range(10, 13)}
        self.assertEqual(battle_map.obstacles, frozenset(expected))
        self.assertEqual(battle_map.rocks, frozenset())
        for cell in expected:
            self.assertFalse(battle_map.is_walkable(cell))
        self.assertTrue(battle_map.is_walkable((6, 3)))
        self.assertFalse(battle_map.in_bounds((-1, 0)))

    def test_chebyshev_distance(self):
        self.assertEqual(chebyshev_distance((2, 3), (10, 3)), 8)
        self.assertEqual(chebyshev_distance((0, 0), (3, 5)), 5)
        self.assertEqual(chebyshev_distance((4, 4), (4, 4)), 0)

    def test_line_of_sight_follows_terrain(self):
        battle_map = get_default_map()
        self.assertTrue(battle_map.has_line_of_sight((2, 3), (10, 3)))
        self.assertTrue(battle_map.has_line_of_sight((2, 3), (5, 3)))
        wall = BattleMap.from_rows(
            "石墙", [".....", "..#..", "....."], spawns=((0, 0), (4, 2))
        )
        self.assertFalse(wall.has_line_of_sight((2, 0), (2, 2)))
        self.assertTrue(wall.has_line_of_sight((0, 0), (1, 1)))
        self.assertEqual(
            bresenham_cells((0, 0), (3, 0)), [(0, 0), (1, 0), (2, 0), (3, 0)]
        )

    def test_no_diagonal_corner_cutting(self):
        battle_map = BattleMap.from_rows(
            "墙角", ["..", "#.", ".."], spawns=((0, 0), (1, 2))
        )
        self.assertNotIn((1, 1), battle_map.neighbors((0, 0)))
        self.assertIn((1, 0), battle_map.neighbors((0, 0)))


class ContinuousPositionTest(unittest.TestCase):
    def test_cell_center_and_cell_at(self):
        self.assertEqual(cell_center((2, 3)), (2.5, 3.5))
        self.assertEqual(cell_at((2.5, 3.5)), (2, 3))
        self.assertEqual(cell_at((2.99, 3.01)), (2, 3))

    def test_point_walkable_with_radius(self):
        wall = BattleMap.from_rows(
            "石墙", [".....", "..#..", "....."], spawns=((0, 0), (4, 2))
        )
        self.assertTrue(wall.is_point_walkable(1.5, 1.5, UNIT_RADIUS))
        self.assertFalse(wall.is_point_walkable(2.6, 1.5, UNIT_RADIUS))
        self.assertTrue(wall.is_point_walkable(2.6, 0.5, UNIT_RADIUS))

    def test_move_point_slides_along_wall(self):
        wall = BattleMap.from_rows(
            "石墙", [".....", "..#..", "....."], spawns=((0, 0), (4, 2))
        )
        x, y = wall.move_point(0.5, 1.5, 2.0, 0.1, UNIT_RADIUS)
        self.assertGreater(x, 0.5)
        self.assertLess(x, 1.8)
        self.assertTrue(wall.is_point_walkable(x, y, UNIT_RADIUS))

    def test_float_line_of_sight_blocked_by_rock(self):
        wall = BattleMap.from_rows(
            "石墙", [".....", "..#..", "....."], spawns=((0, 0), (4, 2))
        )
        self.assertFalse(wall.has_line_of_sight_points((0.5, 1.5), (4.5, 1.5)))
        self.assertTrue(wall.has_line_of_sight_points((0.5, 0.5), (3.5, 0.5)))

    def test_path_to_point_range_uses_float_target(self):
        battle_map = get_default_map()
        target = (10.9, 3.5)
        path = battle_map.find_path_to_point_range(
            (2, 3), target, 1, occupied={(10, 3)}
        )
        self.assertTrue(path)
        end = cell_center(path[-1])
        self.assertLessEqual(chebyshev_distance(end, target), 1)
        self.assertTrue(battle_map.has_line_of_sight_points(end, target))


class PathfindingTest(unittest.TestCase):
    def assert_valid_path(self, battle_map, start, path, occupied):
        prev = start
        for cell in path:
            self.assertTrue(battle_map.is_walkable(cell))
            self.assertNotIn(cell, occupied)
            self.assertEqual(chebyshev_distance(prev, cell), 1)
            if prev[0] != cell[0] and prev[1] != cell[1]:
                self.assertTrue(battle_map.is_walkable((prev[0], cell[1])))
                self.assertTrue(battle_map.is_walkable((cell[0], prev[1])))
            prev = cell

    def test_path_valid_and_deterministic(self):
        battle_map = get_default_map()
        path = battle_map.find_path((2, 3), (10, 3))
        self.assertEqual(len(path), 8)
        self.assertEqual(path[-1], (10, 3))
        self.assert_valid_path(battle_map, (2, 3), path, set())
        self.assertEqual(path, battle_map.find_path((2, 3), (10, 3)))

    def test_path_to_range_stops_at_reach_edge(self):
        battle_map = get_default_map()
        target = (10, 3)
        for reach in (3, 2, 1):
            path = battle_map.find_path_to_range(
                (2, 3), target, reach, occupied={target}
            )
            self.assertIsNotNone(path)
            self.assert_valid_path(battle_map, (2, 3), path, {target})
            end = path[-1] if path else (2, 3)
            self.assertNotEqual(end, target)
            self.assertEqual(chebyshev_distance(end, target), reach)
            self.assertTrue(battle_map.has_line_of_sight(end, target))

    def test_path_to_range_already_in_range(self):
        battle_map = get_default_map()
        self.assertEqual(
            battle_map.find_path_to_range((9, 3), (10, 3), 1, occupied=set()),
            [],
        )

    def test_path_to_range_unreachable(self):
        battle_map = BattleMap.from_rows(
            "围城",
            [".....", ".###.", ".#.#.", ".###.", "....."],
            spawns=((0, 0), (4, 4)),
        )
        self.assertIsNone(
            battle_map.find_path_to_range((0, 0), (2, 2), 1, occupied=set())
        )

    def test_occupied_cells_are_blocked(self):
        battle_map = get_default_map()
        self.assertIsNone(battle_map.find_path((2, 3), (10, 3), {(10, 3)}))
        occupied = {(5, 0)}
        path = battle_map.find_path((2, 3), (10, 3), occupied)
        self.assert_valid_path(battle_map, (2, 3), path, occupied)


class ReachTest(unittest.TestCase):
    def test_category_defaults(self):
        for category, expected in (
            (WeaponCategory.SPEAR, 1),
            (WeaponCategory.GREAT_BLADE, 1),
            (WeaponCategory.HALBERD, 1),
            (WeaponCategory.HEAVY, 1),
        ):
            weapon = Weapon(name="测试兵器", category=category)
            self.assertEqual(weapon.effective_reach, expected)

    def test_per_weapon_override(self):
        weapon = Weapon(
            name="加长枪", category=WeaponCategory.SPEAR, reach=5
        )
        self.assertEqual(weapon.effective_reach, 5)
        short = Weapon(
            name="短枪", category=WeaponCategory.SPEAR, reach=1
        )
        self.assertEqual(short.effective_reach, 1)

    def test_warrior_reach_and_snapshot(self):
        warrior = make_warrior()
        self.assertEqual(warrior.reach, 1)
        self.assertEqual(warrior.snapshot().reach, 1)
        spear_warrior = make_warrior(weapon=get_weapon("虎头湛金枪"))
        self.assertEqual(spear_warrior.reach, 1)
        snapshot = spear_warrior.snapshot()
        self.assertEqual(snapshot.reach, 1)
        self.assertIsNone(snapshot.position)


class MovementTest(unittest.TestCase):
    def test_begin_move_resets_windup(self):
        warrior = make_warrior()
        warrior.position = (2, 3)
        warrior.ap = 80.0
        self.assertTrue(warrior.begin_move([(3, 3), (4, 3)]))
        self.assertEqual(warrior.ap, 0.0)
        self.assertTrue(warrior.is_moving)

    def test_backswing_locks_movement(self):
        warrior = make_warrior()
        warrior.position = (2, 3)
        warrior.start_attack()
        warrior.finish_attack()
        self.assertTrue(warrior.is_in_backswing())
        self.assertFalse(warrior.begin_move([(3, 3)]))

    def test_move_speed_and_manual_state(self):
        warrior = make_warrior(agility=90)
        self.assertEqual(warrior.move_speed, 140)
        self.assertAlmostEqual(warrior.move_speed_cells, 1.4)
        self.assertTrue(warrior.begin_manual_move())
        self.assertTrue(warrior.is_moving)
        self.assertEqual(warrior.ap, 0.0)
        warrior.stop_move()
        self.assertFalse(warrior.is_moving)

    def test_ap_accumulates_while_moving(self):
        """移动中照样积累行动点，但仍然不能出手"""
        warrior = make_warrior()
        warrior.position = (2, 3)
        warrior.begin_move([(3, 3)])
        warrior.tick_ap(TICK_RATE)
        self.assertGreater(warrior.ap, 0.0)
        self.assertFalse(warrior.can_attack())
        warrior.ap = 500.0
        self.assertFalse(warrior.can_attack())
        warrior.stop_move()
        self.assertTrue(warrior.can_attack())

    def test_dead_warrior_cannot_move(self):
        warrior = make_warrior()
        warrior.position = (2, 3)
        warrior.take_damage(10**9)
        self.assertFalse(warrior.is_alive)
        self.assertFalse(warrior.begin_move([(3, 3)]))


class EngineIntegrationTest(unittest.TestCase):
    def test_deploy_move_and_ranged_attacks(self):
        result, _, _, _, _ = make_battle(with_map=True)
        logs = result.logs
        start = next(l for l in logs if l.event_type == "battle_start")
        start_positions = positions_from_states(start.warrior_states)
        self.assertEqual(start_positions["A"], (2.5, 3.5))
        self.assertEqual(start_positions["B"], (10.5, 3.5))

        moves = [l for l in logs if l.event_type == "move"]
        self.assertTrue(moves)
        battle_map = get_default_map()
        for log in moves:
            src = tuple(log.details["from"])
            dst = tuple(log.details["to"])
            # 每段最多跨一格（斜向欧氏距离为 √2，切比雪夫距离仍为 1）
            self.assertLessEqual(chebyshev_distance(src, dst), 1 + 1e-6)
            self.assertGreater(chebyshev_distance(src, dst), 0)
            self.assertTrue(battle_map.is_point_walkable(*dst))

        attacks = [l for l in logs if l.event_type == "attack"]
        self.assertTrue(attacks)
        self.assertGreater(attacks[0].tick, moves[0].tick)
        for log in attacks:
            distance = log.details["attack_distance"]
            self.assertLessEqual(distance, log.details["attacker_reach"])
            positions = positions_from_states(log.warrior_states)
            pos_a, pos_b = positions["A"], positions["B"]
            self.assertAlmostEqual(distance, chebyshev_distance(pos_a, pos_b))
            self.assertTrue(battle_map.has_line_of_sight_points(pos_a, pos_b))

        final_positions = positions_from_states(logs[-1].warrior_states)
        self.assertNotEqual(final_positions["A"], final_positions["B"])
        self.assertTrue(battle_map.is_point_walkable(*final_positions["A"]))
        self.assertTrue(battle_map.is_point_walkable(*final_positions["B"]))

    def test_battle_terminates(self):
        result, _, _, _, _ = make_battle(with_map=True)
        self.assertIsNotNone(result.winner_team)
        self.assertGreater(result.rounds, 0)

    def test_no_map_preserves_legacy_behavior(self):
        result, warrior_a, warrior_b, _, _ = make_battle(with_map=False)
        self.assertIsNone(result.battle_map)
        self.assertIsNone(warrior_a.position)
        self.assertIsNone(warrior_b.position)
        logs = result.logs
        self.assertFalse(any(l.event_type == "move" for l in logs))
        for log in logs:
            for entry in log.warrior_states:
                self.assertNotIn("position", entry)
            if log.event_type == "attack":
                self.assertNotIn("attack_distance", log.details)


class WhiffAttackTest(unittest.TestCase):
    """射程外挥刀：允许出手，但只是空挥，不产生攻防判定"""

    def make_engine(self):
        random.seed(7)
        warrior_a = make_warrior(
            "马超", "A", agility=98, weapon=get_weapon("虎头湛金枪")
        )
        warrior_b = make_warrior(
            "许褚", "B", strength=99, weapon=get_weapon("血煞虎头刀")
        )
        engine = BattleEngine([warrior_a], [warrior_b], battle_map=get_default_map())
        engine.begin()
        warrior_a.position = (2.5, 3.5)
        warrior_b.position = (10.5, 3.5)
        engine.overrides[warrior_a.name] = {
            "mode": "manual", "move": None, "attack": True,
        }
        engine.overrides[warrior_b.name] = {
            "mode": "manual", "move": None, "attack": False,
        }
        warrior_a.ap = WINDUP_BAR
        warrior_b.ap = WINDUP_BAR
        return engine, warrior_a, warrior_b

    def test_out_of_range_swing_only_whiffs(self):
        engine, warrior_a, warrior_b = self.make_engine()
        hp_before = warrior_b.hp
        sp_before = warrior_a.sp

        engine.run_tick()

        types = [log.event_type for log in engine.logs]
        self.assertIn("whiff", types)
        self.assertNotIn("attack", types)
        self.assertNotIn("clash", types)

        whiff = next(log for log in engine.logs if log.event_type == "whiff")
        self.assertEqual(whiff.details["attacker"], "马超")
        self.assertTrue(whiff.details["out_of_range"])
        self.assertEqual(whiff.details["attack_distance"], 8)
        self.assertEqual(whiff.details["attacker_reach"], 1)

        # 对手毫发无伤，出手方付出体力并进入后摇
        self.assertEqual(warrior_b.hp, hp_before)
        self.assertLess(warrior_a.sp, sp_before)
        self.assertTrue(warrior_a.is_in_backswing())
        self.assertFalse(engine.overrides["马超"]["attack"])

    def test_out_of_range_pair_does_not_clash(self):
        """双方都在射程外时凑不成拼刀，各自空挥"""
        engine, warrior_a, warrior_b = self.make_engine()
        engine.overrides["许褚"]["attack"] = True

        engine.run_tick()

        types = [log.event_type for log in engine.logs]
        self.assertNotIn("clash", types)
        self.assertEqual(types.count("whiff"), 2)

    def test_in_range_swing_still_lands(self):
        """射程内不受影响：仍然是正常的攻防判定"""
        engine, warrior_a, warrior_b = self.make_engine()
        warrior_a.position = (5.5, 3.5)
        warrior_b.position = (6.5, 3.5)

        engine.run_tick()

        types = [log.event_type for log in engine.logs]
        self.assertIn("attack", types)
        self.assertNotIn("whiff", types)


class ExportTest(unittest.TestCase):
    def test_v2_document_shape(self):
        result, warrior_a, warrior_b, snapshot_a, snapshot_b = make_battle()
        doc = build_battle_document(
            result, [snapshot_a], [snapshot_b], seed=123
        )
        self.assertEqual(doc["meta"]["version"], 2)
        self.assertEqual(doc["map"]["name"], "演武场")
        self.assertEqual((doc["map"]["width"], doc["map"]["height"]), (13, 7))
        self.assertEqual(
            doc["map"]["spawns"], {"A": [2.5, 3.5], "B": [10.5, 3.5]}
        )
        self.assertIn([0, 1], doc["map"]["obstacles"])
        self.assertEqual(doc["map"]["rocks"], [])

        moves = [e for e in doc["events"] if e["type"] == "move"]
        self.assertTrue(moves)
        for event in moves:
            mv = event["move"]
            self.assertIn(mv["side"], ("A", "B"))
            self.assertEqual(len(mv["from"]), 2)
            self.assertEqual(len(mv["to"]), 2)
        for event in doc["events"]:
            for side in ("A", "B"):
                self.assertEqual(len(event["state"][side]["position"]), 2)
        final_state = doc["events"][-1]["state"]
        self.assertEqual(final_state["A"]["position"], list(warrior_a.position))
        self.assertEqual(final_state["B"]["position"], list(warrior_b.position))
        self.assertEqual(doc["warriors"]["A"]["weapon"]["reach"], 1)
        self.assertEqual(doc["warriors"]["B"]["weapon"]["reach"], 1)

    def test_v1_legacy_document_unchanged(self):
        result, _, _, snapshot_a, snapshot_b = make_battle(with_map=False)
        doc = build_battle_document(
            result, [snapshot_a], [snapshot_b], seed=123
        )
        self.assertEqual(doc["meta"]["version"], 1)
        self.assertNotIn("map", doc)
        self.assertFalse(any(e["type"] == "move" for e in doc["events"]))
        for event in doc["events"]:
            for side in ("A", "B"):
                self.assertNotIn("position", event["state"][side])
        weapon = doc["warriors"]["A"]["weapon"]
        self.assertEqual(set(weapon.keys()), {"name", "category", "categoryLabel"})


class DeterminismTest(unittest.TestCase):
    def test_same_seed_produces_identical_document(self):
        docs = []
        for _ in range(2):
            result, _, _, snapshot_a, snapshot_b = make_battle(seed=123)
            docs.append(
                build_battle_document(result, [snapshot_a], [snapshot_b], seed=123)
            )
        for doc in docs:
            doc["meta"].pop("generatedAt", None)
        self.assertEqual(docs[0], docs[1])


if __name__ == "__main__":
    unittest.main()