# CoT 对照实验：同一模型，三种提示

> 状态：实验中（2026-11-11）。`llm-foundations` 的子模块，不是一级 topic。

## 定位

- 层级：L1（模型能力）与 L4（提示 / Agent 行为）之间
- 前置：[llm-foundations](../README.md)
- 负责：用同一个模型、同一道题，对比「直接回答」「零样本 CoT」「few-shot CoT」的原始输出
- 不负责：论文综述、评测基准、Agent 编排；论文清单见 [papers.md](../../papers.md) 第 4 篇
- 为什么放子模块：CoT 是提示方式，不是新的抽象层；按归属规则归入 `llm-foundations`，不新建 `cot/` 一级 topic

## 这个实验回答什么

1. CoT 不是 API 开关，提示到底改了什么？
2. 同一套权重，只改提示，输出会差多少？
3. 零样本 CoT 和 few-shot CoT 有什么区别？
4. Ollama 的原始返回长什么样？

## 文件

| 文件 | 说明 |
| --- | --- |
| `cot_compare.py` | 三种模式的对照脚本，只依赖标准库 |
| `sample-output.txt` | 一次真实运行的完整原始输出（含请求 / 响应 JSON） |
| `README.md` | 本文件：命令、输出、观察点 |

## few-shot 到底是什么

- **不是微调**：不更新任何权重，只改这次请求的 messages。
- **是构造上下文**：在 messages 里放几组 `user` 问题 + `assistant` 回答，最后再放真正的问题。
- **不是真实会话**：服务端不记得上一轮；每次请求都要把示例重新发一遍。
- **模型看到的仍是 token**：chat template 会把多轮消息渲染成一整段 token 序列，模型只是基于这段上下文继续生成。

所以 few-shot 的「对话」是请求里临时搭出来的，不是持久记忆。本 demo 的构造代码在 [cot_compare.py:72](cot_compare.py#L72)。

## 怎么跑

```bash
cd llm-foundations/cot-demo

# 只打印三种模式将要发送的原始请求 JSON，不调用模型
python3 cot_compare.py --dry-run

# 跑全部三种模式，并保存完整原始输出
python3 cot_compare.py | tee sample-output.txt

# 只跑其中一种
python3 cot_compare.py --mode plain
python3 cot_compare.py --mode zero-shot-cot
python3 cot_compare.py --mode few-shot-cot

# 换一道题（记得同时给期望答案，才能自动判定）
python3 cot_compare.py \
  --question "一件商品原价 80 元，先打八折，再减 10 元，最后多少钱？" \
  --expected 54

# 对支持 thinking 的模型打开思考；qwen2.5 不支持，会无效或报错
python3 cot_compare.py --think --model <thinking-model>
```

先确认模型有没有 thinking 能力：

```bash
ollama show qwen2.5
```

本地的 `qwen2.5` 能力是 `completion, tools`，没有 `thinking`，所以只能用 prompt 开启 CoT。

## 真实输出

以下来自 2026-11-11 的本地运行，模型 `qwen2.5`，温度 `0.2`，问题：

```text
小明有 3 盒铅笔，每盒 12 支。他给了同学 7 支，又买了 2 盒，每盒 10 支。现在有多少支？
```

期望答案：`49`。

### 1. plain：直接回答

原始请求 JSON：

```json
{
  "model": "qwen2.5",
  "messages": [
    {
      "role": "system",
      "content": "直接给出最终答案，不要解释。"
    },
    {
      "role": "user",
      "content": "小明有 3 盒铅笔，每盒 12 支。他给了同学 7 支，又买了 2 盒，每盒 10 支。现在有多少支？"
    }
  ],
  "stream": false,
  "options": {
    "temperature": 0.2
  }
}
```

原始响应 JSON：

```json
{
  "model": "qwen2.5",
  "created_at": "2026-11-11T08:43:45.446812Z",
  "message": {
    "role": "assistant",
    "content": "35支"
  },
  "done": true,
  "done_reason": "stop",
  "total_duration": 127785375,
  "load_duration": 3317291,
  "prompt_eval_count": 66,
  "prompt_eval_cached_count": 65,
  "prompt_eval_duration": 36824000,
  "eval_count": 4,
  "eval_duration": 79592000
}
```

原始 `message.content`（未加工）：

```text
35支
```

判定：`35 ≠ 49`，**错误**。

### 2. zero-shot-cot：只加推理指令

原始请求 JSON：

```json
{
  "model": "qwen2.5",
  "messages": [
    {
      "role": "system",
      "content": "你是一个严谨的助手。请一步一步思考，先写出计算过程，再给结论。最后一行严格输出：答案：<结果>"
    },
    {
      "role": "user",
      "content": "小明有 3 盒铅笔，每盒 12 支。他给了同学 7 支，又买了 2 盒，每盒 10 支。现在有多少支？"
    }
  ],
  "stream": false,
  "options": {
    "temperature": 0.2
  }
}
```

原始 `message.content`（未加工）：

```text
为了解决这个问题，我们分步骤来计算。

1. **计算小明原有的铅笔数量**：
   - 小明有 3 盒铅笔，每盒 12 支，所以原有的铅笔数量是 \(3 \times 12 = 36\) 支。

2. **计算小明给同学后的铅笔数量**：
   - 小明给了同学 7 支铅笔，所以剩下的铅笔数量是 \(36 - 7 = 29\) 支。

3. **计算小明买的新铅笔数量**：
   - 小明又买了 2 盒铅笔，每盒 10 支，所以新买的铅笔数量是 \(2 \times 10 = 20\) 支。

4. **计算小明现在的总铅笔数量**：
   - 将剩下的铅笔数量与新买的铅笔数量相加，即 \(29 + 20 = 49\) 支。

答案：49
```

判定：`49 = 49`，**正确**。

完整原始响应 JSON（含耗时、token 数）：

```json
{
  "model": "qwen2.5",
  "created_at": "2026-11-11T08:43:51.282574Z",
  "message": {
    "role": "assistant",
    "content": "为了解决这个问题，我们分步骤来计算。\n\n1. **计算小明原有的铅笔数量**：\n   - 小明有 3 盒铅笔，每盒 12 支，所以原有的铅笔数量是 \\(3 \\times 12 = 36\\) 支。\n\n2. **计算小明给同学后的铅笔数量**：\n   - 小明给了同学 7 支铅笔，所以剩下的铅笔数量是 \\(36 - 7 = 29\\) 支。\n\n3. **计算小明买的新铅笔数量**：\n   - 小明又买了 2 盒铅笔，每盒 10 支，所以新买的铅笔数量是 \\(2 \\times 10 = 20\\) 支。\n\n4. **计算小明现在的总铅笔数量**：\n   - 将剩下的铅笔数量与新买的铅笔数量相加，即 \\(29 + 20 = 49\\) 支。\n\n答案：49"
  },
  "done": true,
  "done_reason": "stop",
  "total_duration": 5834021334,
  "load_duration": 762167,
  "prompt_eval_count": 86,
  "prompt_eval_cached_count": 3,
  "prompt_eval_duration": 305829000,
  "eval_count": 221,
  "eval_duration": 5523732000
}
```

### 3. few-shot-cot：给两条带推理的示例

原始请求 JSON（示例以 user/assistant 多轮消息给出）：

```json
{
  "model": "qwen2.5",
  "messages": [
    {
      "role": "system",
      "content": "你是一个严谨的助手。请按照示例的格式回答：先写计算过程，最后一行严格输出：答案：<结果>"
    },
    {
      "role": "user",
      "content": "小红有 4 盒橡皮，每盒 6 块。她用掉了 5 块，又买了 1 盒 8 块。现在有多少块？"
    },
    {
      "role": "assistant",
      "content": "原来有 4×6=24 块。用掉 5 块，剩 24−5=19 块。又买 8 块，19+8=27 块。答案：27"
    },
    {
      "role": "user",
      "content": "书架上有 5 排书，每排 9 本。借走 12 本，又放回 3 本。现在有多少本？"
    },
    {
      "role": "assistant",
      "content": "原来有 5×9=45 本。借走 12 本，剩 45−12=33 本。放回 3 本，33+3=36 本。答案：36"
    },
    {
      "role": "user",
      "content": "小明有 3 盒铅笔，每盒 12 支。他给了同学 7 支，又买了 2 盒，每盒 10 支。现在有多少支？"
    }
  ],
  "stream": false,
  "options": {
    "temperature": 0.2
  }
}
```

原始 `message.content`（未加工）：

```text
原来有 3×12=36 支。给了同学 7 支，剩 36−7=29 支。又买了 2×10=20 支。现在有 29+20=49 支。答案：49
```

判定：`49 = 49`，**正确**。

完整原始响应 JSON：

```json
{
  "model": "qwen2.5",
  "created_at": "2026-11-11T08:43:53.720273Z",
  "message": {
    "role": "assistant",
    "content": "原来有 3×12=36 支。给了同学 7 支，剩 36−7=29 支。又买了 2×10=20 支。现在有 29+20=49 支。答案：49"
  },
  "done": true,
  "done_reason": "stop",
  "total_duration": 2436409791,
  "load_duration": 536375,
  "prompt_eval_count": 296,
  "prompt_eval_cached_count": 10,
  "prompt_eval_duration": 832411000,
  "eval_count": 64,
  "eval_duration": 1599883000
}
```

### 汇总（脚本自动判定）

```text
模式               解析答案       正确
plain            35.0       ✗
zero-shot-cot    49.0       ✓
few-shot-cot     49.0       ✓
```

## 观察点

1. **同一套权重，只改 prompt，结果从 35 变成 49。** CoT 不是打开某个模型开关，而是改变模型这次请求的上下文。
2. **plain 输出只有 4 个 token**（`eval_count: 4`），zero-shot 输出 221 个 token。CoT 用更多生成 token 换计算步骤。
3. **零样本和 few-shot 都能做对**，但 few-shot 输出更短、格式更稳定；零样本更省示例，适合快速试用。
4. **原始返回里有耗时和 token 统计**：`total_duration`、`prompt_eval_count`、`eval_count` 都来自 Ollama，不是脚本编的。脚本只做展示和答案解析。
5. **单题只作演示**：一次正确不代表 CoT 普遍有效。论文发现 CoT 收益随模型规模涌现，小模型上可能不稳定；真正的结论要靠评测集。

## 相关

- 论文清单与三篇 CoT 的关系：[papers.md](../../papers.md) 第 4 篇
- CoT 原论文：https://arxiv.org/abs/2201.11903
- 零样本 CoT：https://arxiv.org/abs/2205.11916
- Self-Consistency：https://arxiv.org/abs/2203.11171
