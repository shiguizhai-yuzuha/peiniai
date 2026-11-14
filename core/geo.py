# core/geo.py
"""IP → 地区（城市级）。

⚠️ 默认关闭（ENABLED = False），且没有任何地方调用它。
   要启用：把 ENABLED 改 True，再在需要的地方显式调 client_ip() / region_tag()。

设计原则：
1. 默认关闭，而且一个开关能整体关掉
2. 任何异常都不往上抛 —— 查不到就 UNKNOWN，绝不让聊天挂掉
3. 内网 IP 不联网，直接返回 LOCAL
4. 结果按 IP 缓存在内存里，同一个 IP 只查一次
5. 只用标准库，不引第三方依赖

特殊值：
    region_tag() 返回
      REGION_MAINLAND = "CN"       中国大陆
      REGION_FOREIGN  = "FOREIGN"  港澳台 + 海外  ← 你要的那个特殊值
      REGION_LOCAL    = "LOCAL"    本机/内网
      REGION_UNKNOWN  = "UNKNOWN"  没启用、查不到、或解析失败
"""

import ipaddress
import json
import time
import urllib.request

ENABLED = False          # ← 总开关，改 True 才开始工作
TIMEOUT = 2.5            # 单次查询超时（秒）
CACHE_TTL = 6 * 3600     # 缓存 6 小时

REGION_MAINLAND = "CN"
REGION_FOREIGN = "FOREIGN"
REGION_LOCAL = "LOCAL"
REGION_UNKNOWN = "UNKNOWN"

# 港澳台：有些 IP 库会把它们标成 CN，用地区名再兜一道
_FOREIGN_REGION_HINTS = ("香港", "澳门", "澳門", "台湾", "臺灣")

_cache = {}              # ip -> (时间戳, dict 或 None)


# ─────────────────────────── IP 提取 ───────────────────────────

def _header(headers, key: str) -> str:
    """兼容 dict 和 starlette 的 Headers（后者本来就大小写不敏感）。"""
    if not headers:
        return ""
    # 先按原样试一次（starlette Headers 走这条）
    try:
        v = headers.get(key)
        if v:
            return str(v).strip()
    except Exception:
        pass
    # 再逐个比较（普通 dict 的 key 是大小写敏感的，X-Real-IP 这种要这么找）
    try:
        for k, v in headers.items():
            if str(k).lower() == key.lower() and v:
                return str(v).strip()
    except Exception:
        pass
    return ""


def client_ip(request, default: str = "") -> str:
    """从请求里取真实 IP。

    反代后面 request.client.host 是 nginx 的地址，
    所以必须优先读 X-Real-IP / X-Forwarded-For。
    nginx 里已经配了 `proxy_set_header X-Real-IP $remote_addr;`
    """
    if request is None:
        return default
    headers = getattr(request, "headers", None)
    for key in ("x-real-ip", "x-forwarded-for"):
        v = _header(headers, key)
        if v:
            return v.split(",")[0].strip()
    client = getattr(request, "client", None)
    host = getattr(client, "host", None) if client else None
    return host or default


def is_private(ip: str) -> bool:
    """内网/本机/非法地址 → True（这些不联网查）。"""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True
    return addr.is_private or addr.is_loopback or addr.is_reserved


# ─────────────────────────── 查询 ───────────────────────────

def _fetch_geo(ip: str):
    """真的去查一次。失败返回 None，绝不抛。

    单独抽出来是为了测试时能替换掉（不联网也能测）。
    """
    url = (
        "http://ip-api.com/json/" + ip +
        "?lang=zh-CN&fields=status,countryCode,country,regionName,city"
    )
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None

    if not isinstance(data, dict) or data.get("status") != "success":
        return None

    return {
        "country_code": (data.get("countryCode") or "").upper(),
        "country": data.get("country") or "",
        "region": data.get("regionName") or "",
        "city": data.get("city") or "",
    }


def lookup(ip: str):
    """带缓存的地理查询。返回 dict 或 None。"""
    if not ip:
        return None

    now = time.time()
    hit = _cache.get(ip)
    if hit is not None and now - hit[0] < CACHE_TTL:
        return hit[1]

    info = _fetch_geo(ip)
    _cache[ip] = (now, info)
    return info


# ─────────────────────────── 对外 ───────────────────────────

def region_tag(ip: str) -> str:
    """返回地区标签。启用前永远返回 UNKNOWN。"""
    if not ENABLED:
        return REGION_UNKNOWN
    if not ip:
        return REGION_UNKNOWN
    if is_private(ip):
        return REGION_LOCAL

    info = lookup(ip)
    if not info:
        return REGION_UNKNOWN

    if info["country_code"] != "CN":
        return REGION_FOREIGN
    # 港澳台兜底：IP 库偶尔标成 CN
    for hint in _FOREIGN_REGION_HINTS:
        if hint in info["region"]:
            return REGION_FOREIGN
    return REGION_MAINLAND


def city_of(ip: str) -> str:
    """城市名，查不到返回空串。"""
    if not ENABLED or not ip or is_private(ip):
        return ""
    info = lookup(ip)
    return (info or {}).get("city", "")


def describe(ip: str) -> dict:
    """给外面用的完整描述。查不到也返回结构完整的 dict，不返回 None。"""
    empty = {
        "ip": ip or "",
        "region": REGION_UNKNOWN,
        "country": "",
        "province": "",
        "city": "",
    }
    if not ENABLED or not ip:
        return empty
    if is_private(ip):
        empty["region"] = REGION_LOCAL
        return empty

    info = lookup(ip)
    if not info:
        return empty

    region = REGION_MAINLAND
    if info["country_code"] != "CN":
        region = REGION_FOREIGN
    else:
        for hint in _FOREIGN_REGION_HINTS:
            if hint in info["region"]:
                region = REGION_FOREIGN

    return {
        "ip": ip,
        "region": region,
        "country": info["country"],
        "province": info["region"],
        "city": info["city"],
    }


def clear_cache():
    """测试用。"""
    _cache.clear()
