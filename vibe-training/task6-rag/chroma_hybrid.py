"""拓展④：用 Chroma 替换手写检索，再叠加关键词匹配做混合打分。

用法：
    python chroma_hybrid.py --compare    # 3 个含专有名词的问题：纯向量 vs 混合
    python chroma_hybrid.py              # 交互问答（Chroma + 混合检索）

对比 ask.py 的两点差异：
    1. 检索后端从手写 numpy 余弦换成 Chroma（HNSW 索引 + 余弦空间）
    2. 打分从纯向量换成向量分 + 字符 n-gram 关键词分的加权混合
"""
import json
import os
import sys

import chromadb
import requests
from dotenv import load_dotenv

INDEX_FILE = "index.json"
TOP_K = 3
ALPHA = 0.5       # 混合打分中向量分的权重，1-ALPHA 给关键词分
NGRAM = 3         # 关键词匹配用的字符 n-gram 长度

# 3 个含专有名词/精确数值的问题。选材依据：先用纯向量探过一遍，
# 挑出「已成功 / 擦边 / 已失败」三种难度各一个，好看出混合技术的边界。
COMPARE_QUESTIONS = [
    ("开题报告要求外文文献不少于多少篇？", "外文文献不少于3篇"),         # 专有名词 + 数字
    ("答辩的时候每个人要讲多久？", "8‑10分钟"),                         # 口语化改写
    ("报销被驳回后需要在几个工作日内重新提交？", "7个工作日内完成修改"),   # 已知纯向量失败
]

SYSTEM = """你是知识库问答助手。规则：
1. 只根据用户消息中提供的【参考资料】回答，禁止使用资料之外的知识；
2. 资料不足以回答时，明确说「资料中未找到相关内容」，不要编造；
3. 回答末尾用【来源：文件名·块id】标注依据；
4. 当回答为「资料中未找到相关内容」时，不要标注任何来源——没有依据可标。"""


def get_embeddings(texts):
    resp = requests.post(
        os.getenv("EMBEDDING_BASE_URL").rstrip("/") + "/embeddings",
        headers={"Authorization": "Bearer " + os.getenv("EMBEDDING_API_KEY")},
        json={"model": os.getenv("EMBEDDING_MODEL"), "input": texts},
        timeout=60)
    resp.raise_for_status()
    return [d["embedding"] for d in resp.json()["data"]]


def ngrams(text, n=NGRAM):
    return {text[i:i + n] for i in range(max(len(text) - n + 1, 0))}


def keyword_score(query, text, n=NGRAM):
    """问题里有多大比例的字符 n-gram 原样出现在块里。

    中文没有空格分词，用字符 n-gram 是免分词的近似做法。
    n=3 时「个工作日」这类短语能整段命中，而「报销」这种泛词只能贡献一小部分。
    """
    q = ngrams(query, n)
    return len(q & ngrams(text, n)) / len(q) if q else 0.0


def build_collection(chunks):
    """把 index.json 的向量灌进 Chroma 内存集合（余弦空间）"""
    col = chromadb.EphemeralClient().create_collection(
        "rag_docs", metadata={"hnsw:space": "cosine"})
    col.add(ids=[c["id"] for c in chunks],
            embeddings=[c["vec"] for c in chunks],
            documents=[c["text"] for c in chunks],
            metadatas=[{"source": c["source"]} for c in chunks])
    return col


def query_all(col, question, chunks):
    """在全库上取向量分，返回 [(向量分, 块), ...] 按分倒序"""
    qv = get_embeddings([question])[0]
    res = col.query(query_embeddings=[qv], n_results=len(chunks))
    by_id = {c["id"]: c for c in chunks}
    # Chroma 的 cosine 空间返回距离，相似度 = 1 - 距离
    pairs = [(1 - d, by_id[i]) for d, i in zip(res["distances"][0], res["ids"][0])]
    return sorted(pairs, key=lambda x: -x[0])


def search_vector(col, chunks, question, k=TOP_K):
    """纯向量检索，完全交给 Chroma"""
    return query_all(col, question, chunks)[:k]


def search_hybrid(col, chunks, question, k=TOP_K):
    """混合检索：向量分 + 关键词分加权。

    必须在全库上重打分，不能只在向量 Top-K 里加关键词分——
    否则一个向量排第 8、但关键词命中的块永远没机会翻上来。
    返回 [(混合分, 向量分, 关键词分, 块), ...]
    """
    scored = [(ALPHA * vec + (1 - ALPHA) * keyword_score(question, c["text"]),
               vec, keyword_score(question, c["text"]), c)
              for vec, c in query_all(col, question, chunks)]
    return sorted(scored, key=lambda x: -x[0])[:k]


def compare(col, chunks):
    print(f"索引 {INDEX_FILE}，共 {len(chunks)} 块    "
          f"混合权重 ALPHA={ALPHA}（向量）/{1 - ALPHA:.1f}（关键词），n-gram={NGRAM}")
    improved = 0
    for question, key in COMPARE_QUESTIONS:
        ans = [c["id"] for c in chunks if key in c["text"]]
        print(f"\n{'=' * 76}\n问题：{question}\n答案块：{ans}")

        vec_top = search_vector(col, chunks, question, k=5)
        hyb_top = search_hybrid(col, chunks, question, k=5)

        vrank = next((i for i, (_, c) in enumerate(vec_top, 1) if c["id"] in ans), 0)
        hrank = next((i for i, r in enumerate(hyb_top, 1) if r[3]["id"] in ans), 0)

        print("  纯向量 Top5：")
        for i, (s, c) in enumerate(vec_top, 1):
            print(f"    {i}  {c['id']}  {s:.3f}  {'← 答案' if c['id'] in ans else ''}")
        print("  混合打分 Top5：")
        for i, (mix, vec, kw, c) in enumerate(hyb_top, 1):
            print(f"    {i}  {c['id']}  混合{mix:.3f}（向量{vec:.3f}＋关键词{kw:.3f}）"
                  f"  {'← 答案' if c['id'] in ans else ''}")

        better = bool(hrank) and (not vrank or hrank < vrank)
        improved += better
        print(f"  → 答案排名：纯向量 Top{vrank or '未进前5'}    "
              f"混合 Top{hrank or '未进前5'}    "
              f"{'混合更优' if better else '无改善'}")

    print(f"\n{'=' * 76}")
    print(f"3 题中混合检索更优的：{improved}/3")
    return improved


def build_user_content(question, top):
    refs = "\n".join(f"[{c['source']}·{c['id']}]（相似度{s:.2f}）{c['text']}"
                     for s, c in top)
    return f"【参考资料】\n{refs}\n\n【问题】{question}"


def interact(col, chunks):
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"),
                    base_url=os.getenv("OPENAI_BASE_URL"))

    print(f"已加载知识库 {len(chunks)} 块  |  Chroma + 混合检索（Top{TOP_K}）")
    print("输入问题回车提问，输入 q 退出\n")

    while True:
        try:
            question = input("问题> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if question.lower() in ("q", "quit", "exit"):
            break
        if not question:
            continue

        hits = [(mix, c) for mix, vec, kw, c in
                search_hybrid(col, chunks, question, k=TOP_K)]
        print(f"\n混合检索 Top{TOP_K}：")
        for mix, c in hits:
            print(f"  {mix:.3f}  {c['source']}·{c['id']}  {c['text'][:50]}")

        resp = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "deepseek-chat"),
            messages=[{"role": "system", "content": SYSTEM},
                      {"role": "user", "content": build_user_content(question, hits)}],
            temperature=0.2)
        print(f"\n回答：{resp.choices[0].message.content}\n")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    load_dotenv()

    with open(INDEX_FILE, encoding="utf-8") as f:
        chunks = json.load(f)
    col = build_collection(chunks)

    if "--compare" in sys.argv:
        sys.exit(0 if compare(col, chunks) else 1)
    interact(col, chunks)


if __name__ == "__main__":
    main()
