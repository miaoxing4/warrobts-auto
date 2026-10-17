# -*- coding: utf-8 -*-
"""
数字模板自举（最终版）：从多个已知样本补齐 0-9 全部数字

已知样本（人眼确认）：
  G5_league.png       1848/1899
  league_rating.png   1808/1899
  G3_trophy2.png      (不含进度条文字)
"""
import sys
import os
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import vision as v
import rating_reader as rr

PROJ = os.path.dirname(os.path.abspath(__file__))
CAP = os.path.join(PROJ, "captures")

SAMPLES = [
    ("G5_league.png", "1848/1899"),
    ("league_rating.png", "1808/1899"),
    ("rating_verify_1848.png", "1848/1899"),
]


def glyph_variants(glyph):
    out = [glyph]
    for dy, dx in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
        out.append(np.roll(glyph, (dy, dx), axis=(0, 1)))
    from PIL import Image
    h, w = glyph.shape
    for s in (0.93, 1.07):
        nh, nw = max(4, int(h * s)), max(4, int(w * s))
        im = Image.fromarray((glyph * 255).astype(np.uint8))
        im = im.resize((nw, nh), Image.LANCZOS)
        out.append((np.array(im) > 127).astype(np.uint8))
    return out


def main():
    if os.path.isdir(rr.DIGIT_TEMPLATE_DIR):
        for f in os.listdir(rr.DIGIT_TEMPLATE_DIR):
            if f.endswith(".npy"):
                os.remove(os.path.join(rr.DIGIT_TEMPLATE_DIR, f))

    total = 0
    for fname, known in SAMPLES:
        p = os.path.join(CAP, fname)
        if not os.path.exists(p):
            print("跳过（不存在）:", fname)
            continue
        img = v.load(p)
        chars = rr.segment_chars(rr.binarize_text(img, rr.R_RATING_TEXT))
        if len(chars) != len(known):
            print("跳过（字符数不符 %d vs %d）: %s" % (len(chars), len(known), fname))
            continue
        for (s, e, glyph), ch in zip(chars, known):
            if not ch.isdigit():
                continue
            for var in glyph_variants(glyph):
                rr.save_template(ch, var, suffix=None)
                total += 1
        print("已处理:", fname, known)

    files = os.listdir(rr.DIGIT_TEMPLATE_DIR)
    digits = sorted(set(f.split("_")[0].split(".")[0] for f in files))
    print("模板文件 %d 个，覆盖数字: %s" % (len(files), digits))

    # 回归
    print("\n=== 回归验证 ===")
    allok = True
    for fname, known in SAMPLES:
        p = os.path.join(CAP, fname)
        if not os.path.exists(p):
            continue
        res = rr.read_rating_by_template(v.load(p))
        ok = res["text"] == known
        allok = allok and ok
        print("  %-24s 期望 %-10s 识别 %-10s %s"
              % (fname, known, res["text"], "OK" if ok else "FAIL"))
    print("\n总体:", "全部通过" if allok else "存在失败")


if __name__ == "__main__":
    main()
