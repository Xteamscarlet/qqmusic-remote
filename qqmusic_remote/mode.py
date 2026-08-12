# -*- coding: utf-8 -*-
"""播放模式切换：顺序播放(order) / 列表循环(list) / 单曲循环(single) / 随机播放(random)。

底栏模式按钮的图标随当前模式变化（4 种状态），无法用一个模板定位，
改用恒定的'上一首'按钮做锚点模板匹配，模式按钮在其左侧固定位图偏移处。
点击后弹出菜单是独立浮层窗口（主窗 PrintWindow 截不到），
在全屏截图上用菜单项模板（图标+文字，实采自真实菜单）匹配点击。
菜单直选天然幂等：重复切换到同一模式无副作用，无需读取当前模式。
"""
import os
import tempfile
import time

import pyautogui

from . import vision
from .controller import activate_window, ensure_front, ensure_running
from .search import _match_template
from .settings import load_config

_ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

# '上一首'按钮锚点模板（图标恒定，不随模式变化）
_BTN_PREV = os.path.join(_ASSETS, "btn_prev.png")
# 模式按钮中心相对'上一首'中心的位图像素偏移（其左侧 90 像素）
_MODE_BTN_OFFSET = (-90, 0)

# 目标模式 -> (菜单项模板文件, 中文名)
_MODE_MENU = {
    "order": ("menu_order.png", "顺序播放"),
    "list": ("menu_list.png", "列表循环"),
    "single": ("menu_single.png", "单曲循环"),
    "random": ("menu_random.png", "随机播放"),
}


def _find_mode_button(cfg):
    """用'上一首'锚点定位底栏模式按钮，返回屏幕坐标 (x, y)；找不到返回 None。"""
    cap = vision.capture_window(cfg)
    if not cap:
        return None
    path, left, top, scale = cap
    try:
        hit = _match_template(path, _BTN_PREV)
    finally:
        os.unlink(path)
    if not hit:
        print("[mode] 未匹配到底栏'上一首'锚点按钮")
        return None
    x, y, w, h, score = hit
    cx = x + w / 2 + _MODE_BTN_OFFSET[0]
    cy = y + h / 2 + _MODE_BTN_OFFSET[1]
    sx = left + cx / scale
    sy = top + cy / scale
    print(f"[mode] 锚点置信度 {score:.2f}，模式按钮 -> ({sx:.0f}, {sy:.0f})")
    return sx, sy


def _click_menu_item(template_name, desc):
    """全屏截图模板匹配弹出菜单项并点击。

    菜单是独立浮层窗口，主窗 PrintWindow 截不到，故截全屏；
    菜单弹出时在最上层，点击前不能置前主窗（会把菜单关掉）。
    """
    shot = pyautogui.screenshot()
    fd, path = tempfile.mkstemp(suffix=".png", prefix="qqmenu_")
    os.close(fd)
    shot.save(path)
    try:
        hit = _match_template(path, os.path.join(_ASSETS, template_name))
    finally:
        os.unlink(path)
    if not hit:
        print(f"[mode] 菜单中未匹配到: {desc}")
        return False
    x, y, w, h, score = hit
    scale = vision._dpi_scale()
    sx = (x + w / 2) / scale
    sy = (y + h / 2) / scale
    pyautogui.click(sx, sy)
    print(f"[mode] 点击菜单项 {desc} -> ({sx:.0f}, {sy:.0f}) 置信度 {score:.2f}")
    return True


def set_mode(target, cfg=None):
    """切换播放模式。target: order(顺序播放) / list(列表循环) / single(单曲循环) / random(随机播放)。

    流程：锚点定位模式按钮 -> 点击弹出菜单 -> 菜单项模板匹配点击目标项。
    """
    cfg = cfg or load_config()
    if target not in _MODE_MENU:
        print(f"[mode][错误] 未知模式: {target}，可选 order/list/single/random")
        return False
    ensure_running(cfg)
    activate_window(cfg)
    pos = _find_mode_button(cfg)
    if pos is None:
        return False
    ensure_front(cfg)  # 物理点击前保证窗口在最前
    pyautogui.click(pos[0], pos[1])
    time.sleep(0.8)  # 等菜单弹出
    tpl, desc = _MODE_MENU[target]
    if not _click_menu_item(tpl, desc):
        return False
    time.sleep(0.3)
    print(f"[mode] 已切换到: {desc}")
    return True
