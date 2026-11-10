# 文件名: tests/test_backdrop.py
# 用途: 战场底图切片清单解析与随机选择的单元测试

import random
import struct
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.backdrop import load_battlefield, load_battlefields, pick_backdrop


def write_png_header(path: Path, width: int, height: int) -> None:
    """只写 PNG 签名与 IHDR 头，够外部读取宽高即可"""
    header = (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13)
        + b"IHDR"
        + struct.pack(">II", width, height)
    )
    path.write_bytes(header)


def make_battlefield(root: Path, name: str, tiles) -> Path:
    """tiles: (十六进制序号, 宽, 高)；素材命名是 <ID>_0x<序号>.png"""
    folder = root / name
    folder.mkdir(parents=True)
    for index, width, height in tiles:
        write_png_header(folder / f"{name}_0x{index:x}.png", width, height)
    return folder


class BackdropTest(unittest.TestCase):
    def test_four_tiles_compose_into_two_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = make_battlefield(
                root,
                "battleField_1003",
                [(0, 1024, 1024), (1, 776, 1024), (2, 1024, 176), (3, 776, 176)],
            )
            field = load_battlefield(folder)
            self.assertIsNotNone(field)
            self.assertEqual((field.width, field.height), (1800, 1200))
            offsets = {(tile.x, tile.y): (tile.width, tile.height) for tile in field.tiles}
            self.assertEqual(offsets[(0, 0)], (1024, 1024))
            self.assertEqual(offsets[(1024, 0)], (776, 1024))
            self.assertEqual(offsets[(0, 1024)], (1024, 176))
            self.assertEqual(offsets[(1024, 1024)], (776, 176))

            document = field.to_document()
            self.assertEqual(document["width"], 1800)
            self.assertEqual(document["tiles"][0]["src"], "../battleField/battleField_1003/battleField_1003_0x0.png")

    def test_six_tiles_infer_three_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = make_battlefield(
                Path(tmp),
                "battleField_1044",
                [
                    (0, 1024, 1024), (1, 1024, 1024), (2, 453, 1024),
                    (3, 1024, 526), (4, 1024, 526), (5, 453, 526),
                ],
            )
            field = load_battlefield(folder)
            self.assertIsNotNone(field)
            self.assertEqual((field.width, field.height), (2501, 1550))
            positions = {(tile.x, tile.y) for tile in field.tiles}
            self.assertIn((2048, 0), positions)
            self.assertIn((0, 1024), positions)
            self.assertIn((2048, 1024), positions)

    def test_invalid_files_are_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = make_battlefield(Path(tmp), "battleField_1", [(0, 900, 844)])
            (folder / "battleField_1_notes.txt").write_text("非图片", encoding="utf-8")
            (folder / "broken.png").write_bytes(b"not a png")
            field = load_battlefield(folder)
            self.assertIsNotNone(field)
            self.assertEqual(len(field.tiles), 1)

    def test_empty_folder_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "battleField_2"
            folder.mkdir()
            self.assertIsNone(load_battlefield(folder))

    def test_missing_root_returns_empty(self):
        missing = Path(tempfile.gettempdir()) / "sanguopk_no_such_backdrop_dir"
        self.assertEqual(load_battlefields(missing), [])
        self.assertIsNone(pick_backdrop(root=missing))

    def test_load_sorted_and_pick_is_seeded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("battleField_10", "battleField_2"):
                make_battlefield(root, name, [(0, 800, 600)])
            fields = load_battlefields(root)
            self.assertEqual([field.id for field in fields], ["battleField_2", "battleField_10"])

            picked = [pick_backdrop(random.Random(seed), root)["id"] for seed in range(6)]
            self.assertEqual(picked, [pick_backdrop(random.Random(seed), root)["id"] for seed in range(6)])
            self.assertTrue(set(picked).issubset({"battleField_2", "battleField_10"}))
            self.assertEqual(len(set(picked)), 2)


if __name__ == "__main__":
    unittest.main()
