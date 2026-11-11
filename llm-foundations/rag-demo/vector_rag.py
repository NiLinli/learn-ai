#!/usr/bin/env python3
"""向量版最小 RAG：切片和问题都变成 embedding 向量，按余弦相似度检索。

和 rag.py 的唯一区别是打分器：BM25 数共同词，这里比向量方向。
切片、拼 prompt、调模型的部分直接复用 rag.py。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from rag import build_messages, call_ollama, load_chunks, print_messages, section

CACHE_PATH = Path(__file__).parent / "embeddings.json"
MIN_SCORE = 0.45  # 只对 qwen3-embedding:0.6b 校准过；换模型要重新定阈值


def embed(host: str, model: str, texts: list[str], timeout: int = 180) -> list[list[float]]:
    payload = json.dumps(
        {"model": model, "input": texts}, ensure_ascii=False
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{host.rstrip('/')}/api/embed",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8"))
    if "embeddings" not in data:
        raise RuntimeError(data.get("error", "embedding 接口没有返回 embeddings"))
    return data["embeddings"]


def normalize(vector: list[float]) -> list[float]:
    """把向量长度缩放到 1；之后两个单位向量点积就等于余弦相似度。"""
    norm = math.sqrt(sum(value * value for value in vector))
    if not norm:
        return vector
    return [value / norm for value in vector]


def cosine(unit_a: list[float], unit_b: list[float]) -> float:
    return sum(a * b for a, b in zip(unit_a, unit_b))


def fingerprint(chunks) -> str:
    """切片内容变了就失效，避免拿着旧向量检索新文档。"""
    digest = hashlib.sha256()
    for chunk in chunks:
        digest.update(chunk.source.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(chunk.text.encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()


def load_cache(model: str, chunks) -> list[list[float]] | None:
    if not CACHE_PATH.exists():
        return None
    try:
        cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if (
        cache.get("model") != model
        or cache.get("fingerprint") != fingerprint(chunks)
        or len(cache.get("vectors", [])) != len(chunks)
    ):
        return None
    return cache["vectors"]


def save_cache(model: str, chunks, vectors: list[list[float]]) -> None:
    cache = {
        "model": model,
        "dim": len(vectors[0]) if vectors else 0,
        "fingerprint": fingerprint(chunks),
        "sources": [chunk.source for chunk in chunks],
        "vectors": vectors,
    }
    CACHE_PATH.write_text(
        json.dumps(cache, ensure_ascii=False), encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="向量版最小 RAG 演示")
    parser.add_argument(
        "--query",
        default="量化会改变参数量吗？文件体积怎么估算？",
        help="检索问题",
    )
    parser.add_argument("--top-k", type=int, default=3, help="取前几个片段")
    parser.add_argument(
        "--docs",
        type=Path,
        default=Path(__file__).parent / "docs",
        help="文档目录",
    )
    parser.add_argument("--model", default="qwen2.5", help="生成用的 Ollama 模型")
    parser.add_argument(
        "--embed-model",
        default="qwen3-embedding:0.6b",
        help="向量化用的 Ollama 模型",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
        help="Ollama 地址",
    )
    parser.add_argument(
        "--rebuild", action="store_true", help="忽略缓存，重新计算所有切片向量"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="只检索并打印 prompt，不调用生成模型"
    )
    parser.add_argument(
        "--save-prompt", type=Path, help="把 messages 以 JSON 存到文件"
    )
    args = parser.parse_args()

    chunks = load_chunks(args.docs)
    if not chunks:
        print(f"文档目录为空：{args.docs}", file=sys.stderr)
        return 1

    vectors = None if args.rebuild else load_cache(args.embed_model, chunks)
    cache_hit = vectors is not None
    if vectors is None:
        try:
            vectors = [
                normalize(vector)
                for vector in embed(
                    args.host, args.embed_model, [chunk.text for chunk in chunks]
                )
            ]
        except (urllib.error.URLError, TimeoutError, OSError, RuntimeError) as exc:
            print(f"计算 embedding 失败：{exc}", file=sys.stderr)
            print(
                f"请确认 ollama serve 已启动，且已拉取 {args.embed_model}。",
                file=sys.stderr,
            )
            return 1
        save_cache(args.embed_model, chunks, vectors)

    section("索引概览")
    print(f"文档目录：{args.docs}")
    print(f"切片数量：{len(chunks)}")
    print(f"向量模型：{args.embed_model}（{len(vectors[0])} 维）")
    print(f"向量缓存：{'命中' if cache_hit else '未命中，已重新计算'} → {CACHE_PATH.name}")

    try:
        query_vector = normalize(embed(args.host, args.embed_model, [args.query])[0])
    except (urllib.error.URLError, TimeoutError, OSError, RuntimeError) as exc:
        print(f"计算问题向量失败：{exc}", file=sys.stderr)
        return 1

    section("问题")
    print(args.query)
    preview = ", ".join(f"{value:.4f}" for value in query_vector[:5])
    print(f"查询向量前 5 维：[{preview}, ...]  （共 {len(query_vector)} 维）")

    ranked = sorted(
        ((cosine(query_vector, vector), index) for index, vector in enumerate(vectors)),
        key=lambda item: item[0],
        reverse=True,
    )
    hits = [(score, chunks[index]) for score, index in ranked[: args.top_k]]

    section(f"检索结果 Top {args.top_k}（余弦相似度）")
    for rank, (score, chunk) in enumerate(hits, 1):
        preview = chunk.text.replace("\n", " ")[:42]
        print(
            f"{rank}. cos={score:.4f}  {chunk.source:<18} "
            f"《{chunk.title}》 {preview}..."
        )

    best = hits[0][0] if hits else 0.0
    if best < MIN_SCORE:
        print(
            f"\n⚠ 最高分 {best:.4f} 低于阈值 {MIN_SCORE}：问题可能超出知识库范围。"
            "余弦阈值随 embedding 模型而变，换模型后要重新标定。"
        )

    print(
        "\n观察点：切片向量是提前算好存起来的；查询时只算一次问题向量，"
        "再和每段向量做点积。向量检索没有改模型，改的仍然是这次请求的 prompt。"
    )

    messages = build_messages(args.query, hits)
    print_messages(messages)

    if args.save_prompt:
        args.save_prompt.write_text(
            json.dumps(messages, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\n已保存 messages 到 {args.save_prompt}")

    if args.dry_run:
        section("结束")
        print("--dry-run：没有调用生成模型。")
        return 0

    section(f"模型回答（{args.model}）")
    try:
        answer = call_ollama(args.host, args.model, messages)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"调用 Ollama 失败：{exc}", file=sys.stderr)
        return 1
    print(answer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
