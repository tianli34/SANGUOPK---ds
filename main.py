# 文件名: main.py
# 用途: 程序主入口文件，运行武将对决模拟并生成战斗报告
"""三国武将对决模拟入口"""

import argparse
import json
import random
import secrets
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, unquote, urlsplit

from src import SKILL_REGISTRY, WEAPON_REGISTRY, Warrior, BattleEngine, get_skill, get_weapon, get_default_map
from src.backdrop import backdrop_root, pick_backdrop
from src.battle_report import AggregateReporter, BattleReporter
from src.event_exporter import build_battle_document, write_battle_json, write_battle_js
from src.interactive import BattleSession, SessionStore
from src.seed_history import SeedHistory, SeedRecord
from src.warrior_data import (
    DEFAULT_WARRIORS,
    STAT_FIELDS,
    STAT_LABELS,
    WARRIOR_PRESETS,
)

WEAPON_CHOICES = ["none", *sorted(WEAPON_REGISTRY)]
WARRIOR_CHOICES = sorted(WARRIOR_PRESETS)


def skill_id(value: str) -> str:
    """校验并返回特技 ID"""
    if value not in SKILL_REGISTRY:
        raise argparse.ArgumentTypeError(
            f"未知特技: {value}（可选：{'、'.join(sorted(SKILL_REGISTRY))}）"
        )
    return value


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器"""
    parser = argparse.ArgumentParser(description="三国武将对决模拟")
    parser.add_argument("-n", "--battles", type=int, default=1, help="模拟场次（默认 1）")
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help=(
            "随机种子；设置后第 i 场使用 seed + i。"
            "默认每场自动生成种子并记入 data/seed_history.json，可凭记录复现"
        ),
    )
    parser.add_argument(
        "--export-json",
        metavar="路径",
        default=None,
        help="把结构化战斗事件写入指定 JSON 文件（仅支持单场）",
    )
    parser.add_argument(
        "--export-web",
        action="store_true",
        help="导出到 web/data/battle.json 与 battle-data.js（仅支持单场）",
    )
    parser.add_argument(
        "--serve-web",
        action="store_true",
        help="启动本地网页服务，页面可实时生成新战局（支持 --host / --port）",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="本地网页服务监听地址（默认 127.0.0.1，仅本机可访问）",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="本地网页服务端口（默认 8000）",
    )

    for side, defaults in DEFAULT_WARRIORS.items():
        prefix = side.upper()
        parser.add_argument(
            f"--{side}-warrior",
            default=None,
            choices=WARRIOR_CHOICES,
            help=(
                f"{prefix}队名将预设（可选：{'、'.join(WARRIOR_CHOICES)}）；"
                "指定后覆盖该侧名称、属性、特技与兵器"
            ),
        )
        parser.add_argument(
            f"--{side}-name", default=defaults["name"], help=f"{prefix}队武将名"
        )
        for field in STAT_FIELDS:
            parser.add_argument(
                f"--{side}-{field}",
                type=int,
                default=defaults[field],
                help=f"{prefix}队 {STAT_LABELS[field]}（默认 {defaults[field]}）",
            )
        parser.add_argument(
            f"--{side}-skill",
            action="append",
            type=skill_id,
            default=None,
            metavar="特技ID",
            help=(
                f"{prefix}队装备特技，可重复指定；不指定时沿用名将预设。"
                f"指定后覆盖预设特技。可选：{'、'.join(sorted(SKILL_REGISTRY))}"
            ),
        )
        parser.add_argument(
            f"--{side}-skill-off",
            action="append",
            type=skill_id,
            default=None,
            metavar="特技ID",
            help=f"{prefix}队关闭指定特技的开关（对预设特技同样有效）",
        )
        parser.add_argument(
            f"--{side}-skill-on",
            action="append",
            type=skill_id,
            default=None,
            metavar="特技ID",
            help=f"{prefix}队重新打开指定特技的开关",
        )
        parser.add_argument(
            f"--{side}-weapon",
            default=defaults["weapon"],
            choices=WEAPON_CHOICES,
            help=f"{prefix}队兵器（默认 {defaults['weapon']}；none 表示不装备）",
        )

    return parser


def create_warrior(
    args: argparse.Namespace,
    side: str,
    warrior_override: Optional[str] = None,
    skills_override: Optional[dict] = None,
) -> Warrior:
    """根据命令行参数创建武将并装备指定特技、兵器

    指定 --a-warrior / --b-warrior 时按名将预设整体创建，预设覆盖该侧的
    名称、属性、特技与兵器；未指定时沿用原有的逐项参数。
    显式传入 --a-skill / --b-skill 时覆盖预设特技，可重复指定多个；
    --a-skill-off / --a-skill-on 用来切换任意已装备特技的开关。
    warrior_override / skills_override 供网页开局配置覆盖武将预设与特技，
    skills_override 为 {特技ID: 是否开启}，传入空字典表示不装备任何特技。
    """
    preset_name = warrior_override or getattr(args, f"{side}_warrior", None)
    if preset_name:
        preset = WARRIOR_PRESETS[preset_name]
        name = preset["name"]
        stats = {field: preset[field] for field in STAT_FIELDS}
        weapon_name = preset["weapon"]
        default_skills = preset["skills"]
    else:
        name = getattr(args, f"{side}_name")
        stats = {field: getattr(args, f"{side}_{field}") for field in STAT_FIELDS}
        weapon_name = getattr(args, f"{side}_weapon")
        default_preset = DEFAULT_WARRIORS[side]
        default_skills = (
            default_preset["skills"] if name == default_preset["name"] else {}
        )

    weapon = None
    if weapon_name and weapon_name != "none":
        weapon = get_weapon(weapon_name)
    warrior = Warrior(name, side.upper(), **stats, weapon=weapon)

    if skills_override is not None:
        skill_specs = dict(skills_override)
    else:
        selected_skills = getattr(args, f"{side}_skill")
        skill_specs = (
            {sid: True for sid in selected_skills}
            if selected_skills
            else dict(default_skills)
        )
    for skill_name, enabled in skill_specs.items():
        skill = get_skill(skill_name)
        skill.set_enabled(enabled)
        if warrior.equip_skill(skill):
            continue
        if skill.is_exclusive:
            raise ValueError(
                f"特技【{skill.name}】为 {skill.owner} 专属，{warrior.name} 无法装备"
            )
        raise ValueError(f"{warrior.name} 重复装备特技【{skill.name}】")

    for skill_name in getattr(args, f"{side}_skill_off") or []:
        if not warrior.set_skill_enabled(skill_name, False):
            raise ValueError(f"{warrior.name} 未装备特技 {skill_name}，无法关闭开关")
    for skill_name in getattr(args, f"{side}_skill_on") or []:
        if not warrior.set_skill_enabled(skill_name, True):
            raise ValueError(f"{warrior.name} 未装备特技 {skill_name}，无法打开开关")
    return warrior


def parse_skills_param(raw: str) -> dict:
    """解析网页特技配置：逗号分隔的 特技ID[:0|1]，缺省开关为开启"""
    specs: dict = {}
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        skill_name, _, flag = item.partition(":")
        if skill_name not in SKILL_REGISTRY:
            raise ValueError(
                f"未知特技: {skill_name}（可选：{'、'.join(sorted(SKILL_REGISTRY))}）"
            )
        if flag and flag not in ("0", "1"):
            raise ValueError(f"特技开关只能为 0 或 1: {item}")
        specs[skill_name] = flag != "0"
    return specs


def side_defaults(args: argparse.Namespace, side: str) -> dict:
    """当前命令行配置对应的网页默认开局（武将预设名 + 特技开关）"""
    preset_name = getattr(args, f"{side}_warrior", None)
    if preset_name:
        skills = dict(WARRIOR_PRESETS[preset_name]["skills"])
    else:
        name = getattr(args, f"{side}_name")
        preset_name = name if name in WARRIOR_PRESETS else None
        default_preset = DEFAULT_WARRIORS[side]
        skills = (
            dict(default_preset["skills"]) if name == default_preset["name"] else {}
        )
    selected = getattr(args, f"{side}_skill")
    if selected:
        skills = {sid: True for sid in selected}
    for sid in getattr(args, f"{side}_skill_off") or []:
        if sid in skills:
            skills[sid] = False
    for sid in getattr(args, f"{side}_skill_on") or []:
        if sid in skills:
            skills[sid] = True
    return {"warrior": preset_name, "skills": skills}


def parse_battle_setup(args: argparse.Namespace, query: dict) -> dict:
    """把 /api/battle 查询参数解析成两侧 create_warrior 的覆盖项

    参数：a_warrior / b_warrior（名将预设名），a_skills / b_skills
    （逗号分隔的 特技ID[:0|1]；传空串表示不装备任何特技，缺省沿用预设）。
    专属特技只能配置给归属武将，否则抛出 ValueError。
    """
    setup: dict = {}
    for side in ("a", "b"):
        overrides: dict = {}
        warrior_values = query.get(f"{side}_warrior")
        if warrior_values:
            warrior = warrior_values[0]
            if warrior not in WARRIOR_PRESETS:
                raise ValueError(
                    f"未知武将: {warrior}（可选：{'、'.join(WARRIOR_CHOICES)}）"
                )
            overrides["warrior_override"] = warrior
        skills_values = query.get(f"{side}_skills")
        if skills_values is not None:
            overrides["skills_override"] = parse_skills_param(skills_values[0])
        if overrides:
            preset_name = overrides.get("warrior_override") or getattr(
                args, f"{side}_warrior", None
            )
            name = (
                WARRIOR_PRESETS[preset_name]["name"]
                if preset_name
                else getattr(args, f"{side}_name")
            )
            for sid in overrides.get("skills_override", {}):
                skill_cls = SKILL_REGISTRY[sid]
                if skill_cls.owner and skill_cls.owner != name:
                    raise ValueError(
                        f"特技【{skill_cls.name}】为 {skill_cls.owner} 专属，"
                        f"{name} 无法装备"
                    )
        setup[side] = overrides
    return setup


def build_options_document(args: argparse.Namespace) -> dict:
    """网页开局配置面板所需的武将预设、特技表与默认配置"""
    warriors = [
        {
            "name": preset["name"],
            "stats": {field: preset[field] for field in STAT_FIELDS},
            "weapon": preset["weapon"],
            "skills": dict(preset["skills"]),
        }
        for preset in WARRIOR_PRESETS.values()
    ]
    skills = [skill_cls().to_dict() for skill_cls in SKILL_REGISTRY.values()]
    return {
        "warriors": warriors,
        "skills": skills,
        "statLabels": dict(STAT_LABELS),
        "defaults": {side: side_defaults(args, side) for side in ("a", "b")},
    }


def apply_seed(seed: Optional[int], battle_index: int) -> int:
    """为第 battle_index 场战斗设置随机种子，返回本次实际使用的种子

    指定 seed 时按场次派生（seed + battle_index），使同一 seed 下前 k 场的结果
    与 -n k 完全一致；未指定 seed 时生成一次性随机种子并立即应用，
    使该场战斗同样可以凭种子历史中的记录复现。
    """
    resolved = seed + battle_index if seed is not None else secrets.randbits(32)
    random.seed(resolved)
    return resolved


def build_random_document(
    args: argparse.Namespace, setup: Optional[dict] = None
) -> dict:
    """用随机种子现场模拟一场新战斗，返回网页可直接播放的事件文档

    setup 为 parse_battle_setup 的结果，按侧覆盖武将预设与特技配置。
    """
    seed = secrets.randbits(32)
    random.seed(seed)
    backdrop = pick_backdrop()
    setup = setup or {}
    warrior_a = create_warrior(args, "a", **setup.get("a", {}))
    warrior_b = create_warrior(args, "b", **setup.get("b", {}))
    snapshot_a = warrior_a.snapshot()
    snapshot_b = warrior_b.snapshot()
    result = BattleEngine([warrior_a], [warrior_b], battle_map=get_default_map()).run()
    return build_battle_document(
        result, [snapshot_a], [snapshot_b], seed=seed, backdrop=backdrop
    )


def build_live_session(
    args: argparse.Namespace, setup: Optional[dict] = None
) -> tuple:
    """创建实时操控会话：返回 (会话, 初始文档)，战斗由网页逐步推进"""
    seed = secrets.randbits(32)
    random.seed(seed)
    backdrop = pick_backdrop()
    setup = setup or {}
    warrior_a = create_warrior(args, "a", **setup.get("a", {}))
    warrior_b = create_warrior(args, "b", **setup.get("b", {}))
    snapshot_a = warrior_a.snapshot()
    snapshot_b = warrior_b.snapshot()
    engine = BattleEngine([warrior_a], [warrior_b], battle_map=get_default_map())
    session = BattleSession(
        engine, snapshot_a, snapshot_b, seed=seed, backdrop=backdrop
    )
    return session, session.initial_document()


def serve_web(args: argparse.Namespace) -> None:
    """本地网页服务：静态页面 + /api/battle 新战局 + /api/session 实时操控"""
    web_dir = Path(__file__).resolve().parent / "web"
    if not (web_dir / "index.html").exists():
        print(f"未找到网页目录: {web_dir}", file=sys.stderr)
        return

    sessions = SessionStore()

    class Handler(SimpleHTTPRequestHandler):
        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            if path == "/api/health":
                self._send_json({"ok": True})
                return
            if path == "/api/options":
                self._send_json(build_options_document(args))
                return
            if path == "/api/battle":
                query = parse_qs(
                    urlsplit(self.path).query, keep_blank_values=True
                )
                try:
                    setup = parse_battle_setup(args, query)
                    document = build_random_document(args, setup)
                except ValueError as error:
                    self._send_json({"error": str(error)}, status=400)
                    return
                except Exception as error:  # noqa: BLE001 - HTTP 边界统一转成错误响应
                    self._send_json({"error": str(error)}, status=500)
                    return
                self._send_json(document)
                return
            if path == "/api/session/new":
                query = parse_qs(
                    urlsplit(self.path).query, keep_blank_values=True
                )
                try:
                    setup = parse_battle_setup(args, query)
                    session, document = build_live_session(args, setup)
                except ValueError as error:
                    self._send_json({"error": str(error)}, status=400)
                    return
                except Exception as error:  # noqa: BLE001 - HTTP 边界统一转成错误响应
                    self._send_json({"error": str(error)}, status=500)
                    return
                session_id = sessions.create(session)
                self._send_json({"sessionId": session_id, "doc": document})
                return
            if path.startswith("/battleField/"):
                self._send_backdrop(path)
                return
            super().do_GET()

        def do_POST(self) -> None:
            path = urlsplit(self.path).path
            if path not in ("/api/session/step", "/api/session/close"):
                self.send_error(404)
                return
            try:
                length = int(self.headers.get("Content-Length", 0))
                payload = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                self._send_json({"error": "请求体不是合法 JSON"}, status=400)
                return
            if not isinstance(payload, dict):
                self._send_json({"error": "请求体必须是 JSON 对象"}, status=400)
                return
            session_id = payload.get("sessionId")
            if path == "/api/session/close":
                sessions.close(session_id)
                self._send_json({"ok": True})
                return
            try:
                result = sessions.step(
                    session_id, payload.get("ticks", 2), payload.get("commands")
                )
            except Exception as error:  # noqa: BLE001 - HTTP 边界统一转成错误响应
                self._send_json({"error": str(error)}, status=500)
                return
            if result is None:
                self._send_json({"error": "会话不存在或已过期"}, status=404)
                return
            self._send_json(result)

        def _send_backdrop(self, path: str) -> None:
            """从项目 battleField 目录返回战场底图切片（web 服务根目录是 web/）"""
            root = backdrop_root().resolve()
            relative = unquote(path[len("/battleField/"):])
            target = (root / relative).resolve()
            try:
                target.relative_to(root)
            except ValueError:
                self.send_error(404)
                return
            if not target.is_file():
                self.send_error(404)
                return
            body = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "public, max-age=3600")
            self.end_headers()
            self.wfile.write(body)

        def _send_json(self, payload: dict, status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            # 允许 file:// 打开的页面（Origin: null）跨域请求本地接口
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self) -> None:
            if urlsplit(self.path).path.startswith("/api/"):
                self.send_response(204)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "*")
                self.end_headers()
                return
            self.send_error(405)

    handler = partial(Handler, directory=str(web_dir))
    try:
        server = ThreadingHTTPServer((args.host, args.port), handler)
    except OSError as error:
        print(f"无法启动本地服务: {error}", file=sys.stderr)
        return

    print(f"网页服务已启动: http://{args.host}:{args.port}/")
    print("点击「新的一局」可选择对战武将与特技并生成新战斗；")
    print("点击「实时操控」可用键盘手动控制武将；按 Ctrl+C 停止。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n本地服务已停止。")
    finally:
        server.server_close()


def main() -> None:
    """运行单挑模拟"""
    # Windows 默认 GBK 无法输出 ▶⚔☠ 等符号，统一使用 UTF-8
    # 必须在解析参数前设置，否则 -h 帮助信息仍会使用 GBK
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    parser = build_parser()
    args = parser.parse_args()
    if args.battles < 1:
        parser.error("--battles 必须大于等于 1")
    if (args.export_json or args.export_web) and args.battles != 1:
        parser.error("导出结构化事件仅支持单场战斗（--battles 1）")
    if args.serve_web:
        if args.export_json or args.export_web:
            parser.error("--serve-web 不能与导出参数同时使用")
        serve_web(args)
        return

    print(f"三国武将对决系统 - {args.battles}场单挑模拟")
    print("=" * 70)
    if args.seed is not None:
        print(f"随机种子: {args.seed}")

    # 每场战斗都需要全新的武将实例，先保存初始快照用于汇总战报
    original_a = create_warrior(args, "a")
    original_b = create_warrior(args, "b")
    snapshot_a = original_a.snapshot()
    snapshot_b = original_b.snapshot()

    if args.battles == 1:
        # 单场战报
        battle_seed = apply_seed(args.seed, 0)
        if args.seed is None:
            print(f"随机种子: {battle_seed}")
        reporter = BattleReporter([original_a], [original_b])
        engine = BattleEngine([original_a], [original_b], battle_map=get_default_map())
        result = engine.run()
        print(reporter.generate_full_report(result))

        history = SeedHistory()
        history.append(SeedRecord.from_result(battle_seed, result))
        history.save()

        if args.export_json or args.export_web:
            backdrop = pick_backdrop()
            document = build_battle_document(
                result, [snapshot_a], [snapshot_b], seed=battle_seed, backdrop=backdrop
            )
            if args.export_json:
                path = write_battle_json(document, Path(args.export_json))
                print(f"\n已导出结构化事件: {path}")
            if args.export_web:
                web_data = Path(__file__).resolve().parent / "web" / "data"
                json_path = write_battle_json(document, web_data / "battle.json")
                js_path = write_battle_js(document, web_data / "battle-data.js")
                print(f"已导出网页数据: {json_path}")
                print(f"已导出 file:// 兜底数据: {js_path}")
        print(f"\n种子历史已更新: {history.path}（保留最近 {history.limit} 条）")
        return

    # 多场汇总战报
    print("模拟进行中...")
    reporter = AggregateReporter(original_a.name, original_b.name)
    history = SeedHistory()

    for i in range(args.battles):
        battle_seed = apply_seed(args.seed, i)
        engine = BattleEngine(
            [create_warrior(args, "a")],
            [create_warrior(args, "b")],
            battle_map=get_default_map(),
        )
        result = engine.run()
        reporter.add_battle_result(result)
        history.append(SeedRecord.from_result(battle_seed, result))

        if (i + 1) % 10 == 0:
            print(f"  已完成 {i + 1}/{args.battles} 场...")

    history.save()

    print()
    print(reporter.generate_aggregate_report([snapshot_a], [snapshot_b]))
    print(f"\n种子历史已更新: {history.path}（保留最近 {history.limit} 条）")


if __name__ == "__main__":
    main()
