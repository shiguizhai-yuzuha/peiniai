"""扉 · 陪你AI · 启动入口。

原来 2398 行全在这一个文件里，现在按功能拆到了 webui/ 包：

    webui/helpers.py     小工具（路径、时间、格式化）
    webui/render.py      HTML 渲染（里程碑、关系条、她的主页）
    webui/chat.py        聊天回调
    webui/relation.py    关系推进
    webui/persona.py     角色创建与切换
    webui/memory.py      记忆面板
    webui/export.py      导出
    webui/story.py       剧情
    webui/auth.py        登录注册
    webui/background.py  背景
    webui/pages.py       整页 HTML（/app /home /piano …）
    webui/routes.py      文件路由（纪念册、背景图）
    webui/middleware.py  RootSwitch（/ 走新界面）
    webui/easter.py      彩蛋
    webui/build.py       装配（挂路由、挂中间件）
    webui/ui.py          Gradio 界面装配（Blocks）

名字叫扉——门扇。所有人都是从这扇门进来的。

这个文件只剩三件事：
    ① 启动检查（建库、清僵尸任务）
    ② 把 create_app 换成我们自己的（挂路由）
    ③ main

跑：python app.py
彩蛋：python app.py --love（打印一句就退出，不启服务）
"""
# 名字　扉 —— 门扇。所有人都是从这扇门进来的。

import os
import sys

import gradio as gr

from config import HOST, PORT
from db.models import init_db

# ============ 启动准备 ============

init_db()

# 剧情生成的启动准备：建目录 + 清上次没跑完的僵尸任务
try:
    from services import story_jobs as _sj
    _sj._ensure_dir()
    _sj.recover_stuck(minutes=15)
    print("[启动] 剧情目录就绪，僵尸任务已清理", flush=True)
except Exception as _e:
    print("[启动] 剧情初始化跳过：%s" % _e, flush=True)


# ============ 界面与装配 ============

# 导入 ui 就会执行整个 Blocks 定义（Gradio 就是这样）
# 常量也要挂回来：api_*.py 里用了 _A.DEFAULT_PERSONA
from config import (DEFAULT_PERSONA, PERSONAS, OPENINGS,  # noqa: F401,E402
                    CHARACTER_BACKGROUNDS, LOGIN_BACKGROUND,
                    MEMORY_PINNED_MAX, HOST, PORT)
from webui.ui import demo
from webui.build import _create_app_with_ipblock

# ==========================================================
# 兼容层
#
# core/api_*.py 里到处是 `import app as _A` 再加 _A.respond 这种写法。
# 2026-11-13 拆包之后这些函数搬到了 webui/ 下面，
# 在这里把它们重新挂回 app 这个命名空间，那五个 API 模块一行不用改。
#
# 新代码请直接 from webui.xxx import，不要再往这里加。
# ==========================================================

from webui.auth import do_change_password, do_guest, do_keep, do_login, do_logout, do_register
from webui.background import _ROOT, do_reset_bg, do_set_bg
from webui.build import _create_app_with_ipblock
from webui.chat import _respond_guest, clear_chat, load_history, opening_history, respond
from webui.easter import _nothing, _xiaogong_love_guangli
from webui.export import do_export_all, do_export_book, do_export_refresh, do_export_txt
from webui.helpers import (
    _bg_url, _days_since, _fmt_day, _img_to_b64, _is_vip, _today, _valid_hhmm,
)
from webui.memory import (
    MEM_ORDER, _SEP, _mem_refresh, _mem_split, _pin_stat, _split_value, do_mem_action,
    do_pin, do_preview_memory, do_save_memory_mode, do_save_prefs, open_profile,
)
from webui.middleware import RootSwitch
from webui.pages import (
    _UNIVERSAL_BACK, _ab_page, _app_page, _home_page, _keys_page, _notice_page,
    _piano_page, _scene_act, _scene_page, _voice_page, _menu_page,
)
from webui.persona import (
    _create_fail, _my_personas, do_create_persona, do_delete_persona, switch_persona,
    toggle_create,
)
from webui.relation import (
    _refresh_stage_wrap, do_tell, hide_tell_confirm, open_milestones, refresh_stage,
    show_tell_confirm,
)
from webui.render import (
    _TEMPLATE_DIR, _load_template, get_bg_style, get_static_css, render_milestones,
    render_profile, render_relationship,
)
from webui.routes import _bg_image, _keepsake_dl, _keepsake_file
from webui.story import (
    STORY_AUTO, STORY_DEST, STORY_ORIGINS, _story_list_md, _story_page,
    build_story_profile, do_story_refresh, do_story_start,
)
from webui.ui import BANNER_XLL_HTML, CSS, FOOTER_HTML, NOTICE_HTML


# 彩蛋：这一句要留在 app 这个命名空间里，
# 因为接管指南里写的调用方式是 import app; app._xiaogong_love_guangli()
from webui.easter import _xiaogong_love_guangli, _nothing

import gradio.routes as _gr_routes

_gr_routes.App.create_app = staticmethod(_create_app_with_ipblock)


# ============ 启动 ============

if __name__ == "__main__":
    # 彩蛋：python app.py --love
    if "--love" in sys.argv:
        # 只打印这一句，然后退出。不启动服务，不占端口。
        print("", flush=True)
        print("      魈公 爱 光璃", flush=True)
        print("      2026-11-10", flush=True)
        print("", flush=True)
        raise SystemExit(0)

    _where = "只有本机可访问" if HOST == "127.0.0.1" else "局域网 / 公网可访问"
    print(f"[启动] 监听 {HOST}:{PORT}（{_where}）", flush=True)
    demo.queue(default_concurrency_limit=None).launch(
        server_name=HOST,
        server_port=PORT,
        allowed_paths=[os.path.abspath("static")],
    )
