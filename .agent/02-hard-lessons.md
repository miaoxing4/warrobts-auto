# 踩过的坑与根因（最重要的一篇）

> 每条都是本次会话真实踩过、并定位到根因的。
> **动手改代码前请先读一遍，能省掉几小时。**

---

## 坑 1：Unity 游戏没有无障碍树

**现象**：`uiautomator dump` 成功，但 XML 里只有 5 个嵌套的空 `FrameLayout`，
没有 text / resource-id / bounds，什么都读不到。

**根因**：Unity 用 OpenGL/SurfaceView 自绘，所有"按钮"都是画在画布上的像素，
不是 Android View。

**结论**：放弃"找元素"路线。只能：
1. `screencap` 截图
2. 视觉识别（颜色区域 / 模板匹配 / 相对位置）
3. `input tap <x> <y>` 点坐标

**不要**再尝试 Appium / uiautomator2 / accessibility service。

---

## 坑 2：`input tap` 的坐标空间随屏幕方向变化（曾卡死很久）

**现象**：同样的截图坐标，有时点中、有时完全点不到；点对话框按钮死活无反应。

**根因**：
- 设备物理是竖屏 1080×2400，游戏强制横屏。
- 系统未锁横屏时，`screencap` 输出**已旋转的横屏图 2400×1080**，
  但触摸坐标经过系统旋转映射，与截图坐标**不一致**。
- 一旦用 `settings put system user_rotation 1` 把**系统本身**锁成横屏，
  `input tap` 就与截图坐标**完全一致**。

**修复**：所有流程开始前调用 `ensure_landscape()`
（`accelerometer_rotation=0` + `user_rotation=1`）。

**教训**：
- 不要试图推导旋转映射公式 —— 直接锁横屏，让两者一致。
- 判断是否锁成功：`dumpsys window displays | findstr mCurrentRotation` 应为 `ROTATION_1`。

---

## 坑 3：读图时的"预览缩放"导致坐标全错（反复犯）

**现象**：照着截图目测按钮位置填坐标，点出来总是偏移；一个按钮填了 320，
实际中心在 209。

**根因**：读图工具返回的图片被缩放到 **1960×882**（不是 2400×1080）。
按预览图目测的坐标必须 ×(2400/1960)=**1.2245** 才是真实坐标。

**修复/纪律**：
- **不要靠目测填坐标**。用颜色检测自动测出 bbox，取中心。
- 如果非要目测：先确认预览尺寸，再乘缩放比。
- 项目里 `localize.py`（`scan_rows`/`scan_cols`）就是为此写的。

---

## 坑 4：广告角部按钮的位置不固定

**现象**：AppLovin 广告一直重复点 Next 却关不掉，反复 20+ 次仍停在广告里，
最后超时才退出。

**根因**：左上「▶ Next」按钮位置**随广告版式变化**。实测见过：
`(175,68)`、`(228,67)`、`(212,85)`、`(286,68)`、`(374,81)`。
我最初硬编码 `(228,67)`，多数版式点不中，于是死循环。

**修复**：改为**运行时动态检测角部亮区**（`find_corner_close`），
且 Next 连续 4 次无效就转 `BACK` 兜底。

**教训**：**任何"关闭类"按钮位置都不能硬编码**，必须每帧检测。

---

## 坑 5：广告有两种 SDK，处理方式必须不同

| SDK | Activity | 特征 | 正确做法 |
|---|---|---|---|
| AppLovin | `com.applovin.adview.AppLovinFullscreenActivity` | 视频 → 落地页（中央大 Install）→ 退出调查 → 右上 X | 动态点角部 Next/X，无效则 BACK |
| AdMob | `com.google.android.gms.ads.AdActivity` | 整页应用商店样式，**Install 按钮极大**、占屏幕大半 | **只用 BACK 键**，绝不点任何位置 |

**教训**：
- 最初只识别了 AppLovin，漏了 `gms.ads`，导致把 AdMob 当普通界面，
  到处乱点，把广告点进了 Google Play。
- AdMob 版式下"点角部"也危险（角部可能就是安装区），**BACK 是最安全的**。

**安全黑名单（硬编码，绝不能点）**：
```
(420, 150) - (1980, 1080)    # 广告中央主体：Install / 立即游玩
(1600, 780) - (2400, 1080)   # 右下 Google Play 徽标 / 安装
```

---

## 坑 6：误入 Google Play 商店

**现象**：点广告时被带到 `com.android.vending`。

**处理**：只按 `BACK`（有时要按两次），**绝不点击商店里的任何按钮**，
防止真的装了什么。恢复后如发现仍在商店，直接 `am start` 拉起游戏。

---

## 坑 7：用「沙地/暖色」判断"在战斗中"会误判

**现象**：在商店页被识别成 `battle`，于是 `go_home` 拒绝返回，
`stay_in_battle` 以为还在对局里，计时逻辑全乱。

**根因**：商店页也有大量橙红色（促销角标、火苗图标），
暖色/沙地比例与战场接近。

**修复（关键判据）**：用**左上角亮绿色血量条**。
实测数据（这条是决定性的）：

| 界面 | 左上绿条占比 |
|---|---|
| 真正战斗画面 | **0.227** |
| 机库 / 商店 / 任务 / 黑市 / 结算 / 模式页 / 供给中心 | **0.000** |

判据：`hp > 0.04 且 HUD 特征 ≥3` → `battle`。

**教训**：找**唯一性特征**，不要用"氛围色"。血量条这种功能性 UI 才是可靠锚点。

---

## 坑 8：领奖后弹出「你的奖励」窗口，被当成任务页

**现象**：领取奖励后脚本卡住，`go_home` 反复点返回没反应，状态一直是 `event_tasks`。

**根因**：领奖后弹出「你的奖励」窗口（底部一个宽 613px 的绿色「确定」），
被"右侧绿色按钮"规则误判成任务页。

**修复**：新增 `reward_popup` 状态，判据 = 底部中央绿色占比 > 0.45 且背景暗；
处理 = 点 `(1247,1012)` 的「确定」。

**注意区分宽度**：
- 奖励弹窗「确定」：宽 **613**
- 活动任务「完成全部」：宽 **343**
- 供给中心「获取供给」：宽 **613**（但颜色是紫的）

---

## 坑 9：「每日任务」页与「活动任务」页长得像

**现象**：每日任务页被识别成 `event_tasks`，导致领奖/广告流程走错分支。

**修复（实测判据）**：看顶部标签行的**暗青色占比**：
- 4 个标签（特殊/奖励/每日/派系）：**0.544**
- 2 个标签（活动/最佳投资）：**0.166**

阈值 `> 0.40` → `daily_tasks`。
（注意：机库该指标也有 0.487，所以**必须先判机库**再判每日任务。）

---

## 坑 10：黑市识别用"头部紫色"会误判任务页

**现象**：`event_tasks` 被识别成 `black_market`，进入死循环。

**根因**：最初用左上区域均值判断紫色，任务页的紫色元素也能命中。

**修复**：改用**整屏深紫占比**。
- 黑市：**0.66**
- 其它所有界面：**< 0.01**

阈值 `> 0.35`。

---

## 坑 11：1 分钟内退出会被判罚（用户强调的业务规则）

**现象**：早期脚本打完就退，导致荣誉积分不降反升。

**规则**（用户明确说明）：
- 进战斗后 **1 分钟内退出 → 判罚扣分 → 等级下降 → 匹配更难**
- 角色阵亡后只要**不退出**就不算违规（可观战 / 换机甲继续等）
- **保险做法：1:05 之后退**（本项目用 **70 秒**）
- 目的：**低战绩退出 → 降低荣誉积分 → 降低匹配难度**

**实现要点**：
- 计时起点 = **首次看到部署界面**（最保守）
- 双保险：`stay_in_battle` 之后再校验一次剩余时间
- `go_home()` 检测到在战斗中时**直接返回 False**，绝不强行退
- 判断"已离开战斗"要**连续 3 次确认**，避免加载过场造成误判提前退

---

## 坑 12：「切勿放弃战斗」警告框 —— 点错就扣分

**现象**：机甲阵亡待复活时，脚本尝试退出，弹出：

```
⚠ 注意！
您仍有机器人幸存，切勿放弃战斗！可能会被罚分！
[ 离开 ]（红）      [ 留在战斗中 ]（绿）
```

**处理**：识别为 `leave_warning`，**强制点绿色「留在战斗中」(1563,809)**，
并在 `dismiss_dialog` 里优先处理，"离开"按钮**永不点击**。

判据：`y 765~855` 条带上**同时**存在大面积纯红(>20000px)与纯绿(>20000px)。

---

## 坑 13：阵亡后不部署机甲 → 整局没参与

**现象**：用户指出"没有释放机甲，哪怕一台"。

**修复**：
- 部署界面点机甲卡片（`(1310,730)`，失败则 `(900,700)`、`(1600,700)`）
- `MIN_DEPLOY_COUNT = 1`，退出前若未上场会补一次
- 阵亡复活界面持续换机甲上场，而不是干等

---

## 坑 14：PowerShell 内联 Python 的转义地狱

**现象**：`& $py -c "...| grep ..."` 里 `|`、`"`、`$` 被 PowerShell 抢先解析，
报 `无法加载模块“rot”`、`MissingEndParenthesis` 之类莫名错误。

**纪律**：
- **含管道/引号/正则的 Python 代码，写成 .py 文件再执行**，不要内联。
- 读中文输出乱码：在脚本开头 `sys.stdout.reconfigure(encoding='utf-8')`，
  或用 `Get-Content -Encoding UTF8`。

---

## 坑 15：不要在没有回归样本时乱删截图

**现象**：为"清理"删掉了 `captures/*.png`，结果 `test_state_offline.py`
从 17/17 掉到 4/4（大量 SKIP），失去了回归保护。

**纪律**：
- `captures/` 里有一批文件是**回归基准样本**，删之前对照 `test_state_offline.py` 的用例表。
- 要清理只删带时间戳的临时截图（`wad_*`、`claim_*`、`nav_*` 等）。

---

## 坑 16：还有第三种广告 SDK —— ByteDance 穿山甲

**现象**：点机库顶部「-4时 钟减少」后，脚本报"未触发广告"，
但其实广告已经弹出来了；随后界面被误判成 `battle_prep`。

**根因**：第三个广告 SDK 我最初没识别：
`com.bytedance.sdk.openadsdk.activity.TTFullWebActivity`
（穿山甲 / Pangle）。

**修复**：
- `ad_handler.is_ad_activity()` 与 `ui_state` 都加上
  `openadsdk` / `bytedance` / `pangle` 判定
- 关闭方式：**右上角灰色圆形 X**（实测中心 `(2309,113)`，bbox x[2268,2351] y[72,155]）
  - `BACK` 对它**无效**
  - 动态检测 + 固定位置 `BD_CLOSE_FALLBACK=(2309,113)` 兜底

**教训**：广告 SDK 不止 AppLovin/AdMob。新广告来源可能用新 SDK，
日志里看到 `未触发广告` 但画面明显是广告时，先 `dumpsys` 看 Activity 名。

---

## 坑 17：adb 因 %TEMP%\adb.log 权限问题整个不可用

**现象**：所有 adb 命令失败，`adb devices` 输出
`could not read ok from ADB Server` / `failed to start daemon`，
logcat 里 `cannot open C:\Users\...\Temp\adb.log: Permission denied`。

**根因**：adb 守护进程启动时要写 `%TEMP%\adb.log`，
该文件/目录权限异常（被其它进程创建且 ACL 不对）→ daemon 起不来。

**修复**（已写进 `device.py`）：给所有 adb 子进程强制指定工作区内临时目录：

```python
def _adb_env():
    env = os.environ.copy()
    tmpdir = os.path.join(PROJ_DIR, ".tmp")
    os.makedirs(tmpdir, exist_ok=True)
    env["TMP"] = tmpdir
    env["TEMP"] = tmpdir
    return env

subprocess.run(cmd, capture_output=True, timeout=timeout, env=_adb_env())
```

**救急命令**：

```powershell
Get-Process adb | Stop-Process -Force
Remove-Item "$env:TEMP\adb.log" -Force
# 然后让 device.py 的 _adb_env 生效（重启进程）
```

**教训**：adb 失败先看它自己的错误输出，不要先怀疑设备/线缆。

---

## 坑 18：暗色地图的部署界面被漏判 → 循环对局一直不部署机甲

**现象**（用户实测反馈）：循环对局时有时**不下放机器人**，一直停在开始界面，
日志里 `enter_battle` 一直是 `state=menu_other`，151 秒后超时。

**根因**：`battle_prep`（部署界面）的判据要求 `warm > 0.12`。
在**暗色雨雾地图**上实测 `warm = 0.113`，**刚好差 0.007 不满足** →
回落到 `menu_other` → `enter_battle` 永远不去点机甲 → 空转。

关键数值（同一张暗色部署界面）：

| 指标 | 值 | 旧阈值 | 结果 |
|---|---|---|---|
| card_cyan | **0.546** | > 0.15 | ✅ 通过 |
| warm | **0.113** | > 0.12 | ❌ **卡在这里** |
| bright | 0.189 | — | — |
| center_sum | 180 | — | — |

**修复**（`ui_state.py`）：改用 `card_cyan` 的**区间**判断，去掉对 `warm` 的依赖：

```python
# 3D 场景上覆半透明机甲卡片 → card_cyan 中等（0.2~0.7）
# 纯 UI 页面 card_cyan >= 0.71
if 0.15 < card_cyan < 0.72 and not greens and orange_tr < 0.45:
    battle_prep
```

各界面实测 `card_cyan`（这条是设计依据）：

| 界面 | card_cyan | 说明 |
|---|---|---|
| 活动任务 | **0.99** | 纯 UI 面板 |
| 每日任务 | 0.89 | 纯 UI |
| 奖励弹窗 | 0.96 | 纯 UI |
| 活动通行证 | 0.835 | 纯 UI |
| 抽奖 | 0.807 | 纯 UI |
| **部署界面（暗色地图）** | **0.546** | 3D 场景 + 半透明卡片 |
| 部署界面（沙地/城市） | 0.49~0.55 | 同上 |
| 机库 | 0.52~0.59 | 靠 `greens`/`orange_tr` 排除 |

**教训**：
- **不要给"氛围"类指标（warm/sandy）设贴近实测值的阈值** ——
  换个地图/天气就会踩线。要用结构性特征（卡片区占比、按钮有无）。
- 发现某个判据"差一点点"，说明阈值定错方向了，不是微调能解决的。

**回归保护**：已把该暗色部署界面存为 `tests/fixtures/prep_dark_map.jpg`
并注册测试用例（现 18/18）。

---

## 坑 19：卡在游戏启动画面 → go_home 无限空转

**现象**：日志刷屏
```
go_home[0]: menu_other
go_home[1]: menu_other
...
enter_battle: 无法回到机库
```
任务跑了几百秒毫无进展。

**根因**：游戏重启后停在 **WAR ROBOTS 启动画面**（logo + 机甲插画）。
该画面：
- 返回键完全无效
- 被误判成 `event_tasks`（画面里的紫色机甲被当成"紫色广告按钮"）
- `go_home` 于是反复点 `(155,1000)` 返回，永不成功

**为什么不能靠"整屏很亮"识别**：实测启动画面平均亮度 **91.5**，
机库 **87.0**、战斗 **155.1** —— 亮度完全不具区分性。
（`ui_state` 里那个 `bright` 是"非黑像素占比"，几乎所有界面都 ≈0.99，更不能用。）

**修复**（`engine.go_home`）：加**无进展检测 + 自动重启**，
不依赖识别启动画面，通用于任何"返回键无效"的卡死：

```python
seen.append(st)
if len(seen) >= 3 and len(set(seen[-3:])) == 1:
    d.log("go_home: 连续 3 次停留在 [%s]，返回键无效 → 重启游戏" % st)
    d.stop(); d.launch(wait=25); d.lock_landscape()
```

**教训**：与其为每个"未知卡死界面"加识别规则，
不如加一个通用的"没进展就重启"的兜底 —— 游戏重启是无害且确定的恢复手段。

---

## 坑 20：特惠页有三个分栏，付费页和广告页混在一起（差点误点真钱购买）

**现象**：按用户描述做「特惠页看广告」时，脚本点了绿色按钮，
结果**直接拉起 Google Play 支付界面**（`com.android.vending`）。

**根因**：特惠页左侧 1/2/3 三个分栏，**内容会变**：
- 有的分栏是**广告礼包**（紫色「观看」/ 绿色「获取」，免费）
- 有的分栏是**限时折扣**（橙色 % 背景，`JP¥80`/`JP¥50`，**真实货币购买**）

两种页面**按钮位置完全一样**（卡中心 x=493/940/1386/1832/2278，按钮 y=815），
只有背景风格不同。如果盲目按位置点绿色按钮，就会点中真钱购买。

**修复**（`task_ui.deal_page_is_paid`）：用卡片区橙色占比区分，**为真时绝不点任何按钮**：

| 页面 | 卡片区橙色占比 | 青绿背景占比 |
|---|---|---|
| 广告礼包页 | **0.001** | 0.39 |
| 付费折扣页 | **0.172** | 0.17 |

阈值 `> 0.05` 判为付费页。已加回归用例 `deals_paid_page.jpg`。

**另一个教训**：同一功能的不同分栏内容会随时间/进度变化，
所以**不要硬编码"广告在第 X 栏"**，要遍历所有分栏并逐个判断类型。
实测第一次进入时广告在第 1 栏，后来跑到了第 2、3 栏。

---

## 坑 21：第四个广告 SDK —— Meta / Facebook Audience Network

**现象**：点特惠页「观看」后，Activity 变成
`com.facebook.ads.internal.ipc.AudienceNetworkRemoteActivity`，
**宿主包名是 `com.facebook.katana`（Facebook 应用本身）**，不是游戏。

**修复**：
- `ad_handler.is_ad_activity` 增加 `audiencenetwork` / `facebook.ads` / `katana`
- `is_facebook_ad()` → **只用 BACK**，且**要按多次**
  （实测广告是「Ad 1 of 2」多段式，按 1~6 次才退出，最多见过 7 次）
- 绝不用角部点击（`SEE DETAILS` 蓝色按钮占屏幕很大，极易误触）

**至此共识别 4 种广告 SDK**：

| SDK | Activity 关键字 | 关闭方式 |
|---|---|---|
| AppLovin | `applovin` / `adview` | 动态角部 Next/X，兜底 BACK |
| AdMob | `gms.ads` / `admob` | 只用 BACK |
| ByteDance 穿山甲 | `openadsdk` / `bytedance` | 右上灰色圆形 X `(2309,113)`，兜底 BACK |
| **Meta/Facebook** | `audiencenetwork` / `katana` | **只用 BACK，需多次** |

---

## 坑 22：`.bat` 必须是 CRLF 换行

**现象**（用户反馈）：批处理文件在 Windows 上跑不正常。

**根因**：文件被写成了 **LF（unix）换行**。`cmd.exe` 对 `goto :label`、
`if ... (` 块、多行 `set` 等结构的解析依赖 CRLF，纯 LF 会出现
跳错标签、块内命令被截断、`pause` 之后行为异常等问题。

**修复**：
1. 工作区里的 4 个 `.bat` 全部转成 CRLF（`fix_bat_crlf.py`）
2. `.gitattributes` 里固定规则，保证 checkout 出来就是 CRLF：

```
*.bat text eol=crlf
```

**校验方法**（应 CRLF 数 == LF 总数）：

```python
raw = open("wr.bat", "rb").read()
print(raw.count(b"\r\n"), raw.count(b"\n"))
```

**纪律**：以后**新建/改写 `.bat` 后一定要确认 CRLF**。
写文件的工具默认给 LF，必须显式转换。

---

## 坑 23：无线 ADB 端口每次都在变，长跑进程会"掉线"

**现象**（用户反馈）：手机确定开着无线调试，但脚本报找不到设备。

**根因（三个叠加）**：

1. **mDNS 有延迟**：adb 守护进程刚启动时，UDP 5353 要等几秒才收到广播。
   实测 `adb start-server` 后立刻 `adb mdns services` 是**空的**，
   等 8 秒才出现 `adb-16569970-OuYTFO  _adb-tls-connect._tcp  192.168.1.9:40359`。
   → 原来的脚本只查一次就放弃，所以"找不到手机"。

2. **端口是随机的**：同一台手机实测经历过
   `39365` → `40359` → `42821`。手机重开无线调试/重启就会变。
   → 保存的 `.device_serial` 很快失效。

3. **长跑进程不会重新解析串号**：`webui.py` 只在启动时 `resolve_serial()` 一次。
   端口一变，后台进程的所有命令都报 `device not found`，
   网页上表现为 `界面=screenshot_failed`。

**修复**（三层）：

1. `wr_wireless.py`：发现改为**轮询重试最多 30 秒**，连不上给出明确的 4 条排查
2. `device.resolve_serial()`：配置的是无线串号且不在线时，
   **自动用 mDNS 重新发现并重连**（并更新 `.device_serial`）
3. `device.adb()`：**带自愈** —— 命令返回"设备不在/离线"时，
   自动 `resolve_serial()` 后**重试一次**
   （用 `_HEALING` 标志防递归）

**实测效果**：

```
断开后 ensure_server() → 1.4s 内重新发现并连接
人为写入失效串号 (192.168.1.9:1) → 截图调用自动自愈，串号恢复为真实端口
```

**教训**：无线调试是个"会自己变化"的外部资源，
任何长期运行的进程都必须具备**失败→重新发现→重试**的能力，
不能只在启动时解析一次。

---

## 坑 24：Windows 上 adb mDNS 与其它服务抢 UDP 5353

`Get-NetUDPEndpoint -LocalPort 5353` 显示是 adb 自己占着，属正常。
如果发现不了设备，优先怀疑：
- 手机上「无线调试」被系统自动关闭（部分机型锁屏/省电会关）
- 手机与电脑不在同一网段（本例电脑 `192.168.1.11`、手机 `192.168.1.9`）
- 路由器开了 **AP 隔离**
- Windows 防火墙拦了 adb 的 UDP 5353

最省事的兜底：**插一次 USB 执行 `wireless.bat tcpip`**，
改用固定端口 5555，完全不依赖 mDNS。

---

## 坑 25：手机休眠/锁屏会让自动化"看起来在跑但什么都点不到"

**现象**：一段时间后，`screencap` 全黑（均值 0~2.7）或直接**返回空**，
点击无效，日志里 BACK 按了十几次也没反应。

**根因（两个阶段）**：

1. **Dozing（休眠）**：`mWakefulness=Dozing`。
   息屏后 `screencap` 得到全黑图，`input` 事件被系统吞掉。

2. **安全锁屏**：设备锁屏后 `screencap` **返回 0 字节**
   （锁屏窗口有 FLAG_SECURE，系统直接屏蔽截图）。
   此时背后即使有广告 Activity 也完全不可见，
   `input keyevent` 全部无效 —— 我试了 WAKEUP / dismiss-keyguard /
   上滑 / MENU / ENTER / HOME 六种方式，**全都不行**，
   因为设备设了密码，必须人工解锁。

**修复**：

```python
# device.py
def keep_awake():
    shell("locksettings set-disabled true")          # 关掉锁屏
    shell("settings put secure lockscreen.disabled 1")
    shell("settings put system screen_off_timeout 2147483647")  # 永不息屏
    shell("svc power stayon true")                    # 充电时常亮
    if not is_awake() or is_locked(): wake()
```

另外 `screenshot()` 加了**黑屏自愈**：均值 < 3 时自动 `wake()` 并重试一次。

**检测**（很重要，否则会静默失败）：

```python
_last_secure = {"v": False}   # screencap 返回空 → 判定为安全窗口
def screen_secure(): ...
```

`ui_state.detect()` 在截图失败且 `screen_secure()` 为真时返回
**`locked`** 状态（而不是含糊的 `screenshot_failed`），
网页会弹出"手机锁屏中，请在手机上解锁"的遮罩 + 「尝试唤醒」按钮。

**教训**：
- 长跑自动化必须处理"屏幕会休眠/锁屏"这个现实问题，
  否则会得到大量莫名其妙的失败。
- `screencap` 返回**空**和返回**全黑**是两种不同故障：
  空 = 安全窗口（锁屏/DRM），全黑 = 息屏。
- 设了密码的设备，锁屏后**无法自动解锁**，必须人工介入。

---

## 坑 26：第五种广告 SDK —— Yandex Mobile Ads

`com.yandex.mobile.ads.common.AdActivity`，常见为**竖屏插屏**。

- 已加入 `is_ad_activity`（关键字 `yandex` / `mobileads`）
- 关闭策略：**BACK**（与 Meta 同组，`is_facebook_ad or is_yandex_ad`）

至此共 5 种：
AppLovin / AdMob / ByteDance 穿山甲 / Meta(Facebook) / **Yandex**。

**注意**：竖屏广告会让截图变成 1080x2400，
所有按横屏标定的区域阈值都会越界（触发 numpy "Mean of empty slice"）。
已在 `ui_state.detect()` 加竖屏保护：`h > w` 时直接返回 `unknown`。

---

## 坑 27：频繁替换 blob URL 会把画面刷成空白

**现象**：网页手机画面间歇性变成空白/破图。

**根因**：刷新逻辑在 `img.onload` 里 revoke **上一张**的 blob URL，
但两次刷新间隔很短时，闭包里的"上一张"可能正是**当前正在显示**的那张，
一 revoke 就空白了。

**修复**：用模块级 `curShotUrl` 记录当前真正在用的 URL，
**等新图 onload 成功之后**才 revoke 旧的；加载失败则 revoke 新的、保留旧画面。

```js
const url = URL.createObjectURL(blob);
const prev = curShotUrl;
await new Promise(res => { img.onload = fin; img.onerror = fin; img.src = url; });
if (img.naturalWidth > 0) {
  curShotUrl = url;
  if (prev && prev !== url) URL.revokeObjectURL(prev);
} else {
  URL.revokeObjectURL(url);   // 保留旧画面，不闪白
}
```

加 8 秒超时保护，避免 onload 永不触发时卡死。

**教训**：凡是"定时替换资源 URL"的场景，都要明确
**新资源加载完成 → 再释放旧资源**的顺序。
