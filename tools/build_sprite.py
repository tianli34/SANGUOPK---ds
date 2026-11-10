"""把 Cocos2d / TexturePacker 图集整理成网页可直接播放的横向精灵条带。

每个朝向的每个动作输出一张横向条带（帧等宽等高、对齐一致），并写入
web/data/sprites.js 供前端按武将名称查找。各朝向共用同一包围盒，
切换朝向时单位不会忽大忽小。开发期依赖 Pillow：

    python tools/build_sprite.py "武将精灵图/关羽" --name 关羽 --slug guanyu

图集可用的朝向为 1/5/6/7/8（下、上、右上、右、右下），左侧朝向
由前端镜像右侧条带得到。生成物提交到仓库后，运行网页不需要 Python 环境。
"""

import argparse
import json
import os
import plistlib
import re
import sys

from PIL import Image

ACTION_ORDER = ("idle", "run", "attack", "stuck", "die")
ACTION_MS = {"idle": 170, "run": 80, "attack": 38, "stuck": 140, "die": 210}
DIRECTIONS = (1, 5, 6, 7, 8)
PAD = 4


def parse_rect(text):
    nums = [float(v) for v in re.findall(r"-?\d+\.?\d*", text)]
    if len(nums) == 2:
        return (0, 0), (nums[0], nums[1])
    return (nums[0], nums[1]), (nums[2], nums[3])


def load_frames(folder):
    frames = {}
    for name in sorted(os.listdir(folder)):
        if not name.endswith(".plist"):
            continue
        with open(os.path.join(folder, name), "rb") as handle:
            data = plistlib.load(handle)
        png = os.path.join(folder, data["metadata"]["textureFileName"])
        for key, info in data["frames"].items():
            frames[key] = (info, png)
    return frames


def frame_image(frames, cache, key):
    info, png = frames[key]
    if png not in cache:
        cache[png] = Image.open(png).convert("RGBA")
    (x, y), (w, h) = parse_rect(info["frame"])
    if info["rotated"]:
        piece = cache[png].crop((x, y, x + h, y + w)).transpose(Image.ROTATE_90)
    else:
        piece = cache[png].crop((x, y, x + w, y + h))

    source_size = parse_rect(info["sourceSize"])[1]
    (cx, cy), _ = parse_rect(info["sourceColorRect"])
    canvas = Image.new("RGBA", (round(source_size[0]), round(source_size[1])))
    canvas.alpha_composite(piece, (round(cx), round(cy)))
    return canvas


def action_frames(frames, action, direction):
    keys = []
    index = 1
    while True:
        key = f"{action}{direction}_{index:04d}.png"
        if key not in frames:
            break
        keys.append(key)
        index += 1
    return keys


def collect_images(frames, direction, cache):
    """取出一个朝向的全部动作帧；缺少任一动作时返回 None"""
    images = {}
    for action in ACTION_ORDER:
        keys = action_frames(frames, action, direction)
        if not keys:
            return None
        images[action] = [frame_image(frames, cache, key) for key in keys]
    return images


def content_box(images):
    boxes = [img.getbbox() for group in images.values() for img in group]
    boxes = [box for box in boxes if box]
    if not boxes:
        return None
    return (
        max(0, min(box[0] for box in boxes) - PAD),
        max(0, min(box[1] for box in boxes) - PAD),
        min(700, max(box[2] for box in boxes) + PAD),
        min(700, max(box[3] for box in boxes) + PAD),
    )


def build(folder, name, slug, directions, web_dir, portrait, portrait_dir):
    frames = load_frames(folder)
    cache = {}

    # 第一遍扫描各方向的并集包围盒，保证切换朝向时单位大小不跳变
    boxes = []
    for direction in directions:
        images = collect_images(frames, direction, cache)
        if images is None:
            print(f"跳过方向 {direction}：缺少 idle/run/attack/stuck/die 中的动作帧")
            continue
        box = content_box(images)
        if box:
            boxes.append(box)
    if not boxes:
        raise SystemExit(f"{name}: 图集里没有完整可用的朝向")

    left = min(box[0] for box in boxes)
    top = min(box[1] for box in boxes)
    right = max(box[2] for box in boxes)
    bottom = max(box[3] for box in boxes)
    cell_w, cell_h = right - left, bottom - top

    out_dir = os.path.join(web_dir, "assets", "sprites", slug)
    os.makedirs(out_dir, exist_ok=True)
    entry = {"slug": slug, "cell": [cell_w, cell_h], "dirs": {}}

    # 第二遍逐方向裁切输出，避免同时把上百帧原图留在内存里
    for direction in directions:
        images = collect_images(frames, direction, cache)
        if images is None:
            continue
        actions = {}
        for action in ACTION_ORDER:
            group = [img.crop((left, top, right, bottom)) for img in images[action]]
            strip = Image.new("RGBA", (cell_w * len(group), cell_h))
            for index, img in enumerate(group):
                strip.paste(img, (index * cell_w, 0))
            filename = f"{action}-{direction}.png"
            strip.save(os.path.join(out_dir, filename), optimize=True)
            actions[action] = {
                "src": f"assets/sprites/{slug}/{filename}",
                "frames": len(group),
                "ms": ACTION_MS[action],
            }
        entry["dirs"][str(direction)] = actions

        if portrait and direction == portrait_dir:
            crop = [int(v) for v in portrait.split(",")]
            head = images["idle"][0].crop(tuple(crop))
            head.save(os.path.join(out_dir, "portrait.png"), optimize=True)
            entry["portrait"] = f"assets/sprites/{slug}/portrait.png"

    if not entry["dirs"]:
        raise SystemExit(f"{name}: 没有输出任何朝向")

    data_path = os.path.join(web_dir, "data", "sprites.js")
    existing = {}
    if os.path.exists(data_path):
        with open(data_path, encoding="utf-8") as handle:
            matched = re.search(r"window\.WarriorSprites\s*=\s*(\{.*\});", handle.read(), re.S)
        if matched:
            existing = json.loads(matched.group(1))
    existing[name] = entry
    with open(data_path, "w", encoding="utf-8") as handle:
        handle.write("/* 由 tools/build_sprite.py 生成，请勿手改 */\n")
        handle.write("window.WarriorSprites = ")
        handle.write(json.dumps(existing, ensure_ascii=False, indent=2, sort_keys=True))
        handle.write(";\n")

    first = entry["dirs"][next(iter(entry["dirs"]))]
    print(f"{name}: 单元格 {cell_w}x{cell_h}，朝向 " + "、".join(entry["dirs"]))
    print("  每朝向帧数 " + "、".join(
        f"{action} {first[action]['frames']}" for action in ACTION_ORDER
    ))


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="生成武将精灵条带与前端数据")
    parser.add_argument("folder", help="图集目录（含 .plist 与 .png）")
    parser.add_argument("--name", required=True, help="武将名称，用于前端匹配")
    parser.add_argument("--slug", required=True, help="资源目录名，建议英文")
    parser.add_argument(
        "--dirs",
        default=",".join(str(d) for d in DIRECTIONS),
        help="导出的朝向编号，逗号分隔（默认 1,5,6,7,8）",
    )
    parser.add_argument("--portrait-dir", type=int, default=7, help="取头像用的朝向（默认 7）")
    parser.add_argument("--web", default="web", help="网页根目录")
    parser.add_argument("--portrait", help="头像裁切 x1,y1,x2,y2，省略则不生成头像")
    args = parser.parse_args()
    directions = [int(v) for v in args.dirs.split(",") if v.strip()]
    build(args.folder, args.name, args.slug, directions, args.web, args.portrait, args.portrait_dir)


if __name__ == "__main__":
    main()
