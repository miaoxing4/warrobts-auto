# -*- coding: utf-8 -*-
"""
War Robots 自动化引擎

目标一：自动打开游戏 → 浏览广告 → 点击领取各种任务礼包
目标二：自动启动游戏 → 进入战斗 → 1 分钟内随机操作 → 退出

用法：
  python engine.py ads      [--rounds N] [--minutes M]
  python engine.py battle   [--seconds S]
  python engine.py both     [--rounds N] [--seconds S]
  python engine.py loop     [--cycles N]   循环执行 目标二
  python engine.py state
"""
import os
import sys
import time
import random
import argparse
import numpy as np

PROJ_DIR = os.path.dirname(os.path.abspath(__file__))
if PROJ_DIR not in sys.path:
    sys.path.insert(0, PROJ_DIR)

import device as d
import vision as v
import ui_state as u

# 预设坐标（逻辑 2400x1080，均已按实际截图实测校准）
POS = {
    "battle_btn":       (2215, 160),   # 机库右上「前往战斗」
    "shop_btn":         (2200, 1000),  # 机库右下「商店」
    "settings":         (2350, 45),    # 机库右上齿轮
    "home_btn":         (1985, 40),    # 二级页右上"房子"
    "back":             (155, 1000),   # 二级页左下「后退」
    "left_mission":     (185, 300),    # 机库左侧"活动"
    "left_event2":      (185, 450),
    "left_gift14d":     (185, 600),
    "event_tasks_tab":  (2296, 385),   # 活动页右侧「任务」（实测中心）
    "event_reward_tab": (2296, 240),   # 活动页右侧「奖励」
    "event_claim_all":  (1250, 1038),  # 任务页底部「完成全部」
    "mode_battle_btn":  (966, 816),    # 战斗模式页底部「前往战斗」
    "deploy_robot":     (1310, 730),   # 战前部署：机器人卡片
    "battle_settings":  (2285, 65),    # 战斗内右上设置
    "result_to_hangar": (209, 1012),   # 结算页左下「前往机库」（实测中心）
    "result_to_battle": (2206, 1012),  # 结算页右下「前往战斗」（实测中心）
    "reward_track_close": (2336, 53),  # 活动奖励轨道弹层右上角蓝色 X（实测）
    "stay_in_battle_btn": (1563, 809), # 「留在战斗中」绿色按钮（放弃战斗警告框，实测）
    # --- 每日任务（右侧对勾按钮 → 每日标签）---
    "daily_entry":      (2096, 331),   # 机库右侧第 1 个（对勾图标）
    "daily_tab":        (1412, 136),   # 任务页顶部「每日」标签
    # --- 供给中心抽奖（左侧第 2 个怪物图标）---
    "lottery_entry":    (163, 459),    # 机库左侧第 2 个（带倒计时的怪物图标）
    "lottery_btn":      (1247, 1013),  # 供给中心底部「获取供给」紫色按钮
    "reward_ok":        (1247, 1012),  # 奖励弹窗「你的奖励」绿色确定按钮（实测）
    "modal_confirm":    (1512, 704),
    "modal_cancel":     (886, 704),
    "modal_x":          (2237, 365),
}

# 战斗操作区（逻辑坐标）
JOYSTICK = (280, 660)          # 左下移动摇杆
FIRE_ZONE = (2050, 700, 2300, 1000)   # 右下开火/技能区
LOOK_ZONE = (1400, 400, 2100, 800)    # 视角拖动区


# ---------------------------------------------------------------- 基础动作
def find_buttons(img, kind="green", min_area=9000):
    table = {
        "green": ((16, 185, 129), 60),
        "orange": ((255, 130, 40), 80),
        "purple": ((150, 70, 220), 60),
        "yellow": ((250, 200, 60), 60),
    }
    color, tol = table[kind]
    regs = v.find_color_regions(img, color, tol=tol, min_area=min_area, max_regions=20)
    regs.sort(key=lambda r: r["center"][1])
    return regs


def click(x, y, wait=1.2, jitter=3):
    d.tap(x, y, jitter=jitter)
    time.sleep(wait)


def click_reg(reg, wait=1.2):
    click(reg["center"][0], reg["center"][1], wait)


def ensure_landscape():
    if d.rotation() != 1:
        d.lock_landscape()
    return d.rotation()


def force_stay_in_battle():
    """
    处理「您仍有机器人幸存，切勿放弃战斗！可能会被罚分！」警告框。
    **必须点「留在战斗中」，绝不能点「离开」**（离开会被判罚扣分）。
    返回 True 表示已处理（或当前没有该对话框）
    """
    st = u.detect(keep=False)["state"]
    if st != "leave_warning":
        return True
    d.log("force_stay_in_battle: 检测到放弃战斗警告，点击「留在战斗中」")
    for _ in range(3):
        d.tap(*POS["stay_in_battle_btn"])
        time.sleep(1.8)
        st2 = u.detect(keep=False)["state"]
        if st2 != "leave_warning":
            d.log("force_stay_in_battle: 已留在战斗中（state=%s）" % st2)
            return True
    d.log("force_stay_in_battle: 未能关闭警告框")
    return False


def dismiss_reward_popup(max_try=3):
    """关闭「你的奖励」弹窗（点绿色确定）"""
    for _ in range(max_try):
        st = u.detect(keep=False)["state"]
        if st != "reward_popup":
            return True
        d.log("dismiss_reward_popup: 点击「确定」")
        d.tap(*POS["reward_ok"])
        time.sleep(1.5)
    return u.detect(keep=False)["state"] != "reward_popup"


def dismiss_dialog(max_try=3):
    """
    关闭各种对话框。
    特别注意：「放弃战斗」警告框必须选「留在战斗中」，不能选「离开」；
              「你的奖励」弹窗点绿色「确定」。
    """
    for i in range(max_try):
        info = u.detect(keep=False)
        st = info["state"]
        if st == "leave_warning":
            force_stay_in_battle()
            continue
        if st == "reward_popup":
            dismiss_reward_popup()
            continue
        if st != "dialog":
            return True
        d.log("dismiss_dialog: 第 %d 次尝试" % (i + 1))
        d.tap(*POS["modal_x"])
        time.sleep(1.5)
        img, _ = d.screenshot(save=False)
        if img is not None:
            greens = find_buttons(img, "green", min_area=9000)
            if greens:
                d.tap(greens[0]["center"][0], greens[0]["center"][1])
                time.sleep(1.5)
        if u.detect(keep=False)["state"] == "dialog":
            d.back()
            time.sleep(1.5)
    return u.detect(keep=False)["state"] not in ("dialog", "leave_warning")


def dismiss_overlay():
    """
    关闭各种弹层（非战斗、非对话框模态）：
      - event_reward_track（活动奖励轨道）→ 点右上蓝色 X
    返回 True 表示已关闭或原本就没有弹层
    """
    st = u.detect(keep=False)["state"]
    if st != "event_reward_track":
        return True
    d.log("dismiss_overlay: 关闭活动奖励轨道弹层")
    for _ in range(3):
        d.tap(*POS["reward_track_close"])
        time.sleep(1.8)
        if u.detect(keep=False)["state"] != "event_reward_track":
            d.log("dismiss_overlay: 已关闭")
            return True
        # 备用：按返回键
        d.back()
        time.sleep(1.8)
        if u.detect(keep=False)["state"] != "event_reward_track":
            return True
    d.log("dismiss_overlay: 未能关闭")
    return False


def go_home(max_rounds=6):
    """尽力回到机库"""
    for i in range(max_rounds):
        info = u.detect(keep=False)
        st = info["state"]
        d.log("go_home[%d]: %s" % (i, st))
        if st == "hangar":
            return True
        if st == "ad":
            import ad_handler
            ad_handler.handle_ad(max_seconds=150)
        elif st in ("play_store", "foreign_app", "launcher"):
            import ad_handler
            ad_handler.back_to_game("go_home")
        elif st == "dialog":
            dismiss_dialog()
        elif st == "reward_popup":
            d.log("go_home: 奖励弹窗，点确定")
            dismiss_reward_popup()
        elif st == "event_reward_track":
            d.log("go_home: 奖励轨道弹层，关闭")
            dismiss_overlay()
        elif st == "battle_result":
            d.log("go_home: 结算页，点「前往机库」")
            click(*POS["result_to_hangar"], wait=4.0)
            time.sleep(1.5)
        elif st in ("event_tasks", "event_pass", "battle_modes", "menu_other"):
            click(*POS["back"], wait=2.2)
        elif st in ("battle", "battle_prep"):
            # 绝对安全第一：已在战斗中就不强行离开（1 分钟内退出会被判罚）。
            # 交由调用方决定：先待够时间再退。
            d.log("go_home: 当前在战斗中/部署界面，为遵守 1 分钟规则不主动退出")
            return False
        else:
            d.back()
            time.sleep(1.8)
    return u.detect(keep=False)["state"] == "hangar"


# ---------------------------------------------------------------- 目标一：广告 + 礼包
def claim_task_rewards(max_rounds=15, verbose=True, move=140):
    """
    在活动任务页反复领奖，直到没有可领的。

    使用 task_ui 的精确检测器（实测尺寸/位置），避免误点「全部任务」等导航按钮。
    流程：
      1) 底部「完成全部」优先
      2) 逐个点右侧「获取」
      3) 全部领完后，滚动查找更多任务
    """
    import task_ui

    claimed = 0
    clicked_positions = []
    no_progress = 0
    scroll_tries = 0

    def recent(cx, cy):
        for (px, py) in clicked_positions[-6:]:
            if abs(cx - px) < 60 and abs(cy - py) < 50:
                return True
        return False

    for rnd in range(max_rounds):
        info = u.detect(save_name="claim_%d.png" % rnd if rnd == 0 else None, keep=(rnd == 0))
        st = info["state"]
        if verbose:
            d.log("claim[%d]: state=%s" % (rnd, st))

        if st == "ad":
            import ad_handler
            ad_handler.handle_ad(max_seconds=150)
            continue
        if st == "dialog":
            dismiss_dialog()
            continue
        if st == "event_reward_track":
            d.log("claim: 关闭奖励轨道弹层")
            dismiss_overlay()
            continue
        if st != "event_tasks":
            d.log("claim: 不在任务页（%s），结束" % st)
            break

        img = info["img"]

        # 1) 「完成全部」优先
        claim_all = task_ui.find_claim_all(img)
        if claim_all:
            d.log("claim: 点击「完成全部」@%s" % (claim_all["center"],))
            click(*claim_all["center"], wait=3.2)
            time.sleep(1.2)
            claimed += 1
            no_progress = 0
            continue

        # 2) 逐个「获取」
        buttons = task_ui.find_claim_buttons(img)
        fresh = [b for b in buttons if not recent(*b["center"])]
        if fresh:
            b0 = fresh[0]
            d.log("claim: 点击「获取」@%s" % (b0["center"],))
            click(b0["center"][0], b0["center"][1], wait=2.6)
            clicked_positions.append(b0["center"])
            claimed += 1
            no_progress = 0
            # 处理领取后的弹层/广告
            for _ in range(4):
                i2 = u.detect(keep=False)
                if i2["state"] == "dialog":
                    dismiss_dialog()
                elif i2["state"] == "ad":
                    import ad_handler
                    ad_handler.handle_ad(max_seconds=150)
                elif i2["state"] == "event_reward_track":
                    dismiss_overlay()
                else:
                    break
            time.sleep(0.5)
            continue

        # 3) 没有新按钮：可能这一屏领完了，滚动查找更多任务
        no_progress += 1
        if buttons and no_progress <= 2:
            d.log("claim: 按钮已点过，等待刷新")
            time.sleep(2.5)
            continue

        if scroll_tries < 3:
            scroll_tries += 1
            d.log("claim: 向上滚动查找更多任务 (%d)" % scroll_tries)
            d.swipe(1300, 800, 1300, 800 - move, 400)
            time.sleep(2.0)
            clicked_positions = clicked_positions[-2:]
            no_progress = 0
            continue

        d.log("claim: 没有更多可领取内容")
        break

    d.log("claim: 共领取 %d 次" % claimed)
    return claimed


def nav_to_tasks():
    """从任意界面导航到活动任务页"""
    if not go_home():
        d.log("nav_to_tasks: 无法回到机库")
        return False
    d.log("nav_to_tasks: 进入活动页")
    click(*POS["left_mission"], wait=3.5)
    info = u.detect(save_name="nav_event.png")
    d.log("nav_to_tasks: state=%s" % info["state"])

    if info["state"] == "event_tasks":
        return True
    if info["state"] == "dialog":
        dismiss_dialog()
        info = u.detect(keep=False)
        if info["state"] == "event_tasks":
            return True

    # 在活动页 → 点「任务」
    for attempt in range(2):
        click(*POS["event_tasks_tab"], wait=3.0)
        info = u.detect(save_name="nav_tasks.png")
        d.log("nav_to_tasks: 点击任务后 state=%s" % info["state"])
        if info["state"] == "event_tasks":
            return True
        if info["state"] == "dialog":
            dismiss_dialog()
            info = u.detect(keep=False)
            if info["state"] == "event_tasks":
                return True
        # 重新点一次前面板
        if attempt == 0:
            click(*POS["left_mission"], wait=3.0)
    return u.detect(keep=False)["state"] == "event_tasks"


def nav_to_black_market():
    """
    从机库进入黑市（Black Market），那里有「免费钥匙」激励视频广告。
    实测入口：机库左侧第 3 个图标（礼盒图标，约 (185,600)）
    """
    if not go_home():
        d.log("nav_to_black_market: 无法回到机库")
        return False
    d.log("nav_to_black_market: 打开黑市")
    for pos in (POS.get("left_gift14d", (185, 600)), (185, 730)):
        click(*pos, wait=3.5)
        st = u.detect(keep=False)["state"]
        d.log("nav_to_black_market: 点击 %s 后 state=%s" % (pos, st))
        if st == "black_market":
            return True
        if st in ("dialog", "event_reward_track"):
            dismiss_overlay()
            dismiss_dialog()
    return u.detect(keep=False)["state"] == "black_market"


def nav_to_daily_tasks():
    """
    从机库进入「每日任务」页：右侧对勾按钮 → 顶部「每日」标签。
    该页含多个紫色「新增进度」看广告任务。
    """
    if not go_home():
        d.log("nav_to_daily_tasks: 无法回到机库")
        return False
    d.log("nav_to_daily_tasks: 打开任务页（右侧对勾）")
    click(*POS["daily_entry"], wait=3.5)
    st = u.detect(keep=False)["state"]
    d.log("nav_to_daily_tasks: state=%s" % st)
    if st == "dialog":
        dismiss_dialog()
        st = u.detect(keep=False)["state"]
    if st == "daily_tasks":
        # 可能在其它标签页，切到「每日」
        click(*POS["daily_tab"], wait=3.0)
        return u.detect(keep=False)["state"] == "daily_tasks"
    if st in ("event_reward_track",):
        dismiss_overlay()
        st = u.detect(keep=False)["state"]
        if st == "daily_tasks":
            click(*POS["daily_tab"], wait=3.0)
            return u.detect(keep=False)["state"] == "daily_tasks"
    return False


def nav_to_lottery():
    """
    从机库进入「供给中心」抽奖页：左侧第 2 个怪物图标（带倒计时）。
    实测：(163,459)
    """
    if not go_home():
        d.log("nav_to_lottery: 无法回到机库")
        return False
    d.log("nav_to_lottery: 打开供给中心")
    click(*POS["lottery_entry"], wait=3.8)
    st = u.detect(keep=False)["state"]
    d.log("nav_to_lottery: state=%s" % st)
    # lottery_ready=可抽；冷却时是 menu_other，但页面确实是供给中心
    if st == "lottery_ready":
        return True
    if st == "dialog":
        dismiss_dialog()
        return u.detect(keep=False)["state"] == "lottery_ready"
    # 冷却状态：用标题区颜色确认（供给中心为大标题，深蓝底）
    return st in ("menu_other", "unknown")


def lottery_is_ready():
    """当前供给中心是否可抽（有紫色「获取供给」按钮）"""
    return u.detect(keep=False)["state"] == "lottery_ready"


def read_lottery_cooldown():
    """
    读取供给中心底部冷却倒计时（形如 4分43秒）。
    返回剩余秒数或 None。
    """
    import rating_reader as rr
    img, _ = d.screenshot(save=False)
    if img is None:
        return None
    # 底部文字区
    zone = v.to_gray(img[1000:1075, 900:1500])
    mask = (zone > 170).astype(np.uint8)
    if mask.sum() < 80:
        return None
    try:
        chars = rr.segment_chars(mask, min_w=3)
        templates = rr.load_templates()
        digits = ""
        for (s, e, g) in chars:
            h_, w_ = g.shape
            if h_ < 8:
                continue
            dd, sc = rr.match_digit(g, templates)
            if dd and sc > 0.30:
                digits += str(dd)
        if len(digits) >= 3:
            # 期望 M分SS秒 或 MM:SS，取前若干位拼分钟
            return digits
        return None
    except Exception:
        return None


def watch_daily_task_ads(max_ads=6):
    """
    在「每日任务」页反复点紫色「新增进度」看广告，
    并在任务完成时领取绿色「获取」奖励。
    返回 (观看广告次数, 领取奖励次数)
    """
    import ad_handler
    import task_ui

    watched = 0
    claimed = 0
    empty = 0
    scroll_tries = 0
    start = time.time()

    while watched < max_ads and (time.time() - start) / 60.0 < 20:
        info = u.detect(keep=False)
        st = info["state"]

        if st == "ad":
            ok, secs, acts = ad_handler.handle_ad(max_seconds=150)
            watched += 1
            d.log("每日广告 #%d 完成: ok=%s 用时=%.0fs" % (watched, ok, secs))
            time.sleep(1.5)
            continue
        if st in ("play_store", "foreign_app", "launcher"):
            ad_handler.back_to_game("daily")
            continue
        if st == "dialog":
            dismiss_dialog()
            continue
        if st == "event_reward_track":
            dismiss_overlay()
            continue

        if st != "daily_tasks":
            d.log("watch_daily_task_ads: 不在每日任务页（%s），尝试导航" % st)
            if not nav_to_daily_tasks():
                break
            continue

        img = info["img"]
        # 1) 先领已完成的奖励
        claims = task_ui.find_claim_buttons(img)
        if claims:
            c = claims[0]
            d.log("每日任务: 领取奖励 @%s" % (c["center"],))
            click(c["center"][0], c["center"][1], wait=2.6)
            claimed += 1
            for _ in range(3):
                i2 = u.detect(keep=False)
                if i2["state"] == "dialog":
                    dismiss_dialog()
                elif i2["state"] == "event_reward_track":
                    dismiss_overlay()
                elif i2["state"] == "ad":
                    ad_handler.handle_ad(max_seconds=150)
                else:
                    break
            time.sleep(0.5)
            continue

        # 2) 点紫色「新增进度」看广告
        purples = task_ui.find_watch_video_buttons(img)
        if not purples:
            # 紫色广告任务通常在列表下方，需要滚动查找
            if scroll_tries < 5:
                scroll_tries += 1
                d.log("每日任务: 向下滚动查找广告任务 (%d/5)" % scroll_tries)
                d.swipe(1300, 880, 1300, 460, 450)
                time.sleep(1.8)
                continue
            d.log("每日任务: 已滚动到底，没有可观看的视频任务")
            break

        b = purples[0]
        d.log("每日任务: 点击「新增进度」@%s" % (b["center"],))
        d.tap(b["center"][0], b["center"][1], jitter=2)
        time.sleep(3.5)

        got = False
        for _ in range(10):
            pkg, act = d.top_activity()
            if ad_handler.is_ad_activity(pkg, act) or pkg != d.PKG:
                got = True
                break
            time.sleep(1.0)

        if not got:
            d.log("每日任务: 未触发广告（可能次数已用尽）")
            i3 = u.detect(keep=False)
            if i3["state"] == "dialog":
                dismiss_dialog()
            empty += 1
            if empty >= 2:
                d.log("每日任务: 连续无广告，判定该来源已用尽")
                break
            time.sleep(1.5)
            continue

        ok, secs, acts = ad_handler.handle_ad(max_seconds=150)
        watched += 1
        d.log("每日广告 #%d 完成: ok=%s 用时=%.0fs" % (watched, ok, secs))
        time.sleep(1.5)

    d.log("每日任务流程结束：广告 %d 次，领奖 %d 次" % (watched, claimed))
    return watched, claimed


# ============================================================================
#  外部停止钩子（供 Web UI 等注入）
#  返回 True 表示请求停止。仅在"安全点"（如冷却等待）才会被检查，
#  **战斗中绝不检查**，以免违反 1 分钟规则。
# ============================================================================
STOP_HOOK = None


def stop_requested():
    try:
        return bool(STOP_HOOK and STOP_HOOK())
    except Exception:
        return False


def wait_until_lottery_ready(max_wait=420, step=35, verbose=True):
    """
    轮询等待供给中心重新变为「可抽」状态。

    注意两种"不可抽"的形态（实测）：
      a) 两次抽奖之间：底部「任务距离推出还有：4分53秒」→ 等约 5 分钟即恢复
      b) 今日 3 次用完后：底部「剩余时间：21时31分」→ 要等到次日，不必等
    本函数最多等 max_wait 秒（默认 7 分钟）；仍不可抽即视为已用完。
    返回 True 表示已可抽。
    """
    t0 = time.time()
    rounds = 0
    first_sleep = max(0, max_wait - step * 3)
    if first_sleep > 0:
        if verbose:
            d.log("wait_lottery: 先静候 %.0f 秒（约 %.1f 分钟）..."
                  % (first_sleep, first_sleep / 60.0))
        end = time.time() + first_sleep
        while time.time() < end:
            time.sleep(min(5, end - time.time()))
            if stop_requested():
                d.log("wait_lottery: 收到停止请求，中断冷却等待")
                return False

    while time.time() - t0 < max_wait:
        if stop_requested():
            d.log("wait_lottery: 收到停止请求，结束等待")
            return False
        rounds += 1
        if nav_to_lottery():
            st = u.detect(keep=False)["state"]
            if st == "lottery_ready":
                d.log("wait_lottery: 已恢复可抽（等待 %.0f 秒）" % (time.time() - t0))
                return True
            if verbose:
                d.log("wait_lottery: 第 %d 次复检仍不可抽（state=%s），续等 %ds"
                      % (rounds, st, step))
        time.sleep(step)
    d.log("wait_lottery: 等待 %.0f 秒后仍不可抽 → 判定今日抽奖已用完（下次重置见界面倒计时）"
          % max_wait)
    return False


def run_lottery(max_draws=3, wait_cooldown=True, cooldown_wait=420,
                max_total_minutes=45):
    """
    供给中心抽奖：读一次广告抽一次奖 → 冷却约 5 分钟 → 再抽。
    **每天最多 3 次**（实测），因此默认会等完冷却把 3 次都抽掉。

    参数：
      max_draws         每天最多抽奖次数（默认 3）
      wait_cooldown     冷却时是否原地等待（False 则只抽当前可用次数）
      cooldown_wait     单次冷却最长等待秒数（实测约 4~5 分钟）
      max_total_minutes 整个抽奖流程的时间上限

    返回抽奖成功次数。
    """
    import ad_handler

    d.log("#" * 56)
    d.log("# 供给中心抽奖：目标抽满 %d 次/天" % max_draws)
    d.log("#" * 56)

    drawn = 0
    start = time.time()
    exhausted = False

    if not nav_to_lottery():
        d.log("run_lottery: 无法进入供给中心")
        return 0

    while drawn < max_draws:
        if (time.time() - start) / 60.0 > max_total_minutes:
            d.log("run_lottery: 超过总时长上限 %.0f 分钟，停止" % max_total_minutes)
            break

        st = u.detect(keep=False)["state"]
        d.log("run_lottery: 进度 %d/%d | state=%s" % (drawn, max_draws, st))

        if st == "ad":
            ok, secs, acts = ad_handler.handle_ad(max_seconds=150)
            d.log("run_lottery: 广告处理 ok=%s 用时=%.0fs" % (ok, secs))
            time.sleep(2.0)
            continue
        if st in ("play_store", "foreign_app", "launcher"):
            ad_handler.back_to_game("lottery")
            continue
        if st == "dialog":
            dismiss_dialog()
            continue
        if st == "reward_popup":
            dismiss_reward_popup()
            continue
        if st == "event_reward_track":
            dismiss_overlay()
            continue

        if st == "lottery_ready":
            d.log("run_lottery: >>> 第 %d/%d 次抽奖，点击「获取供给」"
                  % (drawn + 1, max_draws))
            click(*POS["lottery_btn"], wait=3.5)
            got = False
            for _ in range(10):
                pkg, act = d.top_activity()
                if ad_handler.is_ad_activity(pkg, act) or pkg != d.PKG:
                    got = True
                    break
                time.sleep(1.0)
            if got:
                ok, secs, acts = ad_handler.handle_ad(max_seconds=150)
                drawn += 1
                d.log("run_lottery: 第 %d/%d 次抽奖完成（广告 ok=%s 用时=%.0fs）"
                      % (drawn, max_draws, ok, secs))
                time.sleep(2.5)
                for _ in range(4):
                    i2 = u.detect(keep=False)
                    if i2["state"] == "reward_popup":
                        dismiss_reward_popup()
                    elif i2["state"] == "dialog":
                        dismiss_dialog()
                    elif i2["state"] == "event_reward_track":
                        dismiss_overlay()
                    else:
                        break
            else:
                d.log("run_lottery: 未触发广告 → 判定今日抽奖已用尽")
                exhausted = True
                break
            continue

        # 非 ready：冷却中 或 已达今日上限
        if drawn >= max_draws:
            break
        if not wait_cooldown:
            d.log("run_lottery: 冷却中，--no-wait 指定不等待，结束（已抽 %d 次）" % drawn)
            break

        d.log("run_lottery: 冷却中，等待恢复后继续抽第 %d 次" % (drawn + 1))
        if not wait_until_lottery_ready(max_wait=cooldown_wait):
            d.log("run_lottery: 冷却未在期限内结束 → 判定已达今日上限")
            exhausted = True
            break

    d.log("=" * 56)
    d.log("run_lottery: 本次共抽奖 %d/%d 次%s"
          % (drawn, max_draws, "（今日已用完）" if exhausted or drawn < max_draws else ""))
    d.log("=" * 56)
    go_home()
    return drawn


def watch_ads(max_ads=10, max_minutes=20, replenish_battles=0):
    """
    循环触发并安全观看激励视频。广告来源（全部实测可用）：
      1) 活动任务页紫色「新增进度/观看视频」
      2) 黑市「免费钥匙」
      3) 每日任务页紫色「新增进度」（4~5 个/天）
      4) 供给中心抽奖（每天 3 次）
    replenish_battles > 0 时：广告用尽后进战斗补充，最多 N 次。
    """
    import ad_handler
    total = 0
    # 先跑每日任务（数量多，优先级高）
    w1, c1 = watch_daily_task_ads(max_ads=min(max_ads, 6))
    total += w1
    # 再跑活动任务 + 黑市
    if total < max_ads:
        total += ad_handler.watch_video_ads(
            max_ads=max_ads - total,
            max_minutes=max_minutes,
            task_nav=nav_to_tasks,
            go_black_market=nav_to_black_market,
        )
    return total


def upgrade_by_ads(max_ads=12):
    """
    机库顶部「-4时 钟减少」按钮：看一次广告可减少 4 小时升级时间。
    反复看，直到按钮消失（升级完成 / 广告次数用尽）。

    实测：按钮 bbox (1251,160)-(1526,226)，中心 (1388,193)，紫色。
    返回看过广告的次数。
    """
    import ad_handler
    import task_ui

    d.log("#" * 52)
    d.log("# 升级加速：看广告减少 4 小时升级时间（最多 %d 次）" % max_ads)
    d.log("#" * 52)

    if not go_home():
        d.log("upgrade_by_ads: 无法回到机库")
        return 0

    used = 0
    miss = 0
    for i in range(max_ads):
        img, _ = d.screenshot(save=False)
        if img is None:
            time.sleep(2.0)
            continue

        btn = task_ui.find_upgrade_ad_button(img)
        if not btn:
            miss += 1
            d.log("upgrade_by_ads: 第 %d 次未找到「-4时 钟减少」按钮（%d/2）"
                  % (i + 1, miss))
            if miss >= 2:
                d.log("upgrade_by_ads: 按钮已消失 → 升级完成或广告次数已用尽")
                break
            time.sleep(3.0)
            continue

        miss = 0
        d.log("upgrade_by_ads: 点击「-4时 钟减少」@%s（第 %d 次）"
              % (btn["center"], used + 1))
        click(btn["center"][0], btn["center"][1], wait=3.5)

        got = False
        for _ in range(10):
            pkg, act = d.top_activity()
            if ad_handler.is_ad_activity(pkg, act) or pkg != d.PKG:
                got = True
                break
            time.sleep(1.0)

        if not got:
            d.log("upgrade_by_ads: 未触发广告（可能次数已用尽）")
            i2 = u.detect(keep=False)
            if i2["state"] == "dialog":
                dismiss_dialog()
            elif i2["state"] == "reward_popup":
                dismiss_reward_popup()
            break

        ok, secs, acts = ad_handler.handle_ad(max_seconds=150)
        used += 1
        d.log("upgrade_by_ads: 第 %d 次完成（广告 ok=%s 用时=%.0fs），累计减少 %d 小时"
              % (used, ok, secs, used * 4))

        # 处理可能的弹窗，并等界面刷新
        for _ in range(3):
            i3 = u.detect(keep=False)
            if i3["state"] == "reward_popup":
                dismiss_reward_popup()
            elif i3["state"] == "dialog":
                dismiss_dialog()
            elif i3["state"] == "event_reward_track":
                dismiss_overlay()
            else:
                break
        time.sleep(3.0)
        # 若掉出机库，回到机库再继续
        if u.detect(keep=False)["state"] != "hangar":
            go_home()

    d.log("upgrade_by_ads: 共看广告 %d 次（合计减少约 %d 小时）" % (used, used * 4))
    return used


def goal_ads(rounds=8, minutes=25, lottery=False, replenish=0, wait_cooldown=True,
             upgrade=False):
    """
    目标一完整流程：
      1) 领取活动任务 + 每日任务里已完成的奖励
      2) 观看各来源的激励视频（每日任务 / 活动任务 / 黑市）
      3) 可选：供给中心抽奖（每天 3 次，含 5 分钟冷却）
      4) 广告次数用尽时，进战斗补充（每场 +1 次），最多 replenish 场
    返回 (广告次数, 领取奖励次数, 抽奖次数)
    """
    d.log("#" * 64)
    d.log("# 目标一：广告浏览 + 礼包领取%s" % ("  + 供给中心抽奖" if lottery else ""))
    d.log("#" * 64)
    ensure_landscape()
    if not d.is_foreground():
        d.log("启动游戏")
        d.launch(wait=25)
        d.lock_landscape()
        time.sleep(3)

    total_watch = 0
    total_claim = 0
    total_draw = 0

    # ---- 1) 先领现有奖励 ----
    if nav_to_tasks():
        n = claim_task_rewards()
        total_claim += n
        d.log("活动任务领取: %d" % n)
    if nav_to_daily_tasks():
        w, c = watch_daily_task_ads(max_ads=0) if False else (0, 0)
        # 先只领奖励（max_ads=0 会立即返回，这里手动扫一遍）
        claims = 0
        for _ in range(6):
            info = u.detect(keep=False)
            if info["state"] != "daily_tasks":
                break
            import task_ui
            cs = task_ui.find_claim_buttons(info["img"])
            if not cs:
                break
            click(cs[0]["center"][0], cs[0]["center"][1], wait=2.5)
            claims += 1
            dismiss_dialog()
            dismiss_overlay()
        total_claim += claims
        d.log("每日任务领取: %d" % claims)

    # ---- 2) 观看广告（各来源）----
    w = watch_ads(max_ads=rounds, max_minutes=minutes)
    total_watch += w
    d.log("第一轮广告: %d 次" % w)

    # ---- 3) 领广告后解锁的奖励 ----
    for _ in range(2):
        if nav_to_tasks():
            total_claim += claim_task_rewards(max_rounds=6)
        if nav_to_daily_tasks():
            import task_ui
            for _ in range(4):
                info = u.detect(keep=False)
                if info["state"] != "daily_tasks":
                    break
                cs = task_ui.find_claim_buttons(info["img"])
                if not cs:
                    break
                click(cs[0]["center"][0], cs[0]["center"][1], wait=2.5)
                total_claim += 1
                dismiss_dialog()
                dismiss_overlay()

    # ---- 4) 供给中心抽奖 ----
    if lottery:
        total_draw += run_lottery(max_draws=3, wait_cooldown=wait_cooldown)

    # ---- 5) 广告用尽 → 进战斗补充 ----
    if replenish > 0:
        for i in range(replenish):
            d.log("=" * 60)
            d.log("广告次数可能已用尽 → 进入战斗补充（第 %d/%d 场）" % (i + 1, replenish))
            d.log("=" * 60)
            ok = goal_battle()
            if not ok:
                d.log("补充战斗未成功，停止补充")
                break
            # 战斗后重试广告
            w2 = watch_ads(max_ads=2, max_minutes=12)
            total_watch += w2
            d.log("补充战斗后广告: %d 次" % w2)
            if lottery:
                total_draw += run_lottery(max_draws=1, wait_cooldown=False)
            if w2 == 0 and not lottery:
                d.log("补充后仍无广告 → 判定今日广告已用完")
                break

    # ---- 6) 升级加速：看广告减少 4 小时升级时间 ----
    total_upgrade = 0
    if upgrade:
        total_upgrade = upgrade_by_ads(max_ads=12)

    go_home()
    d.log("#" * 64)
    d.log("目标一完成：广告 %d 次，领奖 %d 次，抽奖 %d 次，升级加速 %d 次（-%d 小时）"
          % (total_watch, total_claim, total_draw, total_upgrade, total_upgrade * 4))
    d.log("#" * 64)
    return total_watch, total_claim, total_draw


# ---------------------------------------------------------------- 目标二：参与游戏
def enter_battle(timeout=150):
    """
    从机库进入战斗。
    返回 (ok, prep_at)：
      ok      = 是否成功进入战斗（已上场）
      prep_at = 首次看到"战前部署/阵亡"界面的时间戳（用于安全计时）；
                未见到则为 None
    """
    ensure_landscape()
    if not go_home():
        d.log("enter_battle: 无法回到机库")
        return False, None

    d.log("enter_battle: 点击机库「前往战斗」")
    click(*POS["battle_btn"], wait=4.0)

    info = u.detect(save_name="b_mode.png")
    d.log("enter_battle: state=%s" % info["state"])
    if info["state"] == "dialog":
        dismiss_dialog()
        info = u.detect(keep=False)

    if info["state"] in ("battle_modes", "menu_other"):
        d.log("enter_battle: 点击模式页「前往战斗」")
        click(*POS["mode_battle_btn"], wait=5.0)

    start = time.time()
    prep_at = None
    deployed = False
    deploy_tries = 0

    while time.time() - start < timeout:
        info = u.detect(keep=False)
        st = info["state"]
        elapsed = time.time() - start
        d.log("enter_battle: %3.0fs state=%s" % (elapsed, st))

        if st == "ad":
            import ad_handler
            ad_handler.handle_ad(max_seconds=150)
            continue
        if st == "dialog":
            d.log("enter_battle: 对话框，尝试关闭")
            dismiss_dialog()
            continue
        if st == "battle_result":
            d.log("enter_battle: 上一场已结束，回到机库重新开始")
            click(*POS["result_to_hangar"], wait=4.0)
            time.sleep(1.5)
            click(*POS["battle_btn"], wait=4.0)
            continue

        if st == "battle_prep":
            # 记录首次"进场"时间（部署界面出现即算已加入对局，最保守）
            if prep_at is None:
                prep_at = time.time()
                d.log("enter_battle: 检测到部署界面，开始安全计时")
            # 必须至少上场一台机甲
            if deploy_tries < 6:
                deploy_tries += 1
                d.log("enter_battle: 部署机甲（第 %d 次尝试）" % deploy_tries)
                click(*POS["deploy_robot"], wait=3.0)
                # 若点击后仍是部署界面，换另一台卡片
                i2 = u.detect(keep=False)
                if i2["state"] == "battle_prep" and deploy_tries >= 2:
                    click(900, 700, wait=2.5)   # 第二台
                if i2["state"] == "battle_prep" and deploy_tries >= 4:
                    click(1600, 700, wait=2.5)  # 第三台
                time.sleep(1.5)
            continue

        if st == "battle":
            if prep_at is None:
                prep_at = time.time()
            if not deployed:
                deployed = True
                d.log("enter_battle: 已在战斗中")
            else:
                d.log("enter_battle: 仍在战斗中")
            return True, prep_at

        if elapsed > 25 and st == "hangar":
            d.log("enter_battle: 仍在机库，重试")
            click(*POS["battle_btn"], wait=3.5)
            i2 = u.detect(keep=False)
            if i2["state"] in ("battle_modes", "menu_other"):
                click(*POS["mode_battle_btn"], wait=4.0)
        time.sleep(3.0)

    d.log("enter_battle: 超时未进入战斗")
    return False, prep_at


# ============================================================================
#  关键规则（用户明确要求）：
#   1) 进入战斗后 1 分钟内退出会被判罚（扣战绩/经验分 → 等级下降 → 匹配难度上升）
#      → 必须停留 >= MIN_BATTLE_SECONDS 秒（取 70s 更保险）
#   2) 角色阵亡后不退出也不算违规：可继续观战 / 换机甲上场继续待
#   3) 但"完全不释放机甲、不参加游戏"也不好 → 必须至少上场一台机甲
# ============================================================================
MIN_BATTLE_SECONDS = 70.0     # 1:10，比 1:05 更保险
MIN_DEPLOY_COUNT = 1          # 至少部署 1 台机甲


def random_battle_ops(seconds=60.0, stop_on_end=True):
    """
    战斗中随机操作指定时长：
      移动（左下摇杆拖动）/ 开火（右下）/ 转视角（右侧拖动）/ 偶尔随机点
    不使用任何退出类按钮，保证不会误退出。
    """
    start = time.time()
    ops = []
    check_every = 10.0
    next_check = start + check_every
    while time.time() - start < seconds:
        if seconds - (time.time() - start) < 0.8:
            break
        act = random.choices(
            ["move", "fire", "look", "move", "fire", "tap"],
            weights=[30, 28, 22, 20, 20, 5]
        )[0]

        if act == "move":
            cx, cy = JOYSTICK
            dx = random.randint(-130, 130)
            dy = random.randint(-130, 130)
            d.swipe(cx, cy, cx + dx, cy + dy, random.randint(400, 1000))
        elif act == "fire":
            x1, y1, x2, y2 = FIRE_ZONE
            fx = random.randint(x1, x2)
            fy = random.randint(y1, y2)
            d.tap(fx, fy)
            if random.random() < 0.35:
                d.tap(fx, fy)
        elif act == "look":
            x1, y1, x2, y2 = LOOK_ZONE
            sx = random.randint(x1, x2)
            sy = random.randint(y1, y2)
            d.swipe(sx, sy, sx + random.randint(-350, 350),
                    sy + random.randint(-150, 150), random.randint(200, 500))
        else:
            d.tap(random.randint(700, 1700), random.randint(500, 900))

        ops.append((act, round(time.time() - start, 1)))
        time.sleep(random.uniform(0.25, 0.9))

        if stop_on_end and time.time() >= next_check:
            next_check = time.time() + check_every
            st = u.detect(keep=False)["state"]
            if st != "battle":
                d.log("random_battle_ops: 状态变为 %s，提前结束本段操作" % st)
                break
    return ops


def stay_in_battle(min_seconds=MIN_BATTLE_SECONDS, idle_after_death=True):
    """
    在战斗内"待够" min_seconds 秒，期间可做随机操作。
    绝不在 min_seconds 之前退出。

    状况处理：
      - battle           : 正常战斗，继续随机操作
      - battle_prep      : 阵亡复活/换机甲界面 → 点一台机架上场，或直接等待
      - battle_result    : 战斗已结束（结算页）→ 停留计时仍需满；
                           但结算页说明本局已结算，若未满 min_seconds 则不可退出，
                           所以这里选择等待，不点任何退出按钮。
      - dialog           : 关闭弹窗
      - ad               : 安全处理广告
    返回实际停留秒数。
    """
    start = time.time()
    d.log("stay_in_battle: 开始计时，必须停留 >= %.0f 秒" % min_seconds)
    last_report = 0.0
    ops_count = 0
    deploy_count = 0
    deploy_tries = 0
    deploy_spots = [POS["deploy_robot"], (900, 700), (1600, 700)]

    while True:
        elapsed = time.time() - start
        if elapsed >= min_seconds:
            # 结束前确保至少上场过一台
            if deploy_count < MIN_DEPLOY_COUNT:
                d.log("stay_in_battle: 还未上场过机甲，退出前补一次部署")
                for _ in range(3):
                    i0 = u.detect(keep=False)
                    if i0["state"] == "battle_prep":
                        click(*POS["deploy_robot"], wait=3.0)
                        deploy_count += 1
                    else:
                        break
            d.log("stay_in_battle: 已停留 %.1fs（>= %.0fs），可以退出" % (elapsed, min_seconds))
            break

        st = u.detect(keep=False)["state"]

        # 关键：用"连续 2 次确认"判断是否真的离开了战斗，
        # 避免加载/过场导致的短暂误判引起过早退出（1 分钟规则容错）
        if st in ("hangar", "battle_modes", "menu_other", "event_tasks", "event_pass",
                  "leave_warning", "event_reward_track"):
            confirm = [st]
            for _ in range(2):
                time.sleep(1.5)
                confirm.append(u.detect(keep=False)["state"])
            if any(s in ("battle", "battle_prep") for s in confirm):
                d.log("stay_in_battle: 状态抖动 %s，仍在战斗中，继续" % confirm)
                continue
            st = confirm[-1]

        if st == "battle":
            if deploy_count < MIN_DEPLOY_COUNT:
                deploy_count = max(deploy_count, 1)   # 已在战斗中即视为已上场
            # 正常战斗：随机操作一小段，然后回到循环检查时间
            slice_sec = min(8.0, min_seconds - elapsed)
            ops = random_battle_ops(slice_sec)
            ops_count += len(ops)
            continue

        if st == "battle_prep":
            # 阵亡复活/换机甲：必须换机甲上场（至少一台），
            # 若已有机甲上场则继续换，保持参与感；绝不退出。
            if deploy_tries < 8:
                spot = deploy_spots[min(deploy_tries, len(deploy_spots) - 1)]
                d.log("stay_in_battle: 部署机甲 @%s（第 %d 次，计时 %.0fs）"
                      % (spot, deploy_tries + 1, elapsed))
                click(spot[0], spot[1], wait=3.0)
                deploy_tries += 1
                deploy_count += 1
                i2 = u.detect(keep=False)
                if i2["state"] == "battle":
                    d.log("stay_in_battle: 机甲已上场")
            else:
                d.log("stay_in_battle: 部署尝试次数较多，静观其变（计时 %.0fs）" % elapsed)
                time.sleep(3.0)
            continue

        if st == "battle_result":
            # 本局已结束。剩余时间仍需等待，不可退出。
            remain = min_seconds - elapsed
            d.log("stay_in_battle: 本局已结算，继续等待 %.0fs 以满足 1 分钟规则" % remain)
            # 结算页上不点「前往机库」，只等
            time.sleep(min(5.0, remain))
            continue

        if st == "dialog":
            dismiss_dialog()
            continue

        if st == "leave_warning":
            force_stay_in_battle()
            continue

        if st == "event_reward_track":
            dismiss_overlay()
            continue

        if st == "ad":
            import ad_handler
            ad_handler.handle_ad(max_seconds=150)
            continue

        if st in ("play_store", "foreign_app", "launcher"):
            import ad_handler
            ad_handler.back_to_game("stay_in_battle")
            continue

        if st in ("hangar", "battle_modes", "menu_other"):
            # 掉出战斗了 —— 若还没满 1 分钟，这是最危险的情况。
            remain = min_seconds - elapsed
            d.log("stay_in_battle: 疑似离开战斗，停留 %.0f s（需 %.0f s）" % (elapsed, min_seconds))
            if remain > 0:
                d.log("stay_in_battle: 尝试重新进入战斗以凑满时间")
                if enter_battle(timeout=70)[0]:
                    continue
                d.log("stay_in_battle: 无法重新进场，原地等待 %.0f s" % remain)
                time.sleep(min(5.0, remain))
                continue
            break

        # 其它未知状态：短暂等待后重试进入
        d.log("stay_in_battle: 未知界面(%s)，等待并尝试恢复" % st)
        time.sleep(3.0)
        if elapsed > 8:
            enter_battle(timeout=40)
            continue
        # 进度日志（每 15 秒）
        if elapsed - last_report >= 15:
            last_report = elapsed
            d.log("stay_in_battle: 已停留 %.0f s / %.0f s（累计操作 %d 次）"
                  % (elapsed, min_seconds, ops_count))

    actual = time.time() - start
    d.log("stay_in_battle: 实际停留 %.1fs，操作 %d 次" % (actual, ops_count))
    return actual


def exit_battle():
    """
    退出战斗（仅可在已满足 1 分钟停留后调用）：
      1) 若已在结算页 → 点「前往机库」
      2) 若仍在战斗 → 打开右上设置找「离开战斗」，或退到后台后重启游戏
    返回是否已离开战斗
    """
    d.log("exit_battle: 开始退出流程")
    info = u.detect(keep=False)
    st = info["state"]

    # 已在结算页：直接回机库
    if st == "battle_result":
        d.log("exit_battle: 结算页 → 点击「前往机库」")
        click(*POS["result_to_hangar"], wait=4.5)
        time.sleep(2.0)
        if u.detect(keep=False)["state"] == "hangar":
            d.log("exit_battle: 已回到机库")
            return True

    if st not in ("battle", "battle_prep"):
        d.log("exit_battle: 当前不在战斗中 (state=%s)" % st)
        return True

    # 在战斗中：开设置菜单找离开按钮
    d.tap(*POS["battle_settings"])
    time.sleep(2.5)
    img, _ = d.screenshot("exit_menu")
    if img is not None:
        # 找红色按钮（「离开战斗」通常为红色）
        red = v.find_color_regions(img, (200, 60, 70), tol=55, min_area=8000, max_regions=6)
        red = [r for r in red if r["center"][1] > 300]
        if red:
            d.log("exit_battle: 发现「离开战斗」按钮，点击 @%s" % (red[0]["center"],))
            click_reg(red[0], wait=3.0)
            time.sleep(2.0)
            i2 = u.detect(keep=False)
            if i2["state"] == "dialog":
                d.log("exit_battle: 二次确认")
                greens = find_buttons(i2["img"], "green", min_area=8000)
                if greens:
                    click_reg(greens[0], wait=3.0)
                else:
                    click(*POS["modal_confirm"], wait=3.0)
            if u.detect(keep=False)["state"] in ("hangar", "battle_result"):
                return True

    # 兜底：压后台 + 重启游戏（对局会以掉线结束，但已满足 1 分钟）
    d.log("exit_battle: 兜底方案 —— 退后台并重启游戏")
    d.home()
    time.sleep(2.5)
    d.stop()
    time.sleep(2.0)
    d.launch(wait=22)
    d.lock_landscape()
    time.sleep(2.0)
    d.log("exit_battle: 已重启游戏，当前 state=%s" % u.detect(keep=False)["state"])
    return True


def goal_battle(seconds=60, min_stay=MIN_BATTLE_SECONDS):
    """
    目标二完整流程：
      启动游戏 → 进入战斗 → 在内停留 >= min_stay 秒（随机操作/阵亡后换机甲）→ 退出
    严格遵守 1 分钟规则，绝不提前退出。
    """
    d.log("#" * 60)
    d.log("# 目标二：参与游戏（最少停留 %.0f s，规则要求 >60s）" % min_stay)
    d.log("#" * 60)
    ensure_landscape()
    if not d.is_foreground():
        d.log("启动游戏")
        d.launch(wait=25)
        d.lock_landscape()
        time.sleep(3)

    # 若当前已在战斗中/结算页，先按规则处理，避免误退出
    cur = u.detect(keep=False)["state"]
    d.log("goal_battle: 起始状态 %s" % cur)

    if cur in ("battle", "battle_prep"):
        # 已经在一场对局里：先确保有机甲上场，再从这里开始计时
        d.log("goal_battle: 检测到已在对局中，确保上场机甲后开始计时")
        for _ in range(3):
            i0 = u.detect(keep=False)
            if i0["state"] == "battle_prep":
                d.log("goal_battle: 部署机甲")
                click(*POS["deploy_robot"], wait=3.0)
            else:
                break
        entered_at = time.time()
        stayed = stay_in_battle(min_seconds=min_stay)
        d.log("goal_battle: 停留 %.0f s" % stayed)
        remain = min_stay - (time.time() - entered_at)
        if remain > 0:
            d.log("goal_battle: 双保险等待 %.0f s" % remain)
            time.sleep(remain)
        total = time.time() - entered_at
        d.log("goal_battle: 在战 %.1f s，满足规则，退出" % total)
        exit_battle()
        return True

    if cur == "battle_result":
        d.log("goal_battle: 结算页，先回机库再开新局")
        click(*POS["result_to_hangar"], wait=4.5)
        time.sleep(2.0)

    ok, prep_at = enter_battle()
    if not ok and prep_at is None:
        d.log("goal_battle: 未能进入战斗（未进场则不产生退出判罚）")
        go_home()
        return False

    # 关键：安全计时从"首次看到部署界面"开始（最保守，确保 >= 1 分钟）
    entered_at = prep_at if prep_at is not None else time.time()
    d.log("goal_battle: 已进场，安全计时开始（剩余 %.0f s）"
          % max(0, min_stay - (time.time() - entered_at)))
    stayed = stay_in_battle(min_seconds=max(1.0, min_stay - (time.time() - entered_at)))
    d.log("goal_battle: stay_in_battle 返回 %.1f s" % stayed)

    # 双重保险：即便 stay_in_battle 提前返回，也保证不早于 min_stay 才退出
    remain = min_stay - (time.time() - entered_at)
    if remain > 0:
        d.log("goal_battle: 双保险等待剩余 %.0f s" % remain)
        time.sleep(remain)

    total = time.time() - entered_at
    d.log("goal_battle: 累计进场 %.1f s，满足 1 分钟规则，现在退出" % total)
    exit_battle()
    d.log("目标二完成（在战 %.0f s）" % total)
    return True


# ---------------------------------------------------------------- 荣誉积分
def get_rating(note="", record=True, save=True):
    """
    读取当前荣誉积分（难度分值）并记录历史。
    返回 dict（rating 可能为 None）
    """
    import rating_reader
    res = rating_reader.read_rating_from_hangar() if save else rating_reader.read_rating(save=False)
    r = (res or {}).get("rating")
    if r is not None:
        d.log("荣誉积分: %d  (联赛: %s, 文本: %s)"
              % (r, res.get("league") or res.get("text", ""), res.get("text", "")))
        if record:
            rating_reader.record_rating(r, note=note, extra={
                "text": res.get("text"),
                "bar_frac": res.get("bar_frac"),
            })
    else:
        d.log("荣誉积分读取失败: %s" % (res,))
    return res


def rating_history_report(last_n=20):
    """打印历史趋势"""
    import rating_reader
    trend = rating_reader.check_trend(last_n)
    if not trend:
        d.log("历史样本不足（至少需要 2 条记录）")
        return None
    d.log("=" * 56)
    d.log("荣誉积分历史（最近 %d 条）" % trend["samples"])
    for e in trend["entries"]:
        d.log("  %s  %5d  %s" % (e["ts"], e["rating"], e.get("note", "")))
    d.log("首值=%d  末值=%d  变化=%+d  %s"
          % (trend["first"], trend["last"], trend["delta"],
             "↓ 下降（难度降低）" if trend["decreasing"] else "↑ 上升（难度提高）"))
    d.log("=" * 56)
    return trend


# ---------------------------------------------------------------- CLI
def main():
    ap = argparse.ArgumentParser(description="War Robots 自动化")
    ap.add_argument("action", choices=["ads", "battle", "both", "loop", "state",
                                       "claim", "home", "rating", "history",
                                       "daily", "lottery", "upgrade", "all"])
    ap.add_argument("--rounds", type=int, default=8)
    ap.add_argument("--seconds", type=int, default=60)
    ap.add_argument("--minutes", type=float, default=25)
    ap.add_argument("--cycles", type=int, default=3)
    ap.add_argument("--lottery", action="store_true",
                    help="广告流程里包含供给中心抽奖（每天3次，含5分钟冷却）")
    ap.add_argument("--upgrade", action="store_true",
                    help="广告流程里包含升级加速（每次看广告减少4小时）")
    ap.add_argument("--replenish", type=int, default=0,
                    help="广告用尽后进战斗补充的次数（每场+1次广告）")
    ap.add_argument("--no-wait", action="store_true",
                    help="抽奖冷却时不原地等待")
    ap.add_argument("--draws", type=int, default=3, help="抽奖次数上限")
    ap.add_argument("--max-ads", type=int, default=12, help="升级加速最多看几次广告")
    args = ap.parse_args()

    d.ensure_server()
    dev = d.wait_device(40)
    if not dev:
        print("找不到已授权设备，请插好 USB 并在手机上允许调试")
        return 2
    d.log("设备: %s" % dev["raw"])

    if args.action == "state":
        info = u.detect(save_name="state_now.png")
        print(u.describe(info))
        print("reasons:", info.get("reasons"))
        return 0
    if args.action == "home":
        print("回到机库:", go_home())
        return 0
    if args.action == "claim":
        print("领取次数:", claim_task_rewards() if nav_to_tasks() else 0)
        return 0
    if args.action == "rating":
        res = get_rating(note="手动读取")
        print(res)
        return 0
    if args.action == "history":
        rating_history_report()
        return 0
    if args.action == "daily":
        ok = nav_to_daily_tasks()
        print("进入每日任务页:", ok)
        if ok:
            w, c = watch_daily_task_ads(max_ads=args.rounds)
            print("广告 %d 次，领奖 %d 次" % (w, c))
        return 0
    if args.action == "lottery":
        n = run_lottery(max_draws=args.draws,
                        wait_cooldown=not args.no_wait)
        print("抽奖次数:", n)
        return 0
    if args.action == "upgrade":
        n = upgrade_by_ads(max_ads=args.max_ads)
        print("升级加速广告次数: %d（减少约 %d 小时）" % (n, n * 4))
        return 0

    if args.action == "ads":
        goal_ads(args.rounds, args.minutes, lottery=args.lottery,
                 replenish=args.replenish, wait_cooldown=not args.no_wait,
                 upgrade=args.upgrade or args.action == "all")
    elif args.action == "battle":
        goal_battle(args.seconds)
    elif args.action == "both":
        goal_ads(args.rounds, args.minutes, lottery=args.lottery,
                 replenish=args.replenish, wait_cooldown=not args.no_wait,
                 upgrade=args.upgrade)
        goal_battle(args.seconds)
    elif args.action == "all":
        # 完整日常：领奖 + 广告 + 抽奖 + 升级加速 + 补充战斗
        goal_ads(args.rounds, args.minutes, lottery=True,
                 replenish=args.replenish, wait_cooldown=not args.no_wait,
                 upgrade=True)
    elif args.action == "loop":
        # 每轮开始前记录分值，结束后再记录，便于观察难度变化
        get_rating(note="循环前基线")
        for i in range(args.cycles):
            d.log("=== 循环 %d/%d ===" % (i + 1, args.cycles))
            goal_battle(args.seconds)
            get_rating(note="第 %d 轮后" % (i + 1))
            time.sleep(random.uniform(5, 12))
        rating_history_report()
    d.log("全部完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
