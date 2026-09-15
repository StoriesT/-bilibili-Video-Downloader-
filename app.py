"""Bilibili 高清下载器 —— 本地 Web 服务入口。

仅依赖标准库。启动后自动打开浏览器。
"""

import json
import os
import shutil
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import bilibili_login
import downloader

def _is_frozen():
    return getattr(sys, "frozen", False)


def _exe_dir():
    """可执行文件所在目录：打包后为 exe 同目录（找外部 yt-dlp/ffmpeg），源码运行即项目目录。"""
    if _is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _bundle_dir():
    """打包资源目录（static 等）：打包后为 PyInstaller 解包目录，源码运行即项目目录。"""
    if _is_frozen():
        return Path(getattr(sys, "_MEIPASS", str(_exe_dir())))
    return Path(__file__).resolve().parent


ROOT = _exe_dir()
STATIC_DIR = _bundle_dir() / "static"
OUTPUT_DIR = Path.home() / "Downloads"


def _resolve_ytdlp():
    """定位 yt-dlp：优先同目录 YT-DLP\yt-dlp.exe，回退到系统 PATH 里的 yt-dlp。"""
    bundled = ROOT / "YT-DLP" / "yt-dlp.exe"
    if bundled.is_file():
        return str(bundled)
    if shutil.which("yt-dlp"):
        return "yt-dlp"
    return str(bundled)  # 都没有：保留 bundled 路径，下载时给出清晰报错


def _resolve_ffmpeg_dir():
    """定位 ffmpeg：优先同目录 ffmpeg\bin；否则返回 None（不指定 --ffmpeg-location，
    由 yt-dlp 自行在系统 PATH 查找，找不到则降级为不合并）。"""
    bundled = ROOT / "ffmpeg" / "bin" / "ffmpeg.exe"
    if bundled.is_file():
        return str(ROOT / "ffmpeg" / "bin")
    return None


YTDLP = _resolve_ytdlp()
FFMPEG_DIR = _resolve_ffmpeg_dir()


def _data_dir():
    """登录状态存储目录：优先 C:\\ProgramData\\BilibiliVideoDownloader（机器级），
    不可写时依次回退到 LOCALAPPDATA、项目目录。"""
    program_data = Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "BilibiliVideoDownloader"
    local_appdata = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "BilibiliVideoDownloader"
    for d in (program_data, local_appdata):
        try:
            d.mkdir(parents=True, exist_ok=True)
            probe = d / ".write_test"
            probe.write_text("", encoding="utf-8")
            probe.unlink()
            return d
        except OSError:
            continue
    fallback = ROOT / "BilibiliVideoDownloader"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


DATA_DIR = _data_dir()
COOKIES_TXT = DATA_DIR / "cookies.txt"

HOST = "127.0.0.1"
PORT = 17848

manager = downloader.DownloadManager(YTDLP, FFMPEG_DIR, OUTPUT_DIR, COOKIES_TXT)


class Handler(BaseHTTPRequestHandler):
    server_version = "BiliDownloader/1.0"

    def log_message(self, *args):
        pass  # 静默默认访问日志

    # ---- 基础响应 ----
    def _json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path, ctype):
        if not path.is_file():
            self.send_error(404)
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _static_type(self, suffix):
        return {
            ".html": "text/html",
            ".css": "text/css",
            ".js": "application/javascript",
            ".svg": "image/svg+xml",
        }.get(suffix, "application/octet-stream")

    # ---- 路由 ----
    def do_GET(self):
        u = urlparse(self.path)
        p = u.path

        if p == "/":
            return self._send_file(STATIC_DIR / "index.html", "text/html; charset=utf-8")

        if p == "/help":
            return self._send_file(STATIC_DIR / "help.html", "text/html; charset=utf-8")

        if p.startswith("/static/"):
            rel = p[len("/static/"):]
            f = (STATIC_DIR / rel).resolve()
            if not str(f).startswith(str(STATIC_DIR.resolve())):
                return self.send_error(403)
            return self._send_file(f, self._static_type(f.suffix) + "; charset=utf-8")

        if p == "/api/login/status":
            return self._handle_login_status()

        if p == "/api/login/poll":
            return self._handle_login_poll(u.query)

        if p == "/api/download/status":
            return self._json(manager.get_status())

        return self.send_error(404)

    def do_POST(self):
        u = urlparse(self.path)
        p = u.path

        if p == "/api/login/start":
            return self._handle_login_start()

        if p == "/api/download":
            return self._handle_download()

        if p == "/api/download/cancel":
            manager.cancel()
            return self._json({"ok": True})

        if p == "/api/open-folder":
            return self._handle_open_folder()

        return self.send_error(404)

    # ---- 登录 ----
    def _handle_login_start(self):
        try:
            url, key = bilibili_login.generate_qrcode()
        except Exception as e:
            return self._json({"ok": False, "error": str(e)})
        return self._json({"ok": True, "qrcode_url": url, "qrcode_key": key})

    def _handle_login_poll(self, query):
        key = parse_qs(query).get("key", [None])[0]
        if not key:
            return self._json({"ok": False, "error": "缺少 key"})
        try:
            state, message, cookies = bilibili_login.poll_qrcode(key)
        except Exception as e:
            return self._json({"ok": False, "error": str(e)})

        if state == "confirmed" and cookies:
            try:
                bilibili_login.write_cookies_txt(cookies, COOKIES_TXT)
            except OSError as e:
                return self._json({"ok": False, "error": "保存登录状态失败：%s" % e})
            return self._json({"ok": True, "state": "confirmed", "message": message})

        return self._json({"ok": True, "state": state, "message": message})

    def _handle_login_status(self):
        if not COOKIES_TXT.exists():
            return self._json({"logged_in": False, "uname": ""})
        cookies = bilibili_login.read_cookies_txt(COOKIES_TXT)
        try:
            ok, uname = bilibili_login.check_login(cookies)
        except Exception:
            ok, uname = False, ""
        return self._json({"logged_in": ok, "uname": uname or ""})

    # ---- 下载 ----
    def _handle_download(self):
        try:
            n = int(self.headers.get("Content-Length", 0) or 0)
            body = json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:
            return self._json({"ok": False, "error": "请求解析失败"})

        urls = body.get("urls") or []
        if isinstance(urls, str):
            urls = [urls]
        result = manager.start(urls)
        if not result.get("ok"):
            return self._json({"ok": False, "error": result.get("error")})
        return self._json({"ok": True})

    def _handle_open_folder(self):
        try:
            os.startfile(str(OUTPUT_DIR))  # Windows 下用资源管理器打开下载文件夹
        except Exception as e:
            return self._json({"ok": False, "error": str(e)})
        return self._json({"ok": True, "path": str(OUTPUT_DIR)})


def main():
    args = sys.argv[1:]
    no_browser = "--no-browser" in args
    port = PORT
    if "--port" in args:
        try:
            port = int(args[args.index("--port") + 1])
        except (ValueError, IndexError):
            pass

    try:
        server = ThreadingHTTPServer((HOST, port), Handler)
    except OSError as e:
        print("启动失败：端口 %d 可能被占用。%s" % (port, e))
        return

    url = "http://%s:%d" % (HOST, port)
    print("=" * 50)
    print("  Bilibili 高清下载器已启动")
    print("  地址：%s" % url)
    print("  yt-dlp：%s" % YTDLP)
    print("  ffmpeg：%s" % (FFMPEG_DIR or "系统 PATH 自动查找"))
    print("  登录数据：%s" % DATA_DIR)
    print("  请勿关闭本窗口，关闭即停止服务。")
    print("=" * 50)
    if not no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
