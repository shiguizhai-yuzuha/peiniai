# -*- coding: utf-8 -*-
"""剧情生成任务：扣费、限额、后台线程、状态查询

定价（2026-10-28 定）：
  5 元一次
  每人最多 5 次（= 最多 5 份 JSON）

流程：
  start()  → 检查限额和余额 → 扣 5 元 → 建记录 → 起后台线程
  线程里跑 build_story，跑完写 JSON，把状态改成 done
  get()    → 查状态，done 时能把 JSON 拿出来
"""

import json
import os
import queue
import threading
import uuid

from db import repository as repo
from services import billing

PRICE = 3.0          # 一次 3 元
MAX_PER_USER = 5     # 每人最多 5 次
DAYS = 7
PER_DAY = 3
LINES = 12
CITY = "杭州"

STORY_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "stories")

# 一次只跑一个（2 核，跑两个都会变慢），其它排队
_lock = threading.Lock()
_running = {"count": 0}

_jobs = queue.Queue()
_worker_lock = threading.Lock()
_worker_on = {"started": False}


def _worker():
    """唯一的工人。一个一个来。"""
    while True:
        item = _jobs.get()
        if item is None:
            _jobs.task_done()
            continue
        sid, args = item
        try:
            _run(sid, *args)
        except Exception as e:
            print("[剧情] worker 出错：%s" % e, flush=True)
        finally:
            _jobs.task_done()


def _ensure_worker():
    with _worker_lock:
        if not _worker_on["started"]:
            threading.Thread(target=_worker, daemon=True, name="story-worker").start()
            _worker_on["started"] = True


def _ensure_dir():
    os.makedirs(STORY_DIR, exist_ok=True)


def can_start(user_id):
    """能不能开始。返回 (ok, 原因)。"""
    # 2026-11-01 下架。功能已关，这里也拦一道，防止任何入口绕过。
    try:
        from config import GALGAME_ENABLED
        if not GALGAME_ENABLED:
            return False, "这个功能已经下架了"
    except Exception:
        pass
    if not user_id:
        return False, "请先登录"
    used = repo.count_stories(user_id)
    if used >= MAX_PER_USER:
        return False, "你已经用完了 %d 次" % MAX_PER_USER
    if not billing.has_balance(user_id, PRICE):
        return False, "余额不够，这一次要 %.0f 元" % PRICE
    return True, ""


def start(user_id, city=CITY, origin=None, profile=None,
          days=DAYS, per_day=PER_DAY, lines=LINES, character_text=None):
    """开始生成。返回 (story_id, 错误)。"""
    ok, why = can_start(user_id)
    if not ok:
        return None, why

    _ensure_dir()

    # 出发地：没给就当重合 → 新艾利都
    if not origin or origin == city:
        origin = "新艾利都"

    sid = uuid.uuid4().hex[:12]

    # 先扣钱再跑 —— 不然点一下跑 0.45 元，白送
    try:
        billing.charge_yuan(user_id, PRICE)
    except Exception as e:
        print("[剧情] 扣费失败：%s" % e, flush=True)
        return None, "扣费失败，请稍后再试"

    repo.create_story(sid, user_id, city, origin, days)
    repo.update_story(sid, charged=PRICE)

    _ensure_worker()
    _jobs.put((sid, (user_id, city, origin, profile, days, per_day, lines,
                    character_text)))
    ahead = max(0, _jobs.qsize() - 1)

    print("[剧情] %s 入队 user=%s %s→%s 前面 %d 个"
          % (sid, user_id[:8], origin, city, ahead), flush=True)
    return sid, ""


def _run(sid, user_id, city, origin, profile, days, per_day, lines,
         character_text=None):
    with _lock:
        _running["count"] += 1
    try:
        repo.update_story(sid, status="running")
        from galgame import story as G

        def _prog(done, total, tok):
            # 每完成一天，把进度和已花的 token 写进库里
            repo.update_story(sid, tokens=int(tok),
                              title="%d/%d 天" % (done, total))

        data = G.build_story(city=city, days=days, per_day=per_day,
                             lines_per_scene=lines, profile=profile or {},
                             origin=origin, progress_cb=_prog,
                             character_text=character_text)

        path = os.path.join(STORY_DIR, "%s.json" % sid)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        meta = data.get("meta") or {}
        # 记一下真实 token 成本（只做账，不从余额扣）
        try:
            repo.add_tokens(user_id, int(meta.get("tokens") or 0))
        except Exception:
            pass
        repo.update_story(
            sid, status="done", file=path,
            title=(data.get("days") or [{}])[0].get("title") or "",
            tokens=int(meta.get("tokens") or 0),
            cost_yuan=float(meta.get("cost") or 0),
        )
        print("[剧情] %s 完成 %d 段，成本 %.2f 元"
              % (sid, meta.get("total_lines", 0), meta.get("cost", 0)), flush=True)
    except Exception as e:
        print("[剧情] %s 失败：%s" % (sid, e), flush=True)
        repo.update_story(sid, status="failed", error=str(e)[:200])
        # 失败了就全额退：钱退回，次数也不算
        refund(sid)
    finally:
        with _lock:
            _running["count"] -= 1


def refund(sid):
    """退款：钱退回余额，记录标成已退。

    次数怎么算：count_stories 只数非 failed 的，所以退了自然就不占次数。
    """
    try:
        row = repo.get_story(sid)
        if not row:
            return 0.0
        paid = float(row.get("charged") or 0)
        if paid <= 0:
            return 0.0
        # 直接加回去。不能用 charge_yuan(-paid)，它里面有 abs()，会变成再扣一次
        repo.update_balance(row["user_id"], paid)
        repo.update_story(sid, charged=0)
        print("[剧情] %s 已退 %.2f 元" % (sid, paid), flush=True)
        return paid
    except Exception as e:
        print("[剧情] 退款失败：%s" % e, flush=True)
        return 0.0


def get(sid, user_id=None):
    """查一份剧情。给 user_id 就校验归属。"""
    row = repo.get_story(sid)
    if not row:
        return None, "没有这一份"
    if user_id and row["user_id"] != user_id:
        return None, "不是你的"
    if row["status"] == "done" and row.get("file"):
        try:
            with open(row["file"], encoding="utf-8") as f:
                row["data"] = json.load(f)
        except Exception as e:
            return None, "文件读不出来：%s" % e
    return row, ""


def status_line(row):
    """给界面看的一行状态。"""
    st = row.get("status")
    if st == "pending":
        n = _jobs.qsize()
        return "排队中…（前面还有 %d 个）" % max(0, n - 1) if n > 0 else "排队中…"
    if st == "running":
        ttl = row.get("title") or ""
        if "/" in ttl:
            return "正在生成：%s" % ttl
        return "正在生成…"
    if st == "done":
        lines = ((row.get("data") or {}).get("meta") or {}).get("total_lines", 0)
        return "好了：%d 段对话" % lines
    if st == "failed":
        return "生成失败：%s" % (row.get("error") or "")
    return st or ""


def quota_line(user_id):
    used = repo.count_stories(user_id)
    return "已用 %d / %d 次，每次 %.0f 元" % (used, MAX_PER_USER, PRICE)


def recover_stuck(minutes=15):
    """启动时清僵尸：跑太久还挂着的，标成 failed。

    为什么需要：任务是守护线程，进程一退线程就死，
    记录永远停在 running。服务重启过就会留下这种记录。
    """
    try:
        conn = repo.get_conn()
        rows = conn.execute(
            "SELECT id FROM stories WHERE status IN ('pending','running') "
            "AND updated_at < DATETIME('now', ?)",
            ("-%d minute" % minutes,),
        ).fetchall()
        ids = [r[0] for r in rows]
        conn.close()
        for sid in ids:
            repo.update_story(sid, status="failed", error="生成被中断（服务重启或超时）")
            refund(sid)
        if ids:
            print("[剧情] 清了 %d 个僵尸任务" % len(ids), flush=True)
        return len(ids)
    except Exception as e:
        print("[剧情] 清僵尸失败：%s" % e, flush=True)
        return 0
