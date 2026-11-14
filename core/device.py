# core/device.py
"""设备相关：横竖屏提示、是否手机。

⚠️ 默认关闭（ENABLED = False），没有任何地方调用它。

横竖屏提示是纯 CSS 实现的：
    竖屏 + 窄屏 → 盖一层"把手机横过来"
    转成横屏 → 自动消失
不需要 JS，不需要后端判断，不会误判。
"""

ENABLED = False

# 只在"竖屏 + 窄屏"时出现。宽屏（电脑）永远不显示。
ROTATE_HINT_HTML = """
<style>
  #rotate-hint { display: none; }
  @media (orientation: portrait) and (max-width: 900px) {
    #rotate-hint {
      display: flex;
      position: fixed;
      inset: 0;
      z-index: 999999;
      align-items: center;
      justify-content: center;
      background: #0b0e13;
      color: #e9e7e2;
      font-family: system-ui, -apple-system, "PingFang SC", sans-serif;
    }
  }
  #rotate-hint .box {
    text-align: center;
    line-height: 2;
    font-size: 15px;
    letter-spacing: .06em;
  }
  #rotate-hint .icon {
    font-size: 40px;
    display: block;
    margin-bottom: 10px;
    animation: rh-turn 2.4s ease-in-out infinite;
  }
  #rotate-hint .sub {
    font-size: 12px;
    opacity: .55;
  }
  @keyframes rh-turn {
    0%, 40%   { transform: rotate(0deg); }
    60%, 100% { transform: rotate(90deg); }
  }
</style>

<div id="rotate-hint">
  <div class="box">
    <span class="icon">&#128241;</span>
    把手机横过来
    <div class="sub">横屏体验更好</div>
  </div>
</div>
"""

_MOBILE_TOKENS = ("iphone", "ipad", "ipod", "android", "mobile",
                  "harmonyos", "micromessenger", "windows phone")


def is_mobile(user_agent: str) -> bool:
    """粗判断是不是手机。失败一律当 PC（宁可不提示，也别乱提示）。"""
    ua = (user_agent or "").lower()
    if not ua:
        return False
    return any(t in ua for t in _MOBILE_TOKENS)


def rotate_hint_html(enabled=None) -> str:
    """返回横竖屏提示的 HTML。关闭时返回空串，可以直接塞进 gr.HTML。"""
    on = ENABLED if enabled is None else bool(enabled)
    return ROTATE_HINT_HTML if on else ""
