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


def search_block(query: str) -> str:
    """把搜索整理成一段可塞进 prompt 的文字。"""
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
