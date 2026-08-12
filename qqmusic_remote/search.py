# -*- coding: utf-8 -*-
"""搜索与点播：搜索播放指定歌曲 / 播放指定歌单。

首选视觉通道：窗口截图 + Windows OCR 识别文字元素（搜索框/歌单标签/播放全部/
第一首歌名），直接点击识别到的位置，无需手工校准；
识别失败时回退到 config.yaml 里的校准坐标（窗口相对偏移）。
"""
import difflib
import os
import time

import pyautogui
import pyperclip

from . import vision

try:  # jieba 用于歌单名关键词切分（OCR 容错匹配），未装时退化为纯相似度匹配
    import jieba
except ImportError:
    jieba = None

# 歌单详情页'播放'按钮模板图（绿色按钮视觉特征稳定，比 OCR 文字更可靠）
_BTN_PLAY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "btn_play.png")
# 顶部搜索框模板图（放大镜+'搜索音乐'占位符，外观恒定；框内有残留文字时匹配不上属预期，
# 此时靠 play_song 结束时的清空动作保证下次为空）
_BOX_SEARCH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "box_search.png")


def _match_template(image_path, template_path, threshold=0.75):
    """在窗口截图里做模板匹配，命中返回 (图像 x, y, w, h, 置信度)，否则 None。"""
    import cv2

    hay = cv2.imread(image_path)
    needle = cv2.imread(template_path)
    if hay is None or needle is None:
        return None
    res = cv2.matchTemplate(hay, needle, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)
    if max_val < threshold:
        return None
    h, w = needle.shape[:2]
    return max_loc[0], max_loc[1], w, h, max_val


def _click_play_button(cfg):
    """点击歌单详情页的'播放'按钮（绿色按钮，模板匹配定位，不依赖 OCR 文字）。

    在 PrintWindow 截的窗口本体位图上匹配（不依赖前台），命中换算屏幕坐标后
    置前窗口再物理点击；匹配失败回退 OCR 文字（限内容区），再回退校准坐标。
    """
    cap = vision.capture_window(cfg)
    if cap:
        path, left, top, scale = cap
        try:
            hit = _match_template(path, _BTN_PLAY)
        finally:
            os.unlink(path)
        if hit:
            x, y, w, h, score = hit
            sx = left + (x + w / 2) / scale
            sy = top + (y + h / 2) / scale
            ensure_front(cfg)  # 物理点击前保证窗口在最前
            pyautogui.click(sx, sy)
            print(f"[vision] 模板匹配点击播放按钮 -> ({sx:.0f}, {sy:.0f}) 置信度 {score:.2f}")
            time.sleep(0.5)
            return True
        print("[vision] 模板未匹配到播放按钮，回退 OCR 文字识别")
    if vision.click_text(cfg, "播放", "播放按钮", min_x_rel=250):
        time.sleep(0.5)
        return True
    return _click_coord("playlist_play_all", "播放按钮", cfg)
from .controller import (
    _enum_main_window,
    activate_window,
    current_song,
    ensure_front,
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
    ensure_front(cfg)  # 物理点击前保证窗口在最前
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
    """聚焦搜索框：模板匹配'放大镜+搜索音乐'占位符优先，失败用校准坐标。

    搜索框外观恒定（放大镜图标+占位文字），模板匹配比 OCR 合并行插值可靠——
    后者会把搜索框所在超宽行按字符比例插值，点到右侧'听歌识曲'图标上。
    匹配成功后把点位按窗口相对偏移写回 config 供兜底。
    """
    cap = vision.capture_window(cfg)
    if cap:
        path, left, top, scale = cap
        try:
            hit = _match_template(path, _BOX_SEARCH)
        finally:
            os.unlink(path)
        if hit:
            x, y, w, h, score = hit
            sx = left + (x + w / 2) / scale
            sy = top + (y + h / 2) / scale
            ensure_front(cfg)  # 物理点击前保证窗口在最前
            pyautogui.click(sx, sy)
            print(f"[vision] 模板匹配点击搜索框 -> ({sx:.0f}, {sy:.0f}) 置信度 {score:.2f}")
            _learn_offset(cfg, "search_box", sx, sy)
            time.sleep(0.5)
            return True
        print("[vision] 模板未匹配到搜索框（可能框内有残留文字），走校准坐标")
    return _click_coord("search_box", "搜索框", cfg)


def _click_first_song(cfg):
    """点击搜索结果的第一首歌（双击歌名播放）。

    以结果列表列头行为锚点（'歌名'二字，或'专辑+时长'特征组合，容忍 OCR 丢字）。
    结果行必须排除：左栏导航行（x<=250，否则'我的音乐'会被误选）和
    以'词'开头的歌词预览行。结果页加载/搜索建议下拉关闭需要时间，
    找不到锚点时等待重试两轮，仍失败才回退校准坐标。
    """
    for retry in range(3):
        words, left, top, scale = vision.scan_window(cfg)
        if words:
            lines = vision.merge_lines(words)
            anchor = None
            for l in sorted(lines, key=lambda v: v["y"]):
                t = l["text"]
                if "歌名" in t or ("专辑" in t and "时长" in t):
                    anchor = l
                    break
            if anchor:
                rows = [
                    l for l in lines
                    if l["y"] > anchor["y"] + 15 * scale
                    and l["x"] > 250 * scale  # 排除左栏导航行
                    and not l["text"].startswith("词")  # 排除歌词预览行
                ]
                rows.sort(key=lambda v: (v["y"], v["x"]))
                if rows:
                    row = rows[0]
                    cx = row["x"] + min(120 * scale, row["w"] * 0.3)
                    cy = row["y"] + row["h"] / 2
                    sx, sy = left + cx / scale, top + cy / scale
                    ensure_front(cfg)  # 物理双击前保证窗口在最前
                    pyautogui.doubleClick(sx, sy)
                    print(f"[vision] 双击第一首歌 -> ({sx:.0f}, {sy:.0f}) 行文本: {row['text'][:30]!r}")
                    time.sleep(0.5)
                    return True
        if retry < 2:
            print("[vision] 未找到列头锚点，等待结果页加载后重试")
            time.sleep(1.5)
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


def _clear_search_box(cfg):
    """播放成功后清空搜索框残留文字，恢复'搜索'占位符可见。

    流程：点搜索框 -> Ctrl+A 全选 -> Delete 删除 -> Esc 收焦点并关掉建议下拉。
    不能用'点击内容区空白'来收焦点——会误点结果区首行/热搜区，反而触发新内容。
    """
    coord = cfg.get("coords", {}).get("search_box")
    pos = _resolve(coord, cfg) if coord else None
    if pos is None:
        return
    ensure_front(cfg)
    pyautogui.click(pos[0], pos[1])
    time.sleep(0.3)
    pyautogui.hotkey("ctrl", "a")
    pyautogui.press("delete")
    time.sleep(0.6)  # 删除后多等一会再 Esc，避免客户端吞键
    pyautogui.press("esc")
    time.sleep(0.3)
    # Esc 后搜索框仍是 focus 态（占位符不显示，模板匹配不上）。
    # 点'歌名/歌手'列头退出 focus：此时必在搜索结果页，列头必然存在、
    # 好识别（OCR 文字），且列头点击至多触发排序、不会误播歌曲。
    words, left, top, scale = vision.scan_window(cfg)
    if words:
        for l in sorted(vision.merge_lines(words), key=lambda v: v["y"]):
            t = l["text"]
            if "歌名" in t or ("专辑" in t and "时长" in t):
                hpos = vision.find_text_point([l], "歌名", left, top, scale)
                if hpos:
                    pyautogui.click(hpos[0], hpos[1])
                    print(f"[search] 点击列头退出搜索框 focus -> ({hpos[0]:.0f}, {hpos[1]:.0f})")
                break
    print("[search] 已清空搜索框残留文字")


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
    time.sleep(0.5)  # 等搜索建议下拉刷新
    pyautogui.press("esc")  # 关掉建议下拉，防止回车选中历史/推荐项
    time.sleep(0.2)
    pyautogui.press("enter")
    print(f"[search] 已搜索: {keyword}，等待结果加载...")
    time.sleep(1.5)
    if not _click_first_song(cfg):
        return False
    time.sleep(2.0)
    song = current_song(cfg)
    print(f"[search] 已点播: {keyword}；当前播放: {song or '(未读到标题)'}")
    if song and keyword.lower().split()[0] not in song.lower():
        print("[search][提示] 当前曲目与点播关键字不符，可能点偏了")
    _clear_search_box(cfg)  # 清空残留，保证下次搜索 OCR 能定位搜索框
    return True


def _similarity(a, b):
    """两段文本的字符级相似度（0~1），用于 OCR 容错比较。"""
    return difflib.SequenceMatcher(None, a, b).ratio()


def _name_keywords(name):
    """歌单名关键词：jieba 分词取长度>=2 且非通用后缀的词（'新新歌单' -> ['新新']）。"""
    if jieba is None:
        return []
    return [w for w in jieba.lcut(name) if len(w) >= 2 and w not in ("歌单",)]


def _fuzzy_match_span(text, name, threshold=0.6):
    """在文本中找与 name 最相似的子串（容忍 OCR 丢字/错字）。

    优先级：精确包含 -> jieba 关键词包含 -> 滑动窗口逐子串算相似度。
    命中返回 (子串起 idx, 子串止 idx, 相似度)，未命中返回 None。
    """
    if name in text:
        i = text.index(name)
        return i, i + len(name), 1.0
    for kw in _name_keywords(name):
        if kw in text:
            i = text.index(kw)
            return i, i + len(kw), 0.8
    n = len(name)
    best = None
    # 窗口长度只许与 name 差 1 字：过短的子串（如'歌单'二字）分母小易误判
    for size in range(max(2, n - 1), n + 3):
        for i in range(0, max(0, len(text) - size) + 1):
            r = _similarity(name, text[i:i + size])
            if best is None or r > best[2]:
                best = (i, i + size, r)
    if best and best[2] >= threshold:
        return best
    return None


def _fuzzy_find_point(lines, name, wleft, wtop, scale, threshold=0.6):
    """在合并行里模糊查找 name，按命中子串的字符比例插值返回屏幕点击坐标。

    合并行可能横跨整个窗口（同行内容区文字并入），必须按子串在行内的
    字符位置插值，取相似度分数最高的命中。找不到返回 None。
    """
    best = None
    for ln in sorted(lines, key=lambda l: (l["y"], l["x"])):
        m = _fuzzy_match_span(ln["text"], name, threshold)
        if not m:
            continue
        i0, i1, score = m
        ratio = (i0 + i1) / 2 / max(1, len(ln["text"]))
        cx = ln["x"] + ln["w"] * ratio
        cy = ln["y"] + ln["h"] / 2
        pos = (wleft + cx / scale, wtop + cy / scale)
        if best is None or score > best[2]:
            best = (pos[0], pos[1], score)
    if best:
        return best[0], best[1]
    return None


def _scroll_nav_and_find(cfg, name, max_scrolls=8):
    """在当前歌单列表里模糊查找歌单名，找不到就悬停列表区大幅快滚继续找。

    悬停点必须在页签之下的歌单列表区（窗口中部会被内容区接管滚轮）。
    到底判定：连续两次截图左栏文本几乎不变（滚不动）即到底，返回 None。
    左栏列表只取行起点 x<230 的行，避免误点内容区同名文本。
    找到返回屏幕坐标 (x, y)。
    """
    import win32gui

    hwnd, _ = _enum_main_window(cfg["qqmusic"]["process_name"])
    if not hwnd:
        return None
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    nav_cx = left + 100
    nav_cy = top + (bottom - top) * 0.85  # 左栏下部歌单列表区

    last_sig = None
    still = 0
    for attempt in range(max_scrolls + 1):
        words, wleft, wtop, scale = vision.scan_window(cfg)
        if not words:
            return None
        nav_lines = [l for l in vision.merge_lines(words) if l["x"] < 230 * scale]
        pos = _fuzzy_find_point(nav_lines, name, wleft, wtop, scale)
        if pos:
            return pos
        # 左栏文本签名与上次几乎相同 -> 滚不动了
        sig = "|".join(l["text"] for l in sorted(nav_lines, key=lambda v: (v["y"], v["x"])))
        if last_sig and _similarity(sig, last_sig) > 0.85:
            still += 1
            if still >= 2:
                print("[vision] 左栏连续滚动内容无变化，判定已到底")
                return None
        else:
            still = 0
        last_sig = sig
        if attempt < max_scrolls:
            ensure_front(cfg)  # 滚动是物理输入，先保证窗口在最前
            pyautogui.moveTo(nav_cx, nav_cy)
            time.sleep(0.3)  # 悬停片刻让自绘列表接管滚轮
            pyautogui.scroll(-12)  # 大幅度快滚（歌单列表总长不大）
            print(f"[vision] 左栏未见到 {name}，快滚后继续（第 {attempt + 1} 次）")
            time.sleep(0.8)
    return None


def _click_nav_tab(cfg, tab):
    """点击左栏的分类页签（'自建歌单'/'收藏歌单'），OCR 模糊容错（如识别成'收歌单'）。"""
    words, wleft, wtop, scale = vision.scan_window(cfg)
    if not words:
        return False
    nav_lines = [l for l in vision.merge_lines(words) if l["x"] < 230 * scale]
    pos = _fuzzy_find_point(nav_lines, tab, wleft, wtop, scale)
    if pos:
        ensure_front(cfg)  # 物理点击前保证窗口在最前
        pyautogui.click(pos[0], pos[1])
        print(f"[vision] 点击左栏分类页签 {tab} -> ({pos[0]:.0f}, {pos[1]:.0f})")
        time.sleep(0.8)
        return True
    print(f"[vision] 未找到左栏分类页签: {tab}")
    return False


def _find_in_nav(cfg, name, max_scrolls=8):
    """在左侧歌单列表查找歌单名：'自建歌单'与'收藏歌单'互斥，两个分类都找完才报没找到。

    流程：点'自建歌单'页签 -> 快滚查找到底 -> 没找到则点'收藏歌单'页签
    -> 再次快滚查找到底；两个分类都到底仍没有才返回 None。
    找到返回屏幕坐标 (x, y)。
    """
    for tab in ("自建歌单", "收藏歌单"):
        _click_nav_tab(cfg, tab)  # 页签点不到也在当前视图找一轮兜底
        pos = _scroll_nav_and_find(cfg, name, max_scrolls)
        if pos:
            return pos
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
        print(f"[search][错误] 自建/收藏两个分类都找到底也没有: {name}，请确认歌单名")
        return False
    ensure_front(cfg)  # 物理点击前保证窗口在最前
    pyautogui.click(pos[0], pos[1])
    print(f"[vision] 点击左栏歌单 {name} -> ({pos[0]:.0f}, {pos[1]:.0f})")
    time.sleep(1.5)
    # 详情页绿色'播放'按钮走模板匹配（内部含 OCR/校准坐标两级回退）
    if not _click_play_button(cfg):
        return False
    time.sleep(2.0)
    print(f"[search] 已播放歌单: {name}；当前播放: {current_song(cfg) or '(未读到标题)'}")
    return True
