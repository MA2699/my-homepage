"""检索命中率验收脚本：对给定 index.json 跑一组问题，统计 Top3 命中率。

用法：
    python check_search.py                            # 跑全部题库
    python check_search.py --set retrieval            # 只跑检索验证 5 题
    python check_search.py --set self                 # 只跑标准 10 题自测卷
    python check_search.py index_200_30.json --set self   # 切分对比实验

命中判定：答案关键词出现在检索结果的前 3 块里（Top3 命中）。
出处判定：答案关键词所在的块就是排名第 1 的块（来源标注的第一顺位即正确答案）。
关键词只是代理指标——块边界可能把答案切断，最终仍需人眼确认。
"""
import json
import os
import sys

import numpy as np
import requests
from dotenv import load_dotenv

INDEX_FILE = "index.json"

# 操作文档第 2 步「检索验证」的 5 题：(问题, 答案关键词)
RETRIEVAL = [
    ("毕业设计查重率超过多少不能参加答辩？", "不能参加本次答辩"),
    ("社团活动报销的提交时限是多久？", "15个工作日"),
    ("报销需要准备哪些必备材料？", "采购明细清单"),
    ("山湖风景区怎么去，高铁票价多少？", "票价28元"),
    ("哪些支出项目明确不予报销？", "明确不予报销"),
]

# 实践素材表 3「标准 10 题自测卷」：(问题, 答案关键词)
SELFTEST = [
    ("毕业设计占多少学分，整个周期多长时间？", "占8学分"),
    ("开题报告对参考文献有什么数量要求？", "参考文献不少于12篇"),
    ("理工科工程设计类论文的正文字数要求是多少？", "不少于8000字"),
    ("毕业设计查重有几次免费机会，重复率多少以下才能参加正常答辩？", "2次免费查重机会"),
    ("答辩成绩由哪几部分构成，各占多少比例？", "指导老师评分（40%）"),
    ("社团活动报销的申请提交时限是活动结束后多久？", "15个工作日"),
    ("报销必备材料清单包含哪几项？", "《社团活动申报表》复印件"),
    ("校级重点社团每学期经费申请上限是多少，单场活动最高限额呢？", "上限6000元"),
    ("报销被驳回后需要在几个工作日内重新提交？", "7个工作日内完成修改"),
    ("山湖风景区的高铁车程和票价是多少？", "票价28元"),
]

# 题库名 → (题目列表, Top3 命中验收线)
BANKS = {
    "retrieval": (RETRIEVAL, 4),
    "self": (SELFTEST, 7),
}


def get_embeddings(texts):
    resp = requests.post(
        os.getenv("EMBEDDING_BASE_URL").rstrip("/") + "/embeddings",
        headers={"Authorization": "Bearer " + os.getenv("EMBEDDING_API_KEY")},
        json={"model": os.getenv("EMBEDDING_MODEL"), "input": texts},
        timeout=60)
    resp.raise_for_status()
    return [d["embedding"] for d in resp.json()["data"]]


def cosine(a, b):
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def run_bank(name, questions, threshold, chunks):
    bank, _ = BANKS[name]
    # 一次批量向量化所有问题，省调用次数
    qvecs = get_embeddings([q for q, _ in questions])

    print(f"\n【{name}】共 {len(questions)} 题，验收线 Top3 命中 ≥{threshold}")
    print("-" * 78)

    hits = exact = 0
    for (question, key), qv in zip(questions, qvecs):
        ranked = sorted(((cosine(qv, c["vec"]), c) for c in chunks),
                        key=lambda x: -x[0])
        top5 = ranked[:5]
        rank = next((i + 1 for i, (_, c) in enumerate(top5) if key in c["text"]), 0)
        ok = 0 < rank <= 3
        hits += ok
        exact += (rank == 1)
        where = f"Top{rank}" if rank else "未进Top5"
        print(f"{'命中' if ok else '未命中'}  {where:7s} 最高分{top5[0][0]:.3f}   {question}")
        if not ok:
            print(f"        答案块: {[c['id'] for _, c in top5 if key in c['text']] or '不在Top5内'}")
            print(f"        Top3:   {[(c['id'], round(s, 3)) for s, c in top5[:3]]}")

    ok_all = hits >= threshold
    print("-" * 78)
    print(f"Top3 命中 {hits}/{len(questions)}   出处正确(Top1) {exact}/{len(questions)}"
          f"   （验收线命中 ≥{threshold}）  →  {'通过' if ok_all else '不通过'}")
    return ok_all


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    load_dotenv()

    argv = sys.argv[1:]
    which = "all"
    if "--set" in argv:
        i = argv.index("--set")
        which = argv[i + 1]
        del argv[i:i + 2]
    target = argv[0] if argv else INDEX_FILE

    with open(target, encoding="utf-8") as f:
        chunks = json.load(f)
    print(f"索引文件：{target}    共 {len(chunks)} 块")

    names = list(BANKS) if which == "all" else [which]
    results = [run_bank(n, *BANKS[n], chunks) for n in names]
    return all(results)


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
