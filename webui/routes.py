"""津渡 · 文件路由：纪念册、背景图。

负责
  · /keepsake/{name} /keepsake/dl/{name}
  · /bg/{name}

安全
  · 一律 basename，掐掉 ../"""
# 名字　津渡 —— 渡口。所有要拿东西走的人，都从这里过。


import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from services import keepsake as gkeep


def _keepsake_file(name: str, dl: int = 0):
    """把纪念册 / 聊天记录发给浏览器。

    文件名是纯 ASCII 短码（不会有编码问题）。
    友好名（中文）存在同名 .name 边车里，下载时塞进 Content-Disposition。
    """
    from fastapi.responses import FileResponse, HTMLResponse
    import re as _re

    if not _re.fullmatch(r"[A-Za-z0-9_-]{1,64}(\.[A-Za-z0-9]{1,6})?", name or ""):
        return HTMLResponse("<meta charset='utf-8'><h2>地址不对</h2>", status_code=400)

    path = os.path.join(gkeep.OUT_DIR, name)
    if not os.path.isfile(path) or name.endswith(".name"):
        return HTMLResponse("<meta charset='utf-8'><h2>找不到这一份</h2>", status_code=404)

    media = ("text/plain; charset=utf-8" if name.endswith(".txt")
             else "text/html; charset=utf-8")
    if dl:
        return FileResponse(path, media_type=media,
                            filename=name)
    return FileResponse(path, media_type=media)


def _keepsake_dl(name: str):
    """下载专用路径。不用查询参数 —— nginx 那边对 ?dl=1 处理不稳，会偶发 400。"""
    return _keepsake_file(name, 1)


def _bg_image(name: str):
    """背景图。Gradio 不路由我们的 /static，所以自己开一个。"""
    from fastapi.responses import FileResponse, Response
    base = _ROOT
    safe = os.path.basename(name)          # 只允许文件名，挡掉 ../
    fp = os.path.join(base, "static", safe)
    if not os.path.isfile(fp):
        return Response(status_code=404)
    return FileResponse(fp, headers={"Cache-Control": "public, max-age=86400"})
