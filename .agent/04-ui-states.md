# 界面状态识别规则（ui_state.py）

> 全部阈值来自**实测数据**，不是拍脑袋。
> 判定是**有顺序**的，顺序本身就是逻辑的一部分。

---

## 判定顺序（务必保持）

```
1.  ad               Activity 含 applovin / adview / gms.ads / admob
2.  play_store       前台是 com.android.vending
3.  foreign_app/launcher
4.  battle_result    顶部红色横幅
5.  hangar           右上橙色占比 > 0.45
6.  lottery_ready    底部紫色按钮 > 0.15
7.  reward_popup     底部绿色 > 0.45 且中央暗
8.  daily_tasks      顶部4标签暗青 > 0.40
9.  battle_modes     底部中央橙色 > 0.15
10. event_reward_track  右上纯蓝 X > 150px
11. leave_warning    y765~855 同时有大量红+绿
12. battle_prep      机器人卡片区青灰 > 0.15
13. black_market     整屏深紫 > 0.35
14. event_pass       左侧紫金卡 > 0.05
15. event_tasks      完成全部 / 右侧实心绿获取 / 紫色按钮
16. battle           左上亮绿血条 + HUD>=3
17. dialog           中央暗
18. menu_other       兜底
```

**顺序为什么重要**（都是踩过的坑）：
- 机库必须先于 `daily_tasks`（机库的"暗标签"指标也高：0.487）
- 机库必须先于 `lottery_ready`（机库右上橙按钮区不影响，但保险起见靠前）
- `battle_result` 必须先于 `battle`（结算页顶部红横幅）
- `lottery_ready` / `reward_popup` 必须先于 `daily_tasks` / `event_tasks`
- `battle_prep` 必须先于 `event_tasks`（部署卡片的青色会被误判）

---

## 各状态的量化判据

### battle（战斗）—— 最关键

**决定性特征：左上角亮绿色血量条**

```python
a = img[8:70, 50:420]            # 左上区域
hp = ((g>140) & (g>r+60) & (g>b+40)).mean()
# hp > 0.04 且 HUD 特征数 >= 3  →  battle
```

实测对比：

| 界面 | hp |
|---|---|
| 真实战斗 | **0.227** |
| 机库/商店/任务/黑市/结算/模式页/供给中心 | **0.000** |

辅助 HUD 特征（≥3 个才算）：
- `hp_bar` 左上绿血条
- `shield_icon` 右上绿盾图标（`img[180:420, 2180:2400]`）
- `fire_ring` 右下红色开火环（`img[600:1000, 2050:2400]`）
- `team_strip` 顶部青/红队伍条（`img[0:110, 740:1700]`）
- `joystick` 左下浅色摇杆圆（`img[600:800, 180:420]`）

> **不要**用"沙地/暖色"当主判据 —— 商店页会误判。

### hangar（机库）

```python
orange_tr = 右上区域 (1990,70)-(2400,250) 里橙像素占比
# orange_tr > 0.45 且 sandy < 0.2 且 center_sum > 330
```
实测：机库 `orange_tr` = **0.55~0.57**

### battle_modes（战斗模式选择）

```python
orange_mode = (760,740)-(1180,900) 橙占比
# > 0.15
```
实测：`0.47`

### battle_prep（战前部署 / 阵亡复活）

```python
card_cyan = img[500:1010, 400:1600] 里青灰占比
# 0.15 < card_cyan < 0.85 且 无绿色按钮 且 center_sum<320 且 warm>0.12
```
实测：`0.49~0.55`

### battle_result（结算）

```python
header = mean(img[0:110, 500:1900])
# header[0] > 90 且 r > g+40 且 r > b+30
```
实测：`(128,55,65)`

### lottery_ready（供给中心可抽）

```python
purple_bot = img[940:1080, 800:1700] 里紫色占比
# > 0.15
```
实测：可抽 **0.531**；冷却/其它 **0.000**

### reward_popup（「你的奖励」弹窗）

```python
green_bot = img[940:1080, 800:1700] 里绿占比
# > 0.45 且 center_sum < 300
```
实测：**0.54**（绿按钮宽 613，与「完成全部」的 343 不同）

### daily_tasks（每日任务）

```python
dark_tabs = img[95:185, 600:1900] 里"暗青"像素占比
# ((r>30)&(r<90)&(g>70)&(g<130)&(b>90)&(b<160))
# > 0.40
```
实测：4 标签页 **0.544**；2 标签页（活动/最佳投资）**0.166**；机库 0.487（故须后判）

### black_market（黑市）

```python
purple_ratio = 整屏"深紫"像素占比
# ((b>25)&(b<130)&(r<110)&(b>g+18)&(r>g+3))
# > 0.35
```
实测：黑市 **0.66**；其它界面 **< 0.01**

### leave_warning（切勿放弃战斗）

```python
band = img[765:855, :]
red   = ((r>180)&(g<95)&(b<95)).sum()
green = ((g>130)&(g>r+50)&(g>b+40)).sum()
# red>20000 且 green>20000
```
实测：red=54574, green=54047

### event_reward_track（活动奖励轨道浮层）

```python
bluex = img[0:160, 2150:2400]
# 纯蓝 X：b>200 & r<90 & 50<g<190，像素 > 150
```
实测：556 px

### event_tasks（活动任务）

三条并列（任一命中）：
1. 底部绿色「完成全部」：`y>960, 900<x<1600, 宽>250, 实心度>0.85`
2. 右侧实心绿「获取」：宽 200~400，高 48~105，宽高比 3~5.5，实心度>0.45
3. 紫色「新增进度」按钮（右侧列）

### event_pass（活动通行证）

```python
左侧区域 img[350:900, 120:520] 紫金大卡片占比 > 0.05
```
实测：**0.097**

---

## 回归测试

```powershell
python test_state_offline.py    # 应 17/17 通过
```

当前覆盖（17 例）：hangar×3、battle、battle_result、event_tasks×2、
daily_tasks×3、lottery_ready×2、reward_popup、black_market、event_pass、
menu_other×2、leave_warning。

**加新状态时务必同时加一个真实截图样本**，否则下次改判据会悄悄回归。

采集样本：`python collect_refs.py`（游戏空闲时跑，别在对局中跑）。

---

## 修订记录：`battle_prep` 判据（重要）

**旧（有 bug）**：
```python
if card_cyan > 0.15 and warm > 0.12 and not greens:
```
在暗色雨雾地图上 `warm=0.113`，差 0.007 不满足 → 部署界面被漏判成 `menu_other`，
导致循环对局一直不部署机甲。

**新（现行）**：
```python
# 3D 场景 + 半透明机甲卡片 → card_cyan 中等(0.15~0.72)
# 纯 UI 页面 card_cyan >= 0.71（活动/每日/通行证/抽奖/奖励弹窗）
# greens 非空 → 机库/商店/任务页（有大片绿色按钮）
# orange_tr >= 0.45 → 机库
if 0.15 < card_cyan < 0.72 and not greens and orange_tr < 0.45:
    battle_prep
```

**不要再用 `warm` 判断战斗/部署界面** —— 它随地图天气剧烈变化。

## 关于 `bright` 字段

`info["bright"] = (gray > 18).mean()` 是**非黑像素占比**，
几乎所有界面都 ≈ 0.97~0.99，**没有区分度**。
不要用它判断"画面很亮"，也不要据此识别启动画面（实测启动画面平均亮度 91.5，
机库 87.0，无法区分）。
