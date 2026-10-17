# -*- coding: utf-8 -*-
"""
荣誉积分读取（数字模板匹配版，无外部依赖）

原理：
  「我的联赛」页进度条上的文字为固定的白色粗体 "当前分/满分"，
  例如 1848/1899。我们：
    1) 裁出文字区域
    2) 二值化（白色文字）
    3) 按列投影切分出每个数字/斜杠
    4) 与内置 0-9 模板做归一化相关匹配
  同时用进度条填充比例做交叉校验。
"""
import os
import sys
import re
import time
import numpy as np

PROJ_DIR = os.path.dirname(os.path.abspath(__file__))
if PROJ_DIR not in sys.path:
    sys.path.insert(0, PROJ_DIR)

import device as d
import vision as v

# 界面坐标（2400x1080，实测）
POS_LEAGUE_ENTRY = (2300, 590)      # 机库右侧第 4 个图标（奖杯/联赛）
POS_TAB_MY_LEAGUE = (1110, 130)     # 「我的联赛」标签
POS_BACK = (155, 1000)              # 后退

# 进度条文字区域（实测 1848/1899 所在）
R_RATING_TEXT = (640, 388, 1520, 448)
# 进度条蓝色填充区（实测）
R_BAR = (133, 395, 2218, 440)
# 联赛区间文字（如 1700 - 1899）
R_RANGE_TEXT = (400, 320, 1000, 380)

DIGIT_TEMPLATE_DIR = os.path.join(PROJ_DIR, "templates", "digits")


# ------------------------------------------------------------------ 进度条
def bar_fill_ratio(img):
    """按蓝色填充比例计算进度 0~1（以整条轨道为分母）"""
    x1, y1, x2, y2 = R_BAR
    sub = img[y1:y2, x1:x2].astype(int)
    r, g, b = sub[:, :, 0], sub[:, :, 1], sub[:, :, 2]
    blue = (b > 110) & (b > r + 40) & (g < b)
    cols = blue.any(axis=0)
    if not cols.any():
        return None, None
    idx = np.nonzero(cols)[0]
    filled_end = int(idx[-1])
    return filled_end, cols.shape[0]


def estimate_from_bar(img, lo=1500, hi=2500):
    """用蓝条终点估算当前分值（需要知道区间下限/上限）"""
    end, total = bar_fill_ratio(img)
    if end is None:
        return None
    # 找到轨道的起点与终点（蓝色最左与轨道边界）
    x1, y1, x2, y2 = R_BAR
    sub = img[y1:y2, x1:x2].astype(int)
    r, g, b = sub[:, :, 0], sub[:, :, 1], sub[:, :, 2]
    # 轨道底色是深蓝灰，蓝色填充明显更亮更蓝
    bright = (b > 150) & (b > r + 60)
    cols2 = bright.any(axis=0)
    if not cols2.any():
        return None
    idx2 = np.nonzero(cols2)[0]
    start, end2 = int(idx2[0]), int(idx2[-1])
    if end2 <= start:
        return None
    frac = (end - start) / max(1, (totallen(img) - start))
    return frac


def totallen(img):
    x1, y1, x2, y2 = R_BAR
    return x2 - x1


# ------------------------------------------------------------------ 数字切分
def binarize_text(img, box, thresh=185):
    """裁剪文字区并二值化（白字）"""
    x1, y1, x2, y2 = box
    crop = img[y1:y2, x1:x2]
    gray = v.to_gray(crop)
    mask = (gray > thresh).astype(np.uint8)
    return mask


def segment_chars(mask, min_w=4, max_w=70, min_h=14):
    """
    按列投影切分字符。
    返回 [(x_start, x_end, glyph_mask)]
    """
    colsum = mask.sum(axis=0)
    if colsum.max() == 0:
        return []
    active = colsum > 0
    segs = []
    in_seg = False
    s = 0
    for i, a in enumerate(active):
        if a and not in_seg:
            s = i
            in_seg = True
        elif not a and in_seg:
            segs.append((s, i))
            in_seg = False
    if in_seg:
        segs.append((s, len(active)))

    out = []
    for (s, e) in segs:
        w = e - s
        sub = mask[:, s:e]
        rows = sub.sum(axis=1)
        nz = np.nonzero(rows)[0]
        if len(nz) == 0:
            continue
        h = nz[-1] - nz[0] + 1
        if w < min_w or w > max_w or h < min_h:
            continue
        glyph = sub[nz[0]:nz[-1] + 1, :]
        out.append((s, e, glyph))
    return out


def normalize_glyph(glyph, size=(24, 32)):
    """
    把字形缩放到固定大小，做模糊抗锯齿 + 0/1 归一。
    先裁剪到紧贴包围盒，避免不同字形的空白边距影响匹配。
    """
    from PIL import Image, ImageFilter
    if glyph.size == 0 or glyph.sum() == 0:
        return np.zeros(size, dtype=np.float32)
    im = Image.fromarray((glyph * 255).astype(np.uint8))
    # 轻微模糊，抵消缩放锯齿
    im = im.resize(size, Image.LANCZOS).filter(ImageFilter.GaussianBlur(0.8))
    arr = np.array(im).astype(np.float32) / 255.0
    # 归一化到 0 均值 1 方差
    arr = arr - arr.mean()
    s = arr.std()
    if s > 1e-6:
        arr = arr / s
    return arr


def _shift_match(a, b, max_shift=2):
    """在 ±max_shift 像素内搜索最佳位移相关"""
    h, w = a.shape
    best = -2.0
    for dy in range(-max_shift, max_shift + 1):
        for dx in range(-max_shift, max_shift + 1):
            ya1, ya2 = max(0, dy), min(h, h + dy)
            xa1, xa2 = max(0, dx), min(w, w + dx)
            yb1, yb2 = max(0, -dy), min(h, h - dy)
            xb1, xb2 = max(0, -dx), min(w, w - dx)
            sa = a[ya1:ya2, xa1:xa2]
            sb = b[yb1:yb2, xb1:xb2]
            if sa.size < 16:
                continue
            na = np.sqrt((sa ** 2).sum())
            nb = np.sqrt((sb ** 2).sum())
            if na < 1e-6 or nb < 1e-6:
                continue
            score = float((sa * sb).sum() / (na * nb))
            if score > best:
                best = score
    return best


def match_digit(glyph, templates):
    """与（可能多模板的）数字模板做匹配，返回 (digit, score)"""
    g = normalize_glyph(glyph)
    best = (None, -1.0)
    for ch, tmpl in templates.items():
        cands = tmpl if isinstance(tmpl, list) else [tmpl]
        for t in cands:
            score = _shift_match(g, t)
            if score > best[1]:
                best = (ch, score)
    return best


# ------------------------------------------------------------------ 模板库
def load_templates():
    """从 templates/digits 加载 0-9 模板；支持多样本 digit_0.npy, digit_1.npy..."""
    templates = {}
    if not os.path.isdir(DIGIT_TEMPLATE_DIR):
        return templates
    for f in sorted(os.listdir(DIGIT_TEMPLATE_DIR)):
        if not f.endswith(".npy"):
            continue
        stem = os.path.splitext(f)[0]
        # 文件名格式："4"（单样本）或 "4_1"（多样本）
        ch = stem.split("_")[0]
        if not ch.isdigit():
            continue
        try:
            arr = np.load(os.path.join(DIGIT_TEMPLATE_DIR, f))
        except Exception:
            continue
        templates.setdefault(ch, []).append(arr)
    return templates


def save_template(ch, glyph, suffix=None):
    """保存字形模板；多样本时用 ch_suffix 命名"""
    os.makedirs(DIGIT_TEMPLATE_DIR, exist_ok=True)
    if suffix is None:
        # 自动寻找下一个空闲序号
        existing = [f for f in os.listdir(DIGIT_TEMPLATE_DIR)
                    if f.startswith("%s_" % ch) or f == "%s.npy" % ch]
        suffix = len(existing) + 1 if existing else 0
    name = "%s.npy" % ch if suffix == 0 else "%s_%d.npy" % (ch, suffix)
    np.save(os.path.join(DIGIT_TEMPLATE_DIR, name), normalize_glyph(glyph))
    return name


def read_rating_by_template(img):
    """
    用模板匹配读取 "NNNN/NNNN"。
    返回 dict: {'rating':int|None, 'max':int|None, 'conf':float, 'text':str}
    """
    templates = load_templates()
    mask = binarize_text(img, R_RATING_TEXT)
    chars = segment_chars(mask)
    if not chars:
        return {"rating": None, "max": None, "conf": 0.0, "text": "", "n_chars": 0}

    # 斜杠识别：先看字形是否"细长下坠"（宽度小且右下角像素多、左上角少）
    parts = []
    for (s, e, glyph) in chars:
        h, w = glyph.shape
        ratio = w / max(1, h)
        is_slash = False
        if 0.4 <= ratio <= 0.85 and h >= 12:
            # 检验"从右上到左下"的对角线趋势：逐行重心应单调左移
            centers = []
            for r in range(h):
                idx = np.nonzero(glyph[r])[0]
                if len(idx):
                    centers.append(float(idx.mean()))
            if len(centers) >= 8:
                first = np.mean(centers[:max(2, len(centers) // 4)])
                last = np.mean(centers[-max(2, len(centers) // 4):])
                if (first - last) > (w * 0.30):
                    is_slash = True
        if is_slash:
            parts.append("/")
        elif templates:
            dig, sc = match_digit(glyph, templates)
            parts.append(dig if (dig and sc > 0.35) else "?")
        else:
            parts.append("?")
    text = "".join(str(p) for p in parts)

    nums = text.split("/")
    rating = None
    mx = None
    if len(nums) >= 2:
        if nums[0].isdigit():
            rating = int(nums[0])
        if nums[1].isdigit():
            mx = int(nums[1])
    return {"rating": rating, "max": mx, "conf": float(len(text) and text.count("?") == 0),
            "text": text, "n_chars": len(chars)}


# ------------------------------------------------------------------ 对外接口
def open_league_page():
    """从机库打开「我的联赛」页"""
    import ui_state as u
    import engine as e
    st = u.detect(keep=False)["state"]
    if st != "hangar":
        if not e.go_home():
            d.log("open_league_page: 无法回到机库")
            return False
    d.tap(*POS_LEAGUE_ENTRY)
    time.sleep(3.5)
    d.tap(*POS_TAB_MY_LEAGUE)
    time.sleep(3.0)
    # 确认在联赛页（找进度条蓝色）
    img, _ = d.screenshot(save=False)
    if img is None:
        return False
    end, total = bar_fill_ratio(img)
    return end is not None


def read_rating(save=True):
    """读取当前荣誉积分（模板匹配 + 蓝条交叉校验）"""
    name = "league_rating.png" if save else None
    img, path = d.screenshot(name, save=save)
    if img is None:
        return {"rating": None, "path": None}
    res = read_rating_by_template(img)
    end, total = bar_fill_ratio(img)
    res["bar_end"] = end
    res["bar_total"] = total
    if end is not None and total:
        res["bar_frac"] = round(end / total, 3)
    res["path"] = path
    return res


def read_rating_from_hangar():
    """完整流程：回机库 → 联赛页 → 读取 → 后退"""
    if not open_league_page():
        return {"rating": None, "error": "无法打开联赛页"}
    res = read_rating()
    d.tap(*POS_BACK)
    time.sleep(2.0)
    return res


# ------------------------------------------------------------------ 历史记录
HISTORY_PATH = os.path.join(PROJ_DIR, "logs", "rating_history.jsonl")


def record_rating(rating, note="", extra=None):
    """把一次分值得记录追加到历史文件"""
    import json
    if rating is None:
        return None
    os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
    entry = {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "rating": int(rating),
        "note": note,
    }
    if extra:
        entry.update(extra)
    with open(HISTORY_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def load_history():
    import json
    if not os.path.exists(HISTORY_PATH):
        return []
    out = []
    with open(HISTORY_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except Exception:
                    pass
    return out


def check_trend(last_n=10):
    """检查最近 N 次分值的趋势：返回 (first, last, delta, decreasing)"""
    hist = load_history()[-last_n:]
    if len(hist) < 2:
        return None
    first = hist[0]["rating"]
    last = hist[-1]["rating"]
    return {
        "samples": len(hist),
        "first": first,
        "last": last,
        "delta": last - first,
        "decreasing": last < first,
        "entries": hist,
    }


if __name__ == "__main__":
    d.ensure_server()
    img_path = sys.argv[1] if len(sys.argv) > 1 else None
    if img_path:
        img = v.load(img_path)
        print("模板匹配:", read_rating_by_template(img))
        print("蓝条:", bar_fill_ratio(img))
    else:
        print("打开联赛页...")
        if open_league_page():
            print(read_rating())
        else:
            print("失败")
