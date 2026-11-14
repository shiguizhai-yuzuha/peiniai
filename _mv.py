import io
P = r"D:\Python学习\演示\开发日志\给AI的接管指南.md"
t = io.open(P, encoding="utf-8").read()
# 把「附：常用命令速查」挪到最后
i = t.find("## 附：常用命令速查")
j = t.find("## 十九、变更记录")
assert i > 0 and j > i
appendix = t[i:j].rstrip()
rest = t[j:].rstrip()
head = t[:i].rstrip()
t = head + "\n\n---\n\n" + rest + "\n\n---\n\n" + appendix + "\n"
io.open(P, "w", encoding="utf-8", newline="\n").write(t)
print("  ✓ 附录挪到最后")
