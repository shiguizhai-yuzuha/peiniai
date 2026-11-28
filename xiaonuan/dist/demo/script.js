/* 小暖 · 演示 v2：剧本与文案（纯数据，不碰 DOM） */

window.XNDemoScript = (function () {
  const TIMING = {
    bubbleIn: 320,
    typing: 520,
    stepBase: 850,
    slowFactor: 1.35,
    pptAuto: 3,
    familyHold: 3200,
    pulse: 900,
    exitDelay: 240
  };

  const COPY = {
    bar: "演示模式 · 示例数据",
    skip: "跳过",
    next: "下一步",
    pause: "暂停",
    resume: "继续",
    live: "自己说",
    exit: "退出",
    liveHint: "说一句，走真实接口…",
    livePlaceholder: "随便说一句，比如「我下周三要复查」",
    famTitle: "家人端 · 今日摘要",
    famSub: "她能看到摘要，看不到原话",
    famFoot: "数据来自今天的对话 · 不含隐私原文",
    offline: "接口没连上（本地预览或未部署）",
    offlineTag: "离线"
  };

  // kind: user | ai | fx
  const STEPS = [
    { kind: "user", text: "我下周三回来看你", cap: "她记住了一件事" },
    { kind: "ai", text: "下周三啊，我记下了。要不要我到那天提醒您？", cap: "她回了一句，也没有多问" },
    { kind: "fx", fx: "memory", cap: "这一条进了她的记忆", data: { text: "我下周三回来看你" } },
    { kind: "fx", fx: "event", cap: "明天的事，先挂在那儿", data: { date: "12月2日 周三", text: "女儿回来看我" } },
    { kind: "user", text: "我血压高，每天要吃降压药", cap: "又说了一件" },
    { kind: "ai", text: "这个我记着。药别断。", cap: "她记着" },
    { kind: "fx", fx: "memory", cap: "两条了", data: { text: "我血压高，每天要吃降压药" } },
    { kind: "fx", fx: "memory", cap: "三条", data: { text: "我爱吃软的，不吃辣" } },
    { kind: "user", text: "我上次说的那个药是什么", cap: "问一件她没听过的事" },
    { kind: "ai", text: "这个您没跟我说过。", cap: "她不会编", wait: 1600 },
    { kind: "fx", fx: "proactive", cap: "这次是她先开口", data: { text: "您女儿下周三回来，要不要提前收拾一下？" } },
    { kind: "user", text: "我明天八点去医院", cap: "说个时间" },
    { kind: "ai", text: "明天八点，我记下了。", cap: "她记下了" },
    { kind: "fx", fx: "reminder", cap: "提醒生成", data: { at: "08:00", title: "明天八点去医院" } },
    { kind: "fx", fx: "ringSoon", cap: "出门前一小时" },
    { kind: "fx", fx: "ringDue", cap: "到点了" },
    { kind: "fx", fx: "ack", cap: "回一句，她就知道办完了" },
    { kind: "fx", fx: "elder", cap: "字大一点" },
    { kind: "fx", fx: "style", cap: "换个外观也可以", data: { name: "sakura" } },
    { kind: "fx", fx: "style", cap: "回到纸墨", data: { name: "paper" } },
    { kind: "fx", fx: "facts", cap: "她抽出来的不是原文，是字段" },
    { kind: "fx", fx: "family", cap: "家人只看摘要" },
    { kind: "fx", fx: "live", cap: "轮到您了：随便说一句，走真实接口" }
  ];

  return { TIMING, COPY, STEPS };
})();
