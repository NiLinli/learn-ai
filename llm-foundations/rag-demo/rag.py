#!/usr/bin/env python3
"""最小 RAG：文档 -> 切片 -> 索引 -> 检索 -> 拼进 prompt -> 本地模型回答。

检索端不依赖第三方库，用中文双字切分 + BM25，目的是让每一步都可观察。
生成端调用本地 Ollama；不调用时用 --dry-run 只看检索和 prompt。
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

LATIN_RE = re.compile(r"[a-z0-9_]+")
CJK_RE = re.compile(r"[\u4e00-\u9fff]+")

SYSTEM_PROMPT = (
    "你是一个学习助手。只依据 <资料> 中的内容回答；"
    "资料里没有的信息要明确说不知道。引用时标注片段编号，如 [片段 1]。"
)


@dataclass
class Chunk:
    source: str
    title: str
    text: str


@dataclass
class Index:
    chunks: list[Chunk]
    term_freqs: list[Counter[str]]
    idf: dict[str, float]
    lengths: list[int]
    avg_length: float


def section(title: str) -> None:
    print(f"\n{'─' * 10} {title} {'─' * 10}")


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[。！？!?；;])\s*|\n+", text)
    return [part.strip() for part in parts if part.strip()]


def load_chunks(docs_dir: Path, max_chars: int = 120) -> list[Chunk]:
    """每篇文档的第一段当标题，其余按句子拼成不超过 max_chars 的切片。"""
    chunks: list[Chunk] = []
    for path in sorted(docs_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        if not paragraphs:
            continue
        title = paragraphs[0].splitlines()[0].strip()
        body = "\n".join(paragraphs[1:]) if len(paragraphs) > 1 else ""

        buffer = ""
        index = 1
        for sentence in split_sentences(body):
            if buffer and len(buffer) + len(sentence) > max_chars:
                chunks.append(
                    Chunk(source=f"{path.name}#c{index}", title=title, text=buffer)
                )
                index += 1
                buffer = sentence
            else:
                buffer = f"{buffer}\n{sentence}" if buffer else sentence
        if buffer:
            chunks.append(
                Chunk(source=f"{path.name}#c{index}", title=title, text=buffer)
            )
    return chunks


def tokenize(text: str) -> list[str]:
    """英文按词，中文按相邻双字切，避免引入分词依赖，也减少单字噪声。"""
    text = text.lower()
    tokens = LATIN_RE.findall(text)
    for run in CJK_RE.findall(text):
        if len(run) == 1:
            tokens.append(run)
        else:
            tokens.extend(run[i : i + 2] for i in range(len(run) - 1))
    return tokens


def build_index(chunks: list[Chunk]) -> Index:
    """BM25 索引：idf + 每个切片的词频 + 长度，长度归一化能避免短切片占便宜。

    索引时把标题一起算进词频，相当于给切片加了一个小的上下文头，
    能缓解「标题里有、正文里没重复」导致的漏召回。
    """
    term_freqs = [
        Counter(tokenize(f"{chunk.title}\n{chunk.text}")) for chunk in chunks
    ]
    df: Counter[str] = Counter()
    for tf in term_freqs:
        df.update(set(tf))

    n = len(chunks)
    idf = {
        term: math.log(1 + (n - count + 0.5) / (count + 0.5))
        for term, count in df.items()
    }
    lengths = [sum(tf.values()) for tf in term_freqs]
    avg_length = sum(lengths) / n if n else 0.0
    return Index(chunks, term_freqs, idf, lengths, avg_length)


def bm25_score(
    query: str, index: Index, doc: int, k1: float = 1.5, b: float = 0.75
) -> float:
    terms = set(tokenize(query))
    tf = index.term_freqs[doc]
    length = index.lengths[doc]
    score = 0.0
    for term in terms:
        freq = tf.get(term, 0)
        if not freq:
            continue
        norm = k1 * (1 - b + b * length / (index.avg_length or 1))
        score += index.idf[term] * freq * (k1 + 1) / (freq + norm)
    return score


def retrieve(query: str, index: Index, top_k: int) -> list[tuple[float, Chunk]]:
    ranked = sorted(
        (
            (bm25_score(query, index, doc), chunk)
            for doc, chunk in enumerate(index.chunks)
        ),
        key=lambda item: item[0],
        reverse=True,
    )
    return ranked[:top_k]


def build_messages(query: str, hits: list[tuple[float, Chunk]]) -> list[dict[str, str]]:
    blocks = [
        f"[片段 {index}] 来源：{chunk.source}《{chunk.title}》\n{chunk.text}"
        for index, (_, chunk) in enumerate(hits, 1)
    ]
    context = "\n\n".join(blocks)
    user_prompt = f"<资料>\n{context}\n</资料>\n\n问题：{query}"
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def print_messages(messages: list[dict[str, str]]) -> None:
    section("最终发送给模型的 messages")
    for message in messages:
        print(f"\n[{message['role']}]")
        print(message["content"])
    chars = sum(len(message["content"]) for message in messages)
    print(f"\n（以上内容共 {chars} 字符，就是模型这次真正看到的 prompt）")


def call_ollama(
    host: str, model: str, messages: list[dict[str, str]], timeout: int = 180
) -> str:
    payload = json.dumps(
        {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0.2},
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{host.rstrip('/')}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8"))
    return data["message"]["content"].strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="最小 RAG 演示")
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
    parser.add_argument(
        "--model", default="qwen2.5", help="本地 Ollama 模型名"
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
        help="Ollama 地址",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="只检索并打印 prompt，不调用模型"
    )
    parser.add_argument(
        "--save-prompt", type=Path, help="把 messages 以 JSON 存到文件"
    )
    args = parser.parse_args()

    chunks = load_chunks(args.docs)
    if not chunks:
        print(f"文档目录为空：{args.docs}", file=sys.stderr)
        return 1

    index = build_index(chunks)
    hits = retrieve(args.query, index, args.top_k)

    section("索引概览")
    print(f"文档目录：{args.docs}")
    print(f"切片数量：{len(chunks)}")
    print(f"词表大小：{len(index.idf)}")

    section("问题")
    print(args.query)

    section(f"检索结果 Top {args.top_k}")
    for rank, (score, chunk) in enumerate(hits, 1):
        preview = chunk.text.replace("\n", " ")[:42]
        print(
            f"{rank}. score={score:.3f}  {chunk.source:<18} "
            f"《{chunk.title}》 {preview}..."
        )

    best = hits[0][0] if hits else 0.0
    if best < 0.5:
        print(
            "\n⚠ 最高分很低：问题可能超出知识库范围。"
            "此时模型仍可能编造，需要靠 prompt 约束或拒答。"
        )

    print(
        "\n观察点：上面每段原文会原样出现在下面 <资料> 里。"
        "RAG 没有改模型，它改的只是这次请求的 prompt。"
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
        print("--dry-run：没有调用模型。")
        return 0

    section(f"模型回答（{args.model}）")
    try:
        answer = call_ollama(args.host, args.model, messages)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"调用 Ollama 失败：{exc}", file=sys.stderr)
        print("请确认 ollama serve 已启动；或加 --dry-run 只看 prompt。", file=sys.stderr)
        return 1
    print(answer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
