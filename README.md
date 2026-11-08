# SANGUOPK---ds

三国武将单挑模拟器：命令行战报 + 马战可视化网页版。

## 运行网页版

环境要求：Python 3.8+，仅使用标准库，无需安装第三方依赖。

### 1. 生成战斗数据（可选）

网页读取的是 `web/data/` 下的战斗事件文件。仓库中已有一份数据；想换一场战斗时，在项目根目录执行：

```bash
python main.py --export-web
```

指定随机种子以复现同一场战斗，或自定义双方武将属性：

```bash
python main.py --seed 89 --export-web
python main.py --a-name 马超 --b-name 许褚 --b-skill opening_ap_50 --export-web
```

该命令会同时写入 `web/data/battle.json` 与 `web/data/battle-data.js`（后者用于直接打开网页时的兜底加载）。

### 2. 启动网页

方式一：本地服务器（推荐）

```bash
# 在项目根目录执行
python -m http.server 8000
```

浏览器访问 <http://localhost:8000/web/>。

方式二：直接打开文件

双击 `web/index.html`。此时浏览器无法 `fetch` 本地 JSON，页面会自动回退读取 `web/data/battle-data.js`，效果一致。

### 3. 播放操作

- 「开始」播放，「暂停 / 继续」控制播放，「重新播放」从头开始，「跳到结果」直接看胜负。
- 速度支持 1× / 2× / 4×。
- 拖动底部进度条可定位到任意事件；「上一步」或键盘 ← → 可逐条前后移动。
- 回退是按事件快照重建面板与战报，不是倒放动画；定位后按「继续」从该事件接着播。
- 右侧战报与左侧战场同步，显示每个事件的攻防判定、HP/SP/胆气变化与伤害。

## 命令行运行

```bash
python main.py                  # 单场单挑
python main.py -n 1000          # 批量模拟并输出汇总战报
python main.py --seed 89        # 指定随机种子，可复现
```

每次模拟的随机种子会记录在 `data/seed_history.json`，可凭种子复现结果。

## 目录结构

```
main.py              # 程序入口与命令行参数
src/                 # 战斗引擎、战报、事件导出等核心逻辑
web/                 # 可视化网页
  index.html
  css/style.css
  js/app.js          # 播放控制、面板与战报同步
  js/scene.js        # 战场动画
  js/warrior-art.js  # 武将立绘绘制
  data/              # 由 --export-web 生成的战斗数据
tests/               # 测试
```
