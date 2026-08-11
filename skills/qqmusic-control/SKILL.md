---
name: qqmusic-control
description: 控制本机 QQ 音乐客户端。触发词：播放/暂停、下一首、上一首、切歌、音量加/减、静音、播放歌单（如"新新歌单"）、播放某首歌（如"Dream It Possible"）、切换播放模式（顺序/随机/单曲循环）、校准。当用户想通过对话控制本机 QQ 音乐时使用。
---

# QQ 音乐遥控

通过命令行脚本控制本机 QQ 音乐客户端（Windows）。

## 执行方式

一律使用受管 Python 环境运行，工作目录为项目根目录 `D:\workbuddyQqMusic`：

```bash
PY="C:\\Users\\lenovo\\.workbuddy\\binaries\\python\\envs\\default\\Scripts\\python.exe"
"$PY" "D:\\workbuddyQqMusic\\cli.py" <命令>
```

## 指令映射（用户自然语言 -> 命令）

| 用户说 | 执行 |
|---|---|
| 下一首 / 切歌 / 换一首 | `next` |
| 上一首 | `prev` |
| 暂停 / 继续播放 / 播放暂停 | `pause` |
| 音量加 / 音量大一点 | `volume up` |
| 音量减 / 音量小一点 | `volume down` |
| 静音 | `mute` |
| 播放《XXX》/ 我想听 XXX | `play_song "XXX"` |
| 播放新新歌单 / 播放歌单 XXX | `play_playlist [XXX]`（不带名字时播 config 里的默认歌单"新新歌单"） |
| 切换为顺序播放 | `mode order` |
| 随机播放 | `mode random` |
| 单曲循环 | `mode single` |
| 校准 / 坐标不准了 | `calibrate`（交互式，需用户在终端操作，不适合在对话中直接跑，提示用户手动执行） |

## 注意事项

- 切歌/音量走系统媒体键，不需要 QQ 音乐在前台；搜索点播和歌单播放会激活 QQ 音乐窗口并模拟点击。
- 若 `play_song` / `play_playlist` / `mode` 报"缺少校准坐标"，提示用户在终端运行：`python cli.py calibrate` 完成一次坐标校准。
- 命令输出里 `[search]` / `[mode]` / `[player]` 前缀的日志即为执行证据，向用户转述结果时带上关键行。
- QQ 音乐路径、默认歌单、快捷键均可在项目根目录 `config.yaml` 中修改。
