# -*- coding: utf-8 -*-
"""视觉识别模块：对 QQ 音乐主窗口截图 + Windows 内置中文 OCR，定位界面文字元素。

替代手工坐标校准：搜索框、歌单标签、"播放全部"、歌名行等带文字的元素
直接按 OCR 结果点击；纯图标按钮（如播放模式）仍走校准坐标兜底。
"""
import ctypes
import json
import os
import subprocess
import tempfile

import pyautogui

from .controller import _enum_main_window

_PS1 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ocr.ps1")


def _dpi_scale():
    """屏幕物理像素 / 逻辑像素 的缩放比（如 1.0 / 1.5）。

    pyautogui 的坐标是逻辑像素，screenshot 的位图是物理像素，换算时要用。
    """
    logical_w = pyautogui.size()[0]
    physical_w = pyautogui.screenshot().size[0]
    return physical_w / logical_w if logical_w else 1.0


def capture_window(cfg):
    """截取完整模式主窗口图像。

    返回 (图片路径, 窗口左上角逻辑坐标 left, top, dpi 缩放比)；找不到窗口返回 None。
    """
    import win32gui

    hwnd, _ = _enum_main_window(cfg["qqmusic"]["process_name"])
    if not hwnd:
        print("[vision] 未找到 QQ 音乐主窗口")
        return None
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    scale = _dpi_scale()
    # region 传逻辑坐标，实际截图像素需乘缩放比
    shot = pyautogui.screenshot(region=(left, top, right - left, bottom - top))
    fd, path = tempfile.mkstemp(suffix=".png", prefix="qqmusic_")
    os.close(fd)
    shot.save(path)
    return path, left, top, scale


def ocr_image(path):
    """调用 PowerShell 的 Windows OCR 识别图片，返回词块列表 [{text,x,y,w,h}]。"""
    out = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", _PS1, "-Path", path],
        capture_output=True, text=True, timeout=60,
    )
    if out.returncode != 0 or not out.stdout.strip():
        print(f"[vision] OCR 失败: {out.stderr.strip()[:200]}")
        return []
    try:
        data = json.loads(out.stdout.strip())
    except json.JSONDecodeError:
        print(f"[vision] OCR 输出解析失败: {out.stdout[:200]}")
        return []
    if isinstance(data, dict):  # 只有一个词块时 ConvertTo-Json 返回对象
        data = [data]
    return data


def scan_window(cfg):
    """截图 + OCR 一步到位，返回 (词块列表, left, top, scale)；失败返回 (None,)*4。"""
    cap = capture_window(cfg)
    if not cap:
        return None, None, None, None
    path, left, top, scale = cap
    try:
        words = ocr_image(path)
    finally:
        os.unlink(path)
    return words, left, top, scale


def word_to_screen(word, left, top, scale):
    """把 OCR 词块中心换算成 pyautogui 可点击的屏幕逻辑坐标。"""
    cx = word["x"] + word["w"] / 2
    cy = word["y"] + word["h"] / 2
    return left + cx / scale, top + cy / scale


def find_word(words, keyword, min_conf_topmost=True):
    """在词块中查找包含关键字的项，默认取最靠上的一个。返回词块或 None。"""
    hits = [w for w in words if keyword in w.get("text", "")]
    if not hits:
        return None
    hits.sort(key=lambda w: (w["y"], w["x"]))
    return hits[0]


def dump_words(words, left, top, scale):
    """调试用：打印全部识别到的词块及其屏幕坐标。"""
    for w in sorted(words, key=lambda v: (v["y"], v["x"])):
        sx, sy = word_to_screen(w, left, top, scale)
        print(f"  {w['text']!r:30} 屏幕({sx:.0f}, {sy:.0f}) 块({w['x']:.0f},{w['y']:.0f},{w['w']:.0f}x{w['h']:.0f})")


def merge_lines(words, y_tol=10):
    """把同一视觉行的词块合并成整行（中文 OCR 常把'歌单'拆成'歌'+'单'）。

    按 y 聚类成行，行内按 x 排序拼接文本，返回 [{text,x,y,w,h}]（图像坐标）。
    """
    if not words:
        return []
    words = sorted(words, key=lambda w: (w["y"], w["x"]))
    lines = []
    for w in words:
        if lines and abs(w["y"] - lines[-1]["y"]) <= y_tol:
            cur = lines[-1]
            cur["words"].append(w)
        else:
            lines.append({"y": w["y"], "words": [w]})
    merged = []
    for ln in lines:
        ws = sorted(ln["words"], key=lambda w: w["x"])
        x0 = min(w["x"] for w in ws)
        y0 = min(w["y"] for w in ws)
        x1 = max(w["x"] + w["w"] for w in ws)
        y1 = max(w["y"] + w["h"] for w in ws)
        merged.append({
            "text": "".join(w["text"] for w in ws),
            "x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0,
        })
    return merged


def find_text_point(lines, keyword, left, top, scale, min_y=0, max_x=None):
    """在合并行里找关键字，按字符比例插值返回其屏幕点击坐标（逻辑像素）。

    例：行文本'歌曲视频专辑歌单歌词'中找'歌单'，按其字符位置估算点击点。
    min_y: 排除相对窗口顶部该像素值以上的行（图像坐标，传入时记得乘 scale）。
    max_x: 只考虑行起点不超过该 x 的行（图像坐标），用于限定左侧导航栏等区域。
    """
    for ln in sorted(lines, key=lambda l: (l["y"], l["x"])):
        if ln["y"] < min_y:
            continue
        if max_x is not None and ln["x"] > max_x:
            continue
        idx = ln["text"].find(keyword)
        if idx < 0 or not ln["text"]:
            continue
        ratio = (idx + len(keyword) / 2) / len(ln["text"])
        cx = ln["x"] + ln["w"] * ratio
        cy = ln["y"] + ln["h"] / 2
        return left + cx / scale, top + cy / scale
    return None


def click_text(cfg, keyword, desc="", min_y_rel=0, max_x_rel=None):
    """截图 OCR 找文字并点击其中心，成功返回 True。

    min_y_rel: 只在相对窗口顶部该像素值以下的区域里找（排除搜索框等顶部干扰）。
    max_x_rel: 只找行起点在相对窗口左侧该像素值以内的文字（限定侧栏等区域）。
    """
    words, left, top, scale = scan_window(cfg)
    if words is None:
        return False
    pos = find_text_point(
        merge_lines(words), keyword, left, top, scale,
        min_y=min_y_rel * scale,
        max_x=None if max_x_rel is None else max_x_rel * scale,
    )
    if pos is None:
        print(f"[vision] 未识别到文字: {keyword}")
        return False
    pyautogui.click(pos[0], pos[1])
    print(f"[vision] 点击文字 {desc or keyword} -> ({pos[0]:.0f}, {pos[1]:.0f})")
    return True
