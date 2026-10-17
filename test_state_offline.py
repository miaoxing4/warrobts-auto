# -*- coding: utf-8 -*-
"""
界面状态识别回归测试

依赖 captures/ 下的真实游戏截图作为基准样本。
如需扩充样本，用 collect_refs.py 在游戏空闲时依次走各界面自动采集。
（不要在正在对局时运行采集脚本）
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vision as v
import ui_state as u

PROJ = os.path.dirname(os.path.abspath(__file__))
CAP = os.path.join(PROJ, "captures")
FIX = os.path.join(PROJ, "tests", "fixtures")


def find_sample(fname):
    """
    按优先级查找样本：
      1) tests/fixtures/<stem>.jpg   （仓库内，体积小，git 跟踪）
      2) tests/fixtures/<stem>.png
      3) captures/<fname>             （本地原始 PNG）
    返回路径或 None
    """
    stem = os.path.splitext(fname)[0]
    for cand in (os.path.join(FIX, stem + ".jpg"),
                 os.path.join(FIX, stem + ".png"),
                 os.path.join(CAP, fname)):
        if os.path.exists(cand):
            return cand
    return None

# 基准样本：文件名 -> 期望状态
CASES = [
    ("01_launch.png",         "hangar"),
    ("scan_hangar.png",       "hangar"),
    ("98_deploy_1.png",       "battle"),
    ("C1_result.png",         "battle_result"),
    ("62_event_tasks2.png",   "event_tasks"),
    ("M1_tasks.png",          "event_tasks"),
    ("T7_daily_scrolled.png", "daily_tasks"),
    ("T5_daily.png",          "daily_tasks"),
    ("T2_lottery.png",        "lottery_ready"),
    ("V3_daily_done.png",     "reward_popup"),
    ("P1_check.png",          "black_market"),
    ("scan_left_mission.png", "event_pass"),
    ("N1_check.png",          "menu_other"),
    ("LEAVE_WARNING.png",     "leave_warning"),
    # 暗色雨雾地图的部署界面：旧判据 warm>0.12 会漏判成 menu_other，
    # 导致 enter_battle 停在部署界面空转（用户实测反馈）
    ("prep_dark_map.jpg",     "battle_prep"),
    # 特惠页：左侧白色分栏占比 0.19~0.21（其它界面 <=0.10）
    ("deals_ad_page.jpg",     "deals"),
    ("deals_paid_page.jpg",   "deals"),
]

# 可选扩展样本（存在则一起测）
# 注意：广告界面靠 Activity 判定，离线截图无法还原 Activity，故不放样本
EXTRA = [
    ("scan_left_event2.png", "lottery_ready"),   # 实为供给中心（可抽状态）
    ("Q1_before_ad.png",     "hangar"),
    ("T6_daily_tab.png",     "daily_tasks"),
]

u.d.top_activity = lambda: ("com.pixonic.wwr", "com.unity3d.player.UnityPlayerActivity")


def run(cases, label):
    ok = 0
    tested = 0
    fails = []
    for fname, expect in cases:
        p = find_sample(fname)
        if not p:
            continue
        tested += 1
        info = u.detect(img=v.load(p))
        got = info["state"]
        good = got == expect
        ok += good
        print("%s %-24s expect=%-14s got=%-15s %s" % (
            "OK  " if good else "MISS", fname, expect, got, info.get("reasons")))
        if not good:
            fails.append((fname, expect, got))
    print("[%s] 准确率: %d/%d" % (label, ok, tested))
    return ok, tested, fails


# ---- 付费页安全护栏（关键：误点会拉起 Google Play 真钱支付）----
def check_paid_guard():
    import task_ui
    expect = [("deals_ad_page.jpg", False), ("deals_paid_page.jpg", True)]
    ok = n = 0
    for fname, want in expect:
        p2 = find_sample(fname)
        if not p2:
            continue
        n += 1
        got = task_ui.deal_page_is_paid(v.load(p2))
        good = got == want
        ok += good
        print("%s %-22s 付费页=%-5s 期望 %s" % (
            "OK  " if good else "MISS", fname, got, want))
    print("[付费页安全护栏] 准确率: %d/%d" % (ok, n))
    return ok, n


print("=" * 74)
print("界面状态识别回归测试")
print("=" * 74)
ok1, n1, f1 = run(CASES, "基准样本")
print("-" * 74)
ok2, n2, f2 = run(EXTRA, "扩展样本")
print("-" * 74)
ok3, n3 = check_paid_guard()
print("=" * 74)
print("合计: %d/%d" % (ok1 + ok2 + ok3, n1 + n2 + n3))
if f1 or f2:
    print("失败用例:")
    for f in (f1 + f2):
        print("   ", f)
    sys.exit(1)
print("全部通过")
