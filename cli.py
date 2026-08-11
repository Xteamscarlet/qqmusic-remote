# -*- coding: utf-8 -*-
"""命令行入口：QQ 音乐遥控。

用法：
  python cli.py next                      下一首
  python cli.py prev                      上一首
  python cli.py pause                     播放/暂停
  python cli.py volume up|down            音量加/减
  python cli.py mute                      静音切换
  python cli.py play_song "歌名"          搜索并播放歌曲
  python cli.py play_playlist [歌单名]    播放歌单（默认取 config 的 default_playlist）
  python cli.py mode order|random|single  切换播放模式
  python cli.py calibrate                 坐标校准向导
"""
import sys

from qqmusic_remote import mode as mode_mod
from qqmusic_remote import player, search
from qqmusic_remote.calibrate import run as calibrate_run

_ACTION_MAP = {
    "next": "next",
    "prev": "prev",
    "pause": "play_pause",
    "play": "play_pause",
    "mute": "mute",
}


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    cmd = argv[1]
    if cmd in _ACTION_MAP:
        return 0 if player.control(_ACTION_MAP[cmd]) else 1
    if cmd == "volume" and len(argv) >= 3:
        direction = "volume_up" if argv[2] == "up" else "volume_down"
        return 0 if player.control(direction) else 1
    if cmd == "play_song" and len(argv) >= 3:
        return 0 if search.play_song(" ".join(argv[2:])) else 1
    if cmd == "play_playlist":
        name = " ".join(argv[2:]) if len(argv) >= 3 else None
        return 0 if search.play_playlist(name) else 1
    if cmd == "mode" and len(argv) >= 3:
        return 0 if mode_mod.set_mode(argv[2]) else 1
    if cmd == "calibrate":
        calibrate_run()
        return 0
    print(f"[cli][错误] 未知命令: {' '.join(argv[1:])}")
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
