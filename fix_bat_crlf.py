# -*- coding: utf-8 -*-
"""把所有 .bat 转成 CRLF 换行（Windows 批处理必须 CRLF，否则 goto/标签会出错）"""
import os
import sys

PROJ = os.path.dirname(os.path.abspath(__file__))
sys.stdout.reconfigure(encoding="utf-8")

count = 0
for f in sorted(os.listdir(PROJ)):
    if not f.lower().endswith(".bat"):
        continue
    p = os.path.join(PROJ, f)
    raw = open(p, "rb").read()
    if b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b""):
        print("  已是 CRLF:", f)
        continue
    text = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    text = text.replace(b"\n", b"\r\n")
    open(p, "wb").write(text)
    count += 1
    print("  已转 CRLF:", f)

print("共转换 %d 个文件" % count)
