# 距离、攻击范围、寻路系统实现计划

## 背景与已确认决策
项目目前是纯数值 1v1 模拟器，完全没有空间概念（无坐标/地图/移动，兵器只有名称和类别）。本次从零新建空间层，保持「Python 判定 → JSON 事件 → 网页只演」架构与同种子确定性。你已确认：二维网格地图 + A*、移动打断攻击、射程按兵器类别+单件配置、网页端同步演出。

## 核心设计
opt-in 兼容：BattleEngine(..., battle_map=None)，不传地图行为与现在完全一致（旧测试/旧 JSON 零回归）；main.py 3 处构造点传入内置地图。
地图：新建 src/map.py，13×7「演武场」，出生点 (2,3)/(10,3)，中央岩墙+散石障碍（旋转对称）；MAP_REGISTRY 注册表模式。
距离：切比雪夫距离（全整数，与 8 向移动、格子高亮天然对齐）；Bresenham 视线检查，障碍后不可攻击。
寻路：A*（heapq 全序 tie-break，零随机）+ find_path_to_range——走到「能打到的位置」就停，长枪停在 3 格外。
射程：Weapon 加 reach 可选字段 + effective_reach；类别默认 枪矛=3 / 长柄刀=2 / 戟=2 / 重型=1；无兵器=1。
移动：移速 = 50+敏捷（随体力衰减）；每格累积 100 进度（约 14 tick/格）；移动中不攒 AP、不能攻击，起手移动重置前摇；后摇期间锁定站位不能移动（博弈节拍）；v1 不做风筝 AI。
run_tick 新顺序：移动阶段 → AP 累积 → 后摇推进 → 射程门槛过滤的就绪攻击 → 原有结算。

## 实施阶段（每步独立可验证）
1. 地图与寻路：src/map.py（新）、enums.py 地形枚举、constants.py 移动常量
2. 兵器射程：weapons.py、warrior.py reach/快照字段、__init__.py 导出
3. 移动状态：warrior.py begin_move/tick_move/advance_cell/stop_move
4. 引擎集成：battle_engine.py 布阵、_update_movement、射程门槛、move/坐标日志；main.py 3 处传图
5. 事件导出：event_exporter.py 顶层 map、move 事件、state 含 position、version 2
6. 前端演出：DOM 网格+岩石渲染、单位按坐标定位、rAF 移动动画（暂停安全，不用 CSS transition）、射程格高亮+开关按钮、朝向动态化、restore 精确重建；旧 JSON 走 legacy 演出
7. 战报收尾：battle_report.py 射程/攻击距离/移动行、README

## 测试与验证
新建 tests/test_movement.py（7 组用例：地图/寻路/射程/移动/引擎集成/导出/确定性），不动在途的 test_combat.py
python -m unittest tests.test_movement tests.test_combat 全绿
python main.py --seed 123 --export-web 检查 JSON；--serve-web 浏览器验证绕行接近、射程高亮、暂停/倍速/拖动/跳到结果站位精确、控制台无报错
同 seed 两次输出除 generatedAt 外一致

文件清单：修改 14 个现有文件（均为增量），新建 src/map.py、tests/test_movement.py。