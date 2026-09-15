# Bilibili 高清下载器

一个本地运行的 B 站视频下载工具：浏览器网页界面 + 扫码登录，自动下载最高画质（视频流 + 音频流合并为 MP4）。

> ⚠️ **温馨提示与免责声明**
>
> - 本项目仅供个人学习、研究或存档使用，严禁用于任何商业用途！
> - 请支持正版，尊重创作者的劳动成果。
> - 部分受版权保护、加密或限时的免费视频也可能无法下载。
> - 因使用本服务产生的任何法律责任，由使用者自行承担。开始下载即表示同意此声明。

## 功能特性

- 🔐 **扫码登录**：用 B 站 App 扫码，登录后解锁 1080P，大会员解锁 1080P+/4K
- 🎬 **最高画质**：自动选择最高视频流 + 音频流，ffmpeg 合并输出 MP4
- 📥 **批量下载**：粘贴多个链接（每行一个）依次下载
- 📊 **实时进度**：网页显示下载进度 / 速度 / 剩余时间 / 日志
- 💾 **登录持久化**：登录状态保存在本机，重启免重复扫码
- 🖥 **零第三方依赖**：后端仅用 Python 标准库

## 运行环境

- Python 3.10+
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- [ffmpeg](https://www.gyan.dev/ffmpeg/builds/)

## 安装与运行

1. 安装 Python 3.10+。
2. 准备 yt-dlp 和 ffmpeg（二选一）：
   - **方式 A（免配置）**：下载 `yt-dlp.exe` 放到 `YT-DLP/` 目录、下载 ffmpeg 把 `ffmpeg.exe` 放到 `ffmpeg/bin/` 目录；
   - **方式 B（用系统已装的）**：`pip install yt-dlp`，并把 ffmpeg 装进系统 PATH（如 `winget install Gyan.FFmpeg`）。程序检测不到同目录二进制时，会自动回退使用系统 PATH 里的。
3. 双击 `启动网站.bat`（或命令行执行 `python app.py`），浏览器会自动打开操作页面。

## 目录结构

```
├── app.py                 # 后端入口：HTTP 服务 + 路由
├── bilibili_login.py      # B 站扫码登录
├── downloader.py          # 下载管理：调用 yt-dlp + 进度解析
├── static/                # 前端页面（含二维码库）
├── 启动网站.bat            # Windows 启动脚本
├── YT-DLP/yt-dlp.exe      # 需自行下载
└── ffmpeg/bin/ffmpeg.exe  # 需自行下载
```

## 开源软件声明

本项目使用了以下开源软件，特此声明并致谢：

| 组件 | 用途 | 许可证 |
|------|------|--------|
| [FFmpeg](https://ffmpeg.org) | 视频与音频合并 | GPL v3 |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | 视频解析与下载 | The Unlicense |
| [qrcode-generator](https://github.com/kazuhikoarase/qrcode-generator) | 二维码生成 | MIT |
| Python | 运行环境 | PSF License |

## License

本项目代码采用 [MIT License](LICENSE)。
