# -*- coding: utf-8 -*-
"""校准向导：逐项记录 QQ 音乐界面元素的屏幕坐标，写入 config.yaml。

QQ 音乐是自绘界面且布局随版本变化，坐标校准是 UI 自动化的兜底基础。
QQ 音乐升级/换肤/改分辨率后，重跑本向导即可恢复。
"""
import time

import pyautogui

from .controller import activate_window, ensure_running
from .settings import load_config, save_config

# 需要校准的点位（键名与 config.yaml coords 一致）
_POINTS = [
    ("search_box", "主界面顶部的【搜索框】中心"),
    ("search_first_result", "搜索任意歌后，结果列表【第一首歌的播放按钮】（鼠标悬停歌曲行左侧出现的 ▶）"),
    ("playlist_tab", "搜索结果页顶部的【歌单】标签"),
    ("playlist_first", "歌单结果列表的【第一个歌单封面】中心"),
    ("playlist_play_all", "歌单详情页的【播放全部】按钮"),
    ("play_mode_button", "底部播放栏的【播放模式】按钮（顺序/随机/单曲循环图标）"),
]


def run():
    """交互式校准：提示用户把鼠标移到目标位置，按回车采样坐标。"""
    cfg = load_config()
    ensure_running(cfg)
    activate_window(cfg)
    print("=" * 60)
    print("QQ 音乐坐标校准向导")
    print("每个步骤：把鼠标移动到目标位置 -> 回到本窗口按回车采样")
    print("输入 s 回车可跳过某一项（保留原值）")
    print("=" * 60)
    coords = cfg.setdefault("coords", {})
    for key, desc in _POINTS:
        while True:
            ans = input(f"\n[{key}] 请把鼠标移到 {desc}，然后按回车（s 跳过）: ").strip().lower()
            if ans == "s":
                print(f"  已跳过 {key}")
                break
            if ans == "":
                x, y = pyautogui.position()
                coords[key] = [x, y]
                print(f"  已记录 {key} = ({x}, {y})")
                break
            print("  输入无效：直接回车采样，或 s 跳过")
        time.sleep(0.2)
    save_config(cfg)
    print("\n校准完成，已写入 config.yaml")


if __name__ == "__main__":
    run()
