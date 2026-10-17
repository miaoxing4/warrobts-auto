# -*- coding: utf-8 -*-
"""
War Robots 自动化 - 设备封装与基础操作
"""
import os
import sys
import time
import re
import subprocess

PROJ_DIR = os.path.dirname(os.path.abspath(__file__))
TOOLS_DIR = os.path.join(PROJ_DIR, "tools", "platform-tools")
ADB = os.path.join(TOOLS_DIR, "adb.exe")
CAPTURE_DIR = os.path.join(PROJ_DIR, "captures")
LOG_DIR = os.path.join(PROJ_DIR, "logs")

PKG = "com.pixonic.wwr"
ACTIVITY = "com.unity3d.player.UnityPlayerActivity"

# 逻辑/截图分辨率（横屏）
SW, SH = 2400, 1080


def ensure_dirs():
    os.makedirs(CAPTURE_DIR, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)


def adb(*args, timeout=60, binary=False):
    cmd = [ADB] + list(args)
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=timeout)
        if binary:
            return p.returncode, p.stdout
        return p.returncode, p.stdout.decode("utf-8", errors="replace") + \
            p.stderr.decode("utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return -1, "TIMEOUT"
    except FileNotFoundError:
        return -2, "ADB_NOT_FOUND: " + ADB


def shell(cmd, timeout=60):
    return adb("shell", cmd, timeout=timeout)


def ensure_server():
    adb("start-server", timeout=30)


def devices():
    rc, out = adb("devices", "-l")
    devs = []
    for line in out.splitlines():
        line = line.strip()
        if not line or line.startswith("List of devices") or line.startswith("*"):
            continue
        parts = line.split()
        if len(parts) >= 2:
            devs.append({"serial": parts[0], "state": parts[1], "raw": line})
    return devs


def wait_device(timeout=40):
    end = time.time() + timeout
    while time.time() < end:
        for d in devices():
            if d["state"] == "device":
                return d
        time.sleep(1)
    return None


def get_prop(name):
    return shell("getprop %s" % name)[1].strip()


def is_installed(pkg=PKG):
    return ("package:" + pkg) in shell("pm list packages %s" % pkg)[1]


def launch(wait=0, pkg=PKG, activity=ACTIVITY):
    rc, out = shell("am start -n %s/%s" % (pkg, activity))
    ok = "Error" not in out
    if wait:
        time.sleep(wait)
    return ok, out.strip()


def stop(pkg=PKG):
    return shell("am force-stop %s" % pkg)


def top_activity():
    """返回 (package, activity)"""
    out = shell("dumpsys activity activities")[1]
    for line in out.splitlines():
        if "ResumedActivity" in line:
            m = re.search(r"([\w\.]+)/([\w\.\$]+)", line)
            if m:
                return m.group(1), m.group(2)
    return None, None


def is_foreground(pkg=PKG):
    p, _ = top_activity()
    return p == pkg


def screenshot(name=None, save=True):
    """
    截图，返回 (灰度无关的 RGB numpy 数组 或 None)。
    同时保存到 captures/ 便于排查。
    """
    import numpy as np
    from PIL import Image
    import io
    ensure_dirs()
    rc, data = adb("exec-out", "screencap -p", binary=True, timeout=90)
    if rc != 0 or not data or len(data) < 1000:
        return None, None
    if not data[:8] == b"\x89PNG\r\n\x1a\n":
        data = data.replace(b"\x0d\x0a", b"\x0a")
    try:
        im = Image.open(io.BytesIO(data)).convert("RGB")
    except Exception:
        return None, None
    arr = np.array(im)
    path = None
    if save:
        if name is None:
            name = time.strftime("shot_%H%M%S")
        if not name.lower().endswith(".png"):
            name += ".png"
        path = os.path.join(CAPTURE_DIR, name)
        im.save(path)
    return arr, path


def tap(x, y, jitter=0):
    """点击逻辑坐标"""
    import random
    if jitter:
        x += random.randint(-jitter, jitter)
        y += random.randint(-jitter, jitter)
    shell("input tap %d %d" % (int(x), int(y)))


def long_press(x, y, dur=1200):
    shell("input swipe %d %d %d %d %d" % (int(x), int(y), int(x), int(y), dur))


def swipe(x1, y1, x2, y2, dur=300):
    shell("input swipe %d %d %d %d %d" % (int(x1), int(y1), int(x2), int(y2), dur))


def keyevent(code):
    shell("input keyevent %d" % code)


def back():
    keyevent(4)


def home():
    keyevent(3)


def screen_on():
    out = shell("dumpsys power")[1]
    return "mWakefulness=Awake" in out


def wake():
    if not screen_on():
        keyevent(26)
        time.sleep(0.5)


def unlock():
    """尽力解锁并回到游戏"""
    wake()
    shell("input keyevent 82")  # MENU
    time.sleep(0.3)
    swipe(SW // 2, 800, SW // 2, 300, 250)
    time.sleep(0.5)


def rotation():
    out = shell("dumpsys window displays")[1]
    m = re.search(r"mCurrentRotation=ROTATION_(\d+)", out)
    return int(m.group(1)) if m else None


def lock_landscape():
    shell("settings put system accelerometer_rotation 0")
    shell("settings put system user_rotation 1")
    time.sleep(0.8)


def restore_rotation():
    shell("settings put system accelerometer_rotation 1")
    shell("settings put system user_rotation 0")


def log(msg, file="run.log"):
    ensure_dirs()
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    try:
        with open(os.path.join(LOG_DIR, file), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


if __name__ == "__main__":
    ensure_server()
    print("devices:", devices())
    print("activity:", top_activity())
    print("installed:", is_installed())
    print("rotation:", rotation())
