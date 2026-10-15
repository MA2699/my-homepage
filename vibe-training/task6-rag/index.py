"""RAG 知识库离线建库脚本：读取 docs/ → 切分 → 向量化 → 写入 index.json

用法：python index.py
依赖：.env 中的 EMBEDDING_API_KEY / EMBEDDING_BASE_URL / EMBEDDING_MODEL
只使用 requests + 标准库，不依赖向量数据库和 RAG 框架。
"""
import json
import os
import time

import requests
from dotenv import load_dotenv

DOCS_DIR = "docs"
INDEX_FILE = "index.json"
CHUNK_SIZE = 400      # 每块 400 字
CHUNK_OVERLAP = 60    # 相邻块重叠 60 字
BATCH_SIZE = 32       # Embedding 每批最多 32 条


def read_text(path):
    """读取单个文档正文；类型不支持或内容读不到时返回 None"""
    ext = os.path.splitext(path)[1].lower()

    if ext in (".txt", ".md"):
        try:
            with open(path, encoding="utf-8") as f:
                return f.read()
        except UnicodeDecodeError:
            # 来源文件若是 GBK，退回按 GBK 读，避免中文变乱码
            with open(path, encoding="gbk", errors="ignore") as f:
                return f.read()

    if ext == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            print(f"[跳过] {path}：解析 pdf 需要先 pip install pypdf")
            return None
        # 扫描版 pdf 没有文本层，extract_text() 会返回 None，逐页兜住
        reader = PdfReader(path)
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    print(f"[跳过] {path}：不支持的文件类型 {ext}")
    return None


def load_documents(docs_dir=DOCS_DIR):
    """遍历 docs/ 读取全部文本，返回 [(文件名, 正文), ...]"""
    docs = []
    for name in sorted(os.listdir(docs_dir)):
        path = os.path.join(docs_dir, name)
        if not os.path.isfile(path):
            continue
        text = read_text(path)
        if text and text.strip():
            docs.append((name, text))
        elif text is not None:
            print(f"[跳过] {name}：内容为空")
    return docs


def chunk_text(text, size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    """固定长度切分，块间保留 overlap 个字符的重叠，防止句子被拦腰切断"""
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = end - overlap
    return chunks


def get_embeddings(texts, retries=1):
    """调用 Embedding API 取向量；失败重试一次，仍失败返回 None"""
    url = os.getenv("EMBEDDING_BASE_URL").rstrip("/") + "/embeddings"
    headers = {"Authorization": "Bearer " + os.getenv("EMBEDDING_API_KEY")}
    payload = {"model": os.getenv("EMBEDDING_MODEL"), "input": texts}

    for attempt in range(retries + 1):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=60)
            resp.raise_for_status()
            data = resp.json()["data"]
            if len(data) != len(texts):
                # 返回条数对不上会让向量与文本错位，宁可让这一批失败
                raise ValueError(f"返回 {len(data)} 条，请求 {len(texts)} 条")
            return [d["embedding"] for d in data]
        except Exception as e:
            if attempt == retries:
                print(f"[警告] 批量调用失败，跳过这 {len(texts)} 块：{e}")
                return None
            time.sleep(1)


def build_chunks(docs):
    """切分并编号，每块四个字段：text、vec、source、id"""
    chunks = []
    for name, text in docs:
        for piece in chunk_text(text):
            chunks.append({
                "text": piece,
                "vec": None,
                "source": name,
                "id": f"{len(chunks):03d}",
            })
    return chunks


def main():
    load_dotenv()
    started = time.time()

    docs = load_documents()
    if not docs:
        print(f"{DOCS_DIR}/ 里没有可用文档，先放几份 txt/md 进去")
        return

    total_chars = sum(len(text) for _, text in docs)
    chunks = build_chunks(docs)
    total = len(chunks)
    print(f"读取 {len(docs)} 份文档、共 {total_chars} 字，切成 {total} 块，开始向量化…")

    processed = 0
    for start in range(0, total, BATCH_SIZE):
        batch = chunks[start:start + BATCH_SIZE]
        vecs = get_embeddings([c["text"] for c in batch])
        if vecs is not None:
            for chunk, vec in zip(batch, vecs):
                chunk["vec"] = vec

        prev, processed = processed, processed + len(batch)
        if processed // 10 > prev // 10:      # 每处理 10 块打印一次进度
            print(f"  进度 {processed}/{total}")

    kept = [c for c in chunks if c["vec"] is not None]
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(kept, f, ensure_ascii=False)

    dims = sorted({len(c["vec"]) for c in kept})
    print(f"\n建库完成 → {INDEX_FILE}")
    print(f"  入库块数：{len(kept)}    跳过：{total - len(kept)}")
    print(f"  向量维度：{dims}")
    print(f"  总耗时：{time.time() - started:.1f} 秒")
    print(f"  验收①：块数 ≈ 总字数/340 ≈ {total_chars / 340:.0f}，实际 {len(kept)}")


if __name__ == "__main__":
    main()
