# -*- coding: utf-8 -*-
"""基础播放控制：播放/暂停、上一首、下一首、音量。

通道优先级：系统媒体键（最稳定，QQ音乐默认响应） -> QQ音乐全局快捷键（兜底）。
"""
import time

import pyautogui

from .settings import load_config

# 指令名 -> 系统媒体键（pyautogui 键名）
_MEDIA_KEYS = {
    "play_pause": "playpause",
    "next": "nexttrack",
    "prev": "prevtrack",
    "volume_up": "volumeup",
    "volume_down": "volumedown",
    "mute": "volumemute",
}


def _press_media_key(action):
    """发送系统媒体键，返回是否已发送。"""
    key = _MEDIA_KEYS.get(action)
    if not key:
        return False
    pyautogui.press(key)
    print(f"[player] 已发送系统媒体键: {key}")
    return True


def _press_hotkey(action, cfg):
    """发送 QQ 音乐全局快捷键（兜底通道）。"""
    combo = cfg.get("hotkeys", {}).get(action)
    if not combo:
        return False
    pyautogui.hotkey(*combo)
    print(f"[player] 已发送全局快捷键: {'+'.join(combo)}")
    return True


def control(action, channel="media", cfg=None):
    """执行一次基础播放控制。

    action: play_pause / next / prev / volume_up / volume_down / mute
    channel: media（系统媒体键，默认）或 hotkey（QQ音乐全局快捷键）
    """
    cfg = cfg or load_config()
    ok = _press_media_key(action) if channel == "media" else _press_hotkey(action, cfg)
    if not ok:
        print(f"[player][错误] 未知指令或通道无映射: {action} / {channel}")
        return False
    time.sleep(0.2)  # 防止连续按键过快被客户端吞掉
    return True
