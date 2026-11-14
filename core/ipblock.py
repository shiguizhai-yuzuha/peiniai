# -*- coding: utf-8 -*-
"""IP 地区拦截（默认关闭）

设计原则：
  1. 默认关闭。配置文件不存在 = 关闭。
  2. 失败放行（fail-open）。查不到、超时、解析出错 —— 一律允许通过。
     宁可漏掉一个人，也不能因为一次网络抖动把所有人挡在门外。
  3. 关闭时零开销：只做一次 os.stat，不查库、不联网。
  4. 纯 ASGI 中间件，不缓冲响应，不影响流式输出。
  5. 本机 / 内网地址永不拦截。
"""

import asyncio
import json
import os
import threading
import time
import urllib.parse
import urllib.request

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "ipblock.json")

CACHE_TTL = 12 * 3600      # 同一 IP 12 小时内只查一次
LOOKUP_TIMEOUT = 2.5       # 查询超时就放行

# ---------------- 配置读取（按 mtime 热更新） ----------------
_cfg_lock = threading.Lock()
_cfg_cache = {"mtime": None, "enabled": False, "blocked": []}


def _read_config():
    """读 ipblock.json。文件不存在/坏掉 → 关闭。改文件不用重启。"""
    try:
        st = os.stat(CONFIG_PATH)
        mtime = st.st_mtime
    except OSError:
        return {"enabled": False, "blocked": []}

    with _cfg_lock:
        if _cfg_cache["mtime"] == mtime:
            return _cfg_cache
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                raw = json.load(f)
            enabled = bool(raw.get("enabled", False))
            blocked = [str(x).strip() for x in (raw.get("blocked") or []) if str(x).strip()]
        except Exception:
            # 配置坏了 = 关闭，绝不因为配置错误把人挡在外面
            enabled, blocked = False, []
        _cfg_cache.update({"mtime": mtime, "enabled": enabled, "blocked": blocked})
        return _cfg_cache


# ---------------- 地理位置查询（带缓存） ----------------
_cache = {}
_cache_lock = threading.Lock()


def _is_private(ip):
    if not ip:
        return True
    if ip in ("127.0.0.1", "::1", "localhost"):
        return True
    for p in ("10.", "192.168.", "172.16.", "172.17.", "172.18.", "172.19.",
              "172.20.", "172.21.", "172.22.", "172.23.", "172.24.", "172.25.",
              "172.26.", "172.27.", "172.28.", "172.29.", "172.30.", "172.31.",
              "169.254."):
        if ip.startswith(p):
            return True
    return False


def _lookup(ip):
    """返回 (city, region)。失败返回 (None, None)，调用方据此放行。"""
    url = ("http://ip-api.com/json/%s?lang=zh-CN&fields=status,country,regionName,city"
           % urllib.parse.quote(ip))
    try:
        with urllib.request.urlopen(url, timeout=LOOKUP_TIMEOUT) as r:
            data = json.loads(r.read().decode("utf-8", "ignore"))
        if data.get("status") != "success":
            return None, None
        return (data.get("city") or ""), (data.get("regionName") or "")
    except Exception:
        return None, None


def _geo(ip):
    now = time.time()
    with _cache_lock:
        hit = _cache.get(ip)
        if hit and now - hit[2] < CACHE_TTL:
            return hit[0], hit[1]
    city, region = _lookup(ip)
    with _cache_lock:
        _cache[ip] = (city, region, now)
    return city, region


def is_blocked(ip):
    """True = 拦截。任何不确定的情况都返回 False。"""
    try:
        cfg = _read_config()
        if not cfg["enabled"] or not cfg["blocked"]:
            return False
        if _is_private(ip):
            return False

        city, region = _geo(ip)
        if not city and not region:
            return False          # 查不到 → 放行

        haystack = "%s %s" % (city or "", region or "")
        for kw in cfg["blocked"]:
            if kw and kw in haystack:
                print(f"[IP拦截] {ip} → {city}/{region}（命中「{kw}」）", flush=True)
                return True
        return False
    except Exception as e:
        # 任何意外都不挡人
        print(f"[IP拦截] 判定异常，放行：{e}", flush=True)
        return False


def client_ip(scope_headers, fallback=""):
    """从 X-Forwarded-For / X-Real-IP 取真实 IP（nginx 在后面）。"""
    xff = ""
    for k, v in scope_headers:
        name = k.decode("latin-1").lower() if isinstance(k, bytes) else str(k).lower()
        if name == "x-forwarded-for":
            xff = v.decode("latin-1") if isinstance(v, bytes) else str(v)
            break
        if name == "x-real-ip" and not xff:
            xff = v.decode("latin-1") if isinstance(v, bytes) else str(v)
    if xff:
        return xff.split(",")[0].strip()
    return fallback or ""


BLOCK_HTML = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>无法访问</title>
<style>
 body{margin:0;height:100vh;display:flex;align-items:center;justify-content:center;
      background:#111418;color:#c9ced6;font-family:system-ui,-apple-system,"PingFang SC",sans-serif}
 .box{text-align:center;padding:0 24px}
 h1{font-size:17px;font-weight:500;letter-spacing:.08em;margin:0 0 14px}
 p{font-size:13px;color:#7b8189;margin:0;letter-spacing:.04em}
</style></head>
<body><div class="box">
<h1>当前网络无法访问</h1>
<p>请更换网络后重试</p>
</div></body></html>"""


class IPBlockMiddleware:
    """纯 ASGI 中间件：不缓冲响应，不影响流式输出。"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http":
            try:
                cfg = _read_config()
                if cfg["enabled"] and cfg["blocked"]:
                    headers = scope.get("headers") or []
                    client = scope.get("client") or ("", 0)
                    ip = client_ip(headers, client[0] if client else "")
                    if ip and await asyncio.to_thread(is_blocked, ip):
                        body = BLOCK_HTML.encode("utf-8")
                        await send({
                            "type": "http.response.start",
                            "status": 403,
                            "headers": [
                                (b"content-type", b"text/html; charset=utf-8"),
                                (b"content-length", str(len(body)).encode()),
                                (b"cache-control", b"no-store"),
                            ],
                        })
                        await send({"type": "http.response.body", "body": body})
                        return
            except Exception as e:
                # 中间件本身出错，也绝不挡人
                print(f"[IP拦截] 检查异常，放行：{e}", flush=True)

        await self.app(scope, receive, send)
