# -*- coding: utf-8 -*-
"""把 story.json 变成一个能直接打开的网页。

单文件，JSON 内嵌，不需要再请求任何东西。
点一下出一句，有选项就选，走完显示落点。
"""

import html
import json

BG = {
    "black": "#000000",
    "bg_station": "#2b2d33",
    "bg_street": "#1f2429",
    "bg_lake": "#2a3038",
    "bg_room": "#262a30",
    "bg_night": "#14171c",
}

TPL = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#14171c;color:#e8e6e3;font:16px/1.9 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
     display:flex;align-items:center;justify-content:center;min-height:100vh;overflow:hidden}
#stage{position:relative;width:100%;height:100vh;transition:background .8s}
#box{position:absolute;left:50%;bottom:0;transform:translateX(-50%);
     width:min(860px,94vw);padding:0 0 5vh}
#day{font-size:12px;letter-spacing:.18em;color:#8a9099;margin-bottom:10px;text-align:center}
#txt{background:rgba(10,12,15,.62);backdrop-filter:blur(8px);border-radius:14px;
     padding:26px 30px;min-height:132px;font-size:17px;line-height:2.0;
     cursor:pointer;user-select:none;border:1px solid rgba(255,255,255,.06)}
#who{color:#c94f4f;font-weight:600}
#hint{text-align:center;font-size:12px;color:#5d636b;margin-top:10px;height:16px}
#menu{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);
      width:min(620px,90vw);display:none}
#menu button{display:block;width:100%;margin:12px 0;padding:16px 22px;border-radius:12px;
      background:rgba(20,24,30,.88);color:#e8e6e3;border:1px solid rgba(255,255,255,.12);
      font:inherit;text-align:left;cursor:pointer;transition:.2s}
#menu button:hover{background:rgba(40,48,58,.95);border-color:rgba(255,255,255,.3)}
#end{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);text-align:center;
     display:none;width:min(680px,92vw)}
#end h2{font-size:20px;font-weight:500;margin-bottom:18px;color:#b8bcc2}
#end p{color:#8a9099;font-size:15px;line-height:2.1}
#end a{display:inline-block;margin-top:26px;color:#c94f4f;text-decoration:none;font-size:14px}
#bar{position:fixed;left:0;top:0;height:2px;background:#c94f4f;transition:width .4s;width:0}
</style></head><body>
<div id="bar"></div>
<div id="stage">
  <div id="day"></div>
  <div id="box">
    <div id="txt"></div>
    <div id="hint">点一下继续</div>
  </div>
  <div id="menu"></div>
  <div id="end">
    <h2>__ENDTITLE__</h2>
    <p>__ENDSUB__</p>
    <a href="#" onclick="restart();return false">从头再看一遍</a>
  </div>
</div>
<script>
const S = __DATA__;
const BG = __BG__;
let flat = [];        // 拍平的播放项
let i = 0;

function build() {
  flat = [];
  S.days.forEach((d, di) => {
    (d.scenes || []).forEach((sc, si) => {
      flat.push({kind:'day', day:d, idx:di+1, total:S.days.length});
      (sc.lines || []).forEach(ln => flat.push({kind:'line', ln:ln, sc:sc}));
      if ((sc.choices||[]).length) flat.push({kind:'menu', sc:sc});
    });
  });
  flat.push({kind:'end'});
}

function bgOf(name){ return BG[name] || '#14171c'; }

function render() {
  const it = flat[i];
  if (!it) return;
  document.getElementById('bar').style.width =
    Math.min(100, (i/flat.length)*100) + '%';
  if (it.kind === 'day') {
    const d = it.day;
    document.getElementById('day').textContent =
      'DAY ' + it.idx + ' / ' + it.total + '　' + (d.title || '');
    i++; return render();
  }
  if (it.kind === 'line') {
    const ln = it.ln;
    if (ln.bg) document.getElementById('stage').style.background = bgOf(ln.bg);
    else if (it.sc.bg) document.getElementById('stage').style.background = bgOf(it.sc.bg);
    const t = document.getElementById('txt');
    if (ln.who) {
      t.innerHTML = '<span id="who">' + esc(ln.who) + '</span>　' + esc(ln.text||'');
    } else {
      t.innerHTML = esc(ln.text||'');
    }
    hide('menu'); hide('end');
    i++;
    document.getElementById('hint').textContent = '点一下继续';
    return;
  }
  if (it.kind === 'menu') {
    const m = document.getElementById('menu');
    m.innerHTML = '';
    (it.sc.choices||[]).forEach((c, ci) => {
      const b = document.createElement('button');
      b.textContent = c.text || ('选项 ' + (ci+1));
      b.onclick = () => { pick(c); };
      m.appendChild(b);
    });
    show('menu');
    document.getElementById('hint').textContent = '';
    return;
  }
  if (it.kind === 'end') {
    show('end');
    document.getElementById('hint').textContent = '';
    document.getElementById('bar').style.width = '100%';
  }
}

function pick(c) {
  hide('menu');
  const t = document.getElementById('txt');
  t.innerHTML = c.reply ? esc(c.reply) : '';
  // 选项后可能跳转
  const nxt = (c.next || '').trim();
  i++;
  if (nxt) {
    const k = flat.findIndex(x => x.kind === 'line' && x.sc && x.sc.id === nxt);
    if (k >= 0) i = k;
  }
  document.getElementById('hint').textContent = '点一下继续';
}

function next() {
  if (document.getElementById('menu').style.display === 'block') return;
  render();
}

function show(id){ document.getElementById(id).style.display = 'block'; }
function hide(id){ document.getElementById(id).style.display = 'none'; }
function esc(s){ const d=document.createElement('div'); d.textContent=s; return d.innerHTML; }

function restart(){ i = 0; hide('end'); render(); }

document.getElementById('txt').onclick = next;
document.body.onclick = (e) => { if (e.target.id === 'stage') next(); };
document.onkeydown = (e) => {
  if (e.key === ' ' || e.key === 'Enter' || e.key === 'ArrowRight') { e.preventDefault(); next(); }
};

build(); render();
</script></body></html>"""

END_TITLE = "到这里就结束了"
END_SUB = ("你和她这几天的路，走完了。<br>"
           "想再看一遍就点下面。")


def render_html(story, title=None):
    """把一份 story dict 变成 html 字符串。"""
    try:
        title = title or "%s · %d 天" % (story.get("city") or "旅行",
                                        len(story.get("days") or []))
    except Exception:
        title = "旅行"

    data = json.dumps(story, ensure_ascii=False)
    # 防止 </script> 提前闭合
    data = data.replace("</", "<\\/")

    out = TPL.replace("__TITLE__", html.escape(title))
    out = out.replace("__ENDTITLE__", END_TITLE)
    out = out.replace("__ENDSUB__", END_SUB)
    out = out.replace("__BG__", json.dumps(BG, ensure_ascii=False))
    out = out.replace("__DATA__", data)
    return out
