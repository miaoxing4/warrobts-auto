# -*- coding: utf-8 -*-
"""
难度分值（荣誉积分）趋势报告：生成 Markdown + 文本图表
"""
import os
import sys

PROJ = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJ)

import rating_reader as rr


def sparkline(values):
    chars = "_-=*#@"   # ASCII 安全
    if not values:
        return ""
    lo, hi = min(values), max(values)
    if hi == lo:
        return chars[3] * len(values)
    out = []
    for v in values:
        idx = int((v - lo) / (hi - lo) * (len(chars) - 1))
        out.append(chars[idx])
    return "".join(out)


def report():
    hist = rr.load_history()
    if not hist:
        print("暂无历史记录。先运行：python engine.py rating")
        return
    vals = [h["rating"] for h in hist]
    print("=" * 64)
    print("荣誉积分（游戏难度）趋势")
    print("=" * 64)
    print("样本数: %d   首值: %d   末值: %d   变化: %+d"
          % (len(vals), vals[0], vals[-1], vals[-1] - vals[0]))
    print("趋势图:", sparkline(vals))
    print("-" * 64)
    for h in hist:
        print("  %s   %5d   %s" % (h["ts"], h["rating"], h.get("note", "")))
    print("-" * 64)
    if vals[-1] < vals[0]:
        print("结论: 分值下降 %d 分 -> 匹配难度降低, 策略有效" % (vals[0] - vals[-1]))
    elif vals[-1] > vals[0]:
        print("结论: 分值上升 %d 分 -> 难度提高, 需调整策略" % (vals[-1] - vals[0]))
    else:
        print("结论: 分值未变, 需更多样本或检查退出时机")

    # 写 Markdown
    md = os.path.join(PROJ, "logs", "rating_report.md")
    os.makedirs(os.path.dirname(md), exist_ok=True)
    with open(md, "w", encoding="utf-8") as f:
        f.write("# 荣誉积分（难度分值）趋势报告\n\n")
        f.write("| 时间 | 荣誉积分 | 说明 |\n|---|---|---|\n")
        for h in hist:
            f.write("| %s | **%d** | %s |\n" % (h["ts"], h["rating"], h.get("note", "")))
        f.write("\n- 变化: **%+d**\n" % (vals[-1] - vals[0]))
        f.write("- 趋势: `%s`\n" % sparkline(vals))
    print("\nMarkdown 报告已写入:", md)


if __name__ == "__main__":
    report()
