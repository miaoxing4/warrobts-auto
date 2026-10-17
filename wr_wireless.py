# -*- coding: utf-8 -*-
"""
无线 ADB 连接助手

用法：
  python wr_wireless.py                 # 自动发现并连接（手机需已开「无线调试」）
  python wr_wireless.py --ip 192.168.1.9
  python wr_wireless.py --pair 192.168.1.9:41234 123456   # 首次配对（需手机上的配对码）
  python wr_wireless.py --tcpip 5555    # 用 USB 临时开启 5555 端口（需插 USB）
  python wr_wireless.py --status        # 只看当前设备
  python wr_wireless.py --forget        # 清除已保存的串号，回到自动选择

原理说明：
  * Android 11+ 的「无线调试」用 mDNS 广播 `_adb-tls-connect._tcp`，
    端口是随机的（如 39365），重启会变 —— 所以每次都要重新发现。
  * 老办法 `adb tcpip 5555` 端口固定，但**手机重启后失效**，需要再插 USB 执行一次。
  * 本脚本连接成功后会写 .device_serial，后续 engine/webui 自动用它。
"""
import os
import re
import sys
import time
import subprocess
import argparse

PROJ = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJ)
sys.stdout.reconfigure(encoding="utf-8")

import device as d


def sh(*args, timeout=60):
    return d.adb(*args, timeout=timeout)


def show_devices():
    rc, out = sh("devices", "-l")
    print(out.strip() or "(无)")


def mdns_services():
    """返回 [(name, service, ip:port)]"""
    rc, out = sh("mdns", "services", timeout=30)
    found = []
    for line in out.splitlines():
        line = line.strip()
        if not line or line.startswith("List of") or line.startswith("*"):
            continue
        parts = line.split()
        if len(parts) >= 3 and "_adb" in parts[1]:
            found.append((parts[0], parts[1], parts[2]))
    return found


def connected_wireless():
    rc, out = sh("devices")
    ips = []
    for line in out.splitlines():
        line = line.strip()
        if not line or line.startswith("List of"):
            continue
        p = line.split()
        if len(p) >= 2 and p[1] == "device" and ":" in p[0]:
            ips.append(p[0])
    return ips


def do_pair(addr, code):
    print("配对 %s ..." % addr)
    rc, out = sh("pair", addr, code, timeout=60)
    print("  ", out.strip())
    return "Successfully paired" in out or rc == 0


def do_connect(addr):
    print("连接 %s ..." % addr)
    rc, out = sh("connect", addr, timeout=45)
    print("  ", out.strip())
    return "connected to" in out


def enable_tcpip(port=5555):
    print("尝试用 USB 开启 tcpip %d（需插着 USB）..." % port)
    rc, out = sh("tcpip", str(port), timeout=45)
    print("  ", out.strip())
    return rc == 0


def guess_ip_from_usb():
    rc, out = sh("shell",
                 "ip -f inet addr show wlan0 2>/dev/null | grep 'inet '", timeout=30)
    m = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", out or "")
    return m.group(1) if m else None


def main():
    ap = argparse.ArgumentParser(description="无线 ADB 连接助手")
    ap.add_argument("--ip", help="手机 IP（默认用 mDNS 自动发现）")
    ap.add_argument("--port", type=int, default=0,
                    help="端口（tmDNS 发现时自动获取；tcpip 模式默认 5555）")
    ap.add_argument("--pair", nargs=2, metavar=("ADDR", "CODE"),
                    help="首次配对：ADDR 形如 192.168.1.9:41234，CODE 是手机上的 6 位码")
    ap.add_argument("--tcpip", type=int, nargs="?", const=5555, default=None,
                    help="用 USB 开启固定端口（默认 5555），之后可拔掉 USB")
    ap.add_argument("--status", action="store_true", help="只看当前设备")
    ap.add_argument("--forget", action="store_true", help="清除已保存的串号")
    args = ap.parse_args()

    d.ensure_server()

    if args.forget:
        p = os.path.join(PROJ, ".device_serial")
        if os.path.exists(p):
            os.remove(p)
            print("已清除 .device_serial")
        else:
            print("没有保存的串号")
        return 0

    if args.status:
        print("配置的串号:", d.get_serial() or "(自动)")
        show_devices()
        return 0

    if args.pair:
        addr, code = args.pair
        if not do_pair(addr, code):
            print("配对失败：请确认手机上「使用配对码配对设备」显示的地址和 6 位码")
            return 1
        # 配对后还需 connect，端口通常与配对端口不同，先试 mDNS
        time.sleep(1)
        svcs = mdns_services()
        for name, svc, a in svcs:
            if "_adb-tls-connect" in svc:
                do_connect(a)
                break

    if args.tcpip is not None:
        if not enable_tcpip(args.tcpip):
            print("开启失败：请确认 USB 已连接且已授权")
            return 1
        time.sleep(2)
        ip = args.ip or guess_ip_from_usb()
        if not ip:
            print("拿不到手机 IP，请用 --ip 指定")
            return 1
        addr = "%s:%d" % (ip, args.tcpip)
        if not do_connect(addr):
            return 1
        d.set_serial(addr)
        print("\n已保存串号:", addr)
        show_devices()
        return 0

    # ---- 默认：mDNS 自动发现 + 连接 ----
    if args.ip:
        port = args.port or 5555
        if do_connect("%s:%d" % (args.ip, port)):
            d.set_serial("%s:%d" % (args.ip, port))
            show_devices()
            return 0
        return 1

    print("通过 mDNS 发现无线调试设备 ...")
    svcs = mdns_services()
    if not svcs:
        print("未发现。请确认：")
        print("  1) 手机设置 → 开发者选项 → 无线调试 已打开")
        print("  2) 手机和电脑在同一 Wi-Fi 网段")
        print("  3) 或者用 USB 插上后执行: python wr_wireless.py --tcpip 5555")
        return 1

    addr = None
    for name, svc, a in svcs:
        print("  发现 %-28s %-24s %s" % (name, svc, a))
        if "_adb-tls-connect" in svc and addr is None:
            addr = a

    if not addr:
        print("没有可用的 _adb-tls-connect 服务")
        return 1

    if not do_connect(addr):
        print("\n连接失败。若这是第一次连接，需要先配对：")
        print("  手机上：无线调试 → 使用配对码配对设备（会显示 IP:端口 和 6 位码）")
        print("  电脑上：python wr_wireless.py --pair <IP:端口> <6位码>")
        return 1

    d.set_serial(addr)
    print("\n已保存串号:", addr)
    print("提示：该串号含随机端口，手机重启或重开无线调试后会变化，重跑本脚本即可。")
    show_devices()
    return 0


if __name__ == "__main__":
    sys.exit(main())
