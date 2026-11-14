# -*- coding: utf-8 -*-
"""IP → 出发地城市。

规则（按用户 2026-10-28 定）：
  国内地级市        杭州 / 温州 / 金华        → 用它
  港澳台            台湾 / 香港 / 澳门        → 新艾利都
  国外             任意                      → 新艾利都
  定位失败 / 没 IP                            → 新艾利都
  出发地 == 目的地                            → 新艾利都

为什么重合也变新艾利都：
  重合就没有"来"和"去"了，一趟旅行就散了。
  干脆换成虚构城市，旅程还在。
"""

import json
import urllib.request

FALLBACK = "新艾利都"

# 港澳台的 region 关键词
HMT_KEYWORDS = ("台湾", "台灣", "香港", "澳门", "澳門", "Taiwan", "Hong Kong", "Macau", "Macao")

# 直辖市（ip-api 有时会给省名，这里兜一下）
MUNICIPALITIES = {"北京": "北京", "上海": "上海", "天津": "天津", "重庆": "重庆"}


def _http_json(url, timeout=3):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "peini/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except Exception as e:
        print("[定位] 请求失败：%s" % e, flush=True)
        return None


def locate(ip, destination=None, *, debug=False):
    """把 IP 变成一个出发地城市名。

    destination 给了的话，重合就返回新艾利都。
    """
    if not ip or ip.startswith(("127.", "10.", "192.168.", "172.16.", "172.17.",
                                "172.18.", "172.19.", "172.2", "172.30.", "172.31.")):
        if debug:
            print("[定位] 内网/空 IP → %s" % FALLBACK, flush=True)
        return FALLBACK

    # ip-api 免费版：45 次/分钟，只支持 http
    data = _http_json(
        "http://ip-api.com/json/%s?lang=zh-CN&fields=status,country,countryCode,regionName,city" % ip
    )
    if not data or data.get("status") != "success":
        return FALLBACK

    country = (data.get("countryCode") or "").upper()
    region = str(data.get("regionName") or "")
    city = str(data.get("city") or "").strip()

    # 国外
    if country != "CN":
        if debug:
            print("[定位] 非中国大陆（%s）→ %s" % (country, FALLBACK), flush=True)
        return FALLBACK

    # 港澳台
    if any(k in region for k in HMT_KEYWORDS):
        if debug:
            print("[定位] 港澳台（%s）→ %s" % (region, FALLBACK), flush=True)
        return FALLBACK

    if not city:
        return FALLBACK

    # 统一去掉后缀：「济南市」→「济南」
    for suf in ("市", "地区", "盟", "自治州", "特别行政区"):
        if city.endswith(suf):
            city = city[:-len(suf)]
            break

    # 直辖市归一下
    for name in MUNICIPALITIES:
        if name in city or name in region:
            city = MUNICIPALITIES[name]
            break

    # 重合
    if destination and city == destination:
        if debug:
            print("[定位] 出发地和目的地重合（%s）→ %s" % (city, FALLBACK), flush=True)
        return FALLBACK

    if debug:
        print("[定位] %s → %s（%s）" % (ip, city, region), flush=True)
    return city


def client_ip_from_headers(headers):
    """从请求头里拿真实 IP（nginx 反代下看 X-Forwarded-For）。"""
    try:
        xff = headers.get("x-forwarded-for") or headers.get("X-Forwarded-For")
        if xff:
            return xff.split(",")[0].strip()
        for k in ("x-real-ip", "X-Real-IP"):
            v = headers.get(k)
            if v:
                return v.strip()
    except Exception:
        pass
    return ""


if __name__ == "__main__":
    import sys

    ip = sys.argv[1] if len(sys.argv) > 1 else ""
    dest = sys.argv[2] if len(sys.argv) > 2 else None
    print("出发地：", locate(ip, dest, debug=True))
