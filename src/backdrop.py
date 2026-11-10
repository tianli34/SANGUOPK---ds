# 文件名: backdrop.py
# 用途: 扫描 battleField 战场底图素材，生成网页可拼合的切片清单并按种子随机挑选
"""战场底图

每张战场底图是一张约 1644~2501 宽的俯视大图，按 1024 网格切成
``battleField_<ID>_0x<序号>.png`` 若干块（序号为十六进制、行优先）。
本模块只读取 PNG 头与文件名，不做像素解码：根据切片宽高推断列数，
再由网页端用 canvas 把切片拼回整图。

素材目录体积较大且不入版本库，缺失时返回空清单，网页回退为原有画面。
"""

from __future__ import annotations

import random
import re
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

BACKDROP_DIR_NAME = "battleField"
BACKDROP_URL_PREFIX = "../battleField"
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_TILE_INDEX = re.compile(r"^0x([0-9a-fA-F]+)$")


@dataclass(frozen=True)
class Tile:
    file: str
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class Battlefield:
    """一张完整战场底图：按列/行拼合后的尺寸与各切片偏移"""

    id: str
    width: int
    height: int
    tiles: Tuple[Tile, ...]

    def to_document(self, url_prefix: str = BACKDROP_URL_PREFIX) -> dict:
        return {
            "id": self.id,
            "width": self.width,
            "height": self.height,
            "tiles": [
                {
                    "src": f"{url_prefix}/{self.id}/{tile.file}",
                    "x": tile.x,
                    "y": tile.y,
                    "w": tile.width,
                    "h": tile.height,
                }
                for tile in self.tiles
            ],
        }


def backdrop_root() -> Path:
    return Path(__file__).resolve().parent.parent / BACKDROP_DIR_NAME


def _read_png_size(path: Path) -> Optional[Tuple[int, int]]:
    """只读 PNG 签名与 IHDR，拿宽高；非 PNG 或文件过短返回 None"""
    try:
        with path.open("rb") as handle:
            header = handle.read(24)
    except OSError:
        return None
    if len(header) < 24 or not header.startswith(_PNG_SIGNATURE):
        return None
    if header[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", header[16:24])
    if width <= 0 or height <= 0:
        return None
    return width, height


def _parse_tile_index(name: str) -> Optional[int]:
    """battleField_1003_0x1.png -> 1（十六进制序号，行优先）"""
    stem = name[:-4] if name.lower().endswith(".png") else ""
    if not stem:
        return None
    _, sep, token = stem.rpartition("_")
    if not sep:
        return None
    matched = _TILE_INDEX.match(token)
    return int(matched.group(1), 16) if matched else None


def _grid_shape(
    tiles: List[Tuple[int, int, int]], count: int
) -> Optional[Tuple[Dict[int, int], Dict[int, int]]]:
    """推断列数并返回各列宽度、各行高度

    tiles 为按序号排好的 (宽, 高, 序号)。列数取满足以下约束的最大值：
    同一列的宽度一致、同一行的行高一致、除最后一列外都等于最宽列（1024 切片）。
    """
    max_width = max(width for width, _, _ in tiles)
    for columns in range(count, 0, -1):
        if count % columns:
            continue
        rows = count // columns
        column_widths: Dict[int, int] = {}
        row_heights: Dict[int, int] = {}
        valid = True
        for position, (width, height, _) in enumerate(tiles):
            if position >= rows * columns:
                valid = False
                break
            col, row = position % columns, position // columns
            if column_widths.setdefault(col, width) != width:
                valid = False
                break
            if row_heights.setdefault(row, height) != height:
                valid = False
                break
        if not valid:
            continue
        # 最后一列允许是余量，其余列都应是完整切片宽度
        if all(column_widths[col] == max_width for col in range(columns - 1)):
            return column_widths, row_heights
    return None


def load_battlefield(folder: Path) -> Optional[Battlefield]:
    """读取单个战场文件夹；切片缺失或无法拼合时返回 None"""
    raw: List[Tuple[int, str, int, int]] = []
    for path in folder.glob("*.png"):
        index = _parse_tile_index(path.name)
        size = _read_png_size(path)
        if index is None or size is None:
            continue
        raw.append((index, path.name, size[0], size[1]))
    if not raw:
        return None

    raw.sort(key=lambda item: item[0])
    tiles = [(width, height, index) for index, _, width, height in raw]
    shape = _grid_shape(tiles, len(raw))
    if shape is None:
        return None
    column_widths, row_heights = shape

    col_offsets: Dict[int, int] = {}
    cursor = 0
    for col in sorted(column_widths):
        col_offsets[col] = cursor
        cursor += column_widths[col]
    row_offsets: Dict[int, int] = {}
    cursor = 0
    for row in sorted(row_heights):
        row_offsets[row] = cursor
        cursor += row_heights[row]

    built: List[Tile] = []
    for position, (index, name, width, height) in enumerate(raw):
        col, row = position % len(column_widths), position // len(column_widths)
        built.append(Tile(name, col_offsets[col], row_offsets[row], width, height))
    return Battlefield(
        id=folder.name,
        width=sum(column_widths.values()),
        height=sum(row_heights.values()),
        tiles=tuple(built),
    )


def load_battlefields(root: Optional[Path] = None) -> List[Battlefield]:
    """扫描素材根目录下的所有战场，按编号升序返回；目录不存在时返回空列表"""
    base = Path(root) if root is not None else backdrop_root()
    if not base.is_dir():
        return []

    def sort_key(field: Battlefield) -> Tuple[int, str]:
        suffix = field.id.rsplit("_", 1)[-1]
        return (int(suffix), field.id) if suffix.isdigit() else (10**9, field.id)

    fields = []
    for path in base.iterdir():
        if not path.is_dir():
            continue
        field = load_battlefield(path)
        if field is not None:
            fields.append(field)
    return sorted(fields, key=sort_key)


def pick_backdrop(
    rng: Optional[random.Random] = None, root: Optional[Path] = None
) -> Optional[dict]:
    """按给定随机源挑选一张战场底图；没有素材时返回 None"""
    fields = load_battlefields(root)
    if not fields:
        return None
    return (rng or random).choice(fields).to_document()
