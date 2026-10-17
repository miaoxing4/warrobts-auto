# -*- coding: utf-8 -*-
"""
War Robots 界面状态识别（纯视觉 + Activity）

判别顺序（严格按可信度）：
  1. 外部 App：广告 / Google Play / 其它 App / 桌面  （Activity 判定，最可靠）
  2. battle_result  结算页：顶部红色横幅
  3. hangar         机库：右上橙色「前往战斗」占比 > 0.45
  4. battle_modes   战斗模式：底部中央橙色按钮 > 0.15
  5. battle_prep    战前部署/阵亡复活：下部机器人卡片区青灰占比 > 0.15
  6. event_tasks    活动任务：底部绿色「完成全部」/ 右侧实心绿「获取」/ 紫色观看视频
  7. event_pass     活动通行证：左侧紫金大卡片
  8. battle         战斗中：战斗 HUD 特征 >= 3 个
  9. dialog         对话框：中央暗 + 整体暗
 10. menu_other     其它全屏菜单

实测特征记录：
  I1_now.png(黄昏战场)  HUD=4   sandy=0.11 c=169
  98_deploy_1.png(沙地)  HUD=5   sandy=0.76 c=394
  95_clean_A.png(机库)   HUD=3   orange_tr=0.56
  95_clean_B.png(模式页)  HUD=2   orange_mode=0.47
  D1_stuck.png(城市部署)  HUD=0   card_cyan=0.55
  62_event_tasks2.png    HUD=2   greens
"""
import os
import sys
import numpy as np

PROJ_DIR = os.path.dirname(os.path.abspath(__file__))
if PROJ_DIR not in sys.path:
    sys.path.insert(0, PROJ_DIR)

import device as d
import vision as v

C_GREEN = (16, 185, 129)
C_PURPLE = (150, 70, 220)

R_BATTLE_BTN = (1990, 70, 2400, 250)     # 机库右上「前往战斗」
R_MODE_BTN = (760, 740, 1180, 900)       # 模式页底部「前往战斗」
R_CENTER = (700, 350, 1700, 750)
R_HEADER = (500, 0, 1900, 110)           # 结算页红色横幅
R_CARDS = (400, 500, 1600, 1010)         # 机器人卡片区
R_LEFT_CARD = (120, 350, 520, 900)       # 活动通行证左侧紫金卡


# ------------------------------------------------------------------ 基础度量
def _mean(img, box):
    x1, y1, x2, y2 = box
    p = img[max(0, y1):y2, max(0, x1):x2]
    if p.size == 0:
        return (0, 0, 0)
    return tuple(int(c) for c in p.reshape(-1, 3).mean(axis=0))


def _orange_frac(img, box):
    x1, y1, x2, y2 = box
    p = img[max(0, y1):y2, max(0, x1):x2].reshape(-1, 3).astype(np.int16)
    if p.size == 0:
        return 0.0
    r, g, b = p[:, 0], p[:, 1], p[:, 2]
    return float(((r > 210) & (g > 70) & (g < 200) & (b < 140)).mean())


def _sandy(img):
    sub = img[270:810, ::8].reshape(-1, 3).astype(np.int16)
    if sub.size == 0:
        return 0.0
    r, g, b = sub[:, 0], sub[:, 1], sub[:, 2]
    return float(((r > 90) & (r > b + 20) & (g > b)).mean())


def _warm(img):
    sub = img[300:900, 400:2000].reshape(-1, 3).astype(np.int16)
    return float((sub[:, 0] > sub[:, 2]).mean())


def _card_cyan(img):
    sub = img[R_CARDS[1]:R_CARDS[3], R_CARDS[0]:R_CARDS[2]].astype(np.int16)
    r, g, b = sub[:, :, 0], sub[:, :, 1], sub[:, :, 2]
    return float(((b > 70) & (b > r + 15) & (g > r)).mean())


def detect_battle_timer(img):
    """
    检测顶部居中是否有战斗倒计时 MM:SS（大号白色数字）。
    这是"真正在对局中"的决定性判据（菜单/商店/结算页都没有）。
    返回 (found, text)
    """
    zone = img[18:80, 1195:1400]
    if zone.size == 0:
        return False, ""
    gray = v.to_gray(zone)
    mask = (gray > 205).astype(np.uint8)
    n = int(mask.sum())
    if n < 300:
        return False, ""
    # 数字行高度：统计有像素的行数
    rows = np.nonzero(mask.sum(axis=1) > 0)[0]
    if len(rows) < 18:
        return False, ""
    # 用一个数字模板试识别，确认是数字而非其它白色 UI
    try:
        import rating_reader as rr
        templates = rr.load_templates()
        if not templates:
            return True, "?"   # 没模板时仅凭白色文字特征判定
        chars = rr.segment_chars(mask, min_w=3)
        if len(chars) < 3:
            return False, ""
        txt = ""
        for (s, e, g) in chars:
            h_, w_ = g.shape
            if w_ / max(1, h_) < 0.40 and h_ < 24:
                txt += ":"
                continue
            dd, sc = rr.match_digit(g, templates)
            txt += str(dd) if (dd and sc > 0.30) else "?"
        digits = sum(1 for c in txt if c.isdigit())
        return digits >= 3, txt
    except Exception:
        return True, "?"


def detect_battle_hud(img):
    """
    战斗 HUD 特征检测（区分"真正在对局中"与各种菜单/地图界面）：
      hp_bar      左上角**亮绿色血量条**（最强判据：实测战斗 0.23，其它界面全为 0）
      shield_icon 右上绿盾能力图标
      fire_ring   右下红色开火圆环
      team_strip  顶部青/红队伍条
      joystick    左下浅色摇杆圆
    返回 {'score': n, 'found': [...], 'hp': float}
    """
    found = []

    # 血量条：位置 (50,8)-(420,70)，亮绿色
    a = img[8:70, 50:420].astype(np.int16)
    hp = float(((a[:, :, 1] > 140) & (a[:, :, 1] > a[:, :, 0] + 60)
                & (a[:, :, 1] > a[:, :, 2] + 40)).mean())
    if hp > 0.04:
        found.append("hp_bar")

    b = img[180:420, 2180:2400].astype(np.int16)
    if ((b[:, :, 1] > 110) & (b[:, :, 2] > 90)
            & (b[:, :, 1] > b[:, :, 0] + 30)).mean() > 0.02:
        found.append("shield_icon")

    c = img[600:1000, 2050:2400].astype(np.int16)
    if ((c[:, :, 0] > 120) & (c[:, :, 0] > c[:, :, 1] + 50)
            & (c[:, :, 0] > c[:, :, 2] + 40)).mean() > 0.02:
        found.append("fire_ring")

    dz = img[0:110, 740:1700].astype(np.int16)
    blue = ((dz[:, :, 2] > 150) & (dz[:, :, 2] > dz[:, :, 0] + 50)
            & (dz[:, :, 1] > 100)).mean()
    red = ((dz[:, :, 0] > 140) & (dz[:, :, 0] > dz[:, :, 1] + 60)
           & (dz[:, :, 0] > dz[:, :, 2] + 60)).mean()
    if blue > 0.03 or red > 0.03:
        found.append("team_strip")

    eg = v.to_gray(img[600:800, 180:420])
    if ((eg > 90) & (eg < 200)).mean() > 0.10:
        found.append("joystick")

    return {"score": len(found), "found": found, "hp": round(hp, 3)}


# ------------------------------------------------------------------ 主判定
def detect(img=None, save_name=None, keep=True):
    if img is None:
        img, path = d.screenshot(save_name, save=keep)
        if img is None:
            return {"state": "screenshot_failed", "activity": None, "img": None, "reasons": []}
    pkg, act = d.top_activity()
    act_s = (act or "")
    reasons = []
    info = {"activity": (pkg, act), "img": img, "reasons": reasons}

    # ---- 1) 外部 App ----
    a_low = act_s.lower()
    if ("applovin" in a_low or "adview" in a_low
            or "gms.ads" in a_low or "admob" in a_low
            or "openadsdk" in a_low or "bytedance" in a_low or "pangle" in a_low):
        info["state"] = "ad"
        reasons.append("ad activity: %s" % act_s)
        return info
    if pkg == "com.android.vending":
        info["state"] = "play_store"
        reasons.append("Google Play")
        return info
    if pkg and pkg != d.PKG:
        info["state"] = "launcher" if "launcher" in pkg else "foreign_app"
        reasons.append("pkg=%s" % pkg)
        return info

    # ---- 2) 度量 ----
    orange_tr = _orange_frac(img, R_BATTLE_BTN)
    orange_mode = _orange_frac(img, R_MODE_BTN)
    sandy = _sandy(img)
    warm = _warm(img)
    center_sum = sum(_mean(img, R_CENTER))
    card_cyan = _card_cyan(img)
    header = _mean(img, R_HEADER)
    greens = v.find_color_regions(img, C_GREEN, tol=60, min_area=9000, max_regions=8)
    purples = v.find_color_regions(img, C_PURPLE, tol=60, min_area=6000, max_regions=8)
    gray = v.to_gray(img)
    bright = float((gray > 18).mean())
    hud = detect_battle_hud(img)

    info.update({
        "orange_tr": round(orange_tr, 3),
        "orange_mode": round(orange_mode, 3),
        "sandy": round(sandy, 3),
        "warm": round(warm, 3),
        "center_sum": center_sum,
        "card_cyan": round(card_cyan, 3),
        "bright": round(bright, 3),
        "hud": hud["score"],
        "greens": greens,
        "purples": purples,
    })

    # ---- 3) 判定 ----
    # 结算页
    if header[0] > 90 and header[0] > header[1] + 40 and header[0] > header[2] + 30:
        info["state"] = "battle_result"
        reasons.append("red header %s" % (header,))
        return info

    # 机库
    if orange_tr > 0.45 and sandy < 0.2 and center_sum > 330:
        info["state"] = "hangar"
        reasons.append("orange_tr=%.2f" % orange_tr)
        return info

    # 供给中心（抽奖）：底部中央有大块紫色「获取供给」按钮
    # 实测：可抽时底部紫占比 0.531，冷却时 0.000，其它界面 0.000
    bot = img[940:1080, 800:1700].astype(np.int16)
    _pr, _pg, _pb = bot[:, :, 0], bot[:, :, 1], bot[:, :, 2]
    purple_bot = float(((_pr > 110) & (_pr < 180) & (_pb > 200)
                        & (_pb > _pg + 60)).mean())
    if purple_bot > 0.15:
        info["state"] = "lottery_ready"
        reasons.append("lottery purple button=%.2f" % purple_bot)
        return info

    # 奖励弹窗「你的奖励」：底部中央有大绿「确定」按钮（宽约 613），背景偏暗
    _gr = float(((_pg > 150) & (_pg > _pr + 60) & (_pg > _pb + 40)).mean())
    if _gr > 0.45 and center_sum < 300:
        info["state"] = "reward_popup"
        reasons.append("reward popup green ok=%.2f" % _gr)
        return info

    # 每日任务页（顶部有 4 个标签：特殊/奖励/每日/派系）
    # 实测：4 标签页暗青占比 0.544，2 标签页(活动/最佳投资) 0.166
    tab_band = img[95:185, 600:1900].astype(np.int16)
    _tr, _tg, _tb = tab_band[:, :, 0], tab_band[:, :, 1], tab_band[:, :, 2]
    dark_tabs = float(((_tr > 30) & (_tr < 90) & (_tg > 70) & (_tg < 130)
                       & (_tb > 90) & (_tb < 160)).mean())
    if dark_tabs > 0.40:
        info["state"] = "daily_tasks"
        reasons.append("4-tab row dark=%.2f" % dark_tabs)
        return info

    # 战斗模式选择
    if orange_mode > 0.15 and sandy < 0.2:
        info["state"] = "battle_modes"
        reasons.append("orange_mode=%.2f" % orange_mode)
        return info

    # 活动奖励轨道弹层（横向里程碑卡片 + 右上角蓝色 X）
    # 特征：右上角存在纯蓝 X，且上部中间有大标题
    bluex = img[0:160, 2150:2400].astype(np.int16)
    bx = ((bluex[:, :, 2] > 200) & (bluex[:, :, 0] < 90)
          & (bluex[:, :, 1] > 50) & (bluex[:, :, 1] < 190))
    if bx.sum() > 150:
        info["state"] = "event_reward_track"
        reasons.append("blue close-X=%d px" % int(bx.sum()))
        return info

    # 「放弃战斗」警告对话框（最重要！）
    # 实测文案："您仍有机器人幸存，切勿放弃战斗！可能会被罚分！"
    # 版式：左红「离开」+ 右绿「留在战斗中」，y 约 770-850
    # 判别：该条带上同时存在大面积纯红与纯绿按钮
    band = img[765:855, :].astype(np.int16)
    _br, _bg, _bb = band[:, :, 0], band[:, :, 1], band[:, :, 2]
    red_btn = int(((_br > 180) & (_bg < 95) & (_bb < 95)).sum())
    green_btn = int(((_bg > 130) & (_bg > _br + 50) & (_bg > _bb + 40)).sum())
    if red_btn > 20000 and green_btn > 20000:
        info["state"] = "leave_warning"
        reasons.append("leave warning red=%d green=%d" % (red_btn, green_btn))
        return info

    # 部署/复活界面（机器人卡片）
    if card_cyan > 0.15 and warm > 0.12 and not greens:
        info["state"] = "battle_prep"
        reasons.append("card_cyan=%.2f warm=%.2f" % (card_cyan, warm))
        return info

    # 黑市（Black Market）：**整屏深紫背景**（实测暗紫占比 0.66，其它界面 < 0.01）
    a16 = img.astype(np.int16)
    _r, _g, _b = a16[:, :, 0], a16[:, :, 1], a16[:, :, 2]
    purple_ratio = float(((  _b > 25) & (_b < 130) & (_r < 110)
                          & (_b > _g + 18) & (_r > _g + 3)).mean())
    if purple_ratio > 0.35:
        info["state"] = "black_market"
        reasons.append("black market purple bg=%.2f" % purple_ratio)
        return info

    # 活动通行证页（左侧紫金大卡片是通行证页专有，优先判定）
    lc = img[R_LEFT_CARD[1]:R_LEFT_CARD[3], R_LEFT_CARD[0]:R_LEFT_CARD[2]].astype(np.int16)
    purple_frac = float(((lc[:, :, 0] > 90) & (lc[:, :, 2] > 110)
                         & (lc[:, :, 2] > lc[:, :, 1] + 30)
                         & (lc[:, :, 0] > lc[:, :, 1])).mean())
    if purple_frac > 0.05:
        info["state"] = "event_pass"
        reasons.append("battle-pass purple card=%.3f" % purple_frac)
        return info

    # 活动任务页
    task_all = [g for g in greens
                if g["center"][1] > 960 and 900 < g["center"][0] < 1600
                and g["size"][0] > 250]
    if task_all:
        info["state"] = "event_tasks"
        info["claim_greens"] = greens
        reasons.append("bottom claim-all")
        return info

    def is_claim(g):
        cx, cy = g["center"]
        w_, h_ = g["size"]
        if not (180 <= w_ <= 420 and 44 <= h_ <= 110):
            return False
        if cx < 1200:
            return False
        x1, y1, x2, y2 = g["bbox"]
        patch = img[max(0, y1 + 4):max(1, y2 - 4), max(0, x1 + 6):max(1, x2 - 6)]
        if patch.size == 0:
            return False
        p = patch.reshape(-1, 3).astype(np.int16)
        solid = float(((p[:, 1] > 110) & (p[:, 1] > p[:, 0] + 30)
                       & (p[:, 1] > p[:, 2] + 5)).mean())
        return solid > 0.45

    claim = [g for g in greens if is_claim(g)]
    if [g for g in claim if g["center"][0] > 1400]:
        info["state"] = "event_tasks"
        info["claim_greens"] = claim
        reasons.append("right claim greens=%d" % len(claim))
        return info

    watch_btns = [p for p in purples if p["center"][0] > 1300]
    if watch_btns:
        info["state"] = "event_tasks"
        info["watch_btns"] = watch_btns
        reasons.append("purple watch buttons=%d" % len(watch_btns))
        return info

    # 活动通行证页（已在上面判定）
    # 战斗（核心判据：左上亮绿色血量条 + 至少 2 个其它 HUD 特征）
    info["hp"] = hud["hp"]
    if "hp_bar" in hud["found"] and hud["score"] >= 3:
        info["state"] = "battle"
        reasons.append("battle hp=%.2f HUD=%d %s" % (hud["hp"], hud["score"], hud["found"]))
        return info
    if hud["score"] >= 4:
        # 没有血条但 HUD 很齐全（例如刚复活瞬间）
        info["state"] = "battle"
        reasons.append("battle HUD=%d (no hp) %s" % (hud["score"], hud["found"]))
        return info
    # 沙地/暖色兜底：必须同时具备 2 个以上真实战斗 HUD 特征，否则不算战斗
    if sandy > 0.5 and center_sum > 300 and hud["score"] >= 2:
        info["state"] = "battle"
        reasons.append("sandy=%.2f HUD=%d" % (sandy, hud["score"]))
        return info
    if sandy > 0.03 and center_sum > 160 and warm > 0.35 and hud["score"] >= 3:
        info["state"] = "battle"
        reasons.append("warm=%.2f sandy=%.2f HUD=%d" % (warm, sandy, hud["score"]))
        return info

    # 对话框
    if center_sum < 260 and bright < 0.6:
        info["state"] = "dialog"
        reasons.append("dark c=%d" % center_sum)
        return info

    if bright > 0.4:
        info["state"] = "menu_other"
        reasons.append("bright=%.2f fallback" % bright)
        return info

    info["state"] = "unknown"
    return info


def describe(info):
    keys = ["orange_tr", "orange_mode", "card_cyan", "sandy", "center_sum", "hud"]
    s = "state=%-12s" % info.get("state")
    for k in keys:
        if k in info:
            s += " %s=%s" % (k, info[k])
    if info.get("greens"):
        s += " G=%d" % len(info["greens"])
    return s
