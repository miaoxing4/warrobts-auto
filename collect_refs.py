# -*- coding: utf-8 -*-
"""
采集界面样本集：用于 ui_state 回归测试。

会自动在游戏里依次走到各个界面并截图，保存到 captures_ref/。
某些界面（战斗中/结算）无法随时复现，会用"现有截图 + 已知状态"补充。
"""
import os
import sys
import time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import device as d
import ui_state as u
import engine as e

REF = os.path.join(os.path.dirname(os.path.abspath(__file__)), "captures_ref")
os.makedirs(REF, exist_ok=True)

d.ensure_server()
e.ensure_landscape()


def snap(name, expect):
    img, path = d.screenshot(None, save=False)
    if img is None:
        print("  截图失败:", name)
        return None
    from PIL import Image
    import numpy as np
    out = os.path.join(REF, name)
    Image.fromarray(img).save(out)
    # 同时记录当时识别结果
    info = u.detect(img=img)
    print("  %-24s expect=%-13s got=%-13s" % (name, expect, info["state"]))
    return out


print("=== 采集界面样本 ===")

# 1) 机库
if e.go_home():
    snap("ref_hangar.png", "hangar")

    # 2) 活动页（通行证）
    e.click(*e.POS["left_mission"], wait=3.5)
    snap("ref_event_pass.png", "event_pass")

    # 3) 任务页
    e.click(*e.POS["event_tasks_tab"], wait=3.0)
    snap("ref_event_tasks.png", "event_tasks")

    # 回机库
    e.go_home()

    # 4) 战斗模式选择页
    e.click(*e.POS["battle_btn"], wait=4.0)
    snap("ref_battle_modes.png", "battle_modes")

    # 回机库
    e.go_home()

    # 5) 商店页
    e.click(*e.POS["shop_btn"], wait=3.5)
    snap("ref_shop.png", "menu_other")
    e.go_home()

print("\n样本保存目录:", REF)
print("文件:")
for f in sorted(os.listdir(REF)):
    print("  ", f)
