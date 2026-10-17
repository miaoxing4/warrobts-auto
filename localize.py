# -*- coding: utf-8 -*-
"""
坐标精确定标工具
在图像的可疑区域内扫描，输出颜色分块边界，用于确定按钮真实位置
"""
import sys, os
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vision as v


def scan_rows(img, x1, x2, y1, y2, label=""):
    """在竖直条带内按行扫描平均颜色，找出颜色变化边界"""
    print("=== 扫描竖条 %s  x=[%d,%d] y=[%d,%d] ===" % (label, x1, x2, y1, y2))
    prev = None
    seg_start = y1
    for y in range(y1, y2, 4):
        row = img[y, x1:x2].reshape(-1, 3).mean(axis=0)
        cur = tuple(int(c) for c in row)
        if prev is None:
            prev = cur
            seg_start = y
            continue
        dist = sum(abs(cur[i] - prev[i]) for i in range(3))
        if dist > 45:
            print("  y=%4d -> %4d  color %s -> %s" % (seg_start, y, prev, cur))
            seg_start = y
            prev = cur
    print("  y=%4d -> %4d  color %s (end)" % (seg_start, y2, prev))


def scan_cols(img, y1, y2, x1, x2, label=""):
    print("=== 扫描横条 %s  y=[%d,%d] x=[%d,%d] ===" % (label, y1, y2, x1, x2))
    prev = None
    seg_start = x1
    for x in range(x1, x2, 4):
        col = img[y1:y2, x].reshape(-1, 3).mean(axis=0)
        cur = tuple(int(c) for c in col)
        if prev is None:
            prev = cur
            seg_start = x
            continue
        dist = sum(abs(cur[i] - prev[i]) for i in range(3))
        if dist > 45:
            print("  x=%4d -> %4d  color %s -> %s" % (seg_start, x, prev, cur))
            seg_start = x
            prev = cur
    print("  x=%4d -> %4d  color %s (end)" % (seg_start, x2, prev))


if __name__ == "__main__":
    p = sys.argv[1]
    img = v.load(p)
    print("image:", img.shape)
    # 右侧竖排标签区
    scan_rows(img, 2180, 2330, 180, 450, "右侧标签区")
    # 底部按钮
    scan_rows(img, 1150, 1350, 980, 1075, "底部中央按钮")
    # 左下后退
    scan_rows(img, 100, 220, 960, 1060, "左下后退")
