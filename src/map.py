# 文件名: map.py
# 用途: 战场地图与寻路模块，定义网格地图、距离/视线判定与 A* 寻路
"""战场地图与寻路

二维网格 + 8 向移动，距离采用切比雪夫距离（全整数）；
A* 使用 heapq 全序 tie-break，不含任何随机，同输入必得同路径。
"""

import heapq
import math
from dataclasses import dataclass
from typing import Callable, Dict, FrozenSet, List, Optional, Tuple

from src.constants import LOS_SAMPLE_STEP
from src.enums import Terrain

Cell = Tuple[int, int]
Point = Tuple[float, float]

# 8 向邻居，固定顺序保证确定性
_DIRECTIONS: Tuple[Cell, ...] = (
    (-1, -1), (0, -1), (1, -1),
    (-1, 0), (1, 0),
    (-1, 1), (0, 1), (1, 1),
)

_TERRAIN_BY_CHAR = {".": Terrain.PLAIN, "#": Terrain.ROCK, "x": Terrain.BOUNDARY}


def chebyshev_distance(a: Point, b: Point) -> float:
    """切比雪夫距离：支持整数格与浮点坐标，与 8 向移动、格子高亮对齐"""
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def cell_center(cell: Cell) -> Point:
    """格子中心坐标：格 (x, y) 覆盖 [x, x+1) × [y, y+1)"""
    return (cell[0] + 0.5, cell[1] + 0.5)


def cell_at(point: Point) -> Cell:
    """浮点坐标所在的格子"""
    return (math.floor(point[0]), math.floor(point[1]))


def bresenham_cells(a: Cell, b: Cell) -> List[Cell]:
    """Bresenham 直线经过的格子（含两端点）"""
    x0, y0 = a
    x1, y1 = b
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    cells = []
    while True:
        cells.append((x0, y0))
        if (x0, y0) == (x1, y1):
            return cells
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


@dataclass(frozen=True)
class BattleMap:
    """不可变网格地图：grid[y][x] 为地形，spawn_a/spawn_b 为双方出生点"""

    name: str
    grid: Tuple[Tuple[Terrain, ...], ...]
    spawn_a: Cell
    spawn_b: Cell

    @classmethod
    def from_rows(
        cls, name: str, rows: List[str], spawns: Tuple[Cell, Cell]
    ) -> "BattleMap":
        """从字符行构建地图：'.' 平地，'#' 岩石，'x' 不可见禁行边界"""
        grid = tuple(tuple(_TERRAIN_BY_CHAR[ch] for ch in row) for row in rows)
        if not grid or any(len(row) != len(grid[0]) for row in grid):
            raise ValueError(f"地图 {name} 的行宽不一致")
        battle_map = cls(name, grid, spawns[0], spawns[1])
        for spawn in spawns:
            if not battle_map.is_walkable(spawn):
                raise ValueError(f"地图 {name} 的出生点 {spawn} 不可通行")
        return battle_map

    @property
    def width(self) -> int:
        return len(self.grid[0])

    @property
    def height(self) -> int:
        return len(self.grid)

    @property
    def obstacles(self) -> FrozenSet[Cell]:
        return frozenset(
            (x, y)
            for y, row in enumerate(self.grid)
            for x, terrain in enumerate(row)
            if terrain is not Terrain.PLAIN
        )

    @property
    def rocks(self) -> FrozenSet[Cell]:
        """需要绘制石块的格子；禁行边界不在此列"""
        return frozenset(
            (x, y)
            for y, row in enumerate(self.grid)
            for x, terrain in enumerate(row)
            if terrain is Terrain.ROCK
        )

    def spawn(self, side: str) -> Cell:
        return self.spawn_a if side == "A" else self.spawn_b

    def spawn_point(self, side: str) -> Point:
        """出生点对应的浮点坐标（格心）"""
        return cell_center(self.spawn(side))

    def in_bounds(self, cell: Cell) -> bool:
        return 0 <= cell[0] < self.width and 0 <= cell[1] < self.height

    def is_walkable(self, cell: Cell) -> bool:
        return self.in_bounds(cell) and self.grid[cell[1]][cell[0]] is Terrain.PLAIN

    def is_point_walkable(self, x: float, y: float, radius: float = 0.0) -> bool:
        """浮点坐标是否可站立：半径大于 0 时视为圆形身体，禁止压到障碍或出界"""
        if radius <= 0:
            return self.is_walkable(cell_at((x, y)))
        x0 = math.floor(x - radius)
        x1 = math.floor(x + radius)
        y0 = math.floor(y - radius)
        y1 = math.floor(y + radius)
        for cy in range(y0, y1 + 1):
            for cx in range(x0, x1 + 1):
                if self.is_walkable((cx, cy)):
                    continue
                nearest_x = min(max(x, cx), cx + 1)
                nearest_y = min(max(y, cy), cy + 1)
                if (x - nearest_x) ** 2 + (y - nearest_y) ** 2 < radius * radius - 1e-12:
                    return False
        return True

    def move_point(
        self,
        x: float,
        y: float,
        dx: float,
        dy: float,
        radius: float = 0.0,
        max_substep: float = 0.1,
    ) -> Point:
        """连续移动并处理碰撞：整步不可行时按 X/Y 轴分离滑动，逐步细分防穿越"""
        length = math.hypot(dx, dy)
        if length <= 0:
            return (x, y)
        steps = max(1, math.ceil(length / max_substep))
        sx = dx / steps
        sy = dy / steps
        for _ in range(steps):
            if self.is_point_walkable(x + sx, y + sy, radius):
                x += sx
                y += sy
            elif abs(sx) > 0 and self.is_point_walkable(x + sx, y, radius):
                x += sx
            elif abs(sy) > 0 and self.is_point_walkable(x, y + sy, radius):
                y += sy
            else:
                break
        return (x, y)

    def has_line_of_sight_points(self, a: Point, b: Point) -> bool:
        """浮点视线：沿线段采样，任一采样点落在障碍格内即视为遮挡"""
        ax, ay = a
        bx, by = b
        distance = math.hypot(bx - ax, by - ay)
        if distance <= 1e-9:
            return True
        samples = max(1, math.ceil(distance / LOS_SAMPLE_STEP))
        for index in range(1, samples):
            t = index / samples
            if not self.is_point_walkable(ax + (bx - ax) * t, ay + (by - ay) * t):
                return False
        return True

    def neighbors(self, cell: Cell) -> List[Cell]:
        """可通行的 8 向邻居；斜向不允许穿过两侧都是障碍的墙角"""
        x, y = cell
        result = []
        for dx, dy in _DIRECTIONS:
            nxt = (x + dx, y + dy)
            if not self.is_walkable(nxt):
                continue
            if dx != 0 and dy != 0:
                if not self.is_walkable((x + dx, y)) or not self.is_walkable((x, y + dy)):
                    continue
            result.append(nxt)
        return result

    def has_line_of_sight(self, a: Cell, b: Cell) -> bool:
        """Bresenham 视线：两端点之间的格子有障碍则不可攻击"""
        return all(
            self.is_walkable(cell) for cell in bresenham_cells(a, b)[1:-1]
        )

    def nearest_free(self, origin: Cell, occupied: FrozenSet[Cell] = frozenset()) -> Cell:
        """距 origin 最近的可通行空闲格（切比雪夫距离，坐标全序 tie-break）"""
        candidates = sorted(
            ((x, y) for y in range(self.height) for x in range(self.width)),
            key=lambda c: (chebyshev_distance(c, origin), c[1], c[0]),
        )
        for cell in candidates:
            if self.is_walkable(cell) and cell not in occupied:
                return cell
        raise ValueError(f"地图 {self.name} 没有可用的空闲格子")

    def find_path(
        self, start: Cell, goal: Cell, occupied: FrozenSet[Cell] = frozenset()
    ) -> Optional[List[Cell]]:
        """A* 到指定格子；返回不含起点的路径，不可达返回 None"""
        if not self.is_walkable(goal) or goal in occupied:
            return None
        return self._astar(
            start,
            is_goal=lambda cell: cell == goal,
            heuristic=lambda cell: chebyshev_distance(cell, goal),
            occupied=occupied,
        )

    def find_path_to_range(
        self,
        start: Cell,
        target: Cell,
        reach: int,
        occupied: FrozenSet[Cell] = frozenset(),
    ) -> Optional[List[Cell]]:
        """走到目标格射程内的格心位置就停（格子语义，保留给寻路测试）"""
        return self.find_path_to_point_range(
            start, cell_center(target), reach, occupied=occupied
        )

    def find_path_to_point_range(
        self,
        start: Cell,
        target: Point,
        reach: int,
        occupied: FrozenSet[Cell] = frozenset(),
    ) -> Optional[List[Cell]]:
        """走到「从格心能打到浮点目标」的位置：距离<=射程、视线通畅、可站立"""
        def is_goal(cell: Cell) -> bool:
            if cell in occupied:
                return False
            center = cell_center(cell)
            return (
                chebyshev_distance(center, target) <= reach
                and self.has_line_of_sight_points(center, target)
            )

        return self._astar(
            start,
            is_goal=is_goal,
            heuristic=lambda cell: max(
                0.0, chebyshev_distance(cell_center(cell), target) - reach
            ),
            occupied=occupied,
        )

    def _astar(
        self,
        start: Cell,
        is_goal: Callable[[Cell], bool],
        heuristic: Callable[[Cell], float],
        occupied: FrozenSet[Cell],
    ) -> Optional[List[Cell]]:
        if is_goal(start):
            return []
        # 堆条目 (f, h, x, y) 构成全序，tie-break 完全确定
        open_heap = [(heuristic(start), heuristic(start), start[0], start[1])]
        g_score = {start: 0}
        came_from: Dict[Cell, Cell] = {}
        closed = set()
        while open_heap:
            _, _, x, y = heapq.heappop(open_heap)
            current = (x, y)
            if current in closed:
                continue
            if is_goal(current):
                path = [current]
                while current in came_from:
                    current = came_from[current]
                    path.append(current)
                path.reverse()
                return path[1:]
            closed.add(current)
            for nxt in self.neighbors(current):
                if nxt in occupied or nxt in closed:
                    continue
                tentative = g_score[current] + 1
                if tentative < g_score.get(nxt, float("inf")):
                    g_score[nxt] = tentative
                    came_from[nxt] = current
                    h = heuristic(nxt)
                    heapq.heappush(open_heap, (tentative + h, h, nxt[0], nxt[1]))
        return None

    def to_dict(self) -> dict:
        """导出为网页可直接渲染的结构"""
        return {
            "name": self.name,
            "width": self.width,
            "height": self.height,
            "spawns": {
                "A": list(self.spawn_point("A")),
                "B": list(self.spawn_point("B")),
            },
            "obstacles": sorted([x, y] for x, y in self.obstacles),
            "rocks": sorted([x, y] for x, y in self.rocks),
        }


# 地图注册表：地图名 -> 地图实例
MAP_REGISTRY: Dict[str, BattleMap] = {}

DEFAULT_MAP_NAME = "演武场"


def register_map(battle_map: BattleMap) -> None:
    MAP_REGISTRY[battle_map.name] = battle_map


def get_map(name: str) -> BattleMap:
    """按地图名获取地图实例"""
    try:
        return MAP_REGISTRY[name]
    except KeyError:
        raise ValueError(f"未知地图: {name}") from None


def get_default_map() -> BattleMap:
    return MAP_REGISTRY[DEFAULT_MAP_NAME]


# 13×7 演武场：顶部整行禁行，左上与右下为不可见边界（坐标按 1 基书写，内部 0 基存储）
register_map(
    BattleMap.from_rows(
        DEFAULT_MAP_NAME,
        [
            "xxxxxxxxxxxxx",
            "xxxx.........",
            "x............",
            "x...........x",
            "...........xx",
            "..........xxx",
            "..........xxx",
        ],
        spawns=((2, 3), (10, 3)),
    )
)