# -*- coding: utf-8 -*-
"""播放模式切换：顺序播放 / 随机播放 / 单曲循环。

底栏播放模式按钮是循环切换的（顺序 -> 随机 -> 单曲 -> 顺序...），
先尝试用 UIA 读按钮提示文本判断当前模式；读不到时退化为"点一次切换一档"。
"""
import time

import pyautogui

from .controller import activate_window, ensure_running
from .settings import load_config

# 目标模式别名 -> QQ音乐提示文本关键字
_MODE_KEYWORDS = {
    "order": ["顺序", "列表循环"],
    "random": ["随机"],
    "single": ["单曲"],
}

# QQ音乐播放模式的循环顺序（用于估算要点几次）
_MODE_CYCLE = ["顺序", "随机", "单曲"]


def _read_current_mode(cfg):
    """用 UIA 读底栏播放模式按钮的提示文本，返回命中的关键字或 None。"""
    try:
        from pywinauto import Application

        app = Application(backend="uia").connect(
            path=cfg["qqmusic"]["process_name"] + ".exe", timeout=5
        )
        win = app.top_window()
        for btn in win.descendants(control_type="Button"):
            name = btn.window_text() or ""
            for kw in _MODE_CYCLE:
                if kw in name:
                    print(f"[mode] UIA 读到当前播放模式: {name}")
                    return kw
    except Exception as e:
        print(f"[mode] UIA 读取模式失败: {e}")
    return None


def set_mode(target, cfg=None):
    """切换播放模式。target: order / random / single。

    能读到当前模式时按循环序计算点击次数；读不到时只点一次并提示用户确认。
    """
    cfg = cfg or load_config()
    if target not in _MODE_KEYWORDS:
        print(f"[mode][错误] 未知模式: {target}，可选 order/random/single")
        return False
    coord = cfg.get("coords", {}).get("play_mode_button")
    if not coord:
        print("[mode][错误] 缺少播放模式按钮坐标，请先运行: python cli.py calibrate")
        return False
    ensure_running(cfg)
    activate_window(cfg)

    # 窗口相对坐标实时换算（与 search 模块同一套逻辑，避免窗口移动后点偏）
    from .search import _resolve

    pos = _resolve(coord, cfg)
    if pos is None:
        print("[mode][错误] 播放模式按钮坐标格式异常，请重跑: python cli.py calibrate")
        return False
    x, y = pos

    target_kws = _MODE_KEYWORDS[target]
    current = _read_current_mode(cfg)
    if current is None:
        pyautogui.click(x, y)
        print("[mode][提示] 无法读取当前模式，已点击一次；如不对请再说一次切换指令")
        return True

    # 命中目标包含的关键字之一（顺序/列表循环都视作 order）
    if any(kw in current for kw in target_kws):
        print(f"[mode] 已是目标模式: {current}，无需切换")
        return True

    # 按循环序计算点击次数
    try:
        cur_idx = _MODE_CYCLE.index(current)
    except ValueError:
        cur_idx = 0
    tgt_idx = 0 if target == "order" else (1 if target == "random" else 2)
    clicks = (tgt_idx - cur_idx) % len(_MODE_CYCLE)
    for i in range(clicks):
        pyautogui.click(x, y)
        time.sleep(0.4)
    print(f"[mode] 已点击 {clicks} 次，切换到: {target}")
    return True
