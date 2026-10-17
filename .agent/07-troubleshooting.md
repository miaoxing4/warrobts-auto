# 故障排查手册

> 按"现象"查。每条都有实测根因。

---

## A. 点击没反应 / 点错位置

| 现象 | 根因 | 处理 |
|---|---|---|
| 点按钮完全无效果 | 未锁横屏，坐标空间被系统旋转 | `engine.py home` 重跑；确认 `mCurrentRotation=ROTATION_1` |
| 偏了几十像素 | 你按"预览图"目测了坐标，漏了 ×1.2245 | 用颜色检测取 bbox 中心，别目测 |
| 对话框按钮点不动 | 某些弹窗（如"你收到了挑战"）对注入触摸无响应 | 等它自动超时；别死磕 |
| 点中了别的按钮 | 坐标来自旧版游戏/不同分辨率 | 重新标定（`localize.py` 扫描） |

---

## B. 广告关不掉

| 现象 | 根因 | 处理 |
|---|---|---|
| 反复点 Next 仍停在广告 | 左上按钮位置随版式变化，硬编码点位点不中 | 已在 `ad_handler` 改为动态检测；确认没退回旧代码 |
| 一直重复点同一个无效点 | `find_corner_close` 把广告画面里的大块亮区当按钮 | `next_tries >= 4` 会转 BACK 兜底；必要时调小阈值 |
| 跳到 Google Play 出不来 | 误触 Install | 只按 BACK（可能需 2 次）；`back_to_game()` 已实现 |
| AdMob 广告点角部反而进商店 | AdMob 版式下角部可能就是安装区 | AdMob **只用 BACK** |

**手动救急**：

```powershell
# 连续按返回，直到回到游戏
& $py -c "import sys;sys.path.insert(0,r'.');import device as d;d.ensure_server()
for i in range(5):
    print(d.top_activity()); d.back(); import time; time.sleep(1.5)"
```

---

## C. 战斗相关

| 现象 | 根因 | 处理 |
|---|---|---|
| 卡在 `menu_other` 很久进不去战斗 | **网络问题**（用户已确认）或加载慢 | 脚本会超时安全放弃（不进场=不判罚）；重跑即可 |
| 一直在"模式页"进不去 | 底部「前往战斗」`(966,816)` 未命中（版式变了） | 重标定；或先 `home` 再试 |
| 机甲没上场 | 部署点未命中 | 已加 3 个备选点位 + `MIN_DEPLOY_COUNT` 补偿 |
| 弹出「切勿放弃战斗」 | 试图在有机甲存活时退出 | **点「留在战斗中」`(1563,809)`**，脚本已自动处理 |
| 提前退出被判罚 | 计时逻辑被绕过 / 状态抖动误判 | 确认 `MIN_BATTLE_SECONDS=70` 与"连续3次确认"仍在 |
| 结算页数据全 0 | 该局几乎没参与（没部署机甲） | 正常，不影响降分策略 |

---

## D. 状态识别错误

| 现象 | 可能原因 | 处理 |
|---|---|---|
| 商店页被识别成 battle | 又用回了"沙地/暖色"判据 | 必须用**左上绿血条** `hp>0.04` |
| 任务页被识别成黑市 | 用"头部紫色"判据 | 必须用**整屏深紫 > 0.35** |
| 每日任务页识别成活动任务 | 缺 4 标签判据 | `dark_tabs > 0.40` → daily_tasks |
| 领奖卡住不动 | 弹出「你的奖励」未处理 | `reward_popup` → 点 `(1247,1012)` |
| 机库被识别成 daily_tasks | 判定顺序错 | 机库必须**先于** daily_tasks |

**自检**：

```powershell
& $py test_state_offline.py     # 17/17 才正常
```

---

## E. 荣誉积分读不出来

| 现象 | 根因 | 处理 |
|---|---|---|
| `rating: None` | 数字模板缺该数字（现缺 0,2,3,5） | 用 `bootstrap_digits.py` 补样本 |
| 读成别的数字 | 模板匹配阈值/字形偏移 | 加多样本、调 `match_digit` 阈值 |
| 打不开联赛页 | 奖杯坐标变了 | 重新标定 `(2300,590)` |

**验证**：

```powershell
& $py -c "import sys;sys.path.insert(0,r'.');import rating_reader as rr
print(rr.read_rating_by_template(rr.v.load('captures/rating_verify_1768.png')))"
# 期望 text = '1768/1899'
```

---

## F. 环境类

| 现象 | 根因 | 处理 |
|---|---|---|
| `adb devices` 显示 unauthorized | 手机未授权 | 手机勾"始终允许"再点允许 |
| `adb` 找不到 | 本机原本没装 | 用项目内 `tools/platform-tools/adb.exe` |
| `pip install` 卡死 | 代理/网络问题 | **不要装 opencv/easyocr/torch**，用现有 numpy 方案 |
| `Invoke-WebRequest` / `curl` 下载失败 | schannel 凭证问题 | 用 Python `urllib.request` 下载 |
| PowerShell 内联 Python 报语法错 | `\|`、`"`、`$` 被 PS 抢先解析 | 写成 `.py` 文件再执行 |
| 中文输出乱码 | 控制台 GBK | 脚本内 `sys.stdout.reconfigure(encoding='utf-8')` |

---

## G. 回归测试 SKIP 变多

**原因**：`captures/` 里的基准样本被删了（我曾经为了"清理"删过一次）。

**当前必需的样本**（缺了就会 SKIP）：

```
01_launch.png  scan_hangar.png  T1_hangar.png  98_deploy_1.png
C1_result.png  62_event_tasks2.png  M1_tasks.png
T7_daily_scrolled.png  T5_daily.png  T6_daily_tab.png
T2_lottery.png  V3_daily_done.png  P1_check.png
scan_left_mission.png  N1_check.png  LEAVE_WARNING.png
scan_left_event2.png  Q1_before_ad.png
rating_verify_1848.png  rating_verify_1768.png  G5_league.png
```

**纪律**：要腾空间只删带时间戳的临时图（`wad_*` `claim_*` `nav_*` `T*` 里非基准的）。

---

## H. 通用"一键复位"

当状态彻底混乱时：

```powershell
& $py -c "
import sys; sys.path.insert(0,r'.')
import device as d, engine as e
d.ensure_server()
d.stop(); import time; time.sleep(2)
d.launch(wait=25); d.lock_landscape()
print(e.go_home())
"
```

即：**杀掉游戏 → 重启 → 锁横屏 → 回机库**。
