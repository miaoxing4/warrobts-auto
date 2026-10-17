# -*- coding: utf-8 -*-
"""
把体积大的测试样本压缩成 JPEG，放入 tests/fixtures/，
以便仓库体积可控（PNG 单张 2~3MB → JPEG 约 200~400KB）。

同时把 .agent/screenshots 里的说明截图也转成 JPEG。

用法：python prepare_fixtures.py
"""
import os
import sys
import shutil

PROJ = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJ)

from PIL import Image

CAP = os.path.join(PROJ, "captures")
FIX = os.path.join(PROJ, "tests", "fixtures")
AGENT_SHOTS = os.path.join(PROJ, ".agent", "screenshots")

# 回归测试用到的样本（与 test_state_offline.py 保持一致）
NEEDED = [
    "01_launch.png", "scan_hangar.png", "T1_hangar.png", "98_deploy_1.png",
    "C1_result.png", "62_event_tasks2.png", "M1_tasks.png",
    "T7_daily_scrolled.png", "T5_daily.png", "T6_daily_tab.png",
    "T2_lottery.png", "V3_daily_done.png", "P1_check.png",
    "scan_left_mission.png", "N1_check.png", "LEAVE_WARNING.png",
    "scan_left_event2.png", "Q1_before_ad.png",
    # 数字模板校验用
    "rating_verify_1848.png", "rating_verify_1768.png", "G5_league.png",
]


def convert(src, dst_dir, quality=86, max_w=None):
    os.makedirs(dst_dir, exist_ok=True)
    im = Image.open(src).convert("RGB")
    if max_w and im.width > max_w:
        ratio = max_w / im.width
        im = im.resize((max_w, int(im.height * ratio)), Image.LANCZOS)
    base = os.path.splitext(os.path.basename(src))[0]
    out = os.path.join(dst_dir, base + ".jpg")
    im.save(out, "JPEG", quality=quality, optimize=True)
    return out, os.path.getsize(out)


def main():
    print("=" * 60)
    print("1) 转换回归测试样本 -> tests/fixtures/")
    total = 0
    n = 0
    for f in NEEDED:
        src = os.path.join(CAP, f)
        if not os.path.exists(src):
            print("   跳过（不存在）:", f)
            continue
        out, size = convert(src, FIX, quality=86)
        total += size
        n += 1
        print("   %-26s -> %-40s %6.0f KB" % (f, os.path.basename(out), size / 1024))
    print("   共 %d 个，合计 %.1f MB" % (n, total / 1024 / 1024))

    print("=" * 60)
    print("2) 转换 .agent/screenshots -> JPEG（宽度限 1600）")
    if os.path.isdir(AGENT_SHOTS):
        tot2 = 0
        for f in sorted(os.listdir(AGENT_SHOTS)):
            if not f.lower().endswith(".png"):
                continue
            src = os.path.join(AGENT_SHOTS, f)
            before = os.path.getsize(src)
            out, size = convert(src, AGENT_SHOTS, quality=82, max_w=1600)
            os.remove(src)
            tot2 += size
            print("   %-42s %5.0f KB -> %5.0f KB" % (f, before / 1024, size / 1024))
        print("   合计 %.1f MB" % (tot2 / 1024 / 1024))


if __name__ == "__main__":
    main()
