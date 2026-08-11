# -*- coding: utf-8 -*-
"""进程与窗口控制：探测/启动 QQ 音乐进程，激活主窗口。"""
import subprocess
import time

from .settings import load_config


def _find_process(process_name):
    """按进程名查找 QQ 音乐进程，找到返回 True。"""
    # 用 tasklist 避免额外依赖，输出为 GBK，按字节包含判断
    try:
        out = subprocess.check_output(
            ["tasklist", "/FI", f"IMAGENAME eq {process_name}.exe"],
            stderr=subprocess.DEVNULL,
        )
        return process_name.encode("gbk", errors="ignore").lower() in out.lower()
    except Exception:
        return False


def is_running(cfg=None):
    """判断 QQ 音乐是否已在运行。"""
    cfg = cfg or load_config()
    return _find_process(cfg["qqmusic"]["process_name"])


def ensure_running(cfg=None):
    """确保 QQ 音乐已启动：未运行则拉起进程并等待主窗口出现。

    返回 True 表示进程已就绪（不保证登录态，登录由用户事先完成）。
    """
    cfg = cfg or load_config()
    if is_running(cfg):
        print("[controller] QQ 音乐已在运行")
        return True
    exe = cfg["qqmusic"]["exe_path"]
    timeout = cfg["qqmusic"].get("start_timeout", 20)
    print(f"[controller] 启动 QQ 音乐: {exe}")
    subprocess.Popen([exe], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + timeout
    while time.time() < deadline:
        if is_running(cfg):
            # 进程起来后再等主窗口初始化
            time.sleep(3)
            print("[controller] QQ 音乐进程已就绪")
            return True
        time.sleep(0.5)
    print("[controller][警告] 等待超时，进程可能未正常启动")
    return False


def activate_window(cfg=None):
    """把 QQ 音乐主窗口提到前台并聚焦。

    UI 自动化（点击搜索框等）前必须调用，否则坐标点击会落到别的窗口。
    """
    cfg = cfg or load_config()
    try:
        from pywinauto import Application

        app = Application(backend="uia").connect(
            path=cfg["qqmusic"]["process_name"] + ".exe", timeout=5
        )
        win = app.top_window()
        win.set_focus()
        time.sleep(0.5)
        print(f"[controller] 已聚焦窗口: {win.window_text()!r}")
        return True
    except Exception as e:
        print(f"[controller][警告] 聚焦窗口失败: {e}")
        return False
