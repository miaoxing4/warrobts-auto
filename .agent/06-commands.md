# 命令速查

## Python 路径

```powershell
$py = "C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
```

## 通过 `wr.bat`（推荐，可在任意目录）

```powershell
cd C:\Users\admin\Documents\deepseek-harness\default-workspace\warrobots-auto

wr.bat state                  # 看当前界面识别
wr.bat home                   # 回机库
wr.bat claim                  # 只领活动任务奖励

wr.bat daily                  # 每日任务广告 + 领奖
wr.bat lottery                # 供给中心抽奖（等到 3 次抽满或今日用完）
wr.bat lottery --no-wait      # 只抽当前可用次数
wr.bat ads --rounds 6         # 广告流程（三来源自动切换）
wr.bat ads --lottery          # 广告 + 抽奖
wr.bat ads --replenish 2      # 广告用尽后进战斗补充（最多 2 场）

wr.bat battle                 # 打一局（≥70s 后退出）
wr.bat loop --cycles 6        # 多轮 + 自动记录荣誉积分
wr.bat rating                 # 读当前荣誉积分
wr.bat history                # 分值历史趋势

wr.bat all --replenish 2      # 完整日常（领奖+广告+抽奖+战斗补充）
```

## 直接用 engine.py

```powershell
& $py engine.py state
& $py engine.py battle
& $py engine.py loop --cycles 5
& $py engine.py ads --rounds 6 --minutes 25
& $py engine.py all --replenish 2
& $py rating_report.py          # 带文本趋势图的报告 + logs/rating_report.md
& $py test_state_offline.py     # 回归测试（应 17/17）
```

## 调试用

```powershell
# 单点诊断：现在是什么界面
& $py engine.py state

# 看设备/Activity
& $py -c "import sys;sys.path.insert(0,r'.');import device as d;d.ensure_server();print(d.top_activity())"

# 强制回机库
& $py engine.py home

# 采集界面样本（游戏**空闲**时跑，别在对局中跑）
& $py collect_refs.py

# 重新自举数字模板（有新的已知样本时）
& $py bootstrap_digits.py
```

## 推荐节奏

| 目标 | 命令 | 频率 |
|---|---|---|
| **降难度（主目标）** | `wr.bat loop --cycles 6` | 每天 1 次 |
| 观察降分 | `wr.bat history` / `rating_report.py` | 每次 loop 后 |
| 领资源 | `wr.bat all --replenish 2` | 每天 1 次 |
| 抽奖 | `wr.bat lottery` | 每天 1 次（会等两次 5 分钟冷却，约 11 分钟） |

## 时间成本参考

| 动作 | 耗时 |
|---|---|
| 一次战斗循环（含进退场 + 重启游戏） | 约 2~3 分钟 |
| 一次广告（含关闭） | 30~45 秒 |
| 一次抽奖（含广告） | 40~60 秒 |
| 抽满 3 次（含 2 次冷却） | 约 11~12 分钟 |
| `loop --cycles 6` | 约 15 分钟 |


---

## 升级加速（新增）

```powershell
wr.bat upgrade              # 反复看广告减少升级时间，每次 -4 小时
wr.bat upgrade --max-ads 5  # 限制最多看 5 次
wr.bat all                  # 完整日常里会自动包含升级加速
wr.bat ads --upgrade        # 广告流程里带上升级加速
```

## 同步到 Git 仓库

```powershell
sync_to_git.bat                          # 同步并提交（默认信息）
sync_to_git.bat "feat: 做了什么改动"      # 同步并提交（自定义信息）
```

仓库位置：`D:\git\warrobots-auto`


---

## 特惠礼包（新增）

```powershell
wr.bat deals                 # 购物车 → 看广告领前 3 个礼包
wr.bat deals --cards 3       # 明确只做前 3 张（默认）
wr.bat deals --replenish 1   # 广告用尽时进 1 场战斗补充
wr.bat all                   # 完整日常已包含特惠礼包
```

> ⚠️ 特惠页有一个分栏是**真实货币折扣页**，脚本会自动识别并跳过，
> 绝不会点击付费按钮（已加回归测试保护）。
