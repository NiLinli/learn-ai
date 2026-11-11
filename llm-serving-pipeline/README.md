# 从模型原始文本到 NDJSON：LLM 推理服务流水线

> 状态：已沉淀（2026-11-11）。结论、真实样本和复现脚本齐全；剩余的开放问题见文末「待验证的问题」。

## 定位

- 层级：L2 推理与服务
- 前置：llm-foundations（L1）
- 后续：Agent（L4）
- 负责：请求渲染、生成循环、协议解析、响应组装、NDJSON 传输，以及 Agent 侧应依赖的语义抽象
- 不负责：模型训练、RAG/知识库、Agent 业务编排
- 架构图：[../ai-map/README.md](../ai-map/README.md)

这份笔记回答两个问题：

1. 模型只吐 token，用户看到的 NDJSON 是怎么被推理服务一步步加工出来的？
2. 每一层该用什么抽象来写代码，才能以后换模型、换引擎时不改 Agent？

所有结论都用本地 Ollama（qwen2.5）+ 真实抓包验证，样本和复现命令见 [samples/](samples/)。

## 一句话结论

```text
请求 → 渲染 prompt → 生成 token → 解码文本 → 解析语义事件 → 组装响应 → 传输分帧
```

模型本身不知道什么是 `tool_calls`、什么是 JSON 字段，它只输出文本。**结构化返回是推理服务解析出来的**。

对 Agent 开发，记住一条：**依赖语义层，不要依赖某一层原始 chunk 的形状。**

## 全链路

```text
ChatRequest
   │
   ▼
┌───────────────┐   messages + tools → prompt
│   Renderer     │   模板、特殊 token、工具说明
└───────┬───────┘
        ▼
┌───────────────┐   prompt → token stream
│    Engine      │   采样、停止条件、KV Cache、批处理
└───────┬───────┘
        ▼
┌───────────────┐   token id → text delta
│  Detokenizer   │   增量解码；可能和 Engine 合并
└───────┬───────┘
        ▼
┌───────────────┐   text delta → semantic events
│ ProtocolParser │   状态机：content / thinking / tool_call
└───────┬───────┘
        ▼
┌───────────────┐   events → ChatResponse
│   Assembler    │   聚合增量、分配 tool_call id、finish_reason、usage
└───────┬───────┘
        ▼
┌───────────────┐   response → wire frame
│   Encoder      │   NDJSON / SSE / gRPC 分帧
└───────┬───────┘
        ▼
   用户 / Agent
```

## 八层抽象

| 层 | 抽象 | 职责 | 输入 → 输出 |
| --- | --- | --- | --- |
| 会话层 | `ChatRequest` | 表达意图和可用工具 | messages + tools → request |
| 渲染层 | `Renderer` | 把结构化请求变成模型能读的 prompt | request → prompt |
| 生成层 | `Engine` | 真正跑模型，产出 token 流 | prompt → `TokenEvent` |
| 文本层 | `Detokenizer` | token id 变文本增量 | `TokenEvent` → `TextDelta` |
| 解析层 | `ProtocolParser` | 把文本流解析成语义事件 | `TextDelta` → `SemanticEvent` |
| 组装层 | `Assembler` | 把增量聚合成完整响应 | `SemanticEvent` → `ChatResponse` |
| 传输层 | `WireEncoder` | 按协议分帧输出 | `ChatResponse` → `Frame` |
| 接入层 | `Gateway` | 鉴权、限流、路由、观测 | client → backend |

用 TypeScript 形状表示（概念模型，不是某家厂商的精确 API）：

```ts
type TokenEvent =
  | { type: 'token'; id: number; text?: string; logprob?: number }
  | { type: 'done'; reason: FinishReason };

type SemanticEvent =
  | { type: 'content'; delta: string }
  | { type: 'reasoning'; delta: string }
  | { type: 'tool_call_start'; index: number; id?: string; name: string }
  | { type: 'tool_call_args'; index: number; delta: string }
  | { type: 'tool_call_end'; index: number }
  | { type: 'done'; reason: FinishReason; usage?: Usage };

interface Renderer {
  render(req: ChatRequest): string;
}

interface Engine {
  generate(prompt: string, signal?: AbortSignal): AsyncIterable<TokenEvent>;
}

interface ProtocolParser {
  push(delta: TextDelta): SemanticEvent[];
  end(): SemanticEvent[];
}

interface Assembler {
  apply(event: SemanticEvent): void;
  result(): ChatResponse;
}

interface WireEncoder {
  encode(frame: ChatResponse): string;
}
```

注意：Ollama 在 `llm.CompletionResponse` 这一层已经把 token 解码成了文本，所以你能观察到的边界是 `TextDelta`；`TokenEvent` / `Detokenizer` 在更底层，可能和 Engine 合并在一起。

## 两个稳定边界

### 边界一：ModelAdapter = Renderer + ProtocolParser

`Renderer + ProtocolParser` 总是成对出现，合起来叫 **ModelAdapter（模型协议适配器）**：

```text
换模型家族   → 换 ModelAdapter（render 规则 + parse 规则）
换推理硬件   → 换 Engine（llama.cpp / vLLM / TensorRT-LLM）
换传输协议   → 换 Encoder（NDJSON / SSE / gRPC）
换接入策略   → 换 Gateway（鉴权 / 限流 / 路由）
```

Agent 代码只依赖 `SemanticEvent` 和 `ChatResponse`，不依赖 `<tool_call>` 标签、NDJSON 行数或 chunk 边界。这样换模型时只需要替换 adapter。

### 边界二：NDJSON 只是传输层

NDJSON 属于 `WireEncoder` 的产物，不是语义层：

- 一行 = 一个 `ChatResponse` 帧，不等于一个 token，也不等于一个语义事件
- 工具调用可能在一行里完整出现，也可能跨多行分片（取决于引擎）
- Agent 应该消费 `SemanticEvent`，不要直接 `JSON.parse` 每一行后做业务判断

NDJSON（Newline Delimited JSON，也叫 JSON Lines / `.jsonl`）的格式本身：**每一行是一个完整、独立的 JSON 值**，行与行之间只靠换行符分隔。

Ollama 流式返回的每一行就是：

```text
{"message":{"role":"assistant","content":"token"},"done":false}
{"message":{"role":"assistant","content":"是一种"},"done":false}
{"message":{"role":"assistant","content":"。"},"done":false}
{"message":{"role":"assistant","content":""},"done":true,"done_reason":"stop"}
```

特点：

- 没有外层数组、没有逗号、没有收尾括号
- 每行可以单独 `JSON.parse`，解析完立即处理，内存占用恒定
- 适合**流式、长度未知**的数据：不需要知道总条数，也不需要等收尾括号
- 不是正式标准，但被日志、数据管道、LLM 流式接口广泛使用

和普通 JSON 数组的区别：数组必须等整个文档到齐才能 parse；NDJSON 来一行就能处理一行。

解析时必须缓冲半行：

```js
let buffer = '';
for await (const chunk of res.body) {
  buffer += decoder.decode(chunk, { stream: true });
  const lines = buffer.split('\n');
  buffer = lines.pop();          // 最后一段可能是半行，留到下次
  for (const line of lines) {
    if (line.trim()) handle(JSON.parse(line));
  }
}
```

## Ollama 的实现映射

| 抽象 | Ollama 里的实现 |
| --- | --- |
| `Renderer` | Go template（Modelfile 的 `TEMPLATE`） |
| `Engine` | llama.cpp runner |
| `Detokenizer` | runner 回调，已经是 `Content` 文本 |
| `ProtocolParser` | builtin parser 或 `tools.NewParser`；外加 thinking tag parser |
| `Assembler` | `api.ChatResponse` + `writeChatResponse` |
| `WireEncoder` | `streamResponse`：`json.Marshal(val)` + `\n` |
| `Gateway` | 不在 Ollama 内，生产里由独立网关承担 |

下面各节都是这张表里某一层的具体实例。

## 从请求到 NDJSON 的具体实现

以 `qwen2.5` + `get_weather` 工具为例，Ollama 0.40.13。

### Modelfile：渲染规则和解析规则的来源

Modelfile 是 Ollama 的**模型配置/打包文件**，相当于模型的 Dockerfile。它不包含权重，而是描述这个模型怎么被加载和调用：

```text
FROM qwen2.5                  # 基础模型（引用已有模型或 blob）
PARAMETER temperature 0.7     # 默认推理参数
SYSTEM You are a helpful assistant.
TEMPLATE """..."""            # 把 messages/tools 渲染成模型能吃的 prompt
```

几个主要指令：

- `FROM`：基于哪个模型
- `PARAMETER`：默认采样参数（temperature、top_p 等）
- `SYSTEM`：默认 system prompt
- `TEMPLATE`：Go template，决定消息如何拼成 token 序列；工具调用的 `<tool_call>` / `<tool_response>` 约定就写在这里
- `MESSAGE` / `LICENSE`：示例对话、许可证

常用命令：

```bash
ollama show --modelfile qwen2.5    # 查看已有模型生成的 Modelfile
ollama create my-qwen -f Modelfile # 按 Modelfile 构建/注册新模型
```

工程类比：**Modelfile ≈ Dockerfile，TEMPLATE ≈ 请求序列化器**。改 TEMPLATE 就能改变工具调用格式，不需要重新训练模型。

### Renderer 到底在做什么：chat template

TEMPLATE 不是「把对话排得好看」，而是 **`messages[]` → 模型训练时见过的精确 token 串**。模型只认这个格式：同样的内容，换一种拼法（少一个 `<|im_end|>`、多一个空格），效果就会明显变差。

`ollama show --modelfile qwen2.5` 拿到的真实模板（节选）：

```text
TEMPLATE """{{- if .Messages }}
{{- if or .System .Tools }}<|im_start|>system
{{- if .System }}
{{ .System }}
{{- end }}
{{- if .Tools }}

# Tools
...
{{- end }}<|im_end|>
{{ end }}
{{- range $i, $_ := .Messages }}
{{- $last := eq (len (slice $.Messages $i)) 1 -}}
{{- if eq .Role "user" }}<|im_start|>user
{{ .Content }}<|im_end|>
{{ else if eq .Role "assistant" }}<|im_start|>assistant
{{ if .Content }}{{ .Content }}
{{- else if .ToolCalls }}<tool_call>
...
{{- else if eq .Role "tool" }}<|im_start|>user
<tool_response>
{{ .Content }}
</tool_response><|im_end|>
{{ end }}
{{- if and (ne .Role "assistant") $last }}<|im_start|>assistant
{{ end }}
{{- end }}"""
```

把这段模板用在一次请求上：

```text
输入:
  system: "You are Qwen, created by Alibaba Cloud. You are a helpful assistant."
  user:   "北京今天天气怎么样？"

渲染结果:
  <|im_start|>system
  You are Qwen, created by Alibaba Cloud. You are a helpful assistant.
  <|im_end|>
  <|im_start|>user
  北京今天天气怎么样？<|im_end|>
  <|im_start|>assistant
```

最后一行的 `<|im_start|>assistant` 是**预填**：模型从这之后开始续写。`<|im_start|>` / `<|im_end|>` 是特殊 token（各自对应一个 token id），不是普通字符，所以不能用字符串拼接随意模拟。

Go template 语法在这个模板里只用到几个：

| 写法 | 含义 |
| --- | --- |
| `{{ .System }}` | 取当前上下文的 `System` 字段 |
| `{{- ... }}` / `... -}}` | 去掉左侧/右侧的空白（换行、缩进） |
| `{{ range $i, $_ := .Messages }}` | 遍历消息，`$i` 是下标 |
| `{{ if eq .Role "user" }}` | 条件判断 |
| `{{ $last := ... }}` | 定义局部变量 |
| `$.Messages` | `$` 指根上下文，用于在内层拿到全局数据 |

工具说明也是模板注入的：`{{- if .Tools }}` 这一段把 tools schema 塞进 system message，并约定 `<tool_call>` 格式。所以**模板同时决定了「模型怎么看到工具」和「模型该怎么输出工具调用」**，这两件事必须和 parser 的预期一致。

> 一句话：`TEMPLATE` 是模型协议的一部分，不是展示层。它和权重是配套的——换模板等于换协议。

### Modelfile 是 Ollama 特有的吗

**Modelfile 这个文件格式是 Ollama 特有的，但它装的东西不是。**

拆开看，Modelfile 只是把四类信息打成一个包：

| Modelfile 指令 | 本质 | 别家怎么放 |
| --- | --- | --- |
| `FROM` | 权重 + 基础配置 | HF 仓库 / GGUF 文件 / S3 路径 |
| `TEMPLATE` | **chat template** | HF `tokenizer_config.json` 的 `chat_template`（Jinja） |
| `SYSTEM` | 默认 system prompt | 应用代码或模型仓库的 generation config |
| `PARAMETER` | 默认采样参数 | `generation_config.json` / API 请求参数 |

所以「Modelfile 是 Ollama 特有」只对包装格式成立；里面的 **chat template 是行业通用概念**，而且通常由**模型厂商随权重一起发布**：

- HuggingFace 模型仓库里，`tokenizer_config.json` 带一个 Jinja 版 `chat_template`
- vLLM 用 `--chat-template` 指定它（不指定就用 tokenizer 自带的那份）
- SGLang、TGI、Transformers 的 `apply_chat_template()` 用的是同一份东西
- Ollama 在导入模型时把这份模板写进 Modelfile；也可以手动覆盖

```text
同一份 chat template 的三种存在形式:

HF tokenizer_config.json (Jinja)  →  vLLM --chat-template
                                  →  Transformers apply_chat_template()
                                  →  Ollama 导入后写进 Modelfile 的 TEMPLATE (Go template)
```

注意 Ollama 这里用的是 **Go template**，而 HF 生态用 **Jinja**，两者语法不同、表达同一件事。所以跨引擎迁移时，模板通常要重写或直接用引擎支持的 Jinja 版本；只复制字符串是跑不起来的。

工程类比：**chat template ≈ 序列化协议（protobuf schema + serializer）**。`messages` 是结构化对象，模板负责把它编码成模型能读的字节流；`ProtocolParser` 再负责把模型吐出的字节流解码回结构化对象。两者必须用同一套协议，否则就是「按 JSON 序列化、按 XML 反序列化」。

这也解释了一个常见疑惑：为什么不能直接在应用里拼字符串？因为特殊 token、空白、角色顺序、工具段落的位置都是协议细节，拼错一个换行，模型表现就会漂移。让 Renderer 统一负责，才有唯一事实来源。

### 普通回复

前提：`ollama serve` 已启动，`ollama list` 里有 `qwen2.5`。

#### 非流式

```bash
curl -s http://localhost:11434/api/chat -d '{
  "model": "qwen2.5",
  "stream": false,
  "messages": [{"role": "user", "content": "用一句话解释什么是 token，不超过30字。"}],
  "options": {"num_predict": 40}
}' | jq .
```

实测返回（`samples/native-chat.json`）：

```json
{
  "model": "qwen2.5",
  "created_at": "2026-11-11T02:44:46.330128Z",
  "message": { "role": "assistant", "content": "Token是一种表示身份或权限的数字凭证。" },
  "done": true,
  "done_reason": "stop",
  "total_duration": 383887250,
  "load_duration": 1941000,
  "prompt_eval_count": 40,
  "prompt_eval_cached_count": 39,
  "prompt_eval_duration": 52759000,
  "eval_count": 11,
  "eval_duration": 321607000
}
```

要点：

- 只有一个 `message`，没有候选数组
- 没有请求 id
- 带完整的耗时统计（纳秒）
- `done_reason` 是结束原因

#### 流式

```bash
curl -sN http://localhost:11434/api/chat -d '{
  "model": "qwen2.5",
  "stream": true,
  "messages": [{"role": "user", "content": "用一句话解释什么是 token，不超过30字。"}],
  "options": {"num_predict": 12}
}'
```

响应头是 `Content-Type: application/x-ndjson`，每行一个完整 JSON（`samples/native-stream.ndjson`）：

```text
{"model":"qwen2.5","created_at":"...","message":{"role":"assistant","content":"token"},"done":false}
{"model":"qwen2.5","created_at":"...","message":{"role":"assistant","content":"是一种"},"done":false}
...
{"model":"qwen2.5","created_at":"...","message":{"role":"assistant","content":"。"},"done":false}
{"model":"qwen2.5","created_at":"...","message":{"role":"assistant","content":""},"done":true,"done_reason":"stop","eval_count":11,...}
```

最后一行 `content` 是空串，只用来标记结束并带统计信息。

这就是 `WireEncoder` 层的全部工作：`json.Marshal(val)` 后追加 `\n`。

### 工具调用：文本 → 解析 → 结构

同一个工具调用有三种形态，分别属于三层。理解这三层，就理解了解析器在做什么。

#### 模板层：Ollama 怎么提示模型调用工具

`ollama show --modelfile qwen2.5` 可以看到模板里注入的工具说明：

```text
# Tools

You may call one or more functions to assist with the user query.

You are provided with function signatures within <tools></tools> XML tags:
<tools>
{"type": "function", "function": <工具 schema>}
</tools>

For each function call, return a json object with function name and arguments within <tool_call></tool_call> XML tags:
<tool_call>
{"name": <function-name>, "arguments": <args-json-object>}
</tool_call>
```

也就是说，工具调用是**靠 prompt 约定出来的文本格式**，不是模型的原生输出结构。

#### 模型层：未解析的原始文本

用 `/api/generate` + `"raw": true` 绕过 Ollama 的模板和工具解析（自己按上面的模板拼好 prompt），模型实际输出（`samples/raw-model-tool-call.json`）：

```json
{
  "response": "<tool_call>\n{\"name\": \"get_weather\", \"arguments\": {\"city\": \"北京\"}}\n</tool_call>",
  "done_reason": "stop"
}
```

结论：**模型根本不知道 `tool_calls` 数组**，它只是按模板输出了一段带标签的文本。后面的结构化字段全是 Ollama 解析出来的。

#### API 层：解析后的 `tool_calls`

`/api/chat` 非流式（`samples/native-tool-call.json`）：

```json
{
  "message": {
    "role": "assistant",
    "content": "",
    "tool_calls": [
      {
        "id": "call_ftnoyqyh",
        "function": {
          "index": 0,
          "name": "get_weather",
          "arguments": { "city": "北京" }
        }
      }
    ]
  },
  "done": true,
  "done_reason": "stop"
}
```

要点：

- `arguments` 是**对象**，不是字符串
- `id` 由 Ollama 生成，模型原始文本里没有
- `index` 放在 `function` 里面
- `content` 为空
- `done_reason` 仍然是 `"stop"`，**不是** `"tool_calls"`

流式（`samples/native-tool-stream.ndjson`）：整个工具调用**一次性**出现在一个 `done: false` 的块里：

```text
{"message":{"role":"assistant","content":"","tool_calls":[{"id":"call_m8jwccvu","function":{"index":0,"name":"get_weather","arguments":{"city":"北京"}}}]},"done":false}
{"message":{"role":"assistant","content":""},"done":true,"done_reason":"stop",...}
```

#### 文本和工具调用会同时出现吗

会。模型可以在 `<tool_call>` 前后输出普通文本，Ollama 会把**标签外的文本放进 `content`**，**标签内的内容解析成 `tool_calls`**。

模型层原文（`samples/raw-model-tool-call-with-text.json`）：

```text
我会查询北京的当前天气情况，然后将结果反馈给你。

<tool_call>
{"name": "get_weather", "arguments": {"city": "北京"}}
</tool_call>
```

对应 `/api/chat` 的返回（`samples/native-tool-call-with-text.json`，同样 prompt 的另一次采样）：

```json
{
  "message": {
    "role": "assistant",
    "content": "我会先调用工具查询北京的当前天气情况。\n\n",
    "tool_calls": [
      {
        "id": "call_zn1ytv5e",
        "function": {
          "index": 0,
          "name": "get_weather",
          "arguments": { "city": "北京" }
        }
      }
    ]
  },
  "done_reason": "stop"
}
```

所以不要假设 `content` 一定为空：文本说明和工具调用可以同时存在。

#### 并行工具调用

一条回复里可以出现多个 `<tool_call>` 块。模型原文（`samples/raw-model-parallel-tool-calls.json`）：

```text
<tool_call>
{"name": "get_weather", "arguments": {"city": "北京"}}
</tool_call>
<tool_call>
{"name": "get_weather", "arguments": {"city": "上海"}}
</tool_call>
```

Ollama 解析成两个 `tool_calls`，`index` 从 0 递增，每个调用有自己的 `id`（`samples/native-parallel-tool-calls.json`）：

```json
{
  "message": {
    "role": "assistant",
    "content": "",
    "tool_calls": [
      {
        "id": "call_sbig7s90",
        "function": { "index": 0, "name": "get_weather", "arguments": { "city": "北京" } }
      },
      {
        "id": "call_xh6g9pkt",
        "function": { "index": 1, "name": "get_weather", "arguments": { "city": "上海" } }
      }
    ]
  },
  "done_reason": "stop"
}
```

#### 回传工具结果

执行完工具后，把结果作为 `role: "tool"` 的消息发回去（`samples/native-tool-loop.json`）：

```json
[
  { "role": "user", "content": "北京今天天气怎么样？" },
  { "role": "assistant", "content": "", "tool_calls": [
    { "function": { "name": "get_weather", "arguments": { "city": "北京" } } }
  ]},
  { "role": "tool", "content": "{\"city\":\"北京\",\"weather\":\"晴\",\"temperature\":18}" }
]
```

Ollama 在渲染 prompt 时，会把结构化消息再转回文本：

```text
assistant + tool_calls  →  <tool_call>
                           {"name": "get_weather", "arguments": {"city": "北京"}}
                           </tool_call>
role: tool              →  <tool_response>
                           {"city":"北京","weather":"晴","temperature":18}
                           </tool_response>
```

模型看到这些文本后继续生成，实测回答：

```text
今天北京的天气是晴，气温约为18度。请注意适时增减衣物。
```

所以整条工具链本质上是：**结构化对象 → 文本 → 模型 → 文本 → 结构化对象**。

补充一个细节：如果 assistant 消息同时有 `content` 和 `tool_calls`，Qwen 模板的逻辑是 `if .Content ... else if .ToolCalls`，也就是**只回放 content，不回放工具调用**。实测这种历史仍然能基于 `<tool_response>` 答对，但不要依赖工具调用被重新渲染进 prompt。

#### 分层对照表

| 观察点 | 模型文本 | Ollama API |
| --- | --- | --- |
| 工具调用载体 | `<tool_call>` 标签 | `message.tool_calls` |
| `arguments` | 标签内的 JSON 文本 | 对象 |
| `id` | 无 | Ollama 生成 `call_xxx` |
| 文本 + 工具调用 | 标签外文本 + 标签内调用 | `content` 和 `tool_calls` 可同时存在 |
| 并行调用 | 多个 `<tool_call>` 块 | 多个 `tool_calls`，`index` 递增 |
| 结束信号 | `</tool_call>` | `done_reason: "stop"` |
| 流式形态 | token 文本 | 整段一次 |
| 工具结果 | `<tool_response>` | `role: "tool"` + `content` |

### parser 怎么知道该用哪种格式

TEMPLATE 只负责**告诉模型怎么输出**，真正把文本变成 `tool_calls` 的是 parser。Ollama 有两条路径。

#### 路径 1：有命名 parser 的模型（新模型）

较新的 Ollama 支持在 Modelfile 里显式指定：

```text
FROM functiongemma-finetune
RENDERER functiongemma
PARSER functiongemma
```

- `RENDERER`：把 messages + tools 渲染成 prompt
- `PARSER`：把模型输出解析成 content / thinking / tool_calls
- 内置 parser 是按模型家族写的状态机，放在 `model/parsers`；renderer 在 `model/renderers`

选择逻辑简化后（`server/routes.go`）：

```go
func parserNameForModel(m *Model) string {
    if m.Config.Parser != "" { return m.Config.Parser }
    if shouldUseHarmony(m) { return "harmony" }
    return ""
}
```

名字未知时 `ParserForName` 返回 nil，后面会回退到路径 2。

#### 路径 2：没有命名 parser 的模型（如 qwen2.5）

源码里的回退逻辑：

```go
var toolParser *tools.Parser
if len(req.Tools) > 0 && (builtinParser == nil || !builtinParser.HasToolSupport()) {
    toolParser = tools.NewParser(m.Template.Template, req.Tools)
}
```

通用 parser **不读自然语言说明**，它解析 Go template 的 AST：

1. 找到包含 `.ToolCalls` 的 `IfNode`
2. 取该分支里的第一个非空文本节点
3. 截断到 `{` 之前，得到标记
4. 找不到标记就返回 `{`，表示「从第一个 JSON 对象开始尝试解析」

源码注释很直接（`tools/template.go`）：

```go
// parseTag finds the tool calling tag from a Go template
// often <tool_call> [TOOL_CALL] or similar by finding the
// first text node after .ToolCalls and returning the content
// if no tag is found, return "{" to indicate that json objects
// should be attempted to be parsed as tool calls
```

qwen2.5 的模板里：

```text
{{ else if .ToolCalls }}<tool_call>
{{ range .ToolCalls }}{"name": "{{ .Function.Name }}", "arguments": {{ .Function.Arguments }}}
{{ end }}</tool_call>
```

所以 parser 提取到的标记就是 `<tool_call>`。这也解释了前面的抓包：模型输出 `<tool_call>{...}</tool_call>`，Ollama 能准确切出来。

#### 关键结论

- **解析格式不是从自然语言说明里猜的**，而是从模板的 `.ToolCalls` 分支里提取的
- 改 TEMPLATE 时，`.ToolCalls` 分支和给模型看的说明必须保持一致；只改说明不改分支，parser 仍按旧标记找
- 用命名 `PARSER` 的模型，格式由 parser 代码决定，模板说明要配合它
- 两者都没有明显标记时，通用 parser 会退化成「尝试解析第一个 JSON 对象」

#### 源码位置

- [server/routes.go](https://github.com/ollama/ollama/blob/main/server/routes.go)：parser 选择与 `tools.NewParser` 回退
- [tools/template.go](https://github.com/ollama/ollama/blob/main/tools/template.go)：从 `.ToolCalls` 节点提取标记
- [tools/tools.go](https://github.com/ollama/ollama/blob/main/tools/tools.go)：通用解析状态机
- [model/parsers](https://github.com/ollama/ollama/tree/main/model/parsers) / [model/renderers](https://github.com/ollama/ollama/tree/main/model/renderers)：命名 parser/renderer

## Agent 开发怎么用这套抽象

前面是「推理服务怎么产出」，这里是「你的 Agent 该怎么消费」。核心只有一句：**把 `SemanticEvent` 当成唯一稳定接口**，其余各层都可以换。

### 1. 定义自己的 `SemanticEvent`

不要直接对着 provider 的 chunk 写业务逻辑。先定一个与厂商无关的事件联合类型（就是前面那个 `SemanticEvent`），以后换模型只改 parser，Agent 循环不动。

判断标准：如果把 Ollama 换成 vLLM，你的 Agent 循环代码应该一行都不用改。

### 2. 一个模型家族 = 一个 `ModelAdapter`

`Renderer` 和 `ProtocolParser` 打包成 adapter：

```ts
interface ModelAdapter {
  renderer: Renderer;
  parser: ProtocolParser;
}
```

- `qwen2.5` → `<tool_call>` 标签、`arguments` 是 JSON 对象文本
- `llama3.1` → `<|python_tag|>` 之类的前缀
- `harmony` 系列 → 命名 parser

不要写 `if (model.includes('qwen'))` 散落在业务里，把差异全部收进 adapter。

### 3. Parser 必须是**有状态**的

工具调用的标签和 JSON 都会跨 chunk：

```text
chunk1: "...<tool_"
chunk2: "call>{\"name\":\"get_wea"
chunk3: "ther\",\"arguments\":{...}}</tool_call>"
```

所以 `push(delta)` 要维护缓冲区：遇到 `<` 不能立刻当正文输出，要等确认是不是标签开头；标签内 JSON 没闭合前不能 emit `tool_call_end`；`end()` 时把残留的缓冲区 flush 掉（否则最后一段永远丢）。

这也是 Ollama 的 `tools.Parser.Add` 用 `bytes.Buffer` 边读边切的原因。

### 4. Assembler 负责「身份」和「累积」

- 分配 `tool_call` 的 `id`（模型原文里没有）
- 按 `index` 累积 `arguments` 的字符串分片
- 记录 `finish_reason` 和 `usage`
- 流式场景下同时对外 emit 增量帧、对内累积完整 `ChatResponse`

没有这一层，并行工具调用（`index` 0/1）会串到一起。

### 5. Agent 循环只认 `ChatResponse`

```ts
let messages = [{ role: 'user', content: input }];
while (true) {
  const resp = await client.chat({ model, messages, tools });
  if (!resp.toolCalls?.length) return resp.content;

  messages.push({ role: 'assistant', content: resp.content, tool_calls: resp.toolCalls });
  for (const call of resp.toolCalls) {
    const result = await runTool(call.name, call.arguments);
    messages.push({ role: 'tool', content: JSON.stringify(result) });
  }
}
```

注意循环条件看的是 `toolCalls`，不是 `finish_reason`——Ollama 有工具调用时 `done_reason` 仍然是 `"stop"`。

### 6. 可观测性记语义事件，不记原始行

日志里存 `SemanticEvent` 序列（`content` / `tool_call_start` / `tool_call_args` / `done`）比存 NDJSON 行有价值：

- 换 provider 后历史日志还能对比
- 能直接算出「首 token 延迟」「工具调用耗时」「参数分几片到达」
- 排查问题时不用再反推 chunk 边界

### 7. 超时和重试分层放

| 关注点 | 放哪层 | 原因 |
| --- | --- | --- |
| 单次生成超时 / 取消 | `Engine` | 只有它能真正 abort 生成 |
| 请求重试 / fallback 到别的模型 | `Gateway` | 它知道路由和配额 |
| 解析失败的补救 | `ProtocolParser` | 它能降级成「当普通文本处理」 |

不要在 Agent 循环里做重试——那里已经丢失了分片上下文。

## 生产环境对应什么

没有一个统一名字，通常叫 **大模型推理服务 / 推理平台**。它不是一个进程，而是一套分层：

```text
接入层   API 网关 / LLM Gateway     鉴权、限流、计费、路由、fallback
         LiteLLM、OneAPI、Envoy/Kong、自研
服务层   模型服务框架               多副本、扩缩容、调度、灰度
         KServe、Ray Serve、BentoML、Triton、自研
引擎层   推理引擎                   连续批处理、KV Cache、量化、并行
         vLLM、SGLang、TensorRT-LLM、llama.cpp、MLX
资源层   GPU 集群 / K8s / Ray
```

Ollama 相当于把「模型管理 + 推理引擎 + HTTP API + 模板/解析」打成一个本地开发包：

| Ollama | 生产里的对应物 |
| --- | --- |
| Modelfile 的 TEMPLATE / PARSER | vLLM 的 `--chat-template` + `--tool-call-parser` |
| `/api/chat` | 推理引擎自带的 HTTP API server |
| `ollama pull` / `ollama list` | 模型仓库 + 本地缓存 |
| 单机进程 | K8s + 多副本 + 调度 |

工程类比：**Ollama ≈ SQLite / Vite dev server**（一体化、开箱即用）；生产平台 ≈ **Postgres + K8s + Envoy**（拆成专用组件，分别扩展）。

关键连接：前面学的 renderer/parser 分层在生产引擎里也存在。比如 vLLM 用 `--chat-template` 指定渲染模板、用 `--tool-call-parser` 指定工具调用解析器；SGLang 也有类似参数。所以「模板负责教模型怎么输出，parser 负责把输出解析回来」是通用架构，不是 Ollama 特有。

## 容易踩的坑

- **NDJSON 必须按行缓冲**：TCP 分包会把一行 JSON 截断，不能对每个 chunk 直接 `JSON.parse`。
- **有工具调用时 `done_reason` 仍然是 `"stop"`**：写循环要判断 `message.tool_calls`，不能只看结束原因。
- **`content` 为空不代表出错，也不代表一定为空**：工具调用可能在 `tool_calls` 里；但模型也可以先输出说明文本，此时 `content` 和 `tool_calls` 同时存在。
- **并行工具调用看 `index`**：多个 `<tool_call>` 块会解析成多个 `tool_calls`，`index` 从 0 递增，每个调用有独立 `id`。
- **历史回放只保留 content**：assistant 消息同时有 `content` 和 `tool_calls` 时，模板只渲染 content；工具调用本身不会回到 prompt 里。
- **`arguments` 是对象**：不要按字符串去解析；如果自己转发，需要显式序列化。
- **`id` 是 Ollama 生成的**，模型原始 `<tool_call>` 文本里没有这个字段。
- **流式工具调用是整段一次给出**：不要假设它像普通文本一样逐 token 分片。
- **`usage` 统计的是 token 不是字符**：中文一个字通常是一个 token，但英文子词、数字、符号会拆开，不能按长度估算。
- **改模板要同时改 `.ToolCalls` 分支**：通用 parser 只从这段提取标记；只改给模型看的说明，解析器会继续找旧标记。
- **`raw: true` 会跳过模板和工具解析**：用它观察模型原文时，prompt 要自己按模板拼好，否则模型看不到工具说明。

## 待验证的问题

- [x] 并行工具调用（一次返回多个 `tool_calls`）时 `index` 和顺序怎么排
- [x] 不同模型/模板的工具格式差异是如何解析的（命名 parser vs 通用 parser）
- [ ] 自定义 `.ToolCalls` 标记后，通用 parser 是否跟着新标记走（可用临时 Modelfile 验证）
- [ ] assistant 同时有 content 和 tool_calls 时，怎么回放才能让模型看到完整历史
- [ ] 模型输出格式错误的 `<tool_call>` 时，Ollama 怎么处理（丢弃、报错、还是当普通文本）
- [ ] 官方 Ollama 模板对其它模型（如 llama3.1）的工具调用格式是否一致
- [ ] 如何拿到 token id / logprobs（原生接口似乎不暴露）
- [ ] 错误响应的结构
- [ ] `done_reason` 除 `stop` 外还有哪些取值

## 目录与复现

```text
llm-serving-pipeline/
├── README.md                              # 本文件
└── samples/
    ├── reproduce.sh                       # 下面所有样本的生成脚本
    ├── native-chat.json                   # 原生非流式
    ├── native-stream.ndjson               # 原生流式
    ├── raw-model-tool-call.json           # 模型未解析的纯 <tool_call> 文本
    ├── raw-model-tool-call-with-text.json # 模型未解析的文本 + <tool_call>
    ├── raw-model-parallel-tool-calls.json # 模型未解析的并行工具调用
    ├── native-tool-call.json              # 工具调用非流式
    ├── native-tool-call-with-text.json    # content + tool_calls 同时存在
    ├── native-parallel-tool-calls.json    # 并行工具调用
    ├── native-tool-stream.ndjson          # 工具调用流式
    ├── native-tool-loop.json              # 多轮回传工具结果
    └── native-tool-loop-with-text.json    # 带说明文本的多轮回传
```

样本不是手写的，全部由 [samples/reproduce.sh](samples/reproduce.sh) 请求本地 Ollama 生成。脚本里每个 case 就是对应文件当时的命令：

| 样本 | 命令 | 接口 |
| --- | --- | --- |
| `native-chat.json` | `./reproduce.sh native-chat` | `/api/chat`，非流式 |
| `native-stream.ndjson` | `./reproduce.sh native-stream` | `/api/chat`，流式 |
| `native-tool-call.json` | `./reproduce.sh native-tool-call` | `/api/chat` + tools，非流式 |
| `native-tool-stream.ndjson` | `./reproduce.sh native-tool-stream` | `/api/chat` + tools，流式 |
| `native-parallel-tool-calls.json` | `./reproduce.sh native-parallel-tool-calls` | `/api/chat`，一次问两个城市 |
| `native-tool-loop.json` | `./reproduce.sh native-tool-loop` | `/api/chat`，带 `role: tool` 历史 |
| `native-tool-loop-with-text.json` | `./reproduce.sh native-tool-loop-with-text` | 同上，assistant 带 content |
| `raw-model-tool-call.json` | `./reproduce.sh raw-model-tool-call` | `/api/generate` + `raw: true` |
| `raw-model-tool-call-with-text.json` | `./reproduce.sh raw-model-tool-call-with-text` | 同上，提示模型先说话 |
| `raw-model-parallel-tool-calls.json` | `./reproduce.sh raw-model-parallel-tool-calls` | 同上，一次问两个城市 |

全部重新生成：

```bash
cd samples && ./reproduce.sh
```

几个注意点：

- 脚本依赖 `curl`、`jq`、已启动的 `ollama serve`、已 pull 的 `qwen2.5`；用 `MODEL=` 和 `OLLAMA_HOST=` 可以覆盖。
- 采样有随机性，重跑得到的 `id`、耗时、措辞不会和仓库里的样本逐字一致，但结构一致。少数 case 固定了 `seed`。
- `raw: true` 的 case 用 `raw_prompt()` 手工复刻了 qwen2.5 的模板。这正是 `Renderer` 层在做的事——想观察模型原文，就得自己承担渲染。
- 不想覆盖现有样本时用 `OUT_DIR=/tmp/out ./reproduce.sh <name>`。
