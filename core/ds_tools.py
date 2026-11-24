"""DS 页面的外挂能力：联网搜索 + 文件读取 + 计费换算。

搜索用 DuckDuckGo 的 HTML 端（不需要 key），抓前 4 条结果、取每个结果的前 1200 字。
文件在本地解：txt/md/py/json 直读；docx 解 zip 里的 document.xml；pdf 有 pypdf 就解，没有就报清楚。
"""

from __future__ import annotations

import io
import os
import re
import zipfile

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


from urllib.parse import quote as _q
from urllib.request import Request, urlopen


def _get(url: str, timeout: float = 12) -> str:
    req = Request(url, headers={"User-Agent": UA,
                                "Accept-Language": "zh-CN,zh;q=0.9",
                                "Accept": "text/html,application/xhtml+xml"})
    with urlopen(req, timeout=timeout) as r:
        raw = r.read()
    for enc in ("utf-8", "gbk", "latin-1"):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("utf-8", "ignore")


def _clean(html: str) -> str:
    html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?is)<br\s*/?>", "\n", html)
    html = re.sub(r"(?is)</p>", "\n\n", html)
    text = re.sub(r"(?s)<[^>]+>", "", html)
    text = (text.replace("&nbsp;", " ").replace("&amp;", "&")
                .replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"'))
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


JUNK_HOSTS = ("rili.com.cn", "tthuangli.com", "lishi.", "baike.baidu.com/item/今天",
              "huangli", "wannianli", "xingzuo", "zhihu.com/question/0")


def clean_query(q: str) -> str:
    """把口语问句压成搜索能用的短词；压得太短就退回原句。"""
    raw = q.strip()
    junk = ["怎么样", "怎么", "如何", "请问", "帮我", "帮忙", "查一下", "查查", "搜一下",
            "写一个", "写个", "写一段", "下一个", "来一个", "今天", "明天", "后天", "现在",
            "最近", "要不要", "要带", "带伞吗", "一下", "吗", "呢", "呀", "啊", "吧",
            "我", "你", "的", "了", "？", "?", "！", "，", ",", "。", "~"]
    q2 = raw
    for w in junk:
        q2 = q2.replace(w, " ")
    q2 = " ".join(q2.split())

    # 代码/算法类：补上"代码 示例"，别让搜索去查字义
    code_hint = any(k in raw for k in ("排序", "算法", "函数", "代码", "脚本", "实现", "bug", "报错"))
    if code_hint and q2:
        q2 = q2 + " 代码 示例"

    if len(q2) < 2:
        return raw[:30]
    return q2[:40]


def _keep(title: str, url: str, query: str) -> bool:
    """标题里至少命中查询里的一个 2 字词，否则当噪声丢掉。"""
    words = [w for w in query.split() if len(w) >= 2]
    if not words:
        return True
    return any(w in title for w in words)


def _bing(query: str, limit: int):
    html = _get("https://cn.bing.com/search?q=%s&setlang=zh-CN" % _q(query))
    out = []
    for m in re.finditer(r'<li class="b_algo".*?</li>', html, re.S):
        block = m.group(0)
        a = re.search(r'<h2[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
        if not a:
            continue
        url = a.group(1)
        title = _clean(a.group(2))
        snip = ""
        s = re.search(r'<p[^>]*>(.*?)</p>', block, re.S)
        if s:
            snip = _clean(s.group(1))
        if any(j in url for j in JUNK_HOSTS):
            continue
        if not _keep(title, url, query):
            continue
        out.append((title, url, snip))
        if len(out) >= limit:
            break
    return out


def _baidu(query: str, limit: int):
    html = _get("https://www.baidu.com/s?wd=%s" % _q(query))
    out = []
    for m in re.finditer(r'<h3[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, re.S):
        url = m.group(1)
        title = _clean(m.group(2))
        if not title:
            continue
        out.append((title, url, ""))
        if len(out) >= limit:
            break
    return out


def search_web(query: str, limit: int = 4, per_page: int = 1200):
    """依次试 Bing / 百度，都失败返回空。"""
    query = clean_query(query)
    hits = []
    for fn in (_bing, _baidu):
        try:
            hits = fn(query, limit)
        except Exception as e:
            print("[搜索] %s 失败: %s" % (fn.__name__, e), flush=True)
            hits = []
        if hits:
            break

    if not hits:
        return []

    out = []
    for title, url, snip in hits:
        if not snip:
            try:
                snip = _clean(_get(url, timeout=8))[:per_page]
            except Exception:
                snip = ""
        out.append((title, url, snip))
    return out


def weather_block(query: str) -> str:
    """天气走 wttr.in（免 key），比抓网页可靠。"""
    import json as _json
    import re as _re
    import urllib.parse as _up

    m = _re.search(r"([\u4e00-\u9fff]{2,6})", query)
    city = m.group(1) if m else "杭州"
    url = "https://wttr.in/%s?format=j1&lang=zh" % _up.quote(city)
    try:
        raw = _get(url, timeout=12)
        d = _json.loads(raw)
    except Exception as e:
        print("[天气] 失败:", e, flush=True)
        return ""

    cur = (d.get("current_condition") or [{}])[0]
    days = d.get("weather") or []
    lines = ["[实时天气] %s：%s°C（体感 %s°C），湿度 %s%%，%s" % (
        city, cur.get("temp_C"), cur.get("FeelsLikeC"), cur.get("humidity"),
        (cur.get("lang_zh") or cur.get("weatherDesc") or [{}])[0].get("value", ""))]
    for day in days[:2]:
        desc = (day.get("hourly") or [{}])[4].get("lang_zh") or ""
        if isinstance(desc, list):
            desc = desc[0].get("value", "") if desc else ""
        lines.append("%s：%s~%s°C，%s" % (day.get("date"), day.get("mintempC"),
                                          day.get("maxtempC"), desc))
    lines.append("来源：wttr.in（实时抓取）")
    return "\n".join(lines)


def search_block(query: str) -> str:
    """把搜索整理成一段可塞进 prompt 的文字。"""
    if "天气" in query or "气温" in query or "下雨" in query:
        w = weather_block(query)
        if w:
            return w + "\n\n（以上为实时抓取，具体以官方预报为准）"
    rows = search_web(query)
    if not rows:
        return ""
    import datetime
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    parts = ["[联网搜索结果] 查询：%s　今天是 %s。"
             "请优先依据下面的结果回答，并在句末注明来源链接；"
             "如果结果里没有答案，就直说没查到，不要编。" % (query, today)]
    for i, (title, url, snippet) in enumerate(rows, 1):
        parts.append("【结果 %d】%s\n%s\n来源：%s" % (i, title, snippet or "（抓取失败）", url))
    return "\n\n".join(parts)


def read_file(path: str, max_chars: int = 60000) -> str:
    """把文件解成纯文本。解不了就返回带原因的空串。"""
    ext = os.path.splitext(path)[1].lower()

    if ext in (".txt", ".md", ".py", ".json", ".csv", ".log", ".html", ".htm", ".yaml", ".yml"):
        try:
            with io.open(path, encoding="utf-8", errors="ignore") as f:
                return f.read()[:max_chars]
        except Exception as e:
            return ""

    if ext == ".docx":
        try:
            with zipfile.ZipFile(path) as z:
                xml = z.read("word/document.xml").decode("utf-8", "ignore")
            xml = xml.replace("</w:p>", "\n")
            text = re.sub(r"<[^>]+>", "", xml)
            return text[:max_chars]
        except Exception:
            return ""

    if ext == ".pdf":
        try:
            from pypdf import PdfReader
            reader = PdfReader(path)
            buf = []
            for page in reader.pages[:40]:
                buf.append(page.extract_text() or "")
            return ("\n".join(buf))[:max_chars]
        except Exception as e:
            return ""

    return ""


# ---------- 计费 ----------

PRICE_IN = 4.0      # 元 / 百万 token
PRICE_OUT = 16.0
MARKUP = 3.0        # 用户按 API 价三倍


def estimate_tokens(text: str) -> int:
    """粗估：中文按 1 字 1 token，其他按 4 字符 1 token。"""
    if not text:
        return 0
    zh = len(re.findall(r"[\u4e00-\u9fff]", text))
    other = max(0, len(text) - zh)
    return int(zh + other / 4) + 1


def cost_yuan(prompt_tokens: int, completion_tokens: int) -> float:
    raw = (prompt_tokens * PRICE_IN + completion_tokens * PRICE_OUT) / 1_000_000
    return round(raw * MARKUP, 6)
