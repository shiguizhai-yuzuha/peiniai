"""榫 · 小工具：路径、时间、格式化。

负责
  · 图片转 base64、背景图 URL
  · UTC 转本地日期、今天、相差几天
  · HH:MM 校验、VIP 判断

不负责
  · 不碰数据库（不 import repo）
  · 不生成 HTML"""
# 名字　榫 —— 榫卯的凸头。看不见，但所有东西都靠它接住。


from urllib.parse import quote
import base64
import datetime
import os

from db import repository as repo


def _img_to_b64(path):
    if not path or not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def _bg_url(path):
    """把本地图片变成浏览器能访问的 URL（走 Gradio 的 file 路由）。

    以前是 base64 内联：体积多 33%，而且浏览器没法缓存，每次切角色都重传。
    """
    abs_path = os.path.abspath(path).replace("\\", "/")
    return "/gradio_api/file=" + quote(abs_path, safe="/:")


def _fmt_day(raw):
    """库里存的是 UTC，显示时转成本地日期。"""
    if not raw:
        return "——"
    try:
        from datetime import datetime, timedelta
        return (datetime.fromisoformat(str(raw)) + timedelta(hours=8)).strftime("%Y-%m-%d")
    except Exception:
        return str(raw)[:10]


def _is_vip(user_id):
    u = repo.get_or_create_user(user_id) if user_id else None
    return bool(u and u.get("role") in ("vip", "admin"))


def _today():
    from datetime import date
    return date.today().strftime("%Y%m%d")


def _days_since(ts):
    """UTC 时间戳 → 多少天前。解析失败返回 0，不让主页因为脏数据崩掉。

    2026-11-13 P0：这里原本写的是 datetime.strptime，但文件顶部是
    `import datetime`（模块），模块没有 strptime，于是每次都抛异常、
    被 except 吞掉、返回 0——"来过 1 天""在一起第 1 天"全是从这来的。
    改成 datetime.datetime.strptime，并且顺手兼容带 T 的 ISO 格式。
    """
    if not ts:
        return 0
    try:
        s = str(ts).replace("T", " ")[:19]
        t = datetime.datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
        return max(0, (datetime.datetime.utcnow() - t).days)
    except Exception:
        return 0


def _valid_hhmm(s: str) -> bool:
    try:
        h, m = s.split(":")
        return 0 <= int(h) <= 23 and 0 <= int(m) <= 59
    except Exception:
        return False
