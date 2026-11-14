"""明堂 · Gradio 界面装配。

负责
  · 把登录、聊天、记忆、导出、剧情这些区块拼成一个 Blocks
  · 把按钮接到对应的回调上

不负责
  · 不实现任何业务逻辑（回调都在别的模块里）
"""
# 名字　明堂 —— 天子布政之堂。所有东西在这一个屋子里被看见。


import uuid

import gradio as gr

from config import DEFAULT_PERSONA
from config import GALGAME_ENABLED
from config import PERSONAS
from config import SHOW_STARTUP_NOTICE

from webui.auth import do_change_password, do_guest, do_keep, do_login, do_logout, do_register
from webui.background import do_reset_bg, do_set_bg
from webui.chat import clear_chat, respond
from webui.export import do_export_all, do_export_book, do_export_refresh, do_export_txt
from webui.memory import MEM_ORDER, do_mem_action, do_pin, do_preview_memory, do_save_memory_mode, do_save_prefs, open_profile
from webui.persona import do_create_persona, do_delete_persona, switch_persona, toggle_create
from webui.relation import _refresh_stage_wrap, do_tell, hide_tell_confirm, open_milestones, show_tell_confirm
from webui.render import _load_template, get_bg_style, get_static_css, render_relationship
from webui.story import STORY_AUTO, STORY_ORIGINS, do_story_refresh, do_story_start


CSS = get_static_css()
NOTICE_HTML = _load_template("notice.html")
BANNER_XLL_HTML = _load_template("banner_xll.html")
FOOTER_HTML = _load_template("footer.html")


with gr.Blocks(title="陪你AI", theme=gr.themes.Soft(), css=CSS) as demo:
    user_id_state = gr.State(value=None)
    session_id_state = gr.State(value=str(uuid.uuid4()))
    persona_state = gr.State(value=DEFAULT_PERSONA)
    # 游客的临时凭证。有它就走免登录路径，没有就是正常登录用户。
    guest_token_state = gr.State(value=None)

    bg_layer = gr.HTML(value=get_bg_style(is_login=True), elem_id="bg-layer")

    # 先出警告，点"我明白了"才显示登录区
    with gr.Group(visible=SHOW_STARTUP_NOTICE) as notice_group:
        gr.HTML(NOTICE_HTML)
        notice_btn = gr.Button("我明白了，进去吧", variant="primary")

    with gr.Group(visible=not SHOW_STARTUP_NOTICE) as login_group:
        gr.HTML(BANNER_XLL_HTML)
        gr.Markdown(
            "# 陪你 AI\n"
            "**她记得你说过的话。** 不是聊天记录回放——你手酸过、你明天有实训，"
            "这些她会自己想起来。\n\n"
            "有问题找我：QQ **3427873405**"
        )

        # 免登录试聊：放在最上面。它比登录按钮重要——
        # 陌生人这时候还不知道这里有什么，不该先让他填表。
        guest_btn = gr.Button("不注册，先和她说几句（10 轮）", variant="primary")
        with gr.Tab("登录"):
            login_username = gr.Textbox(label="用户名")
            login_password = gr.Textbox(label="密码", type="password")
            login_btn = gr.Button("登录", variant="primary")
        with gr.Tab("注册"):
            reg_username = gr.Textbox(label="用户名")
            reg_password = gr.Textbox(label="密码", type="password")
            reg_password2 = gr.Textbox(label="确认密码", type="password")
            reg_invite = gr.Textbox(label="邀请码")
            reg_btn = gr.Button("注册", variant="primary")
        login_msg = gr.Markdown("")

    with gr.Group(visible=False) as chat_group:
        with gr.Row():
            persona_dropdown = gr.Dropdown(
                choices=list(PERSONAS.keys()),
                value=DEFAULT_PERSONA,
                label="选择角色",
                scale=2,
                elem_id="persona-select",
            )
            new_btn_open = gr.Button("＋", scale=0)
            logout_btn = gr.Button("退出登录", scale=0)
            ms_btn = gr.Button("纪念", scale=0)
            pf_btn = gr.Button("我的", scale=0)

        with gr.Group(visible=False) as create_group:
            gr.Markdown(
                "### 新建一个她\n"
                "**只要三个问题。** 材料越具体，她越像。\n\n"
                "_她不是你认识的那个人。她是根据你给的材料重建的。_"
            )
            new_name = gr.Textbox(label="她叫什么", placeholder="小柳")
            new_call = gr.Textbox(label="她怎么称呼你", placeholder="魈公 / 宝宝 / 喂")
            new_quote = gr.Textbox(
                label="她说过的、你最记得的一句话（原话最好）",
                lines=3, placeholder="你别老是自己扛着吧",
            )
            new_state = gr.Dropdown(
                label="你们现在",
                choices=["还在一起", "分开了，还在联系", "分开了，不联系了", "她已经不在了"],
                value="分开了，不联系了",
            )
            new_target = gr.Dropdown(
                label="你想要的是",
                choices=["复合", "告别", "恋爱", "自定义"],
                value="复合",
            )
            with gr.Accordion("有聊天记录吗？（可选，但会像很多）", open=False):
                new_raw = gr.Textbox(
                    label="把聊天记录粘进来",
                    lines=8,
                    placeholder="她说：……\n我说：……\n（什么格式都行，认不出来我来猜）",
                )
            new_go = gr.Button("生成她", variant="primary")
            new_msg = gr.Markdown("")
            with gr.Row():
                del_btn = gr.Button("删掉现在那个", variant="stop", size="sm")
                del_msg = gr.Markdown("")

        relationship_html = gr.HTML("")


        # 顶部状态条：像微信标题栏那样显示"XX正在输入……"
        typing_status = gr.Markdown("", elem_id="typing-status")

        # 关系状态条（只有私有角色会显示内容）
        with gr.Row():
            stage_bar = gr.Markdown("", elem_id="stage-bar", scale=4)
            tell_btn = gr.Button("告诉她：我们已经结束了", scale=0, visible=False)

        # 二次确认：不可逆的操作，必须先说清楚后果
        with gr.Group(visible=False) as tell_confirm_group:
            tell_confirm_md = gr.Markdown(
                "### 确定要告诉她吗？\n\n"
                "她会知道你们已经结束了。\n\n"
                "- 她会开始躲，会岔开话题\n"
                "- 你们回不到现在这个状态了\n"
                "- 想重来，只能重新建一个她\n\n"
                "**这一步不能撤回。**"
            )
            with gr.Row():
                tell_yes = gr.Button("确定，告诉她", variant="primary")
                tell_no = gr.Button("我再想想")

        # 告别页：她走了之后，把她说过的话留下来
        with gr.Group(visible=False) as farewell_group:
            farewell_md = gr.Markdown("")

        chatbot = gr.Chatbot(
            height=460,
            elem_id="chatbot",
            group_consecutive_messages=False,
        )
        msg = gr.Textbox(placeholder="说点什么...", label="消息")

        # 十轮讲完之后，这里出那一行字 + 就地注册的小表单
        guest_end_md = gr.Markdown("")
        with gr.Group(visible=False) as guest_save_group:
            gr.Markdown("### 把她留下")
            gr.Markdown("_她说她不想忘。留下，她就记得这十轮。_")
            guest_new_user = gr.Textbox(label="用户名")
            guest_new_pwd = gr.Textbox(label="密码", type="password")
            guest_save_btn = gr.Button("留下她", variant="primary")
            guest_save_msg = gr.Markdown("")

        with gr.Row():
            send_btn = gr.Button("发送", variant="primary")
            clear_btn = gr.Button("清空")

    # ===== 纪念页（独立一屏）=====
    # 和聊天区互斥显示：点"纪念"藏起聊天、点"返回聊天"换回来。
    with gr.Group(visible=False) as milestone_group:
        with gr.Row():
            gr.Markdown("### 🕯️ 我们到过的地方")
            ms_back_btn = gr.Button("返回聊天", scale=0)
        milestone_html = gr.HTML("")

    # ===== 个人主页（独立一屏）=====
    # 和聊天区互斥：点"我的"藏起聊天，点"返回聊天"换回来。
    with gr.Group(visible=False, elem_id="profile-page") as profile_group:
        with gr.Row():
            gr.Markdown("### 👤 我的")
            gr.HTML(
                '<div style="margin:8px 0 14px;font-size:13px;line-height:2.0">'
                '<a href="/voice" target="_blank" style="color:#4e6ef2;text-decoration:none;font-weight:600">她说话的样子</a>'
                '<span style="color:#8b8b8b"> · 调她说话的长短、温度、去 AI 味</span>'
                '<br><a href="/menu" target="_blank" style="color:#4e6ef2;text-decoration:none;font-weight:600">全部功能</a>'
                '<span style="color:#8b8b8b"> · 这个站所有页面的一览</span>'
                '</div>'
            )
            pf_back_btn = gr.Button("返回聊天", scale=0)
        profile_html = gr.HTML("")
        with gr.Accordion("修改密码", open=False):
            old_pwd = gr.Textbox(label="旧密码", type="password")
            new_pwd = gr.Textbox(label="新密码", type="password")
            new_pwd2 = gr.Textbox(label="确认新密码", type="password")
            pwd_btn = gr.Button("修改密码")
            pwd_msg = gr.Markdown("")

        with gr.Accordion("她的说话方式", open=False):
            gr.HTML(
                '<div style="font-size:12.5px;line-height:1.9;color:#646a73;'
                'margin-bottom:8px">'
                '想调得更细（长度、温度、去 AI 味）→ '
                '<a href="/voice" target="_blank" style="color:#4e6ef2;'
                'text-decoration:none">打开「她说话的样子」</a>'
                '（新标签页，和这里是同一份设置）'
                '</div>'
            )
            style_radio = gr.Radio(
                choices=[("短句", "short"), ("正常", "normal"), ("说多点", "long")],
                value="normal", label="回复长短",
            )
            quiet_on = gr.Checkbox(label="开启免打扰（这段时间她像在睡觉）", value=False)
            with gr.Row():
                quiet_start = gr.Textbox(label="从", value="23:30", scale=1)
                quiet_end = gr.Textbox(label="到", value="07:00", scale=1)
            pref_btn = gr.Button("保存设置")
            pref_msg = gr.Markdown("")

        with gr.Accordion("她的记性（本地测试用）", open=False):
            gr.Markdown(
                "她怎么「记起」以前的事。\n\n"
                "- **像人**：时间越久的越模糊，近的更清楚。"
                "她不会说「我忘了」，只会说「你再说一遍那个」。\n"
                "- **记得细**：所有翻到的旧记录都原样给你，细节全在，但像数据库。\n\n"
                "_这是原来纯 BM25 的行为，出问题就切回它。_"
            )
            mem_radio = gr.Radio(
                choices=["像人", "记得细"],
                value="像人",
                label="她的记性",
            )
            with gr.Row():
                mem_save = gr.Button("保存", variant="primary", scale=1)
                mem_preview = gr.Button("对比一下（拿你上一句话）", scale=2)
            mem_msg = gr.Markdown("")
            with gr.Row():
                with gr.Column():
                    mem_out_pure = gr.Markdown("")
                with gr.Column():
                    mem_out_mixed = gr.Markdown("")

        with gr.Accordion("换背景（老友专属）", open=False):
            gr.Markdown(
                "给某个角色换一张背景。**切到那个角色时生效。**\n\n"
                "_每张我要人工看一眼才会放出来，可能要等一会儿。_"
            )
            bg_persona = gr.Dropdown(
                choices=list(PERSONAS.keys()), value=DEFAULT_PERSONA,
                label="给哪个角色换",
            )
            bg_img = gr.Image(
                label="选一张图", type="filepath", sources=["upload"],
                height=200,
            )
            with gr.Row():
                bg_set = gr.Button("换上", variant="primary")
                bg_reset = gr.Button("用回原来的")
            bg_msg = gr.Markdown("")

        with gr.Accordion("把这段带走（导出）", open=False):
            gr.Markdown(
                "**聊天记录免费，纪念册收费。**\n\n"
                "_记录是你自己的，随时能下载。纪念册是排好版的，带封面和她的日记。_"
            )
            export_persona = gr.Dropdown(choices=[], value=None, label="选角色")
            export_load = gr.Button("载入我的角色")
            with gr.Row():
                export_txt_btn = gr.Button("下载聊天记录（免费）")
                export_book_btn = gr.Button("做一份纪念册（3 元）", variant="primary")
            export_all_btn = gr.Button("全部角色一份（9.9 元）")
            export_msg = gr.Markdown("")

        with gr.Accordion("给她做一趟旅行（5 元一次）", open=False, visible=GALGAME_ENABLED):
            gr.Markdown(
                "**七天。** 从你家出发，到她那座城，然后回来。\n\n"
                "_每次 5 元，一共能做 5 次。做好了会给你一个链接，点开就能看。_"
            )
            gr.Markdown("**去哪：杭州**（固定）")
            story_origin = gr.Dropdown(
                choices=STORY_ORIGINS, value=STORY_AUTO,
                label="从哪出发",
            )
            with gr.Row():
                story_go = gr.Button("生成我的七日", variant="primary")
                story_refresh = gr.Button("刷新")
            story_quota = gr.Markdown("")
            story_msg = gr.Markdown("")
            story_list = gr.Markdown("_还没有。_")

        with gr.Accordion("她的记忆", open=True):
            gr.Markdown(
                "她记得的事，按角色分开列在这里。\n\n"
                "勾选后可以**锁定**（永不遗忘）或**忘掉**。"
                "🔒 表示已锁定。每个角色能锁的条数有上限，"
                "超了会自动让位给她自己记的事。"
            )
            pin_stat = gr.Markdown("", elem_id="pin-stat")
            gr.Markdown("#### 所有角色都记得")
            mem_global = gr.CheckboxGroup(
                choices=[], label="共享记忆", interactive=True, elem_id="memg-shared",
            )
            mem_boxes = {}
            for _i, _p in enumerate(MEM_ORDER):
                gr.Markdown(f"#### {_p}")
                mem_boxes[_p] = gr.CheckboxGroup(
                    choices=[], label=_p, interactive=True, show_label=False,
                    elem_id=f"memg-{_i}",
                )
            with gr.Row():
                mem_lock_btn = gr.Button("🔒 锁定选中的")
                mem_unlock_btn = gr.Button("🔓 取消锁定")
                mem_del_btn = gr.Button("🗑 忘掉选中的")
            mem_msg = gr.Markdown("")
            gr.Markdown("---")
            gr.Markdown("#### 手动让她记住")
            with gr.Row():
                pin_target = gr.Dropdown(
                    choices=list(PERSONAS.keys()) + ["所有角色"],
                    value=DEFAULT_PERSONA, label="让谁记住", scale=1,
                    elem_id="pin-target",
                )
                pin_text = gr.Textbox(
                    label="内容", placeholder="比如：我的生日是 10 月 1 日", scale=3,
                )
            pin_btn = gr.Button("记住这件事")

    # ============ 事件绑定 ============

    notice_btn.click(
        lambda: (gr.update(visible=False), gr.update(visible=True)),
        None,
        [notice_group, login_group],
    )

    guest_save_btn.click(
        do_keep,
        [guest_new_user, guest_new_pwd, guest_token_state],
        [user_id_state, chat_group, guest_save_group, chatbot,
         guest_end_md, relationship_html, guest_save_msg],
    )

    guest_btn.click(
        do_guest,
        None,
        [user_id_state, login_msg, login_group, chat_group, chatbot,
         persona_state, bg_layer, relationship_html, guest_token_state,
         persona_dropdown],
    )

    login_btn.click(
        do_login,
        [login_username, login_password],
        [user_id_state, login_msg, login_group, chat_group, chatbot,
         persona_state, bg_layer, relationship_html],
    )

    reg_btn.click(
        do_register,
        [reg_username, reg_password, reg_password2, reg_invite],
        [user_id_state, login_msg, login_group, chat_group, chatbot],
    ).then(
        lambda uid: (DEFAULT_PERSONA, get_bg_style(DEFAULT_PERSONA), "") if uid else (DEFAULT_PERSONA, get_bg_style(is_login=True), ""),
        [user_id_state],
        [persona_state, bg_layer, relationship_html],
    )

    logout_btn.click(
        do_logout,
        None,
        [user_id_state, login_msg, login_group, chat_group, chatbot,
         persona_state, bg_layer, relationship_html],
    )

    # 进纪念页（藏起聊天区）
    ms_btn.click(
        open_milestones,
        [user_id_state, persona_state],
        [chat_group, milestone_group, milestone_html],
    )

    # 回聊天
    ms_back_btn.click(
        lambda: (gr.update(visible=True), gr.update(visible=False)),
        None,
        [chat_group, milestone_group],
    )

    # 进个人主页（藏起聊天区）
    _mem_outputs = [pin_stat, mem_global] + [mem_boxes[p] for p in MEM_ORDER]
    pf_btn.click(
        open_profile,
        [user_id_state, persona_state],
        [chat_group, profile_group, profile_html, style_radio, quiet_on,
         quiet_start, quiet_end, mem_radio] + _mem_outputs + [pin_target],
    )

    # 保存说话方式 / 免打扰
    mem_save.click(
        do_save_memory_mode,
        inputs=[user_id_state, mem_radio],
        outputs=[mem_msg],
    )
    mem_preview.click(
        do_preview_memory,
        inputs=[user_id_state, persona_state],
        outputs=[mem_out_pure, mem_out_mixed],
    )
    pref_btn.click(
        do_save_prefs,
        [user_id_state, style_radio, quiet_on, quiet_start, quiet_end],
        [pref_msg],
    )

    # 记忆管理：锁定 / 取消锁定 / 忘掉（所有分组一起处理）
    _mem_inputs = [user_id_state] + _mem_outputs
    _mem_results = [mem_msg] + _mem_outputs
    mem_lock_btn.click(
        lambda u, *gs: do_mem_action(u, "lock", *gs),
        _mem_inputs, _mem_results,
    )
    mem_unlock_btn.click(
        lambda u, *gs: do_mem_action(u, "unlock", *gs),
        _mem_inputs, _mem_results,
    )
    mem_del_btn.click(
        lambda u, *gs: do_mem_action(u, "delete", *gs),
        _mem_inputs, _mem_results,
    )
    pin_btn.click(
        do_pin,
        [user_id_state, pin_target, pin_text],
        _mem_results,
    )

    # 从主页回聊天
    pf_back_btn.click(
        lambda: (gr.update(visible=True), gr.update(visible=False)),
        None,
        [chat_group, profile_group],
    )

    # 改密码
    pwd_btn.click(
        do_change_password,
        [user_id_state, old_pwd, new_pwd, new_pwd2],
        [pwd_msg],
    )

    new_btn_open.click(toggle_create, None, [create_group])

    del_btn.click(
        do_delete_persona,
        [user_id_state],
        [del_msg, persona_dropdown, create_group],
    ).then(
        lambda p: p,
        [persona_dropdown],
        [persona_state],
    )

    new_go.click(
        do_create_persona,
        [new_name, new_call, new_quote, new_state, new_target,
         user_id_state, session_id_state, new_raw],
        [new_msg, create_group, persona_dropdown, chatbot, bg_layer, session_id_state],
    ).then(
        lambda p: p,
        [persona_dropdown],
        [persona_state],
    ).then(
        render_relationship,
        [user_id_state, persona_state],
        [relationship_html],
    )

    persona_dropdown.change(
        switch_persona,
        [persona_dropdown, user_id_state, session_id_state],
        [chatbot, bg_layer, session_id_state],
    ).then(
        lambda p: p,
        [persona_dropdown],
        [persona_state],
    ).then(
        render_relationship,
        [user_id_state, persona_state],
        [relationship_html],
    ).then(
        _refresh_stage_wrap,
        [user_id_state, persona_state],
        [stage_bar, tell_btn, farewell_md, farewell_group],
    )

    bg_set.click(
        do_set_bg,
        [user_id_state, bg_persona, bg_img],
        [bg_msg],
    )

    bg_reset.click(
        do_reset_bg,
        [user_id_state, bg_persona],
        [bg_msg],
    )

    export_load.click(
        do_export_refresh,
        [user_id_state],
        [export_msg, export_persona],
    )

    export_txt_btn.click(
        do_export_txt,
        [user_id_state, export_persona],
        [export_msg],
    )

    export_book_btn.click(
        do_export_book,
        [user_id_state, export_persona],
        [export_msg],
    )

    export_all_btn.click(
        do_export_all,
        [user_id_state],
        [export_msg],
    )

    story_go.click(
        do_story_start,
        [user_id_state, story_origin, persona_state],
        [story_msg, story_list],
    ).then(
        do_story_refresh,
        [user_id_state],
        [story_quota, story_list],
    )

    story_refresh.click(
        do_story_refresh,
        [user_id_state],
        [story_quota, story_list],
    )

    tell_btn.click(show_tell_confirm, None, [tell_confirm_group])
    tell_no.click(hide_tell_confirm, None, [tell_confirm_group])
    tell_yes.click(
        do_tell,
        [user_id_state, persona_state],
        [stage_bar, tell_btn, farewell_md, farewell_group],
    ).then(
        hide_tell_confirm, None, [tell_confirm_group],
    )

    msg.submit(
        respond,
        [msg, chatbot, user_id_state, session_id_state, persona_state, guest_token_state],
        [msg, chatbot, relationship_html, typing_status,
         guest_save_group, guest_end_md],
    ).then(
        _refresh_stage_wrap,
        [user_id_state, persona_state],
        [stage_bar, tell_btn, farewell_md, farewell_group],
    )
    send_btn.click(
        respond,
        [msg, chatbot, user_id_state, session_id_state, persona_state, guest_token_state],
        [msg, chatbot, relationship_html, typing_status,
         guest_save_group, guest_end_md],
    ).then(
        _refresh_stage_wrap,
        [user_id_state, persona_state],
        [stage_bar, tell_btn, farewell_md, farewell_group],
    )
    clear_btn.click(clear_chat, None, [chatbot, session_id_state])

    # 页脚：备案号（所有页面底部都显示）
    gr.HTML(FOOTER_HTML)


# ---- IP 地区拦截（默认关闭；开关在 ipblock.json）----
# 注意：launch() 会用 App.create_app() 重新建一个 app，
# 直接给 demo.app 挂中间件会被丢掉。所以这里包装 create_app。
# 纯 ASGI 中间件，不缓冲响应，不影响流式输出。
# 关闭时只做一次 os.stat，零开销；查询失败一律放行。
