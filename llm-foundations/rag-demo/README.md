# 最小 RAG demo：看检索片段怎么进入 prompt

这份 demo 只回答一个问题：**RAG 到底改了请求里的哪个部分？**

结论先说：RAG 没有改模型、没有改权重，它改的是这一次请求的 `messages`。检索到的原文，被逐字拼进 user message 的 `<资料>` 块里，模型再基于这段拼好的 prompt 生成回答。

仓库里有两份实现，切片和 prompt 拼接完全一样，**只换了检索打分器**：

- `rag.py`：BM25，数问题和切片有多少共同词，不需要任何模型
- `vector_rag.py`：embedding 向量，比较语义方向，需要一个 embedding 模型

跑完你能亲眼看到三样东西：

1. 一个问题命中了哪几个切片，分数是多少
2. 这些切片被拼成了什么样的字符串
3. 模型拿着这个字符串回答，并在答案里标出 `[片段 N]`

## 数据流

```
docs/*.md
   │  ① 切片：按句子拼成 ≤120 字的块
   ▼
Chunk(title, text, source)
   │  ② 建索引：中文双字 + BM25
   ▼
Index(term_freqs, idf, lengths)
   │  ③ 检索：query 与每个切片打分，取 Top-K
   ▼
hits[(score, Chunk)]
   │  ④ 拼 prompt：切片原文塞进 <资料>，问题放最后
   ▼
messages[system, user]
   │  ⑤ 调 Ollama /api/chat
   ▼
answer（带 [片段 N] 引用）
```

`vector_rag.py` 把 ②③ 换成：切片 → embedding 模型 → 1024 维向量并缓存；查询时问题 → 同一个模型 → 一个向量 → 和每个切片算余弦相似度。

### ① 为什么按句子切片，而不是按段落

段落长度差异太大：短段落检索时天然占优，长段落塞进 prompt 又浪费 token。这里先把正文拆成句子，再贪心地拼到接近 120 字，保证每个切片长度接近。

每篇文档的**第一段当标题**，标题单独存成 `Chunk.title`。这解决一个具体问题：标题里的词（如「量化」）在正文里可能只出现一次，检索容易漏掉。

### ② 为什么用中文双字，而不是直接按空格切词

不引入 jieba 这类分词依赖，同时避免单字噪声。`量化` 切成 `量化`；`文件体积` 切成 `文件 / 件体 / 体积`。英文和数字仍按整词切分。

### ③ 为什么用 BM25，而不是 TF-IDF 余弦相似度

余弦相似度会被短切片带偏：一个只有标题的短块，只要命中一个词，相似度就可能很高。BM25 带长度归一化（`b=0.75`）和词频饱和（`k1=1.5`），更适合长度不齐的切片。

索引时把 `title + text` 一起算词频，相当于给切片加了个上下文头，缓解「标题里有、正文里没重复」的漏召回。

### ④ 拼 prompt 的格式

```text
<资料>
[片段 1] 来源：quantization.md#c1《量化与文件体积》
量化把权重用更少的 bit 表示……

[片段 2] 来源：quantization.md#c2《量化与文件体积》
实际 gguf 文件约 4.3GB……

[片段 3] 来源：parameters.md#c1《参数量与权重》
参数量表示模型里有多少个数字……
</资料>

问题：量化会改变参数量吗？文件体积怎么估算？
```

三处设计各有目的：

- 编号 `[片段 N]`：让模型能引用，也方便你回头对照命中来源
- 来源和标题：模型看到的不是无主文本，能区分不同文档的上下文
- 问题放在资料**后面**：模型是自回归的，越靠后的内容对下一步生成影响越直接；问题放在末尾，比放在开头更容易被「认真对待」

system prompt 里明确写「只依据资料回答、没有就说不知道」，这是为了压住模型用预训练知识编造答案的倾向。

### ⑤ 生成

调用本地 Ollama 的 `/api/chat`，`stream: false`，`temperature: 0.2`。低温度是为了让答案稳定、少发挥；RAG 场景里发挥通常意味着编造。

## 怎么跑

```bash
cd llm-foundations/rag-demo

# 只看检索和 prompt，不调模型（不需要 Ollama）
python3 rag.py --dry-run

# 真实调用本地 qwen2.5
python3 rag.py

# 换问题 / 换 Top-K
python3 rag.py --query "KV Cache 会占多少显存？" --top-k 2

# 把最终 messages 存成 JSON，方便贴到别处对照
python3 rag.py --save-prompt prompt.json

# 向量版：先拉一次 embedding 模型（639MB）
ollama pull qwen3-embedding:0.6b

# 第一次会把 12 个切片算成向量并缓存到 embeddings.json，之后直接复用
python3 vector_rag.py

# 只换问题；切片没变时会命中缓存，检索本身只要几十毫秒
python3 vector_rag.py --dry-run --query "KV Cache 会占多少显存？" --top-k 2

# 文档改动后强制重算向量
python3 vector_rag.py --rebuild
```

前置条件：`ollama serve` 已启动，且本地有 `qwen2.5`（或 `--model` 指定别的）。`rag.py` 的检索只用 Python 标准库；`vector_rag.py` 额外需要 `qwen3-embedding:0.6b`（或 `--embed-model` 指定别的）。

## 你会看到什么

`sample-output.txt` 是一次真实运行的完整输出，关键片段：

```text
切片数量：12
词表大小：428

1. score=15.497  quantization.md#c1 《量化与文件体积》 量化把权重用更少的 bit 表示……
2. score=7.784   quantization.md#c2 《量化与文件体积》 实际 gguf 文件约 4.3GB……
3. score=7.327   parameters.md#c1   《参数量与权重》 参数量表示模型里有多少个数字……

（以上内容共 490 字符，就是模型这次真正看到的 prompt）

模型回答：
量化不会改变参数量 [片段 3]。文件体积可以用「参数量 × 有效位宽 / 8」进行粗略估算 [片段 1]。
```

注意 `[片段 3]` 和 `[片段 1]`：模型确实在引用拼进去的片段编号，说明它是从 `<资料>` 里取的信息，而不是凭记忆回答。

## 向量版：同一个问题，两套榜单

`sample-vector-output.txt` 是 `vector_rag.py` 的真实输出。同一个问题，两种打分器的 Top 3：

| 排名 | BM25（数共同词） | 向量（比语义方向） |
| --- | --- | --- |
| 1 | `quantization.md#c1`（15.497） | `quantization.md#c1`（0.6556） |
| 2 | `quantization.md#c2`（7.784） | `quantization.md#c2`（0.6351） |
| 3 | `parameters.md#c1`（7.327） | `parameters.md#c2`（0.6339） |

前两名一致，第三名开始分叉：

- BM25 选 c1，因为它和问题共享「参数量」这个词
- 向量选 c2，因为 c2 讲的是「参数量相同的模型，文件大小也可能不同」，语义上更贴近「文件体积怎么估算」

两类分数的尺度也不同：BM25 的分数没有绝对含义，只能在同一次查询里横向比；余弦相似度有大致刻度，1 表示方向完全一致，0 表示无关。余弦怎么手算、为什么先归一化，见 L0 笔记 [math-foundations](../../math-foundations/)。

向量版实际做了三件事，和 BM25 版的 `retrieve` 骨架完全一样：

1. **建库**：12 个切片一次性发给 embedding 模型，拿回 12 个 1024 维向量，归一化后存进 `embeddings.json`
2. **查询**：问题发给同一个模型，得到一个 1024 维向量
3. **排序**：问题向量和每个切片向量做点积（单位向量的点积就是余弦），从高到低取 Top-K

几个实现细节：

- **先归一化**：把向量长度缩放到 1，之后点积直接等于余弦，每次比较少算两个平方根
- **缓存带指纹**：缓存里存了模型名和全部切片内容的 sha256；换模型或改文档会自动失效重算
- **阈值要重新标定**：BM25 版用 `< 0.5`，向量版用 `< 0.45`。余弦的绝对尺度随 embedding 模型变化，不能照搬
- **超纲问题仍会掉分**：「公司年假怎么申请？」的最高余弦只有 0.194，同样触发 warning，并被 system prompt 拒答

## 失败模式：问题超出知识库

用 `--query "公司年假怎么申请？"` 跑，所有切片得分都是 0：

```text
1. score=0.000  context.md#c1  《上下文长度》 ……
2. score=0.000  context.md#c2  《上下文长度》 ……
3. score=0.000  kv-cache.md#c1 《KV Cache 与显存》 ……

⚠ 最高分很低：问题可能超出知识库范围。此时模型仍可能编造，需要靠 prompt 约束或拒答。

模型回答：
资料中没有提供关于公司年假申请的信息，因此我不知道公司年假怎么申请。
```

完整输出见 `sample-out-of-scope.txt`。这里有两层防线：

- **检索层**：得分阈值（demo 里是 `< 0.5`）提示「可能召回了不相关内容」
- **生成层**：system prompt 要求「资料里没有就说不知道」，模型因此拒答，而不是拿上下文长度去硬凑年假答案

只有第一层不够——低分内容仍然会被拼进 prompt；只有第二层也不够——资料里恰好有相似词时，模型仍可能被误导。两层都要有。

## 两个 top_k 别混

这份 demo 里有两个同名的 `top_k`，它们在不同层，做的是完全不同的事。

**RAG 的 top_k**：检索阶段取前几段资料，**取几段就放几段进 prompt**。`--top-k 3` 的真实效果是 prompt 里同时出现 `[片段 1]`、`[片段 2]`、`[片段 3]`。模型回答可能只引用其中两段，但三段它都看到了。

**生成的 top_k**：采样阶段每个 token 做一次「取几个候选词、抽一个」。模型先算出词表里每个 token 的分数，`top_k=3` 只保留最高的 3 个候选，再按概率抽 1 个接到后面；下一个 token 再来一遍。

| | RAG 的 top_k | 生成的 top_k |
| --- | --- | --- |
| 发生在哪 | 检索层 | 采样层 |
| 作用对象 | 切片（文档片段） | 下一个 token 的候选 |
| 取几个 | 3 段资料 | 3 个候选词 |
| 输出 | 3 段全部拼进 prompt | 只输出 1 个 token |
| 执行次数 | 每次提问 1 次 | 每生成 1 个 token 1 次 |

demo 调用 Ollama 时只设了 `temperature: 0.2`，没有设采样 `top_k`，所以用的是 Ollama 默认值（通常 40）。不要把 RAG 的 `--top-k 3` 写进 Ollama 的 `options`：那会让模型每一步只能在 3 个词里选，输出容易变得死板、重复。

采样还有一个 `top_p`：不固定个数，而是按概率从高到低累加，凑够 p（比如 0.9）就停；模型越确定，留下的候选越少。

## 这个 demo 故意没做什么

保持最小，以下都是真实 RAG 系统才需要补的：

| 省略的东西 | 真实系统里怎么做 |
| --- | --- |
| ANN 索引 / 向量数据库 | 切片上万后，逐个算余弦太慢；用 FAISS、Qdrant、Milvus 或 pgvector 的 HNSW / IVF 索引先粗筛候选 |
| 混合检索 | BM25 与向量检索各取 Top-K，再融合（RRF） |
| Rerank | 用 cross-encoder 对候选片段重排，提升 Top-3 精度 |
| 切片重叠 | 相邻切片保留 10%–20% 重叠，避免答案被切断 |
| 多轮与追问 | 先做 query 改写，把「它呢？」补全成完整问题再检索 |
| 引用回链 | 片段带原文位置（文件 + 行号/页码），前端可点击跳转 |

但无论加多少层，**最终进入模型的东西仍然是一段拼好的 prompt**。这份 demo 的价值就是把这一步摊开给你看。

## 生产环境长什么样

demo 的每一段都做了简化。真正上线主要补这些：

- 用专用的 embedding 模型，建库和查询必须是同一个；换模型要全量重建索引
- 切片结构优先，中文 300–800 字、10%–20% 重叠，带上章节路径和 metadata
- 把 `embeddings.json` 换成向量库（pgvector / Qdrant / Milvus），由它负责持久化、metadata 过滤和 ANN 检索
- 向量 + BM25 混合召回，再用 rerank 精排
- 权限在检索前过滤；日志要能还原「检索到什么、模型看到了什么」
- 有 golden set，能量化 Recall@k 和答案忠实度

完整展开见 [production.md](production.md)：切片策略、embedding 选型、向量库对比、HNSW/IVF、RRF 融合、评测指标、成本延迟、安全与常见故障。

## 文件

| 文件 | 说明 |
| --- | --- |
| `README.md` | 链路说明、两个 top_k 的区别、运行与观察点 |
| `production.md` | 生产环境补全：embedding 选型、切片、向量库、混合检索、评测与运维 |
| `rag.py` | BM25 版检索，只用标准库 + Ollama HTTP |
| `vector_rag.py` | 向量版检索，复用切片与 prompt 逻辑，只换了打分器 |
| `docs/*.md` | 6 篇知识库文档，内容来自 `llm-foundations` 的概念笔记 |
| `embeddings.json` | 切片向量缓存（12 × 1024），首次运行自动生成 |
| `sample-output.txt` | BM25 版默认问题的真实运行输出 |
| `sample-vector-output.txt` | 向量版默认问题的真实运行输出 |
| `sample-out-of-scope.txt` | 超纲问题的真实运行输出（展示拒答） |
| `prompt.json` / `prompt-vector.json` | 两版 `--save-prompt` 产出的最终 messages，可直接对照 |

## 和推理服务笔记的关系

这里发出去的 `messages` 是 `llm-serving-pipeline` 里 `ChatRequest` 的内容。它到达 Ollama 后，Renderer 会用 chat template 把它渲染成一串带 `<|im_start|>` / `<|im_end|>` 的纯文本，再交给 Engine。

也就是说：

```
RAG 决定 messages 里写什么  →  Renderer 决定 messages 变成什么文本  →  Engine 决定下一个 token 出什么
```

三段各管一段，边界清楚。RAG 不需要知道 chat template 长什么样，模型也不需要知道资料是检索来的还是用户手打的。
