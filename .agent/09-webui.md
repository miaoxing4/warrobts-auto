# 网页图形界面（Web UI）

> 从某个版本起，日常交互**不再用命令行**，改为网页点击。
> 实现见 `webui.py`，启动器见 `web.bat`。

---

## 启动

```powershell
双击 web.bat
```

或命令行：

```powershell
python webui.py                     # 默认 8765 端口，自动开浏览器
python webui.py --port 8770         # 换端口
python webui.py --no-browser        # 不开浏览器
```

- 关闭那个黑窗口 = 停止服务
- 默认地址 `http://127.0.0.1:8765/`
- 只监听 `127.0.0.1`（本机），不对外暴露

---

## 设计决策（为什么这么写）

| 决策 | 原因 |
|---|---|
| **只用标准库**（`http.server` / `threading` / `json`） | 本项目网络装包极慢，`.agent/02` 已立规矩：不装第三方包 |
| **任务在后台线程跑** | 一个任务动辄 2~15 分钟，不能阻塞 HTTP 响应 |
| **单任务互斥** | 手机是独占资源，两个任务同时点会互相干扰 |
| **轮询而非 WebSocket** | 标准库没有 WebSocket，轮询 1.5 秒足够，实现简单可靠 |
| **日志用环形缓冲** | `device.log` 被 monkeypatch 成"写入缓冲 + 写原文件"，页面增量拉取 |
| **截图带 2.5 秒缓存** | 每次 `screencap` 约 1 秒且占带宽，缓存避免和任务抢设备 |
| **停止是协作式** | 见下节，不能让线程硬杀 |

### 日志捕获方式

```python
_orig_log = d.log
def _patched_log(msg, file="run.log"):
    LOG.add(msg)          # 进环形缓冲，页面轮询
    try: _orig_log(msg, file)   # 保留原控制台输出 + logs/run.log
    except Exception: pass      # 控制台编码问题不能影响任务
d.log = _patched_log
```

因为各模块都是 `d.log(...)`（模块属性调用），patch `device.log` 即全局生效。

---

## 停止机制（**重要，关系到 1 分钟规则**）

**问题**：如果用户在对局中点了"停止"，脚本立刻撒手 → 可能违反"1 分钟内不得退出"。

**解决**：两层保护。

### 1) 战斗中延迟停止

包装 `ui_state.detect`，只有**非战斗状态**才抛 `TaskCancelled`：

```python
UNINTERRUPTIBLE = ("battle", "battle_prep", "leave_warning")

def _guarded_detect(*a, **k):
    res = _orig_detect(*a, **k)
    _last_state["v"] = res.get("state")
    if CANCEL.is_set() and _last_state["v"] not in UNINTERRUPTIBLE:
        raise TaskCancelled("用户已请求停止")
    return res
```

→ 战斗中点停止，会显示"正在安全退出"，等对局走到安全点（≥70 秒后）才真正停。

### 2) 长等待可中断

冷却等待（315 秒）期间不会调用 `detect`，所以另给 engine 加了停止钩子：

```python
# engine.py
STOP_HOOK = None
def stop_requested():
    return bool(STOP_HOOK and STOP_HOOK())
# webui.py
e.STOP_HOOK = CANCEL.is_set
```

`wait_until_lottery_ready` 的 sleep 循环每 5 秒查一次，可立即中断。

**实测**：抽奖冷却等待中点停止 → 3 秒内退出。

---

## 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/` | 返回单页 HTML（内嵌在 `webui.py` 的 `HTML` 常量里） |
| GET | `/api/status?since=N` | 任务状态 + 增量日志 + 当前界面 + 分值历史 |
| GET | `/api/shot` | 手机截图 JPEG（2.5s 缓存） |
| POST | `/api/run` | `{"action": "...", "params": {...}}` 启动任务 |
| POST | `/api/stop` | 请求停止 |

`/api/status` 返回示例：

```json
{
  "task": {"running": false, "action": "loop", "elapsed": 405.4,
           "result": "3/3 局完成", "error": null},
  "ui_state": "hangar",
  "logs": [{"t": "14:47:10", "m": "■ 任务已停止：loop"}],
  "log_total": 117,
  "rating": [{"ts": "...", "rating": 1848, "note": "基线"}]
}
```

---

## 动作表（页面按钮 ↔ 引擎函数）

| action | 按钮 | 调用 | 耗时 |
|---|---|---|---|
| `state` | 识别界面 | `go_home()` + `detect()` | ~8s |
| `home` | 回到机库 | `go_home()` | ~5s |
| `claim` | 领取任务奖励 | `nav_to_tasks()` + `claim_task_rewards()` | ~30s |
| `daily` | 每日任务 | `nav_to_daily_tasks()` + `watch_daily_task_ads()` | 2~5min |
| `lottery` | 供给中心抽奖 | `run_lottery(draws, wait)` | 1~12min |
| `ads` | 广告流程 | `goal_ads(rounds, minutes, lottery, replenish, wait)` | 5~25min |
| `battle` | 打一局 | `goal_battle()` | ~2.5min |
| `loop` | 循环打局 | `get_rating` + N×`goal_battle` + `get_rating` + 报告 | N×2.5min |
| `rating` | 读取荣誉积分 | `get_rating()` | ~15s |
| `history` | 分值趋势 | `rating_history_report()` | ~2s |
| `all` | 完整日常 | 同 `ads` 但 `lottery=True` | 10~35min |

---

## 页面功能

- **状态徽章**：空闲 / 运行中：xxx + 已运行秒数 / 上次完成 / 上次失败
- **界面徽章**：实时显示识别到的界面（battle 蓝、hangar 绿、其它灰）
- **手机画面**：实时截图，3 秒自动刷新，可关
- **分值记录**：最新分值 + 样本数 + 首末变化 + 柱状图（最近 24 条）
- **运行日志**：彩色（错误红/完成绿），增量追加，自动滚动
- **参数**：广告轮数、补充战斗、含抽奖、等冷却、局数
- **运行中按钮禁用**，防止重复点击

---

## 已知限制

1. **同一时间只能跑一个任务** —— 点第二个会提示"已有任务在运行"。
2. **浏览器关闭不会停止任务** —— 任务在服务端线程里继续跑；重开页面能看到进度。
3. **停止不是强杀** —— 战斗中会延后；极端情况下最长等到对局结束。
4. **截图与任务共用 ADB** —— 高频率刷新截图会略微影响任务速度（已用缓存缓解）。
5. 如果 8765 端口被占用，用 `--port` 换一个。

---

## 坑：改了页面但浏览器还是旧版（端口被旧进程占用）

**现象**：明明改了 `webui.py` 里的 HTML / 加了按钮，重启服务后页面**仍然是旧版**，
请求 `/` 拿到的 HTML 里没有新按钮。

**根因**：
1. `/api/stop` 只停止**任务**，**不停服务**。所以旧的服务进程一直在跑并占着 8765。
2. 新的 `python webui.py` 启动时 **bind 失败**（address already in use），
   但可能在后台静默退出，看起来像"重启成功"。
3. 于是浏览器连的还是**旧进程**，页面自然是旧代码。

**排查**：

```powershell
# 谁占着 8765
Get-NetTCPConnection -LocalPort 8765 -State Listen | Select-Object OwningProcess

# 所有 webui 进程
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -like '*webui.py*' } |
  Select-Object ProcessId, CommandLine
```

**修复**：

```powershell
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -like '*webui.py*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
# 再重新启动 web.bat
```

**验证方式**：直接抓页面看按钮列表

```python
import re, urllib.request
h = urllib.request.urlopen("http://127.0.0.1:8765/").read().decode()
print(re.findall(r'data-a="(\w+)"', h))
```

应当看到 13 个：state home claim rating history battle daily lottery
upgrade deals ads all loop

**教训**：改前端后不能只靠"重启了"来判断，要**抓页面内容验证**。
另外不要用 `/api/stop` 当"重启服务"用 —— 它只停任务。

---

## 布局改版（build 3/4）：上半屏画面 + 下半屏按钮 + 远程点击

### 布局

```
┌──────────────────────────────────────────┐
│ 顶栏：状态 / 界面 / 点击队列 / 刷新频率 / 停止 │
├──────────────────────────────────────────┤
│                                          │
│      手机画面（占上方约 60%，可点击）        │
│                                          │
├──────────────────────────────────────────┤
│  常用操作 │ 广告·领资源 │ 降难度   │ 日志/分值 │
└──────────────────────────────────────────┘
```

上半屏 `flex:1 1 60%`，下半屏 `flex:1 1 40%` 且内部可滚动。

### 远程点击（重点）

在画面上点一下 → 点击**先入队**，后台线程按顺序发给手机。

**为什么要排队而不是直接发**：
- 无线 ADB 单次操作 ~2s，若每次都"点了就等新截图确认"，会把带宽和 adb 压满
- 入队后前端立刻画一个准星做反馈，**不触发截图刷新**；
  画面按设定的频率（默认 5 秒）自然刷新

服务端实现：
```python
TAP_QUEUE = collections.deque()
TAP_COND  = threading.Condition()
TAP_GAP   = 0.15        # 两次点击最小间隔

def _tap_worker():      # 后台线程
    while True:
        ... 取一个 (x,y) ...
        with DEV_LOCK:  # 与截图共用锁，避免争抢
            d.tap(x, y)
        time.sleep(TAP_GAP)
```

接口：
- `POST /api/tap {x,y}` → `{ok, queued}`
- `/api/status` 返回 `tap_queue` / `tap_done` / `tap_fail` / `tap_last`

### 坐标映射（容易错的地方）

画面用 `object-fit: contain`，元素内会有**黑边（letterbox）**，
必须按"实际绘制区域"换算，否则整体偏移：

```js
const scale = Math.min(r.width/nw, r.height/nh);
const drawnW = nw*scale, drawnH = nh*scale;
const offX = r.left + (r.width - drawnW)/2;
const offY = r.top  + (r.height - drawnH)/2;
x = (clientX - offX)/scale;
y = (clientY - offY)/scale;
```

`nw/nh` 用 `img.naturalWidth/Height`（**不要硬编码 2400x1080**）——
竖屏时截图是 1080x2400，硬编码会全错。

点在黑边上（x/y 越界）直接忽略，不发请求。

### 刷新频率可调

顶栏下拉：不自动 / 3 秒 / 5 秒（默认）/ 8 秒。无线环境建议 5 秒以上。
