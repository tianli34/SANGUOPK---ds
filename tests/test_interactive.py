# 文件名: test_interactive.py
# 用途: 实时操控（手动/自动覆盖、会话推进、事件增量导出）的单元测试

import random
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src import BattleEngine, Warrior, get_default_map, get_weapon
from src.constants import UNIT_SEPARATION
from src.interactive import BattleSession, SessionStore


def make_warrior(name="测试", team="A", **overrides):
    attrs = dict(martialarts=90, agility=90, strength=90, courage=80, sp=90)
    attrs.update(overrides)
    return Warrior(name=name, team=team, **attrs)


def make_engine(seed=123):
    random.seed(seed)
    warrior_a = make_warrior("马超", "A", agility=98, weapon=get_weapon("虎头湛金枪"))
    warrior_b = make_warrior("许褚", "B", strength=99, weapon=get_weapon("血煞虎头刀"))
    engine = BattleEngine([warrior_a], [warrior_b], battle_map=get_default_map())
    return engine, warrior_a, warrior_b


def override(engine, warrior, mode="auto", move=None, attack=False):
    engine.overrides[warrior.name] = {"mode": mode, "move": move, "attack": attack}


def run_ticks(engine, count):
    for _ in range(count):
        if engine.run_tick():
            return True
    return False


def event_types(engine):
    return [log.event_type for log in engine.logs]


class ManualControlTest(unittest.TestCase):
    def test_manual_mode_idles_without_commands(self):
        """手动模式下无指令：不自动接近、不自动攻击"""
        engine, a, b = make_engine()
        engine.begin()
        override(engine, a, mode="manual")
        override(engine, b, mode="manual")
        run_ticks(engine, 300)
        self.assertEqual(a.position, (2.5, 3.5))
        self.assertEqual(b.position, (10.5, 3.5))
        self.assertNotIn("attack", event_types(engine))
        self.assertNotIn("move", event_types(engine))

    def test_manual_move_follows_direction(self):
        """手动移动指令：沿方向逐格推进并记录 move 事件"""
        engine, a, b = make_engine()
        engine.begin()
        override(engine, a, mode="manual", move=(1, 0))
        override(engine, b, mode="manual")
        run_ticks(engine, 60)
        self.assertGreater(a.position[0], 2.5)
        self.assertAlmostEqual(a.position[1], 3.5)
        moves = [log for log in engine.logs if log.event_type == "move"]
        self.assertTrue(moves)
        self.assertEqual(moves[0].details["warrior"], "马超")

    def test_manual_move_stops_at_unit_separation(self):
        """手动移动可以贴近敌人，但不会重叠"""
        engine, a, b = make_engine()
        engine.begin()
        a.position = (5.5, 3.5)
        b.position = (6.5, 3.5)
        override(engine, a, mode="manual", move=(1, 0))
        override(engine, b, mode="manual")
        run_ticks(engine, 60)
        self.assertGreater(a.position[0], 5.5)
        self.assertGreaterEqual(
            abs(b.position[0] - a.position[0]), UNIT_SEPARATION - 1e-9
        )

    def test_manual_attack_fires_when_ready(self):
        """手动攻击意图：蓄力完成且射程内时出手，随后意图清除"""
        engine, a, b = make_engine()
        engine.begin()
        a.position = (5.5, 3.5)
        b.position = (6.5, 3.5)
        override(engine, a, mode="manual", attack=True)
        override(engine, b, mode="manual")
        run_ticks(engine, 60)
        attacks = [log for log in engine.logs if log.event_type == "attack"]
        self.assertTrue(attacks)
        self.assertEqual(attacks[0].details["attacker"], "马超")
        self.assertFalse(engine.overrides["马超"]["attack"])
        # 意图清除后不再自动攻击
        count = len(attacks)
        run_ticks(engine, 200)
        self.assertEqual(len([l for l in engine.logs if l.event_type == "attack"]), count)

    def test_manual_attack_waits_for_windup(self):
        """蓄力不足时攻击意图保留，就绪后才出手"""
        engine, a, b = make_engine()
        engine.begin()
        a.position = (5.5, 3.5)
        b.position = (6.5, 3.5)
        override(engine, a, mode="manual", attack=True)
        override(engine, b, mode="manual")
        engine.run_tick()
        self.assertTrue(engine.overrides["马超"]["attack"])
        self.assertNotIn("attack", event_types(engine))
        run_ticks(engine, 60)
        self.assertIn("attack", event_types(engine))

    def test_manual_move_cancels_attack_intent(self):
        """起手移动打断前摇，同时取消待发的攻击意图"""
        engine, a, b = make_engine()
        engine.begin()
        override(engine, a, mode="manual", move=(0, 1), attack=True)
        override(engine, b, mode="manual")
        run_ticks(engine, 5)
        self.assertFalse(engine.overrides["马超"]["attack"])

    def test_auto_mode_manual_move_overrides_ai(self):
        """自动模式下手动移动优先：AI 想接近，指令却让其后退"""
        engine, a, b = make_engine()
        engine.begin()
        override(engine, a, mode="auto", move=(-1, 0))
        run_ticks(engine, 60)
        self.assertLess(a.position[0], 2.5)

    def test_auto_mode_resumes_after_release(self):
        """松开手动方向后自动模式恢复 AI 寻路"""
        engine, a, b = make_engine()
        engine.begin()
        override(engine, a, mode="auto", move=(-1, 0))
        run_ticks(engine, 40)
        retreated = a.position[0]
        override(engine, a, mode="auto", move=None)
        run_ticks(engine, 200)
        self.assertGreater(a.position[0], retreated)

    def test_switch_manual_to_auto_resumes_ai(self):
        """手动切自动后恢复自动攻击"""
        engine, a, b = make_engine()
        engine.begin()
        override(engine, a, mode="manual")
        override(engine, b, mode="manual")
        run_ticks(engine, 100)
        self.assertNotIn("attack", event_types(engine))
        override(engine, a, mode="auto")
        override(engine, b, mode="auto")
        run_ticks(engine, 400)
        self.assertIn("attack", event_types(engine))

    def test_no_overrides_keeps_legacy_behavior(self):
        """不设置覆盖项时与纯 AI 模拟一致（确定性回归）"""
        engine, _, _ = make_engine(seed=7)
        result = engine.run()
        engine2, _, _ = make_engine(seed=7)
        result2 = engine2.run()
        self.assertEqual(result.outcome, result2.outcome)
        self.assertEqual(result.ticks, result2.ticks)
        self.assertEqual(len(result.logs), len(result2.logs))


class SessionTest(unittest.TestCase):
    def make_session(self, seed=123):
        engine, a, b = make_engine(seed)
        return BattleSession(engine, a.snapshot(), b.snapshot(), seed=seed)

    def test_initial_document_shape(self):
        session = self.make_session()
        doc = session.initial_document()
        self.assertIn("warriors", doc)
        self.assertIn("map", doc)
        self.assertTrue(doc["meta"]["live"])
        self.assertEqual(doc["events"][0]["type"], "battle_start")
        self.assertEqual(doc["warriors"]["A"]["name"], "马超")
        self.assertIn("reach", doc["warriors"]["A"]["weapon"])

    def test_step_returns_incremental_events(self):
        session = self.make_session()
        session.initial_document()
        first = session.step(30)
        second = session.step(30)
        self.assertTrue(first["events"])
        indices = [e["index"] for e in first["events"] + second["events"]]
        self.assertEqual(indices, sorted(set(indices)))
        for event in first["events"] + second["events"]:
            self.assertIn("state", event)
            self.assertIn("effects", event)
            self.assertIn("alive", event)

    def test_step_state_has_ap_gauge(self):
        session = self.make_session()
        session.initial_document()
        response = session.step(10)
        for side in ("A", "B"):
            ap = response["state"][side]["ap"]
            self.assertIn(ap["phase"], ("windup", "backswing"))
            self.assertGreaterEqual(ap["percent"], 0)
            self.assertLessEqual(ap["percent"], 1)

    def test_commands_move_warrior(self):
        session = self.make_session()
        session.initial_document()
        commands = {
            "A": {"mode": "manual", "move": [1, 0]},
            "B": {"mode": "manual"},
        }
        response = session.step(60, commands)
        moves = [e for e in response["events"] if e["type"] == "move"]
        self.assertTrue(moves)
        self.assertEqual(moves[0]["move"]["side"], "A")
        self.assertGreater(response["state"]["A"]["position"][0], 2.5)

    def test_battle_finishes_with_summary(self):
        session = self.make_session()
        session.initial_document()
        response = None
        for _ in range(2000):
            response = session.step(60)
            if response["finished"]:
                break
        self.assertTrue(response["finished"])
        battle = response["battle"]
        self.assertIn(battle["outcome"], ("team_a_win", "team_b_win", "draw", "timeout"))
        self.assertIn("leadRecords", battle)
        self.assertEqual(response["events"][-1]["type"] in ("battle_end", "timeout"), True)
        # 结束后继续 step 不再产生事件
        after = session.step(10)
        self.assertEqual(after["events"], [])
        self.assertTrue(after["finished"])

    def test_event_format_matches_replay(self):
        """实时事件与回放导出格式一致：同种子同指令下逐条对比"""
        from src.event_exporter import build_battle_document

        engine, a, b = make_engine(seed=99)
        sa, sb = a.snapshot(), b.snapshot()
        session = BattleSession(engine, sa, sb, seed=99)
        live_events = session.initial_document()["events"]
        for _ in range(2000):
            response = session.step(60)
            live_events.extend(response["events"])
            if response["finished"]:
                break

        engine2, a2, b2 = make_engine(seed=99)
        sa2, sb2 = a2.snapshot(), b2.snapshot()
        result = engine2.run()
        doc = build_battle_document(result, [sa2], [sb2], seed=99)
        self.assertEqual(len(live_events), len(doc["events"]))
        for live, replay in zip(live_events, doc["events"]):
            self.assertEqual(live["type"], replay["type"])
            self.assertEqual(live["tick"], replay["tick"])
            self.assertEqual(live["round"], replay["round"])
            self.assertEqual(live["state"], replay["state"])
            self.assertEqual(live["effects"], replay["effects"])


class SessionStoreTest(unittest.TestCase):
    def make_session(self):
        engine, a, b = make_engine()
        return BattleSession(engine, a.snapshot(), b.snapshot())

    def test_create_step_close(self):
        store = SessionStore()
        session_id = store.create(self.make_session())
        result = store.step(session_id, 5, None)
        self.assertIsNotNone(result)
        self.assertTrue(store.close(session_id))
        self.assertIsNone(store.step(session_id, 5, None))
        self.assertFalse(store.close(session_id))

    def test_unknown_session_returns_none(self):
        store = SessionStore()
        self.assertIsNone(store.step("missing", 5, None))

    def test_evicts_over_limit(self):
        store = SessionStore()
        store.LIMIT = 3
        ids = [store.create(self.make_session()) for _ in range(5)]
        self.assertIsNone(store.step(ids[0], 5, None))
        self.assertIsNotNone(store.step(ids[-1], 5, None))


if __name__ == "__main__":
    unittest.main()