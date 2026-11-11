#!/usr/bin/env python3
"""对比 Engine 的原始文本 delta 和服务层切分后的 thinking / content。

Ollama 没有「只看引擎」的公开接口，但 /api/generate 的 raw 模式留了两个绕过点：
1. raw=true：不套 chat 模板，prompt 原样送进引擎；
2. think=false：服务层不创建 thinkTagParser，response 字段就是引擎原文。

所以请求 1 能看到带 <think>...</think> 的原始文本；请求 2 走正常的
/api/chat + think=true，能看到服务层切好的两个字段。最后用本地 splitter
重放请求 1 的原始 delta，验证切分逻辑。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

QUESTION = "3 加 4 等于多少？"
OPEN_TAG = "<think>"
CLOSE_TAG = "</think>"


def section(title: str) -> None:
    print(f"\n{'─' * 10} {title} {'─' * 10}")


def post_stream(host: str, path: str, payload: dict, timeout: int = 300):
    request = urllib.request.Request(
        f"{host.rstrip('/')}{path}",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        for line in response:
            line = line.strip()
            if line:
                yield json.loads(line.decode("utf-8"))


def raw_prompt(question: str) -> str:
    """手动拼出 ChatML 的结尾，让模型直接进入 assistant 角色。

    raw 模式不套模板，所以这里必须自己写 <|im_start|> 这些控制符；
    否则模型会把 prompt 当成网页文本继续续写。
    """
    return (
        f"<|im_start|>user\n{question}<|im_end|>\n"
        "<|im_start|>assistant\n"
    )


def run_raw(host: str, model: str, question: str, num_predict: int) -> list[str]:
    payload = {
        "model": model,
        "prompt": raw_prompt(question),
        "raw": True,
        "think": False,
        "stream": True,
        "options": {"temperature": 0.2, "num_predict": num_predict},
    }
    section("请求 1：raw + think=false，拿 Engine 原文")
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    deltas: list[str] = []
    for data in post_stream(host, "/api/generate", payload):
        delta = data.get("response", "")
        if delta:
            deltas.append(delta)
        if data.get("done"):
            break
    return deltas


def run_chat(host: str, model: str, question: str) -> dict:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": question}],
        "stream": False,
        "think": True,
        "options": {"temperature": 0.2},
    }
    section("请求 2：/api/chat + think=true，看服务层切好的字段")
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    request = urllib.request.Request(
        f"{host.rstrip('/')}/api/chat",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        return json.loads(response.read().decode("utf-8"))


def partial_suffix(text: str, tag: str) -> int:
    """text 末尾有多长的片段，可能是 tag 的前半截（标签被切到两个 chunk）。"""
    for size in range(min(len(text), len(tag) - 1), 0, -1):
        if text.endswith(tag[:size]):
            return size
    return 0


class ThinkTagSplitter:
    """复现 Ollama thinking/parser.go 的核心状态机：before -> thinking -> answer。"""

    def __init__(self) -> None:
        self.phase = "before"
        self.pending = ""
        self.thinking = ""
        self.content = ""

    def feed(self, delta: str) -> tuple[str, str]:
        self.pending += delta
        thinking_out = ""
        content_out = ""

        while True:
            if self.phase == "before":
                index = self.pending.find(OPEN_TAG)
                if index >= 0:
                    content_out += self.pending[:index]
                    self.pending = self.pending[index + len(OPEN_TAG):]
                    self.phase = "thinking"
                    continue
                keep = partial_suffix(self.pending, OPEN_TAG)
                content_out += self.pending[: len(self.pending) - keep]
                self.pending = self.pending[len(self.pending) - keep:]
                break

            if self.phase == "thinking":
                index = self.pending.find(CLOSE_TAG)
                if index >= 0:
                    thinking_out += self.pending[:index]
                    self.pending = self.pending[index + len(CLOSE_TAG):]
                    self.phase = "answer"
                    continue
                keep = partial_suffix(self.pending, CLOSE_TAG)
                thinking_out += self.pending[: len(self.pending) - keep]
                self.pending = self.pending[len(self.pending) - keep:]
                break

            content_out += self.pending
            self.pending = ""
            break

        self.thinking += thinking_out
        self.content += content_out
        return thinking_out, content_out

    def finish(self) -> None:
        if self.phase == "thinking":
            self.thinking += self.pending
        else:
            self.content += self.pending
        self.pending = ""


def describe(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def main() -> int:
    parser = argparse.ArgumentParser(description="Engine 原始 delta vs 服务层切分")
    parser.add_argument("--model", default="qwen3:0.6b", help="Ollama 模型")
    parser.add_argument(
        "--host",
        default=os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
        help="Ollama 地址",
    )
    parser.add_argument("--question", default=QUESTION, help="问题")
    parser.add_argument(
        "--num-predict", type=int, default=500, help="raw 模式最多生成多少 token"
    )
    parser.add_argument("--dry-run", action="store_true", help="只打印请求，不调用模型")
    args = parser.parse_args()

    if args.dry_run:
        section("请求 1：raw + think=false（dry-run）")
        print(
            json.dumps(
                {
                    "model": args.model,
                    "prompt": raw_prompt(args.question),
                    "raw": True,
                    "think": False,
                    "stream": True,
                    "options": {
                        "temperature": 0.2,
                        "num_predict": args.num_predict,
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        section("请求 2：/api/chat + think=true（dry-run）")
        print(
            json.dumps(
                {
                    "model": args.model,
                    "messages": [{"role": "user", "content": args.question}],
                    "stream": False,
                    "think": True,
                    "options": {"temperature": 0.2},
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    try:
        deltas = run_raw(args.host, args.model, args.question, args.num_predict)
        chat = run_chat(args.host, args.model, args.question)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"调用 Ollama 失败：{exc}", file=sys.stderr)
        print("请确认 ollama serve 已启动，且已拉取该模型。", file=sys.stderr)
        return 1

    section(f"Engine 原始 delta（共 {len(deltas)} 块，逐块打印）")
    for index, delta in enumerate(deltas):
        marker = ""
        if delta == OPEN_TAG:
            marker = "  ← 开标签"
        elif delta == CLOSE_TAG:
            marker = "  ← 闭标签"
        print(f"[{index:03d}] {describe(delta)}{marker}")

    raw_text = "".join(deltas)
    section("拼起来的原始文本")
    print(raw_text)

    splitter = ThinkTagSplitter()
    transitions: list[tuple[int, str, str, str, str]] = []
    thinking_samples: list[tuple[int, str, str]] = []
    content_samples: list[tuple[int, str, str]] = []
    for index, delta in enumerate(deltas):
        before = splitter.phase
        thinking_out, content_out = splitter.feed(delta)
        if before != splitter.phase:
            transitions.append(
                (index, delta, before, splitter.phase, describe(thinking_out + content_out))
            )
        if thinking_out and len(thinking_samples) < 3:
            thinking_samples.append((index, delta, thinking_out))
        if content_out and len(content_samples) < 3:
            content_samples.append((index, delta, content_out))
    splitter.finish()

    section("本地 splitter 重放同一串 delta")
    print(f"delta 数：{len(deltas)}")
    print(f"状态变化：{len(transitions)} 次")
    for index, delta, before, after, emitted in transitions:
        print(f"[{index:03d}] {describe(delta)}：{before} → {after}，输出 {emitted}")
    print("\n前 3 块进入 thinking 的 delta：")
    for index, delta, emitted in thinking_samples:
        print(f"[{index:03d}] 原始 {describe(delta)} → thinking 输出 {describe(emitted)}")
    print("\n前 3 块进入 content 的 delta：")
    for index, delta, emitted in content_samples:
        print(f"[{index:03d}] 原始 {describe(delta)} → content 输出 {describe(emitted)}")
    print(f"\nthinking 字符数：{len(splitter.thinking)}")
    print(f"content 字符数：{len(splitter.content)}")

    section("splitter 还原出的 thinking")
    print(splitter.thinking)

    section("splitter 还原出的 content")
    print(splitter.content)

    message = chat.get("message", {})
    service_thinking = message.get("thinking") or ""
    service_content = message.get("content") or ""

    section("服务层 /api/chat 返回的 thinking")
    print(service_thinking)

    section("服务层 /api/chat 返回的 content")
    print(service_content)

    section("对比")
    print(f"Engine 原始文本字符数：{len(raw_text)}")
    print(f"splitter thinking / content：{len(splitter.thinking)} / {len(splitter.content)}")
    print(
        f"服务层 thinking / content：{len(service_thinking)} / {len(service_content)}"
    )
    print(
        "两次调用各自采样，文本不会逐字相同；关键是标签被吞掉、两段被分到不同字段。"
    )
    print(f"eval_count（chat）：{chat.get('eval_count')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
