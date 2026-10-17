# -*- coding: utf-8 -*-
"""
任务页按钮检测（精确版）

实测结果（2400x1080）：
  「获取」领取按钮 : 约 343x88，纯绿填充，右侧列 x 2007-2350
                     （同一屏可能有 2 个，y 分别约 477-565 / 710-795）
  「完成全部」大按钮: 约 343x80，底部中央 x 1075-1418, y 984-1064
  「全部任务」导航   : 约 206x52，绿色小图标 + 白字，**不是领取按钮**
"""
import os
import sys
import numpy as np

PROJ_DIR = os.path.dirname(os.path.abspath(__file__))
if PROJ_DIR not in sys.path:
    sys.path.insert(0, PROJ_DIR)

import vision as v

# 绿色填充判据
G_MIN, G_MAX = 120, 255


def _green_mask(img):
    a = img.astype(np.int16)
    r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    return (g > G_MIN) & (g > r + 50) & (g > b + 35)


def find_claim_buttons(img):
    """
    找「获取」领取按钮。
    返回 [{'bbox', 'center', 'size'}]，按 y 排序。
    """
    mask = _green_mask(img)
    H, W = mask.shape
    # 只在右侧列搜索（x > 1600, y 300-1000）
    region = np.zeros_like(mask)
    region[300:1010, 1600:2400] = True
    m = mask & region

    # 行投影找绿色带
    rows = m.sum(axis=1)
    bands = []
    in_band = False
    start = 0
    for y in range(H):
        on = rows[y] > 150
        if on and not in_band:
            start = y
            in_band = True
        elif not on and in_band:
            if y - start >= 50:
                bands.append((start, y))
            in_band = False
    if in_band and H - start >= 50:
        bands.append((start, H))

    out = []
    for (y1, y2) in bands:
        band = m[y1:y2, :]
        cols = band.sum(axis=0)
        xs = np.nonzero(cols > (y2 - y1) * 0.4)[0]
        if len(xs) < 50:
            continue
        x1, x2 = int(xs.min()), int(xs.max())
        w, h = x2 - x1, y2 - y1
        # 尺寸过滤：领取按钮约 343x88
        if not (250 <= w <= 430 and 60 <= h <= 130):
            continue
        out.append({
            "bbox": (x1, y1, x2, y2),
            "center": ((x1 + x2) // 2, (y1 + y2) // 2),
            "size": (w, h),
        })
    out.sort(key=lambda d: d["center"][1])
    return out


def find_claim_all(img):
    """找底部中央的「完成全部」大按钮"""
    mask = _green_mask(img)
    H, W = mask.shape
    region = np.zeros_like(mask)
    region[950:1080, 900:1600] = True
    m = mask & region
    rows = m.sum(axis=1)
    ys = np.nonzero(rows > 150)[0]
    if len(ys) < 40:
        return None
    y1, y2 = int(ys.min()), int(ys.max())
    band = m[y1:y2, :]
    cols = band.sum(axis=0)
    xs = np.nonzero(cols > (y2 - y1) * 0.4)[0]
    if len(xs) < 100:
        return None
    x1, x2 = int(xs.min()), int(xs.max())
    return {
        "bbox": (x1, y1, x2, y2),
        "center": ((x1 + x2) // 2, (y1 + y2) // 2),
        "size": (x2 - x1, y2 - y1),
    }


def find_watch_video_buttons(img):
    """
    找紫色「观看视频/新增进度/免费钥匙」按钮。
    任务页：约 300x70，右侧列
    黑市：约 350x80，右下角（「免费钥匙 X100」）
    """
    a = img.astype(np.int16)
    r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    mask = (r > 100) & (b > 150) & (b > g + 55) & (r > g + 15)
    H, W = mask.shape
    region = np.zeros_like(mask)
    region[200:1040, 1200:2400] = True
    m = mask & region
    rows = m.sum(axis=1)
    bands = []
    in_band = False
    start = 0
    for y in range(H):
        on = rows[y] > 120
        if on and not in_band:
            start = y
            in_band = True
        elif not on and in_band:
            if y - start >= 35:
                bands.append((start, y))
            in_band = False
    if in_band and H - start >= 35:
        bands.append((start, H))

    out = []
    for (y1, y2) in bands:
        band = m[y1:y2, :]
        cols = band.sum(axis=0)
        xs = np.nonzero(cols > (y2 - y1) * 0.30)[0]
        if len(xs) < 80:
            continue
        x1, x2 = int(xs.min()), int(xs.max())
        w, h = x2 - x1, y2 - y1
        if not (160 <= w <= 560 and 35 <= h <= 150):
            continue
        out.append({
            "bbox": (x1, y1, x2, y2),
            "center": ((x1 + x2) // 2, (y1 + y2) // 2),
            "size": (w, h),
        })
    out.sort(key=lambda d: d["center"][1])
    return out


def find_upgrade_ad_button(img):
    """
    机库顶部中央的紫色「-4时 钟减少」按钮 —— 看一次广告减少 4 小时升级时间。

    实测（2400x1080）：
      bbox  x[1251,1526] y[160,226]   center (1388,193)  size 275x66
      颜色  约 (147, 74, 250)
      左侧紧邻绿色「X时XX分 加速」按钮（center 约 (1034,193)）—— 那个**不是**广告
    返回 {'bbox','center','size'} 或 None
    """
    y1, y2, x1, x2 = 130, 250, 1150, 1650
    sub = img[y1:y2, x1:x2].astype(np.int16)
    r, g, b = sub[:, :, 0], sub[:, :, 1], sub[:, :, 2]
    mask = (r > 120) & (r < 215) & (b > 200) & (b > g + 55) & (r > g + 35)
    if mask.sum() < 3000:
        return None
    ys, xs = np.nonzero(mask)
    bx1, bx2 = int(xs.min()) + x1, int(xs.max()) + x1
    by1, by2 = int(ys.min()) + y1, int(ys.max()) + y1
    w, h = bx2 - bx1, by2 - by1
    # 尺寸校验：约 275x66
    if not (180 <= w <= 380 and 45 <= h <= 110):
        return None
    return {
        "bbox": (bx1, by1, bx2, by2),
        "center": ((bx1 + bx2) // 2, (by1 + by2) // 2),
        "size": (w, h),
    }


# ============================================================ 特惠页
# 机库左侧最下方购物车进入的「特惠」页（左侧 1/2/3 分栏）
# 实测：5 张礼包卡横向排列，底部按钮中心 y=815，卡中心 x 如下
DEAL_CARD_X = (493, 940, 1386, 1832, 2278)
DEAL_BTN_Y = 815


def deal_page_is_paid(img):
    """
    **安全护栏**：区分「广告特惠页」和「付费折扣页」。

    实测：
      广告页（紫色观看 / 绿色获取） 卡片区橙色占比 **0.001**，青绿背景 0.39
      付费页（橙色 % 背景、JP¥80/JP¥50）卡片区橙色占比 **0.172**，青绿背景 0.17

    付费页上的按钮是**真实货币购买**，绝不能点（会拉起 Google Play 支付）。
    返回 True 表示是付费页，调用方必须放弃操作。
    """
    h, w = img.shape[:2]
    card = img[250:700, 250:min(w, 2350)].astype(np.int16)
    r, g, b = card[:, :, 0], card[:, :, 1], card[:, :, 2]
    orange = float(((r > 130) & (g > 70) & (g < 180) & (b < 90)
                    & (r > b + 80)).mean())
    return orange > 0.05


def classify_deal_buttons(img, cards=5):
    """
    判断特惠页每张礼包卡底部按钮的类型。

    实测三种状态：
      watch  紫色「观看」     → 可以看广告（点数如 0/3）
      claim  绿色「获取」     → 广告看完，可以领取
      locked 深色「已结束」/🔒 → 不可操作（已领完 / 还没解锁）

    返回 [{'index','x','y','kind','purple','green'}, ...]
    """
    out = []
    h, w = img.shape[:2]
    for i in range(min(cards, len(DEAL_CARD_X))):
        cx = DEAL_CARD_X[i]
        x1, x2 = max(0, cx - 195), min(w, cx + 195)
        y1, y2 = DEAL_BTN_Y - 30, DEAL_BTN_Y + 40
        band = img[y1:y2, x1:x2].astype(np.int16)
        r, g, b = band[:, :, 0], band[:, :, 1], band[:, :, 2]
        purple = float(((r > 110) & (b > 180) & (b > g + 50)).mean())
        green = float(((g > 120) & (g > r + 45) & (g > b + 25)).mean())
        if purple > 0.30:
            kind = "watch"          # 紫色「观看」= 可看广告
        elif green > 0.25:
            kind = "claim"          # 绿色「获取」= 可领取
        elif purple > 0.04:
            kind = "unavailable"    # 紫色但变暗「不可用」= 广告暂时用尽（0/3 之类）
        else:
            kind = "locked"         # 深色「已结束」/🔒 未解锁
        out.append({
            "index": i + 1, "x": cx, "y": DEAL_BTN_Y, "kind": kind,
            "purple": round(purple, 3), "green": round(green, 3),
        })
    return out


if __name__ == "__main__":
    CAP = os.path.join(PROJ_DIR, "captures")
    for f in ["62_event_tasks2.png", "L1_tasks.png"]:
        p = os.path.join(CAP, f)
        if not os.path.exists(p):
            continue
        img = v.load(p)
        print("==", f)
        print("  获取:", find_claim_buttons(img))
        print("  完成全部:", find_claim_all(img))
        print("  观看视频:", find_watch_video_buttons(img))
