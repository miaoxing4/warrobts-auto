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

# 截图短缓存（供 screenshot 使用；输入动作会清空）
_shot_cache = {"t": 0.0, "arr": None}


def invalidate_shot_cache():
    """任何输入动作后调用，避免用到过期的画面"""
    _shot_cache["arr"] = None
    _shot_cache["t"] = 0.0


# ---------------------------------------------------------------- 设备选择
# 支持 USB 串号（如 16569970）与无线串号（如 192.168.1.9:5555）
# 优先级：环境变量 WR_SERIAL > 文件 .device_serial > 自动挑选
def get_serial():
    s = os.environ.get("WR_SERIAL", "").strip()
    if s:
        return s
    p = os.path.join(PROJ_DIR, ".device_serial")
    if os.path.exists(p):
        try:
            s = open(p, encoding="utf-8").read().strip()
            if s:
                return s
        except Exception:
            pass
    return None


def set_serial(serial, persist=True):
    """设置要使用的设备串号（persist=True 时写入 .device_serial 供后续进程使用）"""
    global _serial
    _serial = serial
    if persist:
        try:
            with open(os.path.join(PROJ_DIR, ".device_serial"), "w",
                      encoding="utf-8") as f:
                f.write(serial + "\n")
        except Exception:
            pass


_serial = None


def current_serial():
    global _serial
    if _serial:
        return _serial
    return get_serial()


def ensure_dirs():
    os.makedirs(CAPTURE_DIR, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)


def _adb_env():
    """
    给 adb 子进程准备环境变量。

    踩坑记录：Windows 下 adb 守护进程会尝试写 %TEMP%\\adb.log，
    若该文件/目录权限异常，会报
        "cannot open ...\\adb.log: Permission denied"
        "could not read ok from ADB Server" → 整个 adb 不可用。
    因此强制把 TMP/TEMP 指到项目内可写目录。
    """
    env = os.environ.copy()
    tmpdir = os.path.join(PROJ_DIR, ".tmp")
    try:
        os.makedirs(tmpdir, exist_ok=True)
        env["TMP"] = tmpdir
        env["TEMP"] = tmpdir
    except Exception:
        pass
    return env


# 这些是 adb 的「主机级」命令，不能带 -s 串号
_HOST_CMDS = ("devices", "connect", "disconnect", "pair", "mdns",
              "start-server", "kill-server", "version", "keygen",
              "reconnect", "root", "unroot", "wait-for-device")

_HEALING = {"busy": False}

_OFFLINE_HINTS = ("device not found", "no devices", "device offline",
                  "not found", "closed", "connection reset",
                  "cannot connect", "protocol fault")


def _looks_offline(rc, out, binary):
    if rc == 0:
        return False
    if binary:
        # 二进制模式下拿不到文本，靠返回码 + 输出长度判断
        return True
    low = (out or "").lower()
    return any(h in low for h in _OFFLINE_HINTS)


def adb(*args, timeout=60, binary=False, use_serial=True):
    """
    执行 adb 命令。

    带**自愈**：如果报"设备不在/离线"，会自动重新发现设备（无线端口是随机的，
    长时间运行的进程里串号会失效）并重试一次。
    """
    def _run():
        cmd = [ADB]
        ser = current_serial()
        if use_serial and ser and args and args[0] not in _HOST_CMDS:
            cmd += ["-s", ser]
        cmd += list(args)
        try:
            p = subprocess.run(cmd, capture_output=True, timeout=timeout,
                               env=_adb_env())
            if binary:
                return p.returncode, p.stdout
            return p.returncode, (p.stdout.decode("utf-8", errors="replace")
                                  + p.stderr.decode("utf-8", errors="replace"))
        except subprocess.TimeoutExpired:
            return -1, ("TIMEOUT" if not binary else b"")
        except FileNotFoundError:
            return -2, ("ADB_NOT_FOUND: " + ADB if not binary else b"")

    rc, out = _run()
    if (not _HEALING["busy"] and args and args[0] not in _HOST_CMDS
            and _looks_offline(rc, out, binary)):
        _HEALING["busy"] = True
        try:
            new = resolve_serial(auto_wireless=True)
            if new or current_serial() != get_serial():
                pass
        finally:
            _HEALING["busy"] = False
        rc2, out2 = _run()
        return rc2, out2
    return rc, out


def shell(cmd, timeout=60):
    return adb("shell", cmd, timeout=timeout)


def ensure_server():
    adb("start-server", timeout=30)
    resolve_serial()


def _alive_devices():
    rc, out = adb("devices", "-l", timeout=30)
    alive = []
    for line in out.splitlines():
        line = line.strip()
        if not line or line.startswith("List of") or line.startswith("*"):
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            alive.append(parts[0])
    return alive


def wireless_reconnect(timeout=30, verbose=True):
    """
    通过 mDNS 重新发现并连接无线设备。

    踩坑：无线调试的端口是**随机**的（实测 39365 → 40359 变过），
    手机重开无线调试/重启后旧串号必然失效；
    而且 adb 守护进程刚启动时 mDNS 需要几秒才能发现服务。
    所以这里做**轮询重试**。
    返回新串号或 None。
    """
    t0 = time.time()
    while time.time() - t0 < timeout:
        rc, out = adb("mdns", "services", timeout=20)
        for line in out.splitlines():
            if "_adb-tls-connect" not in line:
                continue
            addr = line.split()[-1]
            if verbose:
                print("[device] 发现无线设备 %s，尝试连接..." % addr)
            adb("connect", addr, timeout=25)
            time.sleep(1.2)
            if addr in _alive_devices():
                set_serial(addr, persist=True)
                if verbose:
                    print("[device] 无线已连接并保存串号: %s" % addr)
                return addr
        time.sleep(3)
    if verbose:
        print("[device] %d 秒内没发现无线设备。"
              "请确认手机「无线调试」开着、和电脑同一 Wi-Fi；"
              "或用 USB 插一次执行 wireless.bat tcpip" % timeout)
    return None


def resolve_serial(auto_wireless=True):
    """
    校验当前配置的串号是否真的在线，必要时自动修复。

    * 配置的串号在线                  → 保持不变
    * 配置的是无线串号且不在线        → **自动用 mDNS 重新发现并重连**
    * 配置的串号不在线、只有 1 台在线 → 自动改用那一台
    * 没有配置                        → 单设备时自动选中；否则尝试无线重连
    返回最终使用的串号（或 None 表示不指定）。
    """
    global _serial
    want = current_serial()
    alive = _alive_devices()

    if want and want in alive:
        return want

    # 无线串号失效 → 自动重连（端口会变）
    if auto_wireless and (want is None or ":" in (want or "")):
        if not alive:
            new = wireless_reconnect(timeout=20)
            if new:
                return new
            if want:
                return want      # 保留旧串号，等设备恢复
            return None

    if want and want not in alive:
        if len(alive) == 1:
            print("[device] 配置的串号 %s 不在线，自动改用 %s" % (want, alive[0]))
            set_serial(alive[0], persist=True)
            return alive[0]
        print("[device] 配置的串号 %s 不在线，改为自动选择" % want)
        set_serial("", persist=False)
        _serial = None
        return None

    if len(alive) == 1:
        return alive[0]
    if not alive and auto_wireless:
        new = wireless_reconnect(timeout=15)
        if new:
            return new
    return None


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


def screenshot(name=None, save=True, use_cache=True):
    """
    截图，返回 (RGB numpy 数组 或 None, 保存路径 或 None)。

    实现要点（实测优化）：
      * 优先用 **raw** 方式（`screencap` 不加 -p）：
        USB   : PNG 约 1.0s / RAW 约 0.7s
        无线  : PNG 2.84s / RAW **2.07s**（快 27%）
        原因：设备端 PNG 编码很慢（1.08s），而带宽充裕（12MB/s）。
        RAW 只要 10MB 传输，省掉编码时间。
      * raw 头部 16 字节：w, h, format, colorspace（小端 uint32），后面是 RGBA
      * RAW 失败则回退 PNG
      * 可选短缓存（环境变量 WR_SHOT_TTL，秒）：减少高频 detect 造成的截图风暴
        缓存会在任何输入动作（tap/swipe/back 等）后被 invalidate
    """
    import numpy as np
    from PIL import Image
    import io
    import struct

    ensure_dirs()
    now = time.time()
    try:
        ttl = float(os.environ.get("WR_SHOT_TTL", "0"))
    except Exception:
        ttl = 0.0

    if use_cache and ttl > 0 and _shot_cache["arr"] is not None:
        if (now - _shot_cache["t"]) <= ttl:
            arr = _shot_cache["arr"]
            path = _save_shot(arr, name) if save else None
            return arr, path

    arr = None
    # ---- 首选 RAW ----
    rc, data = adb("exec-out", "screencap", binary=True, timeout=120)
    if rc == 0 and data and len(data) > 16:
        try:
            w, h, _fmt, _cs = struct.unpack("<IIII", data[:16])
            if 100 <= w <= 10000 and 100 <= h <= 10000:
                px = np.frombuffer(data[16:], dtype=np.uint8)
                if px.size >= w * h * 4:
                    arr = px[:w * h * 4].reshape(h, w, 4)[:, :, :3]
        except Exception:
            arr = None

    # ---- 回退 PNG ----
    if arr is None:
        rc, data = adb("exec-out", "screencap -p", binary=True, timeout=120)
        if rc == 0 and data and len(data) > 1000:
            if not data[:8] == b"\x89PNG\r\n\x1a\n":
                data = data.replace(b"\x0d\x0a", b"\x0a")
            try:
                arr = np.array(Image.open(io.BytesIO(data)).convert("RGB"))
            except Exception:
                arr = None

    if arr is None:
        return None, None

    _shot_cache["arr"] = arr
    _shot_cache["t"] = now
    path = _save_shot(arr, name) if save else None
    return arr, path


def _save_shot(arr, name):
    from PIL import Image
    if name is None:
        name = time.strftime("shot_%H%M%S")
    if not name.lower().endswith(".png"):
        name += ".png"
    path = os.path.join(CAPTURE_DIR, name)
    try:
        Image.fromarray(arr).save(path)
    except Exception:
        return None
    return path


def tap(x, y, jitter=0):
    """点击逻辑坐标"""
    import random
    if jitter:
        x += random.randint(-jitter, jitter)
        y += random.randint(-jitter, jitter)
    shell("input tap %d %d" % (int(x), int(y)))
    invalidate_shot_cache()


def long_press(x, y, dur=1200):
    shell("input swipe %d %d %d %d %d" % (int(x), int(y), int(x), int(y), dur))
    invalidate_shot_cache()


def swipe(x1, y1, x2, y2, dur=300):
    shell("input swipe %d %d %d %d %d" % (int(x1), int(y1), int(x2), int(y2), dur))
    invalidate_shot_cache()


def keyevent(code):
    shell("input keyevent %d" % code)
    invalidate_shot_cache()


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
