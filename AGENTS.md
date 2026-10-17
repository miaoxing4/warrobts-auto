# AGENTS.md — 给 AI agent 的项目入口

> **接手本项目前，请先读 `.agent/` 目录**（那里有全部实测经验与踩坑记录）。

## 项目是什么

War Robots（`com.pixonic.wwr`）手机端自动化工具，运行在真机 realme RMX3366 上，
通过 ADB + 视觉识别完成：

1. 自动开游戏、看激励视频广告、领任务礼包
2. 自动进战斗、随机操作、**停留 ≥70 秒**后退出（用低战绩主动降低游戏难度）

## 三条铁律（违反会出事）

1. **Unity 游戏没有无障碍树** —— 不要尝试 uiautomator / Appium 找元素，
   只能截图 + 视觉识别 + 坐标点击。
2. **必须先锁横屏**，否则触摸坐标与截图坐标不一致。
3. **战斗中绝不点"离开"** —— 只点绿色「留在战斗中」，且必须停留 ≥70 秒才能退。

## 目录导航

| 路径 | 内容 |
|---|---|
| `.agent/README.md` | 经验库索引（**从这里开始**） |
| `.agent/02-hard-lessons.md` | 15 个踩坑实录与根因（**必读**） |
| `.agent/03-coordinates.md` | 全部实测坐标表 |
| `.agent/04-ui-states.md` | 状态识别阈值与来源 |
| `.agent/05-game-rules.md` | 游戏机制（1分钟规则/广告/抽奖） |
| `.agent/06-commands.md` | 命令速查 |
| `.agent/07-troubleshooting.md` | 故障排查手册 |
| `.agent/08-todo.md` | 未完成事项 |
| `.agent/screenshots/` | 12 张关键界面截图（无需真机也能对照） |
| `.agent/09-webui.md` | **网页界面**架构与停止机制（改了 UI 必读） |
| `webui.py` / `web.bat` | 网页控制台（当前主交互方式） |
| `README.md` | 面向人的使用文档 |

## 改代码前

```powershell
# 1. 确认设备在线
& <adb> devices -l          # 应显示 device（不是 unauthorized）

# 2. 跑回归（必须 17/17）
python test_state_offline.py

# 3. 看当前界面
python engine.py state
```

## 改代码后

- 动了视觉判据 → 跑 `test_state_offline.py`，并**补一个真实截图样本**
- 动了战斗逻辑 → 确认 `MIN_BATTLE_SECONDS`、`force_stay_in_battle` 仍在
- 动了广告逻辑 → 确认黑名单 `DANGER_RECTS` 与「AdMob 只用 BACK」仍在

## 不要做的事

- ❌ 装 opencv / easyocr / torch（网络极慢，已有 numpy 方案）
- ❌ 用固定坐标点广告角部按钮（位置随机变化，必须动态检测）
- ❌ 凭目测填坐标（读图有 1960→2400 的缩放，会全错）
- ❌ 删 `captures/` 里的基准样本（会让回归失效）
- ❌ 清理时删 `.agent/` 或 `templates/digits/`
