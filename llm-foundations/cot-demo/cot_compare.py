#!/usr/bin/env python3
"""CoT 对照实验：同一模型、同一问题，比较三种提示方式。

- plain：直接给最终答案
- zero-shot-cot：要求先推理、再给答案
- few-shot-cot：给两条带推理过程的示例

只依赖标准库，调用本地 Ollama 的 /api/chat。默认模型 qwen2.5。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

DEFAULT_QUESTION = (
    "小明有 3 盒铅笔，每盒 12 支。他给了同学 7 支，"
    "又买了 2 盒，每盒 10 支。现在有多少支？"
)
DEFAULT_EXPECTED = 49.0

FEW_SHOT_EXAMPLES = [
    (
        "小红有 4 盒橡皮，每盒 6 块。她用掉了 5 块，又买了 1 盒 8 块。现在有多少块？",
        "原来有 4×6=24 块。用掉 5 块，剩 24−5=19 块。"
        "又买 8 块，19+8=27 块。答案：27",
    ),
    (
        "书架上有 5 排书，每排 9 本。借走 12 本，又放回 3 本。现在有多少本？",
        "原来有 5×9=45 本。借走 12 本，剩 45−12=33 本。"
        "放回 3 本，33+3=36 本。答案：36",
    ),
]

SYSTEM_PLAIN = "直接给出最终答案，不要解释。"
SYSTEM_ZERO_SHOT = (
    "你是一个严谨的助手。请一步一步思考，先写出计算过程，再给结论。"
    "最后一行严格输出：答案：<结果>"
)
SYSTEM_FEW_SHOT = (
    "你是一个严谨的助手。请按照示例的格式回答：先写计算过程，"
    "最后一行严格输出：答案：<结果>"
)

MODES = {
    "plain": "直接回答",
    "zero-shot-cot": "零样本 CoT",
    "few-shot-cot": "few-shot CoT",
}


def build_messages(mode: str, question: str) -> list[dict[str, str]]:
    if mode == "plain":
        return [
            {"role": "system", "content": SYSTEM_PLAIN},
            {"role": "user", "content": question},
        ]

    if mode == "zero-shot-cot":
        return [
            {"role": "system", "content": SYSTEM_ZERO_SHOT},
            {"role": "user", "content": question},
        ]

    if mode == "few-shot-cot":
        messages = [{"role": "system", "content": SYSTEM_FEW_SHOT}]
        for example_question, example_answer in FEW_SHOT_EXAMPLES:
            messages.append({"role": "user", "content": example_question})
            messages.append({"role": "assistant", "content": example_answer})
        messages.append({"role": "user", "content": question})
        return messages

    raise ValueError(f"未知模式：{mode}")


def build_payload(
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
    think: bool,
) -> dict:
    payload: dict = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature},
    }
    if think:
        payload["think"] = True
    return payload


def ask_ollama(
    host: str,
    payload: dict,
    timeout: int = 300,
) -> tuple[dict, str, str | None]:
    request = urllib.request.Request(
        f"{host.rstrip('/')}/api/chat",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8"))

    message = data.get("message", {})
    return data, message.get("content", ""), message.get("thinking")


def parse_number(text: str) -> float | None:
    matches = re.findall(r"答案\s*[:：]\s*(-?\d+(?:\.\d+)?)", text)
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
    host: str,
    model: str,
    temperature: float,
    think: bool,
    dry_run: bool,
) -> tuple[float | None, bool]:
    print(f"\n{'=' * 12} {mode}（{MODES[mode]}） {'=' * 12}")
    messages = build_messages(mode, question)
    payload = build_payload(model, messages, temperature, think)

    print("--- 原始请求 JSON ---")
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    if dry_run:
        print("\n--dry-run：未调用模型。")
        return None, False

    try:
        data, content, thinking = ask_ollama(host, payload)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"\n调用 Ollama 失败：{exc}", file=sys.stderr)
        print(
            "请确认 ollama serve 已启动，且模型已拉取。",
            file=sys.stderr,
        )
        raise SystemExit(1)

    print("\n--- 原始响应 JSON ---")
    print(json.dumps(data, ensure_ascii=False, indent=2))

    if thinking:
        print("\n--- 原始 message.thinking（未加工） ---")
        print(thinking)

    print("\n--- 原始 message.content（未加工） ---")
    print(content)
    print("--- 原始 message.content 结束 ---")

    parsed = parse_number(content)
    correct = same_number(parsed, expected)
    print("\n--- 解析结果（仅用于自动判定） ---")
    print(f"解析答案：{parsed}    期望：{expected:g}    {'✓ 正确' if correct else '✗ 错误'}")
    return parsed, correct


def main() -> int:
    parser = argparse.ArgumentParser(description="CoT 对照实验")
    parser.add_argument("--question", default=DEFAULT_QUESTION, help="要问的问题")
    parser.add_argument(
        "--expected",
        type=float,
        default=DEFAULT_EXPECTED,
        help="期望的数值答案，用于自动判定",
    )
    parser.add_argument("--model", default="qwen2.5", help="Ollama 生成模型")
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
        help="只跑某一种模式",
    )
    parser.add_argument(
        "--think",
        action="store_true",
        help="对支持 thinking 的模型打开思考；qwen2.5 不支持",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="只打印 messages，不调用模型"
    )
    args = parser.parse_args()

    selected = list(MODES) if args.mode == "all" else [args.mode]

    print("CoT 对照实验")
    print(f"模型：{args.model}")
    print(f"问题：{args.question}")
    print(f"期望答案：{args.expected:g}")
    print(f"温度：{args.temperature}")
    print(f"thinking：{'开' if args.think else '关'}")

    results: list[tuple[str, float | None, bool]] = []
    for mode in selected:
        parsed, correct = run_mode(
            mode,
            args.question,
            args.expected,
            args.host,
            args.model,
            args.temperature,
            args.think,
            args.dry_run,
        )
        results.append((mode, parsed, correct))

    if not args.dry_run:
        print(f"\n{'=' * 12} 汇总 {'=' * 12}")
        print(f"{'模式':<16} {'解析答案':<10} {'正确'}")
        for mode, parsed, correct in results:
            print(f"{mode:<16} {str(parsed):<10} {'✓' if correct else '✗'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
