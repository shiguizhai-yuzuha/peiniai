import io
P = r"D:\Python学习\演示\app.py"
t = io.open(P, encoding="utf-8").read()

old = '''    if "--love" in sys.argv:
        print("", flush=True)
        print("      魈公 爱 光璃", flush=True)
        print("      2026-11-10", flush=True)
        print("", flush=True)'''
new = '''    if "--love" in sys.argv:
        # 只打印这一句，然后退出。不启动服务，不占端口。
        print("", flush=True)
        print("      魈公 爱 光璃", flush=True)
        print("      2026-11-10", flush=True)
        print("", flush=True)
        raise SystemExit(0)'''

assert old in t
t = t.replace(old, new, 1)
io.open(P, "w", encoding="utf-8", newline="\n").write(t)
print("  ✓ --love 现在打印完就退出")
