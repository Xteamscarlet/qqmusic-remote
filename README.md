# qqmusic-remote

用自然语言 / 命令行遥控本机 QQ 音乐客户端（Windows）的小工具。

## 功能

- 播放 / 暂停、上一首 / 下一首、音量加减、静音（系统媒体键通道，QQ 音乐无需在前台）
- 搜索并播放指定歌曲（如 `Dream It Possible`）
- 播放账号内的歌单（默认示例：`新新歌单`）
- 切换播放模式：顺序播放 / 随机播放 / 单曲循环
- 可作为 WorkBuddy 技能在对话中用自然语言触发（见 `skills/qqmusic-control/SKILL.md`）

## 原理

QQ 音乐桌面端没有开放 API，本项目组合三条控制通道：

1. **系统媒体键**：`pyautogui.press('nexttrack')` 等，QQ 音乐默认响应，最稳定；
2. **QQ 音乐全局快捷键**（`Ctrl+Alt+→` 等，需在客户端设置中开启）：媒体键的兜底；
3. **UI 自动化**：搜索点播、歌单播放、播放模式切换需要操作界面。优先用 UIA（pywinauto）定位控件；QQ 音乐是自绘界面，UIA 常失效，此时回退到**校准坐标 + 剪贴板粘贴 + 模拟点击**。

只模拟键鼠，不抓包、不逆向、不触碰账号数据。

## 快速开始

```bash
pip install -r requirements.txt
copy config.example.yaml config.yaml   # 修改 qqmusic.exe_path 为你的安装路径
python cli.py calibrate                # 首次使用：校准搜索框等坐标
```

### 命令一览

```bash
python cli.py next                       # 下一首
python cli.py prev                       # 上一首
python cli.py pause                      # 播放/暂停
python cli.py volume up|down             # 音量
python cli.py mute                       # 静音
python cli.py play_song "Dream It Possible"   # 搜索播歌
python cli.py play_playlist 新新歌单      # 播放歌单（省略名字则用默认歌单）
python cli.py mode order|random|single   # 播放模式
python cli.py calibrate                  # 坐标校准向导
```

## 坐标校准

搜索点播 / 歌单 / 播放模式依赖屏幕坐标。QQ 音乐升级、换肤、改窗口大小或换显示器后坐标会失效，重跑一次：

```bash
python cli.py calibrate
```

按提示把鼠标悬停到目标控件上按 Enter 即可，坐标会写入 `config.yaml`（含 DPI 缩放换算）。

## 配置说明（config.yaml）

| 键 | 说明 |
|---|---|
| `qqmusic.exe_path` | QQMusic.exe 完整路径 |
| `qqmusic.process_name` | 进程名（一般不用改） |
| `default_playlist` | 默认歌单名（如 `新新歌单`） |
| `hotkeys.*` | QQ 音乐全局快捷键映射（兜底通道） |
| `coords.*` | 校准产生的屏幕坐标（由 calibrate 写入） |

`config.yaml` 含本机路径与坐标，已在 `.gitignore` 中排除，不会被提交。

## 已知限制

- 媒体键在远程桌面 / 锁屏场景下可能被系统拦截，可在 QQ 音乐设置中开启全局快捷键作为兜底；
- 搜索播放依赖"第一个搜索结果"即目标歌曲，重名歌曲可能播错；
- 播放模式按钮是循环切换，UIA 读不到当前模式时只点一次并提示确认；
- 电视 / 音箱扩展的调研结论见 `docs/research.md`。

## License

MIT
