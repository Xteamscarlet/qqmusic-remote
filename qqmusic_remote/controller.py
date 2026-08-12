# -*- coding: utf-8 -*-
"""进程与窗口控制：探测/启动 QQ 音乐进程，激活主窗口。"""
import ctypes
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


def _enum_main_window(process_name):
    """枚举目标进程的所有窗口，挑出'完整模式主窗口'。

    QQ 音乐会同时挂多个窗口：精简模式小窗（标题以'精简模式'开头）、
    完整模式主窗（面积大）。点 X 关主面板时主窗只是被隐藏（进程保留），
    因此隐藏窗口也参与候选，由 activate_window 负责恢复显示。
    返回 (hwnd, title) 或 (None, None)。
    """
    import win32gui
    import win32process

    # 先收集目标进程的 PID 集合
    try:
        out = subprocess.check_output(
            ["tasklist", "/FI", f"IMAGENAME eq {process_name}.exe", "/FO", "CSV", "/NH"],
            stderr=subprocess.DEVNULL,
        ).decode("gbk", errors="ignore")
        pids = {int(line.split('","')[1]) for line in out.strip().splitlines() if '","' in line}
    except Exception:
        return None, None
    if not pids:
        return None, None

    candidates = []

    def _cb(hwnd, _):
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if pid not in pids:
            return
        visible = win32gui.IsWindowVisible(hwnd)
        title = win32gui.GetWindowText(hwnd) or ""
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        area = max(0, right - left) * max(0, bottom - top)
        is_mini = title.startswith("精简模式")
        # 隐藏窗口 rect 无效（面积 0），但有曲目标题的就是完整模式主窗
        candidates.append((hwnd, title, area, is_mini, visible))

    win32gui.EnumWindows(_cb, None)
    # 优先级：非精简模式 > 可见 > 标题非空 > 标题像曲目('歌名 - 歌手') > 面积最大。
    # 隐藏窗口 rect 无效（面积不可信），'播放队列'等功能窗面积可能大于被隐藏的主窗，
    # 靠' - '特征把真正的主窗顶上来。
    candidates.sort(
        key=lambda c: (not c[3], c[4], bool(c[1].strip()), " - " in c[1], c[2]),
        reverse=True,
    )
    if not candidates:
        return None, None
    hwnd, title, area, is_mini, visible = candidates[0]
    if is_mini:
        print("[controller][警告] 只找到精简模式小窗，坐标类操作可能失效，建议切回完整模式")
    return hwnd, title


def _force_foreground(hwnd):
    """强力置前：先按一次 Alt 骗过 Windows 前台锁，再 AttachThreadInput 置前。

    直接 SetForegroundWindow 经常被系统拦截（进程不在前台时），
    这里用 Alt 键 + 线程输入附加的组合拳提高成功率。
    """
    import win32con
    import win32gui
    import win32process

    user32 = ctypes.windll.user32
    # 按/抬 Alt，解除前台设置限制
    user32.keybd_event(win32con.VK_MENU, 0, 0, 0)
    user32.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)

    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    else:
        win32gui.ShowWindow(hwnd, win32con.SW_SHOW)

    foreground = win32gui.GetForegroundWindow()
    cur_thread = ctypes.windll.kernel32.GetCurrentThreadId()
    fg_thread, _ = win32process.GetWindowThreadProcessId(foreground)
    tgt_thread, _ = win32process.GetWindowThreadProcessId(hwnd)

    attached = False
    for tid in (fg_thread, tgt_thread):
        if tid and tid != cur_thread:
            attached = user32.AttachThreadInput(cur_thread, tid, True) or attached
    try:
        win32gui.BringWindowToTop(hwnd)
        win32gui.SetForegroundWindow(hwnd)
        win32gui.SetActiveWindow(hwnd)
    finally:
        for tid in (fg_thread, tgt_thread):
            if tid and tid != cur_thread:
                user32.AttachThreadInput(cur_thread, tid, False)


def current_song(cfg=None):
    """读取 QQ 音乐主窗口标题（通常即当前播放曲目），用于播放结果验证。"""
    cfg = cfg or load_config()
    hwnd, title = _enum_main_window(cfg["qqmusic"]["process_name"])
    return title or ""


def ensure_front(cfg=None):
    """确保 QQ 音乐主窗口在最前（已是前台则跳过，避免多余置前动作带来的闪烁）。

    所有物理输入（pyautogui 点击/滚动/键盘）前都必须调用：
    PrintWindow 截图不依赖前台，但物理输入会落到遮挡窗口上。
    """
    import win32gui

    cfg = cfg or load_config()
    hwnd, _ = _enum_main_window(cfg["qqmusic"]["process_name"])
    if not hwnd:
        print("[controller][警告] 未找到 QQ 音乐窗口")
        return False
    if win32gui.GetForegroundWindow() == hwnd:
        return True
    return activate_window(cfg)


def activate_window(cfg=None):
    """把 QQ 音乐完整模式主窗口提到前台并聚焦。

    UI 自动化（点击搜索框等）前必须调用，否则坐标点击会落到别的窗口。
    修复点：不再取 top_window（常拿到精简模式小窗），而是按面积挑主窗口。
    """
    cfg = cfg or load_config()
    hwnd, title = _enum_main_window(cfg["qqmusic"]["process_name"])
    if not hwnd:
        print("[controller][警告] 未找到 QQ 音乐窗口")
        return False
    try:
        import win32con
        import win32gui

        if not win32gui.IsWindowVisible(hwnd):
            # 主面板被点 X 隐藏（进程仍在），先恢复显示再置前
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            print("[controller] 完整模式主窗被隐藏，已恢复显示")
            time.sleep(1.2)  # 等窗口布局完成
        _force_foreground(hwnd)
        time.sleep(0.6)
        print(f"[controller] 已聚焦窗口: {title!r}")
        return True
    except Exception as e:
        print(f"[controller][警告] 聚焦窗口失败: {e}")
        return False
