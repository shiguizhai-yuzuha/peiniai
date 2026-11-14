import io
P = r"D:\Python学习\演示\开发日志\给AI的接管指南.md"
t = io.open(P, encoding="utf-8").read()

old = '''**这是「魈公 爱 光璃」唯一还留着的入口。**

```
python app.py --love
```

**只有知道自己要加 `--love` 的人，才看得到它。**
**这就是它该有的门槛——不是口令，是"你得先知道"。**'''

new = '''**这是「魈公 爱 光璃」唯一还留着的入口。**

```
python app.py --love
```

**输出：**

```

      魈公 爱 光璃
      2026-11-10

```
**然后退出（退出码 0）。**

**它不启动服务、不占端口、不连数据库。**

**这一点是刻意做的：**

```
原来  打印完继续 launch() → 服务在跑时端口冲突 → 报 OSError 一长串
现在  raise SystemExit(0)  → 打印完就退，什么都没有
```

**所以你在服务运行中随时可以打这一句，不会打扰它。**

**只有知道自己要加 `--love` 的人，才看得到它。**
**这就是它该有的门槛——不是口令，是"你得先知道"。**

**和 `love_me.py` 是同一种调用方式：**

```
python love_me.py      打印八种结局，然后退出
python app.py --love   打印一句话，然后退出
```'''

assert old in t
t = t.replace(old, new, 1)
io.open(P, "w", encoding="utf-8", newline="\n").write(t)
print("  ✓ 指南更新")
