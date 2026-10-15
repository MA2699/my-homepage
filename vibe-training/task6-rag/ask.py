"""命令行 RAG 问答脚本：加载 index.json → 检索 Top3 → 调对话模型作答

用法：
    python ask.py                  # 交互问答（输入 q 退出）
    python ask.py --search-only    # 只做检索验证：打印 Top5，不调对话模型
"""
import json
import os
import sys

import numpy as np
import requests
from dotenv import load_dotenv

INDEX_FILE = "index.json"
TOP_K = 3

SYSTEM = """你是知识库问答助手。规则：
1. 只根据用户消息中提供的【参考资料】回答，禁止使用资料之外的知识；
2. 资料不足以回答时，明确说「资料中未找到相关内容」，不要编造；
3. 回答末尾用【来源：文件名·块id】标注依据。"""


def get_embeddings(texts):
    """问题向量化；建库和提问必须用同一个 EMBEDDING_MODEL，否则坐标系对不上"""
    resp = requests.post(
        os.getenv("EMBEDDING_BASE_URL").rstrip("/") + "/embeddings",
        headers={"Authorization": "Bearer " + os.getenv("EMBEDDING_API_KEY")},
        json={"model": os.getenv("EMBEDDING_MODEL"), "input": texts},
        timeout=60)
    resp.raise_for_status()
    return [d["embedding"] for d in resp.json()["data"]]


def cosine(a, b):
    """余弦相似度：两向量夹角越小越接近 1"""
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def load_index(path=INDEX_FILE):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def search(question, chunks, k=TOP_K):
    """问题向量化后按余弦相似度倒序排列，返回 [(分数, 块), ...]"""
    qv = get_embeddings([question])[0]
    scored = sorted(((cosine(qv, c["vec"]), c) for c in chunks),
                    key=lambda x: -x[0])
    return scored[:k]


def build_user_content(question, top):
    """把 Top-K 块全文塞进【参考资料】，让模型只能依据这些内容作答"""
    refs = "\n".join(
        f"[{c['source']}·{c['id']}]（相似度{s:.2f}）{c['text']}" for s, c in top)
    return f"【参考资料】\n{refs}\n\n【问题】{question}"


def ask_model(client, question, top):
    resp = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "deepseek-chat"),
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": build_user_content(question, top)},
        ],
        temperature=0.2)
    return resp.choices[0].message.content


def print_hits(top):
    for score, c in top:
        print(f"  {score:.3f}  {c['source']}·{c['id']}  {c['text'][:50]}")


def main():
    # Windows 控制台默认 GBK，遇到 ‑ 这类字符会抛 UnicodeEncodeError，统一切到 UTF-8
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    load_dotenv()
    chunks = load_index()
    search_only = "--search-only" in sys.argv
    k = 5 if search_only else TOP_K

    mode = "检索验证模式：打印 Top5，不调对话模型" if search_only else f"问答模式：Top{TOP_K}"
    print(f"已加载知识库 {len(chunks)} 块  |  {mode}")
    print("输入问题回车提问，输入 q 退出\n")

    client = None
    if not search_only:
        from openai import OpenAI
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"),
                        base_url=os.getenv("OPENAI_BASE_URL"))

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

        top = search(question, chunks, k=k)
        print(f"\n检索 Top{k}：")
        print_hits(top)
        print()

        if search_only:
            continue

        print("回答：", ask_model(client, question, top))
        print()


if __name__ == "__main__":
    main()
