# 小暖 · 会记住独居老人说过什么的陪伴助手

Hack4Good（技术向善）· 老年人数字鸿沟赛道作品。

一句话：**让一个没人陪的老人，说的话有人接着。**

---

## 它做什么

- **记得住**：不是存聊天记录，是抽成字段（人物 / 事件 / 计划 / 身体 / 承诺）
- **不编**：没听过的事直说「这个您没跟我说过」
- **先开口**：不等你问，到点会提
- **家人端**：只看摘要，看不到原话
- **老人端**：字大、按钮大、对比度 ≥ 7:1、减少动效

---

## 目录

```
dist/                 可直接部署的静态站点
  simple.html         主界面
  app.css             样式（20 种外观）
  app.js              交互与渲染
  intro.html          开场 PPT（10 张）
  family.html         家人端
  demo/               演示系统 v2
    script.js         剧本与文案（纯数据）
    state.js          状态机
    view.js           画面渲染
    live.js           真实接口调用
    index.js          装配

backend/              服务端（FastAPI，挂在主站上）
  xn.py               /xn/* 接口：chat / memories / facts / family / promises
  memcore.py          记忆内核：抽取 → 存储 → 召回 → 注入
```

---

## 记忆内核怎么设计的

四层，每层只做一件事：

```
抽取   EXTRACT_PROMPT → 一次模型调用 → JSON
       字段：name / people / events / plans / health / likes / dislikes / promises

存储   sqlite 三张表
       mf_facts（结构化事实）· mf_turns（最近对话）· mf_promises（承诺）

召回   关键词命中优先，其次按权重与时间
       不用向量，因为老人说法固定，关键词就够

注入   人设 → 记得的事 → 最近六轮 → 本次输入
```

**为什么不用 RAG 存原文：**

原文检索会把整段话塞回 prompt，越用越慢；抽成字段之后，只带相关的几条，而且能回答「我答应过您什么」。

---

## 接口

```
POST /xn/chat        { text, uid }        → { reply, ms, memories }
GET  /xn/memories    ?uid=                → { items }
GET  /xn/facts       ?uid=                → { kinds, total }
GET  /xn/family      ?uid=                → { rows, chart, elapsed_ms, lib }
GET  /xn/promises    ?uid=                → { items }
POST /xn/promises    { id }               → 标记已完成
```

`/xn/family` 用 pandas 现场统计近七天，返回 `lib` 与 `elapsed_ms`，前端直接显示「pandas 2.3.3 · 4.1 ms」。

---

## 本地怎么跑

```bash
# 前端
python -m http.server 8200 --directory dist
# 打开 http://127.0.0.1:8200/simple.html

# 后端（需要主站的 config 与 core.client）
uvicorn 你的主应用:app --port 7864
```

前端接口地址在 `app.js` 与 `demo/index.js` 里的 `XN_API`，默认指向线上实例。

---

## 用 Qoder 做的部分

- 生成页面结构与样式初稿
- 写接口桩、修 CSS 冲突、执行发布

**我自己重写的部分**：演示系统（从 34 个互相调用的函数，拆成 5 个模块）、20 种外观与对比度检测、记忆内核抽取、老人端可读性调整。

---

## 许可

代码：**PolyForm Noncommercial 1.0.0**（源码可见，禁止商用），与主项目「陪你」一致。

个人使用、学习、修改、分享都可以，但不能拿去卖钱，也不能放进商业产品。

**陪伴不该按人民币计费。**

肖像与角色素材仅用于比赛演示，不随代码授权商用。
