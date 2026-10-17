# -*- coding: utf-8 -*-
"""
视觉工具（numpy + PIL 实现，不依赖 opencv）
 - 颜色区域检测（找到按钮等色块）
 - 模板匹配（多尺度归一化相关）
 - 图像统计/差异比较（用于判断界面是否变化）
"""
import os
import sys
import numpy as np
from PIL import Image

PROJ_DIR = os.path.dirname(os.path.abspath(__file__))


def load(path):
    """加载图像为 RGB numpy 数组 (H, W, 3)"""
    return np.array(Image.open(path).convert("RGB"))


def find_color_regions(img, target_rgb, tol=25, min_area=1500, max_regions=10):
    """
    查找与目标颜色相近的连通区域（快速：先掩码，再用简单的行列聚合）
    返回 [{'bbox': (x1,y1,x2,y2), 'center': (cx,cy), 'area': n, 'color': (r,g,b)}]
    """
    if isinstance(img, str):
        img = load(img)
    r, g, b = int(target_rgb[0]), int(target_rgb[1]), int(target_rgb[2])
    mask = (np.abs(img[:, :, 0].astype(np.int16) - r) <= tol) & \
           (np.abs(img[:, :, 1].astype(np.int16) - g) <= tol) & \
           (np.abs(img[:, :, 2].astype(np.int16) - b) <= tol)

    regions = []
    visited = np.zeros(mask.shape, dtype=bool)
    ys, xs = np.where(mask)
    if len(ys) == 0:
        return []
    H, W = mask.shape

    # 用扫描线 + 并查集太慢；改用行段聚合
    for y0 in range(0, H, 4):
        row = mask[y0]
        if not row.any():
            continue
        # 找连续段
        idx = np.where(row)[0]
        if len(idx) == 0:
            continue
        splits = np.where(np.diff(idx) > 1)[0]
        starts = np.concatenate(([idx[0]], idx[splits + 1]))
        ends = np.concatenate((idx[splits], [idx[-1]]))
        for s, e in zip(starts, ends):
            if e - s < 40:
                continue
            regions.append((s, y0, e, y0))

    if not regions:
        return []

    # 合并重叠区域
    merged = []
    for r_ in regions:
        x1, y1, x2, y2 = r_
        hit = False
        for i, m in enumerate(merged):
            mx1, my1, mx2, my2 = m
            if not (x2 < mx1 - 10 or x1 > mx2 + 10 or y2 < my1 - 10 or y1 > my2 + 10):
                merged[i] = (min(x1, mx1), min(y1, my1), max(x2, mx2), max(y2, my2))
                hit = True
                break
        if not hit:
            merged.append(r_)

    # 迭代收敛
    changed = True
    while changed:
        changed = False
        out = []
        for r_ in merged:
            x1, y1, x2, y2 = r_
            hit = False
            for i, m in enumerate(out):
                mx1, my1, mx2, my2 = m
                if not (x2 < mx1 - 10 or x1 > mx2 + 10 or y2 < my1 - 10 or y1 > my2 + 10):
                    out[i] = (min(x1, mx1), min(y1, my1), max(x2, mx2), max(y2, my2))
                    hit = True
                    changed = True
                    break
            if not hit:
                out.append(r_)
        merged = out

    res = []
    for (x1, y1, x2, y2) in merged:
        area = (x2 - x1 + 1) * (y2 - y1 + 1)
        if area < min_area:
            continue
        res.append({
            "bbox": (int(x1), int(y1), int(x2), int(y2)),
            "center": (int((x1 + x2) / 2), int((y1 + y2) / 2)),
            "size": (int(x2 - x1 + 1), int(y2 - y1 + 1)),
            "area": int(area),
        })
    res.sort(key=lambda d: -d["area"])
    return res[:max_regions]


def region_mean_color(img, bbox):
    if isinstance(img, str):
        img = load(img)
    x1, y1, x2, y2 = bbox
    patch = img[y1:y2, x1:x2]
    if patch.size == 0:
        return None
    return tuple(int(v) for v in patch.reshape(-1, 3).mean(axis=0))


def diff_score(img1, img2):
    """两张同尺寸图像的差异比例 (0~1)"""
    if isinstance(img1, str):
        img1 = load(img1)
    if isinstance(img2, str):
        img2 = load(img2)
    if img1.shape != img2.shape:
        return 1.0
    a = img1.astype(np.int16)
    b = img2.astype(np.int16)
    d = np.abs(a - b).sum(axis=2)
    return float((d > 40).mean())


def to_gray(img):
    if isinstance(img, str):
        img = load(img)
    return img.astype(np.float32) @ np.array([0.299, 0.587, 0.114], dtype=np.float32)


def template_match(img, template, search_region=None, scales=(1.0,)):
    """
    归一化互相关模板匹配（灰度，多尺度）
    返回 (score, (cx, cy), scale) 最佳结果
    """
    src = to_gray(img)
    H, W = src.shape
    if search_region:
        sx1, sy1, sx2, sy2 = search_region
    else:
        sx1, sy1, sx2, sy2 = 0, 0, W, H
    sub = src[sy1:sy2, sx1:sx2]

    best = (-2.0, (0, 0), 1.0)
    for sc in scales:
        tmpl = to_gray(template) if not isinstance(template, str) else to_gray(load(template))
        if sc != 1.0:
            th, tw = tmpl.shape
            nh, nw = max(1, int(th * sc)), max(1, int(tw * sc))
            tmpl = np.array(Image.fromarray(tmpl).resize((nw, nh), Image.BILINEAR))
        th, tw = tmpl.shape
        if th > sub.shape[0] or tw > sub.shape[1]:
            continue
        th_mean = tmpl.mean()
        tc = tmpl - th_mean
        tn = np.sqrt((tc ** 2).sum())
        if tn < 1e-6:
            continue

        # 暴力滑动（用 stride 采样加速）
        step = max(1, min(4, (sub.shape[1] * sub.shape[0]) // 300000))
        best_local = (-2.0, (0, 0))
        for y in range(0, sub.shape[0] - th + 1, step):
            for x in range(0, sub.shape[1] - tw + 1, step):
                win = sub[y:y + th, x:x + tw]
                wc = win - win.mean()
                wn = np.sqrt((wc ** 2).sum())
                if wn < 1e-6:
                    continue
                score = float((wc * tc).sum() / (wn * tn))
                if score > best_local[0]:
                    best_local = (score, (x, y))
        if best_local[0] > best[0]:
            best = (best_local[0], (sx1 + best_local[1][0] + tw // 2, sy1 + best_local[1][1] + th // 2), sc)
    return best


if __name__ == "__main__":
    import json
    p = sys.argv[1] if len(sys.argv) > 1 else None
    if not p:
        print("usage: vision.py <image.png>")
        sys.exit(1)
    img = load(p)
    print("size:", img.shape)
    print("mean color:", region_mean_color(img, (0, 0, img.shape[1], img.shape[0])))
    print("green regions:", json.dumps(find_color_regions(img, (26, 188, 130), tol=40), ensure_ascii=False))
