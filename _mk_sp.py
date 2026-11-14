import io
io.open(r"C:\Users\HUAWEI\Documents\deepseek-harness\default-workspace\_srv_prof.py","w",encoding="utf-8").write('''
import sys, os
sys.path.insert(0, "/opt/mybot"); os.chdir("/opt/mybot")
from webui.memory import open_profile
for name, uid, per in (("fgv", "f5d4615f-f3d9-4354-9077-3ea934c483b8", "流萤"),
                       ("刘", "4762a16f-c045-4b40-aa6f-076471bd7e4c", "浮波柚叶")):
    try:
        out = open_profile(uid, per)
        html = out[2]
        import re
        txt = re.sub(r"<[^>]+>", " ", html)
        txt = re.sub(r"\\\\s+", " ", txt).strip()
        print("  %-4s ✓ %d 项" % (name, len(out)))
        print("      " + txt[:150])
    except Exception as e:
        print("  %-4s ✗ %s: %s" % (name, type(e).__name__, e))
''')
print("ok")
