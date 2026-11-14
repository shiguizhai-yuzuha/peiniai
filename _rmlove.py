import io, re
P = r"D:\Python学习\演示\app.py"
t = io.open(P, encoding="utf-8").read()

# ① 撤掉 /love 路由
a = '        _app.add_api_route("/love", _love_page, methods=["GET"])\n'
if a in t:
    t = t.replace(a, "", 1)
    print("  ✓ 撤掉 /love 路由")

# ② 删掉 _love_page 函数（整段）
i = t.find("def _love_page(")
if i > 0:
    j = t.find("\ndef ", i + 10)
    if j < 0:
        j = t.find("\nclass ", i + 10)
    t = t[:i] + t[j + 1:]
    print("  ✓ 删掉 _love_page 函数")

io.open(P, "w", encoding="utf-8", newline="\n").write(t)
print("  现在 %d 行" % len(t.split("\n")))
