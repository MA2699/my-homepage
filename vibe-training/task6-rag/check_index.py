"""index.json 建库验收脚本：核对提示词里约定的三项验收。

用法：
    python check_index.py                       # 默认检查 index.json
    python check_index.py --seed 6              # 固定随机种子，抽查结果可复现
    python check_index.py index_200_30.json     # 切分对比实验时检查指定索引文件

三项验收：① 块数 ≈ 总字数/340  ② 随机抽 3 块与原文逐字一致  ③ 所有 vec 长度相同
"""
import json
import os
import random
import sys

DOCS_DIR = "docs"
TOLERANCE = 0.15     # 验收①允许的偏差比例


def load_docs(docs_dir=DOCS_DIR):
    """读回 docs/ 原文，用于验收②的逐字比对"""
    docs = {}
    for name in os.listdir(docs_dir):
        path = os.path.join(docs_dir, name)
        if os.path.isfile(path) and name.lower().endswith((".txt", ".md")):
            with open(path, encoding="utf-8") as f:
                docs[name] = f.read()
    return docs


def check(index_file="index.json", docs_dir=DOCS_DIR, sample=3, seed=None):
    with open(index_file, encoding="utf-8") as f:
        idx = json.load(f)
    docs = load_docs(docs_dir)

    passed = []

    # 验收① 块数 ≈ 总字数 / 340
    total_chars = sum(len(t) for t in docs.values())
    expect = total_chars / 340
    ok1 = abs(len(idx) - expect) / expect <= TOLERANCE if expect else False
    passed.append(ok1)
    print(f"① 块数        ：期望 ≈ {expect:.1f}，实际 {len(idx)}"
          f"（偏差 {abs(len(idx) - expect) / expect * 100:.1f}%，容差 {TOLERANCE:.0%}）"
          f"  →  {'通过' if ok1 else '不通过'}")

    # 验收② 随机抽 sample 块，逐字回查原文
    picked = random.Random(seed).sample(idx, min(sample, len(idx)))
    ok2 = True
    print(f"② 抽查 {len(picked)} 块    ：")
    for c in picked:
        hit = c["source"] in docs and c["text"] in docs[c["source"]]
        ok2 &= hit
        print(f"     id={c['id']}  {c['source']}  {len(c['text'])} 字"
              f"  逐字命中原文: {hit}")
        print(f"        开头: {c['text'][:44]!r}")
    print(f"   →  {'通过' if ok2 else '不通过'}")
    passed.append(ok2)

    # 验收③ 所有向量长度相同
    dims = {len(c["vec"]) for c in idx}
    ok3 = len(dims) == 1 and len(idx) > 0
    passed.append(ok3)
    print(f"③ 向量长度集合：{sorted(dims)}  →  {'通过' if ok3 else '不通过'}")

    print(f"\n{'全部通过' if all(passed) else '存在未通过项'}  "
          f"（入库 {len(idx)} 块，覆盖 {len(docs)} 份文档）")
    return all(passed)


if __name__ == "__main__":
    argv = sys.argv[1:]
    seed = None
    if "--seed" in argv:
        i = argv.index("--seed")
        seed = int(argv[i + 1])
        del argv[i:i + 2]
    target = argv[0] if argv else "index.json"
    sys.exit(0 if check(target, seed=seed) else 1)
