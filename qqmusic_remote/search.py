# -*- coding: utf-8 -*-
"""搜索与点播：搜索播放指定歌曲 / 播放指定歌单。

实现策略：UIA 优先尝试定位搜索框；QQ 音乐为自绘界面，UIA 常拿不到控件，
此时回退到 config.yaml 中校准好的屏幕坐标 + 剪贴板粘贴 + 模拟点击。
"""
import time

import pyautogui
import pyperclip

from .controller import _enum_main_window, activate_window, current_song, ensure_running
from .settings import load_config


def _paste_text(text):
    """通过剪贴板粘贴文本（比逐字输入快且支持中文）。"""
    pyperclip.copy(text)
    time.sleep(0.1)
    pyautogui.hotkey("ctrl", "v")


def _resolve(coord, cfg):
    """把校准坐标换算成当前屏幕坐标。

    新格式 {"win": [dx, dy], "abs": [x, y]}：按主窗口当前位置实时换算，
    窗口移动后依然点得准；旧格式 [x, y]（绝对坐标）原样使用并提示重新校准。
    """
    if isinstance(coord, dict) and coord.get("win"):
        hwnd, _ = _enum_main_window(cfg["qqmusic"]["process_name"])
        if hwnd:
            import win32gui

            left, top, _, _ = win32gui.GetWindowRect(hwnd)
            dx, dy = coord["win"]
            return left + dx, top + dy
        abs_xy = coord.get("abs")
        if abs_xy:
            return abs_xy[0], abs_xy[1]
        return None
    if isinstance(coord, (list, tuple)) and len(coord) == 2:
        print("[search][提示] 正在使用旧版绝对坐标，窗口移动后可能点偏，建议重跑校准")
        return coord[0], coord[1]
    return None


def _click(coord, desc="", cfg=None):
    """按校准坐标点击（优先窗口相对坐标）；坐标缺失时抛出可读错误。"""
    if not coord:
        raise RuntimeError(
            f"缺少校准坐标({desc})，请先运行: python cli.py calibrate"
        )
    pos = _resolve(coord, cfg) if cfg else (coord[0], coord[1])
    if pos is None:
        raise RuntimeError(f"校准坐标格式异常({desc})，请重跑: python cli.py calibrate")
    x, y = pos
    pyautogui.click(x, y)
    print(f"[search] 点击 {desc or '坐标'} -> ({x}, {y})")
    time.sleep(0.5)


def _focus_search_box(cfg):
    """聚焦搜索框：优先 UIA 查找编辑框，失败则用校准坐标点击。返回是否成功。"""
    coords = cfg.get("coords", {})
    if coords.get("search_box"):
        _click(coords["search_box"], "搜索框", cfg)
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
    _click(cfg["coords"].get("search_first_result"), "第一首结果播放按钮", cfg)
    # 播后验证：主窗口标题会变为当前曲目，据此确认是否真的播上了
    time.sleep(2.0)
    song = current_song(cfg)
    print(f"[search] 已点播: {keyword}；当前播放: {song or '(未读到标题)'}")
    if song and keyword.lower().split()[0] not in song.lower():
        print("[search][提示] 当前曲目与点播关键字不符，可能是坐标偏移，建议重跑校准")
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
    _click(cfg["coords"].get("playlist_tab"), "歌单标签", cfg)
    time.sleep(1.0)
    _click(cfg["coords"].get("playlist_first"), "第一个歌单", cfg)
    time.sleep(1.5)
    _click(cfg["coords"].get("playlist_play_all"), "播放全部按钮", cfg)
    time.sleep(2.0)
    print(f"[search] 已播放歌单: {name}；当前播放: {current_song(cfg) or '(未读到标题)'}")
    return True
