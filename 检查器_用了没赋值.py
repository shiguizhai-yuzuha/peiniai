# -*- coding: utf-8 -*-
"""只查一种笨错：函数顶层有赋值，但在它之前就用了。

就是今晚那个：
    line 165  messages.append(...)
    line 332  messages = []

判定规则（收窄到零误报）：
  ① 只认"函数体顶层"的赋值（if/for/try 里的不算）
  ② 只认函数内唯一的顶层赋值点
  ③ 若该名字在更早的行被读过 → 报
这样循环变量、条件赋值都不会误报。
"""
import ast
import io
import os

SKIP = ("__pycache__", "venv", "版本博物馆", "备份", "node_modules")


def top_level_assigns(func):
    """函数体顶层（直接子语句）里赋值的名字 → 最小行号。"""
    out = {}
    for st in func.body:
        targets = []
        if isinstance(st, ast.Assign):
            for t in st.targets:
                targets.append(t)
        elif isinstance(st, (ast.AnnAssign, ast.AugAssign)):
            targets.append(st.target)
        for t in targets:
            for x in ast.walk(t):
                if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Store):
                    nm = x.id
                    ln = st.lineno
                    if nm not in out or ln < out[nm]:
                        out[nm] = ln
    return out


def all_reads(func):
    """函数里所有读某个名字的行号。"""
    out = {}
    for n in ast.walk(func):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
            out.setdefault(n.id, []).append(n.lineno)
    return out


def check_function(func, module_names, params):
    tl = top_level_assigns(func)
    reads = all_reads(func)
    problems = []

    # 这个函数里"只在非顶层赋值"的名字（循环变量等），不查
    nested_only = set()
    for n in ast.walk(func):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
            if n.id not in tl:
                nested_only.add(n.id)

    for nm, assign_line in tl.items():
        if nm in params or nm in module_names:
            continue
        if nm in nested_only:
            continue
        lines = [l for l in reads.get(nm, []) if l < assign_line]
        if lines:
            problems.append((min(lines), assign_line, func.name, nm))
    return problems


def scan(path):
    try:
        tree = ast.parse(io.open(path, encoding="utf-8-sig").read(), filename=path)
    except SyntaxError as e:
        return [("SYNTAX", e.lineno or 0, 0, os.path.basename(path), str(e))]

    # 只收“模块级”的名字（Module.body 的直接子语句）。
    # 不能把函数里的局部赋值也收进来，否则每个局部变量都被当全局，什么都查不出。
    module_names = set()
    for st in tree.body:
        if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            module_names.add(st.name)
        elif isinstance(st, ast.Assign):
            for tg in st.targets:
                for x in ast.walk(tg):
                    if isinstance(x, ast.Name):
                        module_names.add(x.id)
        elif isinstance(st, (ast.AnnAssign, ast.AugAssign)):
            for x in ast.walk(st.target):
                if isinstance(x, ast.Name):
                    module_names.add(x.id)
        elif isinstance(st, (ast.Import, ast.ImportFrom)):
            for a in st.names:
                module_names.add((a.asname or a.name).split(".")[0])
        elif isinstance(st, ast.Try):
            for sub in ast.walk(st):
                if isinstance(sub, ast.Assign):
                    for tg in sub.targets:
                        for y in ast.walk(tg):
                            if isinstance(y, ast.Name):
                                module_names.add(y.id)

    out = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            params = set()
            a = node.args
            for x in list(a.posonlyargs) + list(a.args) + list(a.kwonlyargs):
                params.add(x.arg)
            for pr in check_function(node, module_names, params):
                out.append(("USE_BEFORE", pr[0], pr[1], pr[2], pr[3]))
    return out


def main():
    root = r"D:\Python学习\演示"
    files = []
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in SKIP]
        for f in fns:
            if f.endswith(".py"):
                files.append(os.path.join(dp, f))

    print("扫描 %d 个文件" % len(files))
    print()
    n = 0
    for p in sorted(files):
        for kind, use_line, assign_line, fname, detail in scan(p):
            rel = p.replace(root + "\\", "")
            if kind == "SYNTAX":
                print("  [语法] %-32s %s" % (rel, detail))
            else:
                print("  [%s] %-30s 第 %4d 行用了 %-16s（它在第 %d 行才赋值）"
                      % ("用了没赋值", rel, use_line, detail, assign_line))
            n += 1
    print()
    print("可疑点：%d" % n)


if __name__ == "__main__":
    main()
