#!/usr/bin/env python3
"""对比 thinking 模型的思考开关。

同一个模型、同一个问题，分别发送 think=true 和 think=false，
打印原始请求、原始响应、message.thinking 和 message.content。

只依赖标准库，调用本地 Ollama /api/chat。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

DEFAULT_MODEL = "qwen3:0.6b"
DEFAULT_QUESTION = "一个数加上 7，再乘以 2，结果是 30。这个数是多少？请给出最终答案。"
DEFAULT_EXPECTED = 8.0

MODES = {
    "think": True,
    "no-think": False,
}


def build_payload(
    model: str,
    question: str,
    think: bool,
    temperature: float,
) -> dict:
    return {
        "model": model,
        "messages": [{"role": "user", "content": question}],
        "stream": False,
        "think": think,
        "options": {"temperature": temperature},
    }


def ask_ollama(host: str, payload: dict, timeout: int = 300) -> dict:
    request = urllib.request.Request(
        f"{host.rstrip('/')}/api/chat",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def parse_final_number(text: str) -> float | None:
    patterns = [
        r"\\boxed\{\s*(-?\d+(?:\.\d+)?)\s*\}",
        r"(?:最终答案|答案)\s*[：:]\s*\$?\\?boxed\{\s*(-?\d+(?:\.\d+)?)",
        r"(?:最终答案|答案)\s*[：:]\s*(-?\d+(?:\.\d+)?)",
    ]
    for pattern in patterns:
        matches = re.findall(pattern, text)
        if matches:
            return float(matches[-1])

    numbers = re.findall(r"-?\d+(?:\.\d+)?", text)
    return float(numbers[-1]) if numbers else None


def same_number(value: float | None, expected: float) -> bool:
    return value is not None and abs(value - expected) < 1e-6


def run_mode(
    mode: str,
    question: str,
    expected: float,
    model: str,
    host: str,
    temperature: float,
    dry_run: bool,
) -> tuple[float | None, bool, int | None]:
    think = MODES[mode]
    payload = build_payload(model, question, think, temperature)

    print(f"\n{'=' * 12} {mode}（think={str(think).lower()}） {'=' * 12}")
    print("--- 原始请求 JSON ---")
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    if dry_run:
        print("\n--dry-run：未调用模型。")
        return None, False, None

    try:
        data = ask_ollama(host, payload)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"\n调用 Ollama 失败：{exc}", file=sys.stderr)
        print(
            "请确认 ollama serve 已启动，且已拉取 qwen3:0.6b。",
            file=sys.stderr,
        )
        raise SystemExit(1)

    print("\n--- 原始响应 JSON ---")
    print(json.dumps(data, ensure_ascii=False, indent=2))

    message = data.get("message", {})
    thinking = message.get("thinking")
    content = message.get("content", "")
    eval_count = data.get("eval_count")

    print("\n--- message.thinking（未加工） ---")
    print(repr(thinking))
    print("\n--- message.content（未加工） ---")
    print(repr(content))

    parsed = parse_final_number(content)
    correct = same_number(parsed, expected)

    print("\n--- 解析结果（仅用于自动判定） ---")
    print(f"解析答案：{parsed}    期望：{expected:g}    {'✓ 正确' if correct else '✗ 错误'}")
    print(
        f"thinking 字符数：{len(thinking) if thinking else 0}    "
        f"content 字符数：{len(content)}    eval_count：{eval_count}"
    )
    return parsed, correct, eval_count


def main() -> int:
    parser = argparse.ArgumentParser(description="thinking 开关对照实验")
    parser.add_argument("--question", default=DEFAULT_QUESTION, help="要问的问题")
    parser.add_argument(
        "--expected",
        type=float,
        default=DEFAULT_EXPECTED,
        help="期望的数值答案，用于自动判定",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Ollama 模型")
    parser.add_argument(
        "--host",
        default=os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
        help="Ollama 地址",
    )
    parser.add_argument("--temperature", type=float, default=0.2, help="采样温度")
    parser.add_argument(
        "--mode",
        choices=["all", *MODES],
        default="all",
        help="只跑 think 或 no-think",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="只打印请求，不调用模型"
    )
    args = parser.parse_args()

    selected = list(MODES) if args.mode == "all" else [args.mode]

    print("thinking 开关对照实验")
    print(f"模型：{args.model}")
    print(f"问题：{args.question}")
    print(f"期望答案：{args.expected:g}")
    print(f"温度：{args.temperature}")

    results: list[tuple[str, float | None, bool, int | None]] = []
    for mode in selected:
        parsed, correct, eval_count = run_mode(
            mode,
            args.question,
            args.expected,
            args.model,
            args.host,
            args.temperature,
            args.dry_run,
        )
        results.append((mode, parsed, correct, eval_count))

    if not args.dry_run:
        print(f"\n{'=' * 12} 汇总 {'=' * 12}")
        print(f"{'模式':<12} {'解析答案':<10} {'正确':<6} {'eval_count'}")
        for mode, parsed, correct, eval_count in results:
            print(
                f"{mode:<12} {str(parsed):<10} "
                f"{'✓' if correct else '✗':<6} {eval_count}"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
