# -*- coding: utf-8 -*-
"""搜索与点播：搜索播放指定歌曲 / 播放指定歌单。

首选视觉通道：窗口截图 + Windows OCR 识别文字元素（搜索框/歌单标签/播放全部/
第一首歌名），直接点击识别到的位置，无需手工校准；
识别失败时回退到 config.yaml 里的校准坐标（窗口相对偏移）。
"""
import time

import pyautogui
import pyperclip

from . import vision
from .controller import (
    _enum_main_window,
    activate_window,
    current_song,
    ensure_running,
)
from .settings import load_config, save_config


def _paste_text(text):
    """通过剪贴板粘贴文本（比逐字输入快且支持中文）。"""
    pyperclip.copy(text)
    time.sleep(0.1)
    pyautogui.hotkey("ctrl", "v")


def _resolve(coord, cfg):
    """把校准坐标换算成当前屏幕坐标（窗口相对偏移优先，绝对坐标兜底）。"""
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
        print("[search][提示] 正在使用旧版绝对坐标，建议重跑校准升级为窗口相对坐标")
        return coord[0], coord[1]
    return None


def _click_coord(key, desc, cfg):
    """按校准坐标点击（视觉识别失败时的兜底通道）。"""
    coord = cfg.get("coords", {}).get(key)
    pos = _resolve(coord, cfg) if coord else None
    if pos is None:
        print(f"[search][错误] 视觉识别失败且缺少校准坐标({desc})，可运行: python cli.py calibrate")
        return False
    pyautogui.click(pos[0], pos[1])
    print(f"[search] 点击校准坐标 {desc} -> ({pos[0]}, {pos[1]})")
    time.sleep(0.5)
    return True


def _learn_offset(cfg, key, sx, sy):
    """把视觉识别到的点位按窗口相对偏移写回 config，作为以后的快速兜底。"""
    hwnd, _ = _enum_main_window(cfg["qqmusic"]["process_name"])
    if not hwnd:
        return
    import win32gui

    left, top, _, _ = win32gui.GetWindowRect(hwnd)
    cfg.setdefault("coords", {})[key] = {
        "win": [int(sx - left), int(sy - top)],
        "abs": [int(sx), int(sy)],
    }
    save_config(cfg)


def _focus_search_box(cfg):
    """聚焦搜索框：OCR 识别'搜索'占位文字优先，失败用校准坐标。"""
    words, left, top, scale = vision.scan_window(cfg)
    if words:
        lines = vision.merge_lines(words)
        # 搜索框在窗口顶部区域（相对窗口顶部 130 像素以内）
        top_lines = [l for l in lines if l["y"] < 130 * scale]
        pos = vision.find_text_point(top_lines, "搜索", left, top, scale)
        if pos:
            pyautogui.click(pos[0], pos[1])
            print(f"[vision] 点击搜索框 -> ({pos[0]:.0f}, {pos[1]:.0f})")
            _learn_offset(cfg, "search_box", pos[0], pos[1])
            time.sleep(0.5)
            return True
        print("[vision] 顶部区域未识别到'搜索'占位文字（可能框内已有文字），走校准坐标")
    return _click_coord("search_box", "搜索框", cfg)


def _click_first_song(cfg):
    """点击搜索结果的第一首歌（双击歌名播放）。

    以列头'歌名'行为锚点，取其下方最近一行的左侧歌名位置双击。
    """
    words, left, top, scale = vision.scan_window(cfg)
    if words:
        lines = vision.merge_lines(words)
        anchor = None
        for l in sorted(lines, key=lambda v: v["y"]):
            if "歌名" in l["text"]:
                anchor = l
                break
        if anchor:
            rows = [l for l in lines if l["y"] > anchor["y"] + 15 * scale]
            rows.sort(key=lambda v: (v["y"], v["x"]))
            if rows:
                row = rows[0]
                cx = row["x"] + min(120 * scale, row["w"] * 0.3)
                cy = row["y"] + row["h"] / 2
                sx, sy = left + cx / scale, top + cy / scale
                pyautogui.doubleClick(sx, sy)
                print(f"[vision] 双击第一首歌 -> ({sx:.0f}, {sy:.0f}) 行文本: {row['text'][:30]!r}")
                time.sleep(0.5)
                return True
        print("[vision] 未找到'歌名'列头或结果行")
    return _click_coord("search_first_result", "第一首结果播放按钮", cfg)


def _window_px_size(cfg, scale):
    """主窗口的图像像素尺寸（宽、高），用于按区域过滤 OCR 结果。"""
    import win32gui

    hwnd, _ = _enum_main_window(cfg["qqmusic"]["process_name"])
    if not hwnd:
        return None, None
    l, t, r, b = win32gui.GetWindowRect(hwnd)
    return (r - l) * scale, (b - t) * scale


def _click_playlist_tab(cfg):
    """点击搜索结果页的'歌单'标签。

    标签行特征：同一行里同时出现 单曲/视频/歌曲 等兄弟标签，
    以此排除搜索框残留文字和左侧导航'自建歌单'的误命中。
    """
    words, left, top, scale = vision.scan_window(cfg)
    if words:
        lines = vision.merge_lines(words)
        tab_lines = [
            l for l in lines
            if "歌单" in l["text"]
            and any(k in l["text"] for k in ("单曲", "视频", "歌曲", "专辑", "歌手"))
            and "自建" not in l["text"]
        ]
        pos = vision.find_text_point(tab_lines, "歌单", left, top, scale)
        if pos:
            pyautogui.click(pos[0], pos[1])
            print(f"[vision] 点击歌单标签 -> ({pos[0]:.0f}, {pos[1]:.0f})")
            time.sleep(1.0)
            return True
        print("[vision] 未找到歌单标签行")
    return _click_coord("playlist_tab", "歌单标签", cfg)


def _open_playlist_from_nav(cfg, name):
    """从左侧导航的'自建歌单'里直接点开指定歌单（找不到就滚动导航继续找）。

    用户自建/收藏的歌单就在左导航里，比搜索快且不会点到别人的同名歌单。
    """
    for attempt in range(9):
        words, left, top, scale = vision.scan_window(cfg)
        if not words:
            return False
        lines = vision.merge_lines(words)
        win_w, win_h = _window_px_size(cfg, scale)
        nav_x_max = (win_w or 1100) * 0.23  # 左导航约占窗口宽度的 23%
        nav_lines = [l for l in lines if l["x"] < nav_x_max]
        # 直接命中目标歌单
        pos = vision.find_text_point(nav_lines, name, left, top, scale)
        if pos:
            pyautogui.click(pos[0], pos[1])
            print(f"[vision] 左导航点击歌单 {name} -> ({pos[0]:.0f}, {pos[1]:.0f})")
            time.sleep(1.5)
            return True
        # 第 4 次还没找到时，试着切到'收藏歌单'页签再找
        if attempt == 3:
            fav = vision.find_text_point(nav_lines, "收藏歌单", left, top, scale)
            if fav:
                pyautogui.click(fav[0], fav[1])
                print("[vision] 切到'收藏歌单'页签继续找")
                time.sleep(0.8)
                continue
        # 没找到：把鼠标移到左导航上向下滚动一屏再找
        scroll_x = left + nav_x_max * 0.5 / scale
        scroll_y = top + ((win_h or 700) * 0.6) / scale
        pyautogui.moveTo(scroll_x, scroll_y)
        pyautogui.scroll(-4)
        print(f"[vision] 左导航未找到 {name}，向下滚动后继续（第 {attempt + 1} 次）")
        time.sleep(0.8)
    print(f"[vision] 左导航滚动多屏后仍未找到歌单: {name}")
    return False


def _click_first_playlist(cfg):
    """进入第一个歌单（双击其标题文字）。"""
    words, left, top, scale = vision.scan_window(cfg)
    if words:
        lines = vision.merge_lines(words)
        # 过滤掉标签行/提示行，取内容区最靠上的一行作为第一个歌单标题
        skip_kws = ("歌单", "找到", "满意", "单曲", "专辑", "视频", "歌词", "歌手", "用户")
        rows = [
            l for l in lines
            if len(l["text"]) >= 2 and not any(k in l["text"] for k in skip_kws)
        ]
        rows.sort(key=lambda v: (v["y"], v["x"]))
        if rows:
            row = rows[0]
            cx = row["x"] + min(100 * scale, row["w"] * 0.3)
            cy = row["y"] + row["h"] / 2
            sx, sy = left + cx / scale, top + cy / scale
            pyautogui.doubleClick(sx, sy)
            print(f"[vision] 双击第一个歌单 -> ({sx:.0f}, {sy:.0f}) 文本: {row['text'][:30]!r}")
            time.sleep(1.5)
            return True
        print("[vision] 未找到歌单标题行")
    return _click_coord("playlist_first", "第一个歌单", cfg)


def _click_play_all(cfg):
    """点击歌单详情页的'播放全部'。"""
    if vision.click_text(cfg, "播放全部", "播放全部按钮"):
        time.sleep(0.5)
        return True
    return _click_coord("playlist_play_all", "播放全部按钮", cfg)


def play_song(keyword, cfg=None):
    """搜索并播放指定歌曲（如 'Dream It Possible'）。

    流程：确保客户端运行 -> 聚焦窗口 -> 点搜索框 -> 粘贴歌名 -> 回车
    -> 等待结果 -> 双击第一首歌 -> 读回当前曲目标题验证。
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
    if not _click_first_song(cfg):
        return False
    time.sleep(2.0)
    song = current_song(cfg)
    print(f"[search] 已点播: {keyword}；当前播放: {song or '(未读到标题)'}")
    if song and keyword.lower().split()[0] not in song.lower():
        print("[search][提示] 当前曲目与点播关键字不符，可能点偏了")
    return True


def _find_in_nav(cfg, name, max_scrolls=8):
    """在左侧导航栏（自建/收藏歌单区）OCR 查找歌单名，找不到就滚动左栏继续找。

    左栏宽约 230 像素，只在这个区域内匹配，避免误点内容区同名文本。
    找到返回屏幕坐标 (x, y)，找不到返回 None。
    """
    import win32gui

    hwnd, _ = _enum_main_window(cfg["qqmusic"]["process_name"])
    if not hwnd:
        return None
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    nav_cx, nav_cy = left + 100, (top + bottom) // 2  # 左栏中部，滚动时鼠标悬停处

    for attempt in range(max_scrolls + 1):
        words, wleft, wtop, scale = vision.scan_window(cfg)
        if words:
            for ln in vision.merge_lines(words):
                if name in ln["text"] and ln["x"] < 230 * scale:
                    cx = ln["x"] + ln["w"] / 2
                    cy = ln["y"] + ln["h"] / 2
                    return wleft + cx / scale, wtop + cy / scale
        if attempt < max_scrolls:
            pyautogui.moveTo(nav_cx, nav_cy)
            pyautogui.scroll(-4)  # 左栏向下滚一屏，继续找
            time.sleep(0.8)
            print(f"[vision] 左栏未见到 {name}，滚动后继续（第 {attempt + 1} 次）")
    return None


def _click_sidebar_playlist(cfg, name, max_scrolls=12):
    """在左侧边栏找自建/收藏歌单并点击打开。

    侧边栏一次显示不全，找不到就把鼠标悬停到侧边栏区域滚轮下滚，再重新识别，
    直到找到或超过 max_scrolls 次。匹配支持名称被截断为'新新歌…'的情况。
    """
    import win32gui

    for attempt in range(max_scrolls):
        words, left, top, scale = vision.scan_window(cfg)
        if not words:
            return False
        lines = vision.merge_lines(words)
        for l in sorted(lines, key=lambda v: (v["y"], v["x"])):
            if l["x"] > 260 * scale:
                continue  # 只看侧边栏区域
            txt = l["text"].replace("…", "").replace("...", "")
            if len(txt) < 2:
                continue
            # 完整包含 或 截断名称的互相包含
            if name in l["text"] or (len(txt) >= 2 and txt in name):
                sx = left + (l["x"] + l["w"] / 2) / scale
                sy = top + (l["y"] + l["h"] / 2) / scale
                pyautogui.click(sx, sy)
                print(f"[vision] 侧边栏点击歌单 -> ({sx:.0f}, {sy:.0f}) 文本: {l['text']!r}")
                time.sleep(1.5)
                return True
        # 未找到：悬停侧边栏并向下滚动后重新识别
        hwnd, _ = _enum_main_window(cfg["qqmusic"]["process_name"])
        if not hwnd:
            return False
        wleft, wtop, wright, wbottom = win32gui.GetWindowRect(hwnd)
        pyautogui.moveTo(wleft + 120, wtop + (wbottom - wtop) * 0.6)
        pyautogui.scroll(-6)
        print(f"[vision] 侧边栏未找到《{name}》，向下滚动重试（{attempt + 1}/{max_scrolls}）")
        time.sleep(0.8)
    return False


def play_playlist(name=None, cfg=None):
    """播放账号内的自建/收藏歌单（默认取 config 的 default_playlist，如 '新新歌单'）。

    正确路径不是搜索（搜出来是别人的公开歌单），而是点击左侧导航栏
    "自建歌单"里的条目：OCR 找名字 -> 滚轮下翻直到出现 -> 单击进详情
    -> 点"播放全部" -> 读回当前曲目验证。
    """
    cfg = cfg or load_config()
    name = name or cfg.get("default_playlist", "新新歌单")
    ensure_running(cfg)
    activate_window(cfg)
    pos = _find_in_nav(cfg, name)
    if pos is None:
        print(f"[search][错误] 左侧歌单栏滚到底也没找到: {name}，请确认歌单名")
        return False
    pyautogui.click(pos[0], pos[1])
    print(f"[vision] 点击左栏歌单 {name} -> ({pos[0]:.0f}, {pos[1]:.0f})")
    time.sleep(1.5)
    if not vision.click_text(cfg, "播放全部", "播放全部按钮"):
        if not _click_coord("playlist_play_all", "播放全部按钮", cfg):
            return False
    time.sleep(2.0)
    print(f"[search] 已播放歌单: {name}；当前播放: {current_song(cfg) or '(未读到标题)'}")
    return True
