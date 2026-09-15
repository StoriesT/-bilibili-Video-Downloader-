"""DownloadManager：后台调用 yt-dlp 下载，解析进度，维护共享状态。"""

import os
import re
import subprocess
import threading

PROGRESS_PREFIX = "PROGRESS:"


class DownloadManager:
    def __init__(self, ytdlp_path, ffmpeg_dir, output_dir, cookies_path):
        self.ytdlp = str(ytdlp_path)
        self.ffmpeg_dir = str(ffmpeg_dir) if ffmpeg_dir else None
        self.output_dir = str(output_dir)
        self.cookies_path = str(cookies_path)

        self._lock = threading.Lock()
        self._proc = None
        self._state = {
            "state": "idle",        # idle / running / done / error / cancelled
            "current_index": 0,     # 0-based，当前处理第几个链接
            "total": 0,
            "percent": None,        # float 或 None
            "speed": "",
            "eta": "",
            "message": "",
            "log": [],
        }

    # ---- 状态读取 ----
    def get_status(self):
        with self._lock:
            return dict(self._state)

    def _update(self, **kw):
        with self._lock:
            self._state.update(kw)

    def _log(self, text):
        with self._lock:
            self._state["log"].append(text)
            if len(self._state["log"]) > 200:
                self._state["log"] = self._state["log"][-200:]

    # ---- 控制 ----
    def start(self, urls):
        if self._state["state"] == "running":
            return {"ok": False, "error": "已有下载任务在进行中"}

        urls = [u.strip() for u in urls if u and u.strip()]
        if not urls:
            return {"ok": False, "error": "没有有效的链接"}

        self._update(
            state="running",
            current_index=0,
            total=len(urls),
            percent=None,
            speed="",
            eta="",
            message="",
            log=[],
        )
        t = threading.Thread(target=self._run, args=(urls,), daemon=True)
        t.start()
        return {"ok": True}

    def cancel(self):
        with self._lock:
            proc = self._proc
        if proc is not None and proc.poll() is None:
            try:
                proc.kill()
            except Exception:
                pass
        self._update(state="cancelled", message="已取消")

    # ---- 下载流程 ----
    def _run(self, urls):
        for i, url in enumerate(urls):
            self._update(current_index=i)
            self._log("[%d/%d] 开始下载：%s" % (i + 1, len(urls), url))
            if not self._download_one(url):
                return  # 出错/取消时 _download_one 已设置 state
        self._update(state="done", message="全部下载完成", percent=None)
        self._log("全部下载完成")

    def _download_one(self, url):
        cmd = [self.ytdlp]
        if self.ffmpeg_dir:
            cmd += ["--ffmpeg-location", self.ffmpeg_dir]
        cmd += [
            "-f", "bestvideo+bestaudio/best",
            "--merge-output-format", "mp4",
            "--windows-filenames",
            "--newline",
            "--progress-template",
            PROGRESS_PREFIX + "%(progress._percent_str)s|%(progress._speed_str)s|%(progress._eta_str)s",
            "-P", self.output_dir,
        ]
        if os.path.exists(self.cookies_path):
            cmd += ["--cookies", self.cookies_path]
        cmd.append(url)

        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding=None,  # 用系统默认编码（中文 Windows 为 GBK），避免中文标题乱码
                errors="replace",
                creationflags=creationflags,
            )
        except Exception as e:
            self._update(state="error", message="启动下载进程失败")
            self._log("[错误] %s" % e)
            return False

        with self._lock:
            self._proc = proc

        for raw in proc.stdout:
            line = raw.rstrip("\n").rstrip("\r")
            if line.startswith(PROGRESS_PREFIX):
                self._parse_progress(line[len(PROGRESS_PREFIX):])
            elif line.strip():
                s = line.strip()
                if any(k in s for k in ("[download]", "[Merger]", "ERROR", "has already been downloaded")):
                    self._log(s)

        code = proc.wait()
        with self._lock:
            if self._proc is proc:
                self._proc = None

        if self._state["state"] == "cancelled":
            return False
        if code != 0:
            self._update(state="error", message="第 %d 个链接下载失败" % (self._state["current_index"] + 1))
            self._log("[错误] yt-dlp 退出码 %d" % code)
            return False
        self._log("[完成] %s" % url)
        return True

    def _parse_progress(self, raw):
        # raw 形如 "34.5%|1.23MiB/s|00:45"
        parts = raw.split("|")
        percent = None
        speed = ""
        eta = ""
        if len(parts) >= 1:
            m = re.search(r"([\d.]+)%", parts[0])
            if m:
                percent = float(m.group(1))
        if len(parts) >= 2:
            speed = parts[1].strip()
        if len(parts) >= 3:
            eta = parts[2].strip()
        self._update(percent=percent, speed=speed, eta=eta)
