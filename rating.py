# -*- coding: utf-8 -*-
"""
荣誉积分读取（兼容入口）

实际实现见 rating_reader.py（数字模板匹配，无需 OCR）。
本模块保留原有 API，内部转调 rating_reader。
"""
import os
import sys

PROJ_DIR = os.path.dirname(os.path.abspath(__file__))
if PROJ_DIR not in sys.path:
    sys.path.insert(0, PROJ_DIR)

import rating_reader as _rr
import device as d

POS_LEAGUE_ENTRY = _rr.POS_LEAGUE_ENTRY
POS_TAB_MY_LEAGUE = _rr.POS_TAB_MY_LEAGUE
POS_BACK = _rr.POS_BACK


def open_league_page():
    return _rr.open_league_page()


def read_rating(save=True, use_ocr=False):
    return _rr.read_rating(save=save)


def read_rating_from_hangar():
    return _rr.read_rating_from_hangar()


def record_rating(rating, note="", extra=None):
    return _rr.record_rating(rating, note, extra)


def load_history():
    return _rr.load_history()


def check_trend(last_n=10):
    return _rr.check_trend(last_n)


if __name__ == "__main__":
    d.ensure_server()
    print("打开联赛页...")
    if open_league_page():
        print(read_rating())
    else:
        print("失败")
