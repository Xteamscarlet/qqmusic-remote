# -*- coding: utf-8 -*-
"""搜索与点播：搜索播放指定歌曲 / 播放指定歌单。

实现策略：UIA 优先尝试定位搜索框；QQ 音乐为自绘界面，UIA 常拿不到控件，
此时回退到 config.yaml 中校准好的屏幕坐标 + 剪贴板粘贴 + 模拟点击。
"""
import time

import pyautogui
import pyperclip

from .controller import activate_window, ensure_running
from .settings import load_config


def _paste_text(text):
    """通过剪贴板粘贴文本（比逐字输入快且支持中文）。"""
    pyperclip.copy(text)
    time.sleep(0.1)
    pyautogui.hotkey("ctrl", "v")


def _click(coord, desc=""):
    """按校准坐标点击；坐标缺失时抛出可读错误。"""
    if not coord:
        raise RuntimeError(
            f"缺少校准坐标({desc})，请先运行: python cli.py calibrate"
        )
    x, y = coord
    pyautogui.click(x, y)
    print(f"[search] 点击 {desc or '坐标'} -> ({x}, {y})")
    time.sleep(0.5)


def _focus_search_box(cfg):
    """聚焦搜索框：优先 UIA 查找编辑框，失败则用校准坐标点击。返回是否成功。"""
    coords = cfg.get("coords", {})
    if coords.get("search_box"):
        _click(coords["search_box"], "搜索框")
        return True
    # UIA 尝试：在 QQ 音乐主窗口后代里找 Edit 控件
    try:
        from pywinauto import Application

        app = Application(backend="uia").connect(
            path=cfg["qqmusic"]["process_name"] + ".exe", timeout=5
        )
        win = app.top_window()
        edits = win.descendants(control_type="Edit")
        if edits:
            edits[0].click_input()
            print("[search] UIA 定位搜索框成功")
            time.sleep(0.5)
            return True
    except Exception as e:
        print(f"[search] UIA 定位搜索框失败: {e}")
    print("[search][错误] 无法定位搜索框，请先运行校准: python cli.py calibrate")
    return False


def play_song(keyword, cfg=None):
    """搜索并播放指定歌曲（如 'Dream It Possible'）。

    流程：确保客户端运行 -> 聚焦窗口 -> 点搜索框 -> 粘贴歌名 -> 回车
    -> 等待结果 -> 点击第一首结果的播放按钮。
    """
    cfg = cfg or load_config()
    ensure_running(cfg)
    activate_window(cfg)
    if not _focus_search_box(cfg):
        return False
    pyautogui.hotkey("ctrl", "a")  # 清空原有搜索词
    _paste_text(keyword)
    time.sleep(0.3)
    pyautogui.press("enter")
    print(f"[search] 已搜索: {keyword}，等待结果加载...")
    time.sleep(2.5)
    _click(cfg["coords"].get("search_first_result"), "第一首结果播放按钮")
    print(f"[search] 已点播: {keyword}")
    return True


def play_playlist(name=None, cfg=None):
    """搜索并播放指定歌单（默认取 config 的 default_playlist，如 '新新歌单'）。

    流程同搜索歌曲，但先切到'歌单'标签，进第一个歌单后点'播放全部'。
    """
    cfg = cfg or load_config()
    name = name or cfg.get("default_playlist", "新新歌单")
    ensure_running(cfg)
    activate_window(cfg)
    if not _focus_search_box(cfg):
        return False
    pyautogui.hotkey("ctrl", "a")
    _paste_text(name)
    time.sleep(0.3)
    pyautogui.press("enter")
    print(f"[search] 已搜索歌单: {name}，等待结果加载...")
    time.sleep(2.5)
    _click(cfg["coords"].get("playlist_tab"), "歌单标签")
    time.sleep(1.0)
    _click(cfg["coords"].get("playlist_first"), "第一个歌单")
    time.sleep(1.5)
    _click(cfg["coords"].get("playlist_play_all"), "播放全部按钮")
    print(f"[search] 已播放歌单: {name}")
    return True
