"""B 站二维码登录：生成二维码、轮询状态、解析 Cookie、查登录态。

仅依赖标准库。对外接口：
- generate_qrcode() -> (url, key)
- poll_qrcode(key)   -> (state, message, confirmed_url_or_None)
- parse_cookies_from_url(url) -> dict
- write_cookies_txt(cookies, path)
- read_cookies_txt(path) -> dict
- check_login(cookies) -> (is_login, uname)
"""

import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

GENERATE_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
POLL_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"
NAV_URL = "https://api.bilibili.com/x/web-interface/nav"

# 轮询返回 data.code 的含义（注意：0 才是登录成功，86090 是已扫码未确认，别搞反）
CODE_CONFIRMED = 0      # 登录成功（已扫码并确认，此时 data.url 带 Cookie）
CODE_SCANNED = 86090    # 已扫码，未确认（继续轮询等确认）
CODE_EXPIRED = 86038    # 二维码已失效
CODE_UNSCANNED = 86101  # 未扫码


def _get(url, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


DEBUG_LOG = os.path.join(
    os.environ.get("ProgramData", r"C:\ProgramData"),
    "BilibiliVideoDownloader",
    "login_debug.log",
)


def _debug(msg):
    try:
        with open(DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (time.strftime("%H:%M:%S"), msg))
    except OSError:
        pass


def _parse_set_cookie(headers):
    """从 Set-Cookie 响应头列表解析出 {name: value}。"""
    cookies = {}
    for h in headers:
        first = h.split(";")[0].strip()
        if "=" in first:
            name, _, value = first.partition("=")
            name = name.strip()
            value = value.strip()
            if name:
                cookies[name] = value
    return cookies


def generate_qrcode():
    """生成二维码，返回 (qrcode_url, qrcode_key)。"""
    data = _get(GENERATE_URL, headers={"Referer": "https://passport.bilibili.com/login"})
    if data.get("code") != 0:
        raise RuntimeError("生成二维码失败: %r" % data)
    d = data["data"]
    _debug("generate url=%s | key=%s" % (d["url"], d["qrcode_key"]))
    return d["url"], d["qrcode_key"]


def poll_qrcode(key):
    """轮询扫码状态，返回 (state, message, cookies)。

    state 取值：waiting / scanned / confirmed / expired。
    cookies 仅在 confirmed 时有值（dict），从 Set-Cookie 头 + data.url 合并。
    """
    req = urllib.request.Request(
        POLL_URL + "?" + urllib.parse.urlencode({"qrcode_key": key}),
        headers={
            "User-Agent": UA,
            "Referer": "https://passport.bilibili.com/login",
            "Origin": "https://passport.bilibili.com",
            "Cookie": "SESSDATA=",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        set_cookie_headers = resp.headers.get_all("Set-Cookie") or []

    d = data.get("data") or {}
    code = d.get("code")
    _debug("poll key=%s code=%s data=%s" % (key, code, json.dumps(d, ensure_ascii=False)[:300]))

    if code == CODE_UNSCANNED:
        return "waiting", d.get("message", "等待扫码"), None
    if code == CODE_SCANNED:
        return "scanned", d.get("message", "已扫码，请在手机上确认"), None
    if code == CODE_CONFIRMED:
        cookies = _parse_set_cookie(set_cookie_headers)
        url = d.get("url", "")
        if url:
            url_cookies = parse_cookies_from_url(url)
            # 只合并非空值，避免 URL 里的空字段覆盖 Set-Cookie 的有效值
            for k, v in url_cookies.items():
                if v:
                    cookies[k] = v
        # 部分版本在 data.cookie_info.cookies 数组里返回 Cookie，一并提取
        cookie_info = d.get("cookie_info") or {}
        for c in (cookie_info.get("cookies") or []):
            name = c.get("name")
            value = c.get("value")
            if name and value:
                cookies[name] = value
        _debug("confirmed cookies keys=%s SESSDATA_len=%d" % (sorted(cookies.keys()), len(cookies.get("SESSDATA", ""))))
        return "confirmed", "登录成功", cookies
    if code == CODE_EXPIRED:
        return "expired", "二维码已失效，请刷新", None
    return "waiting", d.get("message", "未知状态"), None


def parse_cookies_from_url(url):
    """从确认后的 crossDomain URL 里解析出 SESSDATA / bili_jct / DedeUserID。"""
    query = urllib.parse.urlsplit(url).query
    params = urllib.parse.parse_qs(query)

    def first(k):
        v = params.get(k)
        return v[0] if v else ""

    cookies = {
        "SESSDATA": first("SESSDATA"),
        "bili_jct": first("bili_jct"),
        "DedeUserID": first("DedeUserID"),
    }
    try:
        cookies["expires"] = int(first("Expires")) if first("Expires") else 0
    except ValueError:
        cookies["expires"] = 0
    return cookies


def write_cookies_txt(cookies, path):
    """把 cookie 写成 Netscape 格式的 cookies.txt（yt-dlp --cookies 可直接用）。"""
    path = Path(path)
    expires = cookies.get("expires") or int(time.time()) + 180 * 86400
    lines = [
        "# Netscape HTTP Cookie File",
        "# This file is generated by the downloader. Do not edit.",
        "",
    ]
    for name in ("SESSDATA", "bili_jct", "DedeUserID"):
        val = cookies.get(name, "")
        if val:
            lines.append(
                ".bilibili.com\tTRUE\t/\tTRUE\t%d\t%s\t%s" % (expires, name, val)
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_cookies_txt(path):
    """读取 cookies.txt，返回 {name: value}。"""
    path = Path(path)
    cookies = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 7 and parts[5] and parts[6]:
                cookies[parts[5]] = parts[6]
    except OSError:
        pass
    return cookies


def check_login(cookies):
    """调用 B 站 nav 接口判断是否已登录，返回 (is_login, uname)。"""
    header = "; ".join("%s=%s" % (k, v) for k, v in cookies.items() if v)
    data = _get(NAV_URL, headers={"Cookie": header})
    d = data.get("data") or {}
    return bool(d.get("isLogin")), d.get("uname", "") or ""
