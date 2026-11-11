# Thinking 模型：think 开关与原始输出

> 状态：实验中（2026-11-11）。`llm-foundations` 的子模块，不是一级 topic。

## 定位

- 层级：L1（模型能力）与 L2（推理服务）之间
- 前置：[llm-foundations](../README.md)
- 负责：用最小的 thinking 模型观察 `think` 开关、`message.thinking` / `message.content` 的分离，以及流式输出的相位
- 不负责：thinking 的训练方法、推理引擎调度、复杂 Agent 规划
- 为什么放子模块：这是模型能力与 API 协议的观察实验，不构成新的抽象层

## 实验用的模型

```bash
ollama pull qwen3:0.6b
```

`ollama show qwen3:0.6b` 的关键信息：

```text
architecture        qwen3
parameters          751.63M
context length      40960
quantization        Q4_K_M

Capabilities
  completion
  tools
  thinking
      levels     false, true
      default    true
```

模型文件约 522MB，是当前能拉到的最小 thinking 模型之一。

## 它到底怎么运作

### 非流式：一次返回两段文本

请求里加 `"think": true`：

```json
{
  "model": "qwen3:0.6b",
  "messages": [{"role": "user", "content": "一个数加上 7，再乘以 2，结果是 30。这个数是多少？"}],
  "stream": false,
  "think": true,
  "options": {"temperature": 0.2}
}
```

返回的 `message` 里有两个字段：

```json
{
  "message": {
    "role": "assistant",
    "content": "这个数是8。……**答案：8**",
    "thinking": "嗯，我现在要解决这个问题……"
  }
}
```

- `message.thinking`：模型的思考过程，原始文本
- `message.content`：最终给用户看的回答

### 流式：先出 thinking，再出 content

`stream: true` 时，Ollama 逐行返回 NDJSON。thinking 阶段的每个 chunk 都是 `content: ""`、`thinking: "..."`；thinking 结束后，才开始返回非空的 `content`。

```json
{"message":{"content":"","thinking":"Okay"},"done":false}
{"message":{"content":"","thinking":","},"done":false}
...
{"message":{"content":"2"},"done":false}
{"message":{"content":""},"done":true,"eval_count":245}
```

这就是「thinking 和回答是两段生成」在协议层的表现。

### Engine 层看到的原始 delta 是什么

上面这些 `thinking` / `content` 字段是 Ollama **服务层**加工后的结果。再往下一层到 Engine（真正跑模型的地方），流出来的只有一段连续的文本 token：

```text
"<think>" → "\n" → "Okay" → "," → " so" → ... → "\n" → "</think>" → "\n\n" → "3" → " 加" → " 4" → " 等" → " 于" → " 7" → "。"
```

也就是说：

- Engine 并不知道「思考」和「回答」是两个概念，它只负责算「下一个 token 是什么」。
- 两段能分开，是因为模型训练时学会了用 `<think>` / `</think>` 把思考和答案括起来。
- 拆分发生在服务层：引擎回调里的 `cr.Content` 是原始 delta，服务层把它交给 `thinkTagParser.AddContent(cr.Content)`，返回的值分别写进 `res.Thinking` 和 `res.Response`。

对应源码：

- [`thinking/template.go`](https://github.com/ollama/ollama/blob/main/thinking/template.go)：`InferTags` 从模板里识别 `<think>` / `</think>` 两个标签。
- [`thinking/parser.go`](https://github.com/ollama/ollama/blob/main/thinking/parser.go)：`LookingForOpening → Thinking → ThinkingDone` 状态机。标签可能被切成多个 chunk（比如 `<thi` + `nk>`），所以解析器要缓冲，不能指望每个 delta 都是完整标签。
- [`server/routes.go`](https://github.com/ollama/ollama/blob/main/server/routes.go)：`cr.Content`（Engine 原始文本）经 `thinkTagParser.AddContent(...)` 之后，才变成 API 返回里的 `thinking` / `content`。

这也解释了 `think=false` 为什么不是「引擎硬开关」：Qwen3 的模板会给最后一条 user 消息追加 ` /no_think`，并在 assistant 开头插入一个空的 `<think>\n\n</think>`；引擎照常逐 token 生成，只是被模板引导着跳过思考。

想直接看到引擎原文，需要同时绕过两件事：`raw: true` 不套模板，`think: false` 不创建解析器。这时 `/api/generate` 的 `response` 字段就是带 `<think>` 标签的原始文本。如果只加 `raw: true`，thinking 模型仍会默认 `think=true`，服务层照样切分。

一句话：**`thinking` 不是模型直接吐出来的 JSON 结构，而是服务层从 `<think>` 标记里切出来的字段。**

### 怎么看到它：`raw: true` + `think: false`

```bash
python3 engine_raw_delta.py | tee sample-engine-delta.txt
```

脚本发两个请求（Ollama 0.40.13 实测）：

1. `/api/generate`，`raw: true`、`think: false`，手动拼 ChatML 结尾 → 拿到引擎原文；
2. `/api/chat`，`think: true` → 拿到服务层切好的字段。

真实输出（问题：`3 加 4 等于多少？`）：

```text
[000] "<think>"  ← 开标签
[001] "\n"
[002] "Okay"
...
[328] ".\n"
[329] "</think>"  ← 闭标签
[330] "\n\n"
[331] "3"
...
[339] "。"
```

拼起来就是：

```text
<think>
Okay, so the question is 3 plus 4 equals how much? ... 
</think>

3 加 4 等于 7。
```

本地 splitter 按同一串 delta 重放，状态只变两次：

```text
[000] "<think>"：before → thinking，输出 ""
[329] "</think>"：thinking → answer，输出 ""
thinking 字符数：1238
content 字符数：13
```

标签本身不产出任何字符：开标签只是把状态切到 `thinking`，闭标签切到 `answer`；之后的内容才进入 `content`。服务层的 `thinkTagParser` 做的是同一件事。

## 文件

| 文件 | 说明 |
| --- | --- |
| `thinking_compare.py` | 同一问题对比 `think=true` / `think=false`，打印原始请求与响应 |
| `stream_thinking.py` | 流式读取，观察 thinking chunk 到 content chunk 的切换 |
| `engine_raw_delta.py` | 用 `raw + think=false` 拿引擎原文，再用本地 splitter 重放 `<think>` 切分 |
| `sample-output.txt` | 非流式对照的完整原始输出 |
| `sample-stream.txt` | 流式观察的完整原始输出 |
| `sample-engine-delta.txt` | Engine 原始 delta 与切分的完整原始输出 |
| `README.md` | 本文件：命令、原始输出、观察点 |

## 怎么跑

```bash
cd llm-foundations/thinking-demo

# 只看请求 JSON
python3 thinking_compare.py --dry-run

# think=true vs think=false，保存完整原始输出
python3 thinking_compare.py | tee sample-output.txt

# 只跑一种
python3 thinking_compare.py --mode think
python3 thinking_compare.py --mode no-think

# 观察流式相位
python3 stream_thinking.py | tee sample-stream.txt

# 看引擎原文，并重放服务层的 <think> 切分
python3 engine_raw_delta.py | tee sample-engine-delta.txt

# 换问题
python3 thinking_compare.py \
  --question "鸡兔同笼，共 10 只，脚 28 只，鸡兔各几只？" \
  --expected 6
```

## 真实输出

### 1. 非流式对照

同一道题：`一个数加上 7，再乘以 2，结果是 30。这个数是多少？`，期望答案 `8`。

```text
模式           解析答案       正确     eval_count
think        8.0        ✓      573
no-think     16.0       ✗      77
```

`think=true` 的原始 `message.thinking`（节选，完整内容见 `sample-output.txt`）：

```text
嗯，我现在要解决这个问题：一个数加上7，再乘以2，结果是30。这个数是多少呢？让我仔细想想怎么解决这个问题。
……
所以，最终这个数应该是8。
```

`think=true` 的原始 `message.content`：

```text
这个数是8。

**步骤：**
1. 设这个数为 $ x $。
2. 根据题意，方程为 $ 2(x + 7) = 30 $。
3. 解方程：$ x + 7 = \frac{30}{2} = 15 $，因此 $ x = 15 - 7 = 8 $。

**答案：8**
```

`think=false` 的原始 `message.content`：

```text
设这个数为 $ x $，根据题意：

$$
x + 7 \times 2 = 30
$$

$$
x + 14 = 30
$$

$$
x = 30 - 14 = 16
$$

所以，这个数是：

$$
\boxed{16}
$$
```

`think=false` 时 `message.thinking` 是 `None`，模型没有思考阶段，直接把「先加 7 再乘 2」错写成了 `x + 7 × 2`。

### 2. 流式相位

```text
thinking chunk 数：227
content chunk 数：9
eval_count：245
total_duration：1242439583
```

首批 thinking：

```json
{"message":{"content":"","thinking":"Okay"},"done":false}
```

最后一批 thinking：

```json
{"message":{"content":"","thinking":".\n"},"done":false}
```

首批 content：

```json
{"message":{"content":"2"},"done":false}
```

最终块：

```json
{"message":{"content":""},"done":true,"eval_count":245,"total_duration":1242439583}
```

## 观察点

1. **`think` 是请求参数，不是提示词。** 打开后，模型先进行一段独立的思考生成；关闭后直接生成回答。
2. **两段文本走两个字段。** `thinking` 是过程，`content` 是结果；UI 通常只展示 `content`。
3. **流式能看出相位。** thinking 阶段 `content` 为空；thinking 结束后才开始出现 `content`。
4. **思考会显著增加 token 和时间。** 这道题 think 模式 `eval_count=573`，no-think 只有 `77`；总耗时约 2.2s vs 0.3s。
5. **小模型的思考不一定可靠。** `qwen3:0.6b` 的 thinking 会反复自我确认、绕圈；思考更长不等于答案更对。
6. **`think=false` 可能明显变差。** 同一个模型关掉思考后，这道题从 8 变成了 16。
7. **`think` 只对支持 thinking 的模型有效。** `qwen2.5` 的能力是 `completion, tools`，没有 thinking；对它传 `think` 没有意义。
8. **Engine 只吐原始 token。** `thinking` / `content` 的分离是服务层解析 `<think>` 标签做的，不是引擎输出的两个通道。

## 和提示词 CoT 的区别

「thinking 模型把 CoT 内置了」这个理解方向是对的，但「内置」有两层含义：

1. **训练内置**：模型在训练阶段（监督微调、强化学习等）学会了「先产生一段推理，再给答案」这种行为，不需要你在 prompt 里示范。
2. **服务内置**：推理引擎把思考阶段和回答阶段分开，分别放进 `message.thinking` 和 `message.content`，并提供 `think` 开关。

对比一下：

| 维度 | 提示词 CoT | 内置 thinking |
| --- | --- | --- |
| 推理从哪来 | prompt 指令或 few-shot 示例触发 | 训练阶段学到的行为 |
| 是否改权重 | 否 | 是，训练时已经改了 |
| 推理放在哪 | `content` 里，用户可见 | `thinking` 字段，通常默认隐藏 |
| 怎么控制 | 改 prompt、换示例、要求格式 | `think` 参数、思考档位 |
| 典型表现 | 按示例格式写步骤 | 可能自我纠错、回溯、尝试多条路径 |
| 成本 | 输出 token 增加 | 额外思考 token，通常更多 |
| 可靠性 | 依赖提示和模型 | 也不保证忠实，小模型会绕圈 |

需要强调：**thinking 不是模型里多了一个「推理模块」**。它仍然是逐 token 生成，只是训练让模型学会了先写一段思考，服务层再把这段思考单独暴露出来。思考内容可能看起来合理，但不保证真实反映模型的内部计算。

## 工程上怎么用

- **UI**：默认只展示 `message.content`；thinking 可以折叠，或只在调试模式显示。
- **日志**：两段都存，但注意 thinking 可能很长，成本和存储都要算。
- **评测**：不要只看最终答案；记录 thinking 长度、是否循环、是否自我纠正。
- **安全**：thinking 可能包含不该展示的中间信息，不要默认透传给终端用户。
- **模型选择**：小模型 + thinking 不等于大模型；复杂任务仍然需要更大模型或外部工具。

## 相关

- 提示词版 CoT（不依赖模型内置 thinking）：[cot-demo](../cot-demo/)
- 论文清单：[papers.md](../../papers.md)
- Ollama API 文档：https://github.com/ollama/ollama/blob/main/docs/api.md
