# -*- coding: utf-8 -*-
"""
广告安全处理器（基于实测的 AppLovin 激励视频流程）

实测流程：
  1. 激励视频播放中：左上角有「▶ Next」按钮 (228, 67) —— 点它可跳过/进入下一步
  2. 广告落地页：中间有大绿色「Install」按钮（绝对禁止点击）
  3. 点 Next 后出现退出调查：「Interested / Not interested」，
     右上角有真正关闭按钮「X」 (2306, 81) —— 点它退出广告
  4. 若误触 Install → 跳到 Google Play → 必须按 BACK 返回，绝不安装

安全规则：
  * 只允许点击这几个"安全点"：左上 Next、右上 X、以及运行时检测到的角部亮区
  * 中央大按钮区域（Install / 立即游玩）永久黑名单，绝不点击
  * 外部 App（Google Play / 浏览器）→ 只用 BACK 键返回，不点任何界面元素
  * 广告可能连续多个，需循环处理直到回到游戏
"""
import os
import sys
import time
import numpy as np

PROJ_DIR = os.path.dirname(os.path.abspath(__file__))
if PROJ_DIR not in sys.path:
    sys.path.insert(0, PROJ_DIR)

import device as d
import vision as v

W, H = 2400, 1080

# ---------------------------------------------------------------------------
# 黑名单：绝不允许点击的区域
# 覆盖：中央广告主体（Install / 立即游玩 / 点击下载）、右下 Google Play 徽标区
# ---------------------------------------------------------------------------
DANGER_RECTS = [
    (420, 150, 1980, 1080),   # 广告中央主体（Install 按钮所在）
    (1600, 780, 2400, 1080),  # 右下角 Google Play 徽标 / 安装
]

# 实测可用的安全按钮位置（逻辑坐标）
SAFE_NEXT = (228, 67)      # 左上「▶ Next」
SAFE_CLOSE = (2306, 81)    # 右上「X」关闭
SAFE_SPOTS = [SAFE_NEXT, SAFE_CLOSE]

FOREIGN_PKGS = {
    "com.android.vending": "Google Play",
    "com.android.chrome": "Chrome",
    "mark.via": "Via 浏览器",
    "com.quark.browser": "夸克",
    "org.mozilla.firefox": "Firefox",
    "com.android.browser": "浏览器",
}


def in_danger(x, y):
    for (x1, y1, x2, y2) in DANGER_RECTS:
        if x1 <= x <= x2 and y1 <= y <= y2:
            return True
    return False


def safe_tap(x, y, label=""):
    """只在白名单/安全区域点击"""
    if in_danger(x, y):
        d.log("  [安全拦截] 拒绝点击危险区域 (%d,%d) %s" % (x, y, label))
        return False
    d.tap(x, y, jitter=0)
    d.log("  [点击] (%d,%d) %s" % (x, y, label))
    return True


def is_ad_activity(pkg, act):
    """
    识别广告 Activity。实测 War Robots 使用三类广告 SDK：
      - AppLovin  : com.applovin.adview.AppLovinFullscreenActivity
      - AdMob     : com.google.android.gms.ads.AdActivity
      - ByteDance/穿山甲: com.bytedance.sdk.openadsdk.activity.TTFullWebActivity 等
    """
    a = (act or "").lower()
    if "applovin" in a:
        return True
    if "adview" in a or "interstitial" in a or "rewarded" in a:
        return True
    if "gms.ads" in a or "admob" in a:
        return True
    # 穿山甲 / Pangle
    if "openadsdk" in a or "bytedance" in a or "pangle" in a:
        return True
    if ".tt" in a and ("activity" in a or "ad" in a):
        return True
    return False


def is_bytedance_ad(act):
    a = (act or "").lower()
    return ("openadsdk" in a or "bytedance" in a or "pangle" in a)


def find_bytedance_close(img):
    """
    穿山甲广告右上角的「灰色圆形 X」关闭按钮。
    实测：bbox x[2268,2351] y[72,155]，中心约 (2309,113)。
    返回 (x, y) 或 None
    """
    sub = img[40:180, 2230:2400].astype(np.int16)
    r, g, b = sub[:, :, 0], sub[:, :, 1], sub[:, :, 2]
    # 灰色圆：RGB 接近中性，中等亮度（阈值放宽，'立即下载'类白底页面也能识别）
    m = (np.abs(r - g) < 32) & (np.abs(g - b) < 32) & (r > 70) & (r < 210)
    if int(m.sum()) < 400:
        return None
    ys, xs = np.nonzero(m)
    w = int(xs.max() - xs.min())
    h = int(ys.max() - ys.min())
    if not (28 <= w <= 160 and 28 <= h <= 160):
        return None
    return ((int(xs.min()) + int(xs.max())) // 2 + 2230,
            (int(ys.min()) + int(ys.max())) // 2 + 40)


# 穿山甲广告关闭 X 的实测固定位置（动态检测失败时兜底）
BD_CLOSE_FALLBACK = (2309, 113)


def find_corner_close(img):
    """
    在四个角的小范围里找"关闭按钮"（浅色圆底 X 或 Next 文字）
    返回 [(x, y, score)]，已过滤危险区
    """
    gray = v.to_gray(img)
    results = []
    regions = [
        ("右上", 2100, 0, 2400, 220),
        ("左上", 0, 0, 420, 220),
        ("右下", 2100, 880, 2400, 1080),
        ("左下", 0, 880, 300, 1080),
    ]
    for name, x1, y1, x2, y2 in regions:
        sub = gray[y1:y2, x1:x2]
        if sub.size == 0:
            continue
        mask = sub > 190
        n = int(mask.sum())
        if n < 60:
            continue
        ys, xs = np.nonzero(mask)
        cx = int(xs.mean()) + x1
        cy = int(ys.mean()) + y1
        if in_danger(cx, cy):
            continue
        # 越靠角、亮像素越多 → 越可能是关闭按钮
        corner = min(cx, W - cx) + min(cy, H - cy)
        score = n / 200.0 + (500 - min(corner, 500)) / 150.0
        results.append((cx, cy, round(score, 2), name))
    results.sort(key=lambda r: -r[2])
    return results


def detect_install_cta(img):
    """
    检测广告里是否存在显眼的「Install / 下载」大按钮（中央绿色大块）
    仅用于日志与决策（决定优先点 Next 而不是等）
    """
    # 中央区域找大块绿色
    zone = img[300:1080, 600:1900].astype(np.int16)
    r, g, b = zone[:, :, 0], zone[:, :, 1], zone[:, :, 2]
    green = ((g > 120) & (g > r + 40) & (g > b + 30))
    return float(green.mean()) > 0.02


def back_to_game(reason=""):
    """从任何外部 App 回到游戏（只用 BACK / 启动游戏）"""
    for _ in range(6):
        pkg, act = d.top_activity()
        if pkg == d.PKG:
            return True
        d.log("  [返回] 当前 %s (%s)，按 BACK" % (pkg, reason))
        d.back()
        time.sleep(1.8)
    pkg, act = d.top_activity()
    if pkg != d.PKG:
        d.log("  [返回] 直接启动游戏")
        d.launch(wait=8)
    return d.top_activity()[0] == d.PKG


def handle_ad(max_seconds=150, verbose=True):
    """
    安全处理一个广告（可能包含多个阶段 / 多种 SDK）。
    返回 (ok, elapsed, actions)

    策略差异：
      - AdMob    ：版式复杂且「安装」按钮极大，**优先用 BACK 关闭**，不乱点
      - AppLovin ：实测左上 Next + 右上 X 有效，点安全角部按钮
      - 外部 App ：只用 BACK 返回，绝不点击界面元素
    """
    start = time.time()
    actions = []
    phase = 0
    last_log = 0.0
    back_tries = 0
    next_tries = 0
    last_back = 0.0

    d.log("=== 广告处理开始（上限 %ds）===" % max_seconds)
    time.sleep(1.2)

    while time.time() - start < max_seconds:
        pkg, act = d.top_activity()
        a_low = (act or "").lower()

        # ---- 外部 App → 立刻返回，绝不点击界面 ----
        if pkg != d.PKG:
            d.log("[广告] 跳到外部应用: %s" % pkg)
            actions.append(("foreign", pkg))
            back_to_game("ad")
            time.sleep(1.5)
            continue

        # ---- 广告 Activity ----
        if is_ad_activity(pkg, act):
            is_admob = ("gms.ads" in a_low or "admob" in a_low)
            is_bd = is_bytedance_ad(act)
            elapsed = time.time() - start

            # 穿山甲广告：右上角灰色圆形 X（实测有效），BACK 无效
            if is_bd:
                img, _ = d.screenshot(save=False)
                pos = find_bytedance_close(img) if img is not None else None
                if pos and elapsed > 1.5:
                    if safe_tap(pos[0], pos[1], "穿山甲关闭X"):
                        actions.append(("bd_close", pos[0], pos[1]))
                        time.sleep(2.5)
                        continue
                # 动态检测失败时，用实测固定位置兜底（穿山甲 X 位置很稳定）
                if elapsed > 6 and (elapsed - last_back) > 6:
                    last_back = elapsed
                    back_tries += 1
                    fx, fy = BD_CLOSE_FALLBACK
                    d.log("[广告] 穿山甲：动态未命中，点固定位置 (%d,%d)（第 %d 次）"
                          % (fx, fy, back_tries))
                    if safe_tap(fx, fy, "穿山甲固定X"):
                        actions.append(("bd_close_fixed", fx, fy))
                        time.sleep(2.5)
                    else:
                        d.back()
                        time.sleep(2.5)
                    if back_tries >= 8:
                        d.log("[广告] 穿山甲关闭多次失败，结束本广告")
                        break
                    continue
                if verbose and elapsed - last_log > 5:
                    last_log = elapsed
                    d.log("[广告] 穿山甲广告处理中 %.0fs" % elapsed)
                time.sleep(1.5)
                continue

            if is_admob:
                # AdMob：先等待（有些广告需播放几秒才有响应），再用 BACK 关闭
                if elapsed < 3:
                    time.sleep(1.5)
                    continue
                d.log("[广告] AdMob，使用 BACK 关闭（第 %d 次）" % (back_tries + 1))
                actions.append(("admob_back", round(elapsed, 1)))
                d.back()
                back_tries += 1
                time.sleep(2.5)
                if back_tries >= 6:
                    d.log("[广告] BACK 多次无效，停止尝试")
                    break
                continue

            # AppLovin：动态检测角部按钮（不同广告版式位置会变，不能用固定坐标）
            img, _ = d.screenshot(save=False)
            if img is None:
                time.sleep(2.0)
                continue

            has_cta = detect_install_cta(img)
            tapped = False

            xs = find_corner_close(img)
            # 优先右上角 X（关闭/推出调查）
            cand_right = [c for c in xs if c[0] > W * 0.72 and c[1] < H * 0.35]
            if cand_right and elapsed > 1.5:
                cx, cy, sc, name = cand_right[0]
                if safe_tap(cx, cy, "右上X/" + name):
                    actions.append(("close_x", cx, cy))
                    tapped = True
                    time.sleep(2.0)
                    continue

            # 其次左上角「▶ Next / 跳过」（位置随版式变化，用检测值）
            cand_left = [c for c in xs if c[0] < W * 0.30 and c[1] < H * 0.35]
            if not tapped and cand_left and elapsed > 1.2:
                cx, cy, sc, name = cand_left[0]
                if safe_tap(cx, cy, "左上Next/" + name):
                    actions.append(("next", cx, cy))
                    next_tries += 1
                    tapped = True
                    time.sleep(2.0)
                    if next_tries >= 4:
                        # Next 连点无效 → 说明已在末页且无 X，用 BACK 兜底
                        d.log("[广告] Next 连续 %d 次无效，改用 BACK" % next_tries)
                        actions.append(("back_fallback",))
                        d.back()
                        time.sleep(2.5)
                        next_tries = 0
                        if back_tries >= 4:
                            break
                        back_tries += 1
                    continue

            if not tapped:
                # 兜底：固定位尝试（部分版式不显示亮色角标）
                if elapsed > 4 and back_tries < 3 and (elapsed - last_back) > 12:
                    last_back = elapsed
                    back_tries += 1
                    d.log("[广告] 未检测到角部按钮，尝试 BACK（第 %d 次）" % back_tries)
                    actions.append(("back",))
                    d.back()
                    time.sleep(2.5)
                    continue
                if verbose and elapsed - last_log > 5:
                    last_log = elapsed
                    d.log("[广告] AppLovin 等待中 %.0fs（Install按钮=%s）" % (elapsed, has_cta))
                time.sleep(2.0)
            continue

        # ---- 已回到游戏 ----
        d.log("[广告] 已回到游戏（用时 %.0fs）" % (time.time() - start))
        time.sleep(1.2)

        pkg2, act2 = d.top_activity()
        if is_ad_activity(pkg2, act2):
            phase += 1
            d.log("[广告] 连续广告 #%d，继续处理" % phase)
            if phase > 6:
                d.log("[广告] 连续广告过多，停止")
                break
            time.sleep(1.0)
            continue
        if pkg2 != d.PKG:
            back_to_game("after ad")
            continue
        return True, time.time() - start, actions

    d.log("[广告] 处理超时，强制回到游戏")
    back_to_game("timeout")
    return d.top_activity()[0] == d.PKG, time.time() - start, actions


def watch_video_ads(max_ads=10, max_minutes=20, task_nav=None, go_black_market=None):
    """
    主流程：反复点紫色「观看视频」按钮并安全看广告。
    支持的广告入口：
      - 活动任务页的「新增进度 / 观看视频」
      - 黑市（Black Market）的「免费钥匙」按钮
    """
    import ui_state as u
    import engine as e
    import task_ui

    AD_STATES = ("event_tasks", "black_market")

    watched = 0
    start = time.time()
    empty_rounds = 0
    exhausted = set()   # 已用尽的广告来源（event_tasks / black_market）

    while watched < max_ads and (time.time() - start) / 60.0 < max_minutes:
        info = u.detect(save_name="wad_%d.png" % watched if watched < 3 else None,
                        keep=watched < 3)
        st = info["state"]
        d.log("--- 广告轮次 %d，界面=%s ---" % (watched + 1, st))

        if st == "ad":
            ok, secs, acts = handle_ad()
            watched += 1
            d.log("广告完成: ok=%s 用时=%.0fs" % (ok, secs))
            time.sleep(1.5)
            continue

        if st in ("play_store", "foreign_app", "launcher"):
            back_to_game("watch_loop")
            continue

        # 奖励轨道弹层：先关掉
        if st == "event_reward_track":
            e.dismiss_overlay()
            continue

        # 不在广告来源页 → 导航
        if st not in AD_STATES:
            if task_nav:
                d.log("不在广告页，尝试导航到任务页")
                if task_nav() and u.detect(keep=False)["state"] in AD_STATES:
                    continue
            # 任务页没有入口时，尝试黑市
            if go_black_market:
                d.log("尝试前往黑市查找「免费钥匙」广告")
                if go_black_market() and u.detect(keep=False)["state"] == "black_market":
                    continue
            empty_rounds += 1
            if empty_rounds >= 3:
                d.log("连续多次找不到广告入口，结束")
                break
            time.sleep(2.0)
            continue

        empty_rounds = 0
        img = info["img"]
        purples = task_ui.find_watch_video_buttons(img)
        if not purples:
            d.log("当前界面（%s）没有可用的视频按钮" % st)
            # 记录该来源已用尽，避免原地打转
            exhausted.add(st)
            if st == "event_tasks":
                n = e.claim_task_rewards(max_rounds=3)
                if n > 0:
                    continue
            # 尝试另一个来源
            candidates = []
            if "event_tasks" not in exhausted and task_nav:
                candidates.append(("tasks", task_nav))
            if "black_market" not in exhausted and go_black_market:
                candidates.append(("black_market", go_black_market))
            if candidates:
                name, fn = candidates[0]
                d.log("尝试切换广告来源: %s" % name)
                ok_nav = fn()
                if ok_nav:
                    continue
            d.log("所有广告来源均已耗尽，结束")
            break

        btn = purples[0]
        d.log("点击视频按钮 @%s" % (btn["center"],))
        d.tap(btn["center"][0], btn["center"][1], jitter=2)
        time.sleep(3.5)

        got = False
        for _ in range(10):
            pkg, act = d.top_activity()
            if is_ad_activity(pkg, act) or pkg != d.PKG:
                got = True
                break
            time.sleep(1.0)

        if not got:
            d.log("未检测到广告（可能无库存或需等待）")
            i = u.detect(keep=False)
            if i["state"] == "dialog":
                e.dismiss_dialog()
            empty_rounds += 1
            if empty_rounds >= 3:
                d.log("多次触发广告失败，结束")
                break
            time.sleep(1.5)
            continue

        ok, secs, acts = handle_ad()
        watched += 1
        d.log("广告 #%d 完成: ok=%s 用时=%.0fs actions=%s" % (watched, ok, secs, acts))
        time.sleep(1.5)

        i = u.detect(keep=False)
        if i["state"] == "dialog":
            e.dismiss_dialog()
        if i["state"] == "event_reward_track":
            e.dismiss_overlay()
        if u.detect(keep=False)["state"] == "event_tasks":
            e.claim_task_rewards(max_rounds=3)

    d.log("广告流程结束，共 %d 次" % watched)
    return watched


if __name__ == "__main__":
    d.ensure_server()
    pkg, act = d.top_activity()
    print("当前:", pkg, act)
    if is_ad_activity(pkg, act):
        print(handle_ad())
    else:
        print("当前不在广告界面")
