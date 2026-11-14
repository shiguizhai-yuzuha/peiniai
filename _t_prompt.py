import sys, os
sys.path.insert(0, r"D:\Python学习\演示"); os.chdir(r"D:\Python学习\演示")
from core import personas
from config import DEFAULT_PERSONA, PERSONAS

p = personas.get_prompt(DEFAULT_PERSONA)
print("  角色:", DEFAULT_PERSONA)
print("  提示词长度:", len(p), "字")
print("  含样本:", "【人说话的样子】" in p)
print()
print("  --- 末尾 20 行 ---")
for ln in p.split("\n")[-20:]:
    print("    " + ln)
