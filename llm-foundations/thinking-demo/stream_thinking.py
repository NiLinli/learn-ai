#!/usr/bin/env python3
"""观察 thinking 模型的流式输出：thinking 先到，content 后到。

调用 Ollama /api/chat，stream=true、think=true，逐行读取 NDJSON。
打印首批 thinking、最后一批 thinking、首批 content、最终统计，
以及完整的 thinking / content 文本。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_MODEL = "qwen3:0.6b"
DEFAULT_QUESTION = "2 加 2 等于多少？"


def stream_chat(
    host: str,
    model: str,
    question: str,
    temperature: float,
) -> None:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": question}],
        "stream": True,
        "think": True,
        "options": {"temperature": temperature},
    }
    request = urllib.request.Request(
        f"{host.rstrip('/')}/api/chat",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    first_thinking = last_thinking = first_content = final = None
    thinking_parts: list[str] = []
    content_parts: list[str] = []
    thinking_chunks = content_chunks = 0

    with urllib.request.urlopen(request, timeout=300) as response:
        for raw in response:
            chunk = json.loads(raw)
            message = chunk.get("message", {})
            if message.get("thinking"):
                thinking_chunks += 1
                thinking_parts.append(message["thinking"])
                if first_thinking is None:
                    first_thinking = chunk
                last_thinking = chunk
            if message.get("content"):
                content_chunks += 1
                content_parts.append(message["content"])
                if first_content is None:
                    first_content = chunk
            if chunk.get("done"):
                final = chunk
                break

    for label, chunk in [
        ("首批 thinking", first_thinking),
        ("最后一批 thinking", last_thinking),
        ("首批 content", first_content),
        ("最终块", final),
    ]:
        print(f"\n--- {label} ---")
        print(json.dumps(chunk, ensure_ascii=False)[:800])

    print("\n--- 完整 message.thinking（未加工） ---")
    print("".join(thinking_parts))
    print("\n--- 完整 message.content（未加工） ---")
    print("".join(content_parts))

    print("\n--- 统计 ---")
    print(f"thinking chunk 数：{thinking_chunks}")
    print(f"content chunk 数：{content_chunks}")
    if final:
        print(f"eval_count：{final.get('eval_count')}")
        print(f"total_duration：{final.get('total_duration')}")


def main() -> int:
    parser = argparse.ArgumentParser(description="thinking 流式输出观察")
    parser.add_argument("--question", default=DEFAULT_QUESTION, help="要问的问题")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Ollama 模型")
    parser.add_argument(
        "--host",
        default=os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
        help="Ollama 地址",
    )
    parser.add_argument("--temperature", type=float, default=0.2, help="采样温度")
    args = parser.parse_args()

    print("thinking 流式观察")
    print(f"模型：{args.model}")
    print(f"问题：{args.question}")

    try:
        stream_chat(args.host, args.model, args.question, args.temperature)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"调用 Ollama 失败：{exc}", file=sys.stderr)
        print("请确认 ollama serve 已启动，且已拉取 qwen3:0.6b。", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
