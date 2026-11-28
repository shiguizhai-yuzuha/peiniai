"""memcore · 可复用的记忆内核

从「陪你」的 core/memory.py 抽出来的一层：
  抽取（结构化字段）→ 存储（sqlite）→ 召回（关键词 + 时间衰减）→ 注入（分层 prompt）

不依赖任何具体产品：传入 db 路径和取模型的函数即可。
"""

import json
import re
import sqlite3
import time

SCHEMA = """
create table if not exists mf_facts(
  id integer primary key autoincrement,
  uid text not null, kind text not null, key text, val text not null,
  weight real default 1.0, ts real not null);
create index if not exists idx_mf_uid on mf_facts(uid);
create index if not exists idx_mf_kind on mf_facts(uid, kind);

create table if not exists mf_turns(
  id integer primary key autoincrement,
  uid text not null, role text not null, text text not null, ts real not null);
create index if not exists idx_mft_uid on mf_turns(uid);

create table if not exists mf_promises(
  id integer primary key autoincrement,
  uid text not null, what text not null, by_who text default 'user',
  status text default 'pending', ts real not null, done_ts real);
create index if not exists idx_mfp_uid on mf_promises(uid, status);

create table if not exists mf_summary(
  id integer primary key autoincrement,
  uid text not null, day text not null, text text not null, ts real not null);
create index if not exists idx_mfs_uid on mf_summary(uid, day);
"""

EXTRACT_PROMPT = """从下面这段对话里，抽取关于「用户」的长期信息。
只输出 JSON，不要解释。字段如下（没有就留空数组/空串）：

{
  "name": "",
  "people": [{"who": "", "relation": "", "note": ""}],
  "events": [{"what": "", "when": ""}],
  "plans": [{"what": "", "when": ""}],
  "likes": [],
  "dislikes": [],
  "health": [],
  "promises": [{"what": "", "by_who": "user|assistant"}]
}

规则：
1 只抽用户说的、或明确被确认的事实，不猜。
2 时间保留原话（如「下周三」「明天八点」），不要换算。
3 没提到的字段必须是空数组或空串。

对话：
{dialogue}
"""

KIND_ORDER = ["people", "events", "plans", "health", "likes", "dislikes", "promises", "name"]


class MemoryCore:
    def __init__(self, db_path, llm=None, model=None):
        self.db = db_path
        self.llm = llm            # callable(prompt) -> str
        self.model = model
        self._init()

    # ── 基础 ──
    def _conn(self):
        c = sqlite3.connect(self.db, timeout=8)
        c.row_factory = sqlite3.Row
        return c

    def _init(self):
        c = self._conn()
        c.executescript(SCHEMA)
        c.commit()
        c.close()

    # ── 写入 ──
    def add_turn(self, uid, role, text):
        c = self._conn()
        c.execute("insert into mf_turns(uid,role,text,ts) values(?,?,?,?)",
                  (uid, role, text, time.time()))
        c.execute("delete from mf_turns where uid=? and id not in "
                  "(select id from mf_turns where uid=? order by id desc limit 60)", (uid, uid))
        c.commit()
        c.close()

    def recent_turns(self, uid, n=6):
        c = self._conn()
        rows = c.execute("select role,text from mf_turns where uid=? order by id desc limit ?",
                         (uid, n)).fetchall()
        c.close()
        return [(r["role"], r["text"]) for r in reversed(rows)]

    def put_fact(self, uid, kind, val, key=None, weight=1.0):
        val = (val or "").strip()[:300]
        if not val:
            return
        c = self._conn()
        old = c.execute("select id from mf_facts where uid=? and kind=? and val=?",
                        (uid, kind, val)).fetchone()
        if old:
            c.execute("update mf_facts set weight=weight+0.5, ts=? where id=?", (time.time(), old["id"]))
        else:
            c.execute("insert into mf_facts(uid,kind,key,val,weight,ts) values(?,?,?,?,?,?)",
                      (uid, kind, key, val, weight, time.time()))
        c.commit()
        c.close()

    # ── 抽取 ──
    def extract(self, uid, dialogue):
        if not self.llm:
            return {}
        try:
            raw = self.llm(EXTRACT_PROMPT.replace("{dialogue}", dialogue))
            data = json.loads(raw) if isinstance(raw, str) else (raw or {})
        except Exception:
            return {}
        self.apply(uid, data)
        return data

    def apply(self, uid, data):
        if not isinstance(data, dict):
            return
        if data.get("name"):
            self.put_fact(uid, "name", str(data["name"]), key="name")
        for p in data.get("people") or []:
            note = " ".join(x for x in [p.get("who"), p.get("relation"), p.get("note")] if x)
            self.put_fact(uid, "people", note, key=p.get("who"))
        for e in data.get("events") or []:
            self.put_fact(uid, "events", f"{e.get('what','')} {e.get('when','')}".strip())
        for p in data.get("plans") or []:
            self.put_fact(uid, "plans", f"{p.get('what','')} {p.get('when','')}".strip())
        for h in data.get("health") or []:
            self.put_fact(uid, "health", str(h))
        for k in ("likes", "dislikes"):
            for v in data.get(k) or []:
                self.put_fact(uid, k, str(v))
        for p in data.get("promises") or []:
            self.add_promise(uid, p.get("what", ""), p.get("by_who", "user"))

    # ── 承诺 ──
    def add_promise(self, uid, what, by_who="user"):
        what = (what or "").strip()[:200]
        if not what:
            return
        c = self._conn()
        old = c.execute("select id from mf_promises where uid=? and what=? and status='pending'",
                        (uid, what)).fetchone()
        if not old:
            c.execute("insert into mf_promises(uid,what,by_who,status,ts) values(?,?,?,'pending',?)",
                      (uid, what, by_who or "user", time.time()))
            c.commit()
        c.close()

    def promises(self, uid, status="pending"):
        c = self._conn()
        rows = c.execute("select id,what,by_who,status,ts from mf_promises "
                         "where uid=? and status=? order by id desc limit 20",
                         (uid, status)).fetchall()
        c.close()
        return [{"id": r["id"], "what": r["what"], "by": r["by_who"],
                 "ts": r["ts"], "status": r["status"]} for r in rows]

    def done_promise(self, uid, pid):
        c = self._conn()
        c.execute("update mf_promises set status='done', done_ts=? where id=? and uid=?",
                  (time.time(), pid, uid))
        c.commit()
        c.close()

    # ── 召回 ──
    def _kw(self, text):
        t = re.sub(r"[，。！？、,.!?~\s]+", " ", text or "")
        return [p for p in t.split(" ") if len(p) >= 2][:8]

    def recall(self, uid, text, per_kind=2):
        kws = self._kw(text)
        c = self._conn()
        out = {}
        for kind in KIND_ORDER:
            rows = c.execute(
                "select val,weight,ts from mf_facts where uid=? and kind=? "
                "order by weight desc, ts desc limit 30", (uid, kind)).fetchall()
            hits = []
            for r in rows:
                v = r["val"]
                if any(k in v for k in kws) or any(k in text for k in self._kw(v)):
                    hits.append(v)
            if not hits:
                hits = [r["val"] for r in rows[:per_kind]]
            out[kind] = hits[:per_kind]
        c.close()
        return out

    # ── 注入 ──
    def build_messages(self, uid, user_text, system_prompt, max_history=6):
        facts = self.recall(uid, user_text)
        lines = []
        pend = self.promises(uid)
        if pend:
            lines.append("还没兑现的答应：" + "；".join(p["what"] for p in pend[:3]))
        if facts.get("name"):
            lines.append("对方名字：" + "、".join(facts["name"]))
        for label, key in [("他身边的人", "people"), ("他提过的事", "events"),
                           ("他计划的事", "plans"), ("他的身体", "health"),
                           ("他喜欢", "likes"), ("他不喜欢", "dislikes"),
                           ("答应过的事", "promises")]:
            vals = [v for v in facts.get(key, []) if v]
            if vals:
                lines.append(label + "：" + "；".join(vals[:3]))

        msgs = [{"role": "system", "content": system_prompt}]
        if lines:
            msgs.append({"role": "system",
                         "content": "你记得这些（可以自然带一句，别全念出来）：\n" + "\n".join(lines)})
        for role, text in self.recent_turns(uid, max_history):
            msgs.append({"role": "user" if role == "user" else "assistant", "content": text})
        msgs.append({"role": "user", "content": user_text})
        return msgs, facts

    # ── 摘要 ──
    def summarize_day(self, uid, day, text):
        c = self._conn()
        c.execute("insert into mf_summary(uid,day,text,ts) values(?,?,?,?)",
                  (uid, day, text[:500], time.time()))
        c.commit()
        c.close()

    def facts(self, uid):
        c = self._conn()
        rows = c.execute("select kind,val,weight,ts from mf_facts where uid=? "
                         "order by kind, weight desc", (uid,)).fetchall()
        c.close()
        out = {}
        for r in rows:
            out.setdefault(r["kind"], []).append(
                {"val": r["val"], "weight": round(r["weight"], 1), "ts": r["ts"]})
        return out
