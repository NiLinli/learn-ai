# 论文地图：从 Transformer 到 Agent

> 状态：维护中（2026-11-11）。这是一份**跨 topic 的阅读索引**，不是学习 topic。论文标题与 arXiv 编号已于 2026-11-11 通过 arXiv API 核对。

## 定位

- 负责：按知识依赖整理论文、给出链接、说明每篇解决什么问题、读到什么程度算读完
- 不负责：论文精读笔记、公式推导、代码复现；这些落到对应 topic
- 为什么不建 `papers/` 一级 topic：它横跨 L1（模型）、L3（推理与上下文）、L4（Agent），没有独立的抽象层和实验证据。按 [AGENTS.md](AGENTS.md) 的归属规则，作为根目录元文档维护，与 [ai-map/](ai-map/)、[learning-model.md](learning-model.md) 同级

## 怎么读

1. **按依赖顺序读，不按年份读。** 先有底座，再读提示技术，最后读 Agent。
2. 每篇只回答三个问题：**解决什么问题、核心机制是什么、证据是什么**。
3. 数学推导可以跳过。重点看输入输出、状态变化和失败模式；需要补数学时转到 [math-foundations](math-foundations/)。
4. 读完一篇，更新下面的状态，并在对应 topic 里留一条自己的结论。只收藏不读不算进度。

## 推荐路径

```text
底座      1 Transformer → 2 BERT → 3 GPT-3
推理      4 CoT → 5 Self-Consistency → 6 Tree of Thoughts
工具行动  9 MRKL → 7 ReAct → 8 Toolformer
Agent     12 Reflexion → 13 Plan-and-Execute → 14 Generative Agents
```

对应的论文链接：

- 底座：[Transformer](https://arxiv.org/abs/1706.03762) → [BERT](https://arxiv.org/abs/1810.04805) → [GPT-3](https://arxiv.org/abs/2005.14165)
- 推理：[CoT](https://arxiv.org/abs/2201.11903) → [Self-Consistency](https://arxiv.org/abs/2203.11171) → [Tree of Thoughts](https://arxiv.org/abs/2305.10601)
- 工具行动：[MRKL](https://arxiv.org/abs/2205.00445) → [ReAct](https://arxiv.org/abs/2210.03629) → [Toolformer](https://arxiv.org/abs/2302.04761)
- Agent：[Reflexion](https://arxiv.org/abs/2303.11366) → [Plan-and-Execute](https://arxiv.org/abs/2305.04091) → [Generative Agents](https://arxiv.org/abs/2304.03442)

为什么这样排：

- **MRKL 放在 ReAct 前面**：先理解「LLM 当路由器、专家模块干活」的模块化思想，再看 ReAct 怎么把思考和行动交替起来。
- **Toolformer 放在 ReAct 后面**：ReAct 是推理时的循环，Toolformer 解决的是「模型怎么学会在合适的地方调工具」。
- **Reflexion 放在 Plan-and-Execute 前面**：先理解单轮失败后的反思，再看跨步骤的规划与重规划。
- **Generative Agents 最后读**：它把记忆、反思、计划组合成一个长期运行的完整系统，适合作为阶段总结。

## 论文清单

### 一、底座与范式（L1 模型与生成）

#### 1. [Attention Is All You Need](https://arxiv.org/abs/1706.03762)（2017）

- 作用：理解 Transformer，现代 LLM 的底座
- 核心机制：完全用 self-attention 替代 RNN/CNN，训练可以并行；多头注意力 + 位置编码 + 残差
- 读完能回答：self-attention 为什么能并行、Q/K/V 各自是什么、Transformer 为什么比 RNN 更适合长序列
- 关联：llm-foundations
- 状态：待读

#### 2. [BERT](https://arxiv.org/abs/1810.04805)（2018）

- 作用：理解预训练 / 微调范式
- 核心机制：双向 Transformer + 掩码语言模型（MLM）+ 下一句预测（NSP）；预训练一次，下游接一个任务头微调
- 读完能回答：预训练和微调各改什么、为什么双向、BERT 和 GPT 的训练目标差在哪
- 关联：llm-foundations
- 状态：待读

#### 3. [GPT-3](https://arxiv.org/abs/2005.14165)（2020）

- 作用：理解 few-shot / in-context learning
- 核心机制：175B 参数的自回归模型；不改权重，只在 prompt 里给 0 / 1 / K 个示例，分别叫 zero-shot / one-shot / few-shot。GPT-3 的 K 通常是 10–100，受 2048 context 限制
- 关键证据：CoQA F1 81.5 / 84.0 / 85.0；TriviaQA 64.3 / 68.0 / 71.2；few-shot 2 位加法 100%、3 位加法 80.2%、2 位乘法 29.2%；单词去随机插入字符 zero-shot 几乎不会、few-shot 66.9%
- 失败模式：ANLI、WiC、QuAC、RACE 等「比较 / 蕴含 / 长文阅读」任务接近随机；K 通常越大越好但不总是；论文没有定论 few-shot 是「从零学会」还是「识别出预训练见过的任务」
- **易混**：ML 里的 few-shot learning 通常指 meta-learning + 少量标注适应；GPT-3 的 few-shot 是纯前向的 in-context learning，不改权重。它也不是「用少量数据微调」
- 笔记：[few-shot 与 in-context learning](llm-foundations/README.md#few-shot-与-in-context-learning)
- 关联：llm-foundations
- 状态：已读（2026-11-11）

### 二、推理提示（L1 与 L4 之间）

这一组不是新模型，而是**改变模型怎么输出**的提示方法。它们说明：同一套权重，输出结构不同，推理效果会差很多。

#### 4. [Chain-of-Thought Prompting](https://arxiv.org/abs/2201.11903)（2022）

- 作用：理解多步推理提示
- 核心机制：在 few-shot 示例里，不只给「问题 → 答案」，而是给「问题 → 中间推理步骤 → 答案」；模型模仿示例格式，先输出推理再输出答案
- 关键证据：8 条手写推理示例；PaLM 540B 在 GSM8K 上 17.9% → 56.9%，GPT-3 175B 15.6% → 46.9%；PaLM 540B 在 StrategyQA 上 68.6% → 77.8%。能力随规模涌现，约 100B 以上才明显
- **易混**：`Let's think step by step` 出自 [Large Language Models are Zero-Shot Reasoners](https://arxiv.org/abs/2205.11916)（Kojima et al., 2022），是**零样本 CoT**，不是这篇。那篇用一句触发词，这篇用带推理过程的手写示例
- 三篇的关系：

  | 论文 | 做法 | 需要示例 |
  | --- | --- | --- |
  | CoT（本篇） | 示例里写推理链 | 需要，通常 8 条 |
  | [Zero-shot CoT](https://arxiv.org/abs/2205.11916) | 加一句 `Let's think step by step` | 不需要 |
  | [Self-Consistency](https://arxiv.org/abs/2203.11171) | 采样多条 CoT 路径并投票 | 需要，多次采样 |

- 怎么开启：CoT 不是 API 开关，而是提示方式。
  - 零样本：在 system 或 user prompt 里写「请一步一步思考，先写推理过程，最后一行输出『答案：X』」
  - few-shot：给 2–8 条「问题 → 推理步骤 → 答案」的示例，格式要和目标任务一致
  - 结构化输出：要求推理和最终答案分开，方便程序解析
  - 推理模型：能力已经训练进模型，通常不需要手动加「step by step」；Ollama 对支持 thinking 的模型提供 `think` 参数（布尔值或思考档位），模型本身不支持时无效。本地的 `qwen2.5` 没有 thinking 能力，只能靠 prompt
- 实践提醒：推理链不保证忠实，答案对不代表过程可信；简单任务加 CoT 可能更贵更差；小模型上收益有限甚至为负
- 本地实测（2026-11-11，`qwen2.5` 7.6B，同一道多步算术题）：直接回答得到 `35支`（错），提示推理得到 `49`（对）。单题只作演示，不代表普遍效果
- 读完能回答：CoT 为什么有效、为什么小模型上不灵、为什么说它是涌现能力、什么时候不该用 CoT
- 关联：llm-foundations
- 状态：待读

#### 5. [Self-Consistency](https://arxiv.org/abs/2203.11171)（2022）

- 作用：理解多路径采样与投票增强推理可靠性
- 核心机制：同一问题采样多条推理路径，对最终答案投票，取多数；用采样多样性换稳定性
- 读完能回答：为什么投票能提升准确率、采样温度和多路径数量怎么权衡、成本增加多少
- 关联：llm-foundations
- 状态：待读

#### 6. [Tree of Thoughts](https://arxiv.org/abs/2305.10601)（2023）

- 作用：理解搜索式推理和分支决策
- 核心机制：把推理组织成树；每一步生成多个候选，评估后保留有希望的分支，可以回溯
- 读完能回答：生成、评估、搜索三部分各做什么、ToT 和 CoT 的成本差多少、什么任务值得用搜索
- 关联：llm-foundations
- 状态：待读

### 三、工具与行动（L4 行为与编排）

#### 7. [ReAct](https://arxiv.org/abs/2210.03629)（2022）

- 作用：理解 reasoning + acting 的基本范式
- 核心机制：交替产生「思考 → 行动 → 观察」，行动调用外部工具，观察结果回到上下文，再继续思考
- 读完能回答：ReAct 循环由哪几步组成、它和纯 CoT 的区别、为什么观察结果必须回到上下文
- 关联：Agent（待建）
- 状态：待读

#### 8. [Toolformer](https://arxiv.org/abs/2302.04761)（2023）

- 作用：理解模型如何学习调用工具
- 核心机制：用自监督方式筛选「调用 API 后能降低预测损失」的位置，把 API 调用插入文本，再训练模型
- 读完能回答：工具调用的训练信号从哪来、模型如何决定何时调、推理时怎么触发调用
- 关联：Agent（待建）
- 状态：待读

#### 9. [MRKL Systems](https://arxiv.org/abs/2205.00445)（2022）

- 作用：理解模块化工具路由思想
- 核心机制：LLM 作为路由器，把请求分发给专家模块（计算器、数据库、检索器、符号推理器），再汇总结果
- 读完能回答：路由和端到端生成的区别、专家模块怎么组合、路由错了怎么办
- 关联：Agent（待建）
- 状态：待读

> 原清单缺少 10、11。这里保留编号空位，后续按原编号补入，不重排已有编号。

#### 12. [Reflexion](https://arxiv.org/abs/2303.11366)（2023）

- 作用：理解反思式 agent
- 核心机制：任务失败后，模型用语言总结失败原因，把反思写入记忆，下一轮带着反思重试；不更新权重
- 读完能回答：反思写什么、存在哪、下一轮怎么用、什么情况下反思会变成自我强化错误
- 关联：Agent（待建）
- 状态：待读

#### 13. Plan-and-Execute（2022–2023，类论文与实现）

这一项没有唯一原论文，按「先规划、再执行、必要时重规划」的思想，给三份代表材料：

- [Plan-and-Solve Prompting](https://arxiv.org/abs/2305.04091)
  - 在 prompt 里要求模型先制定计划，再按计划求解，适合零样本多步任务
- [LLM+P](https://arxiv.org/abs/2304.11477)
  - LLM 把自然语言问题转成 PDDL，交给经典规划器求最优计划，再翻译回自然语言执行
- [LangChain Plan-and-Execute 实现](https://www.langchain.com/blog/plan-and-execute-agents)
  - 工程实现：Planner 生成步骤列表，Executor 逐步执行，可根据结果重规划

读完能回答：计划和执行怎么分工、计划粒度多细、什么时候触发重规划、它和 ReAct 的取舍是什么

- 关联：Agent（待建）
- 状态：待读

#### 14. [Generative Agents](https://arxiv.org/abs/2304.03442)（2023）

- 作用：理解记忆、行为、长期模拟
- 核心机制：记忆流 + 检索 + 反思 + 计划；多个 agent 在虚拟小镇里按日程行动，产生可信的长期社会行为
- 读完能回答：记忆怎么存和检索、反思什么时候触发、计划怎么随环境变化调整、长期一致性靠什么维持
- 关联：Agent（待建）
- 状态：待读

## 进度总表

| # | 论文 | 年份 | 层 | 状态 |
| --- | --- | --- | --- | --- |
| 1 | [Attention Is All You Need](https://arxiv.org/abs/1706.03762) | 2017 | L1 | 待读 |
| 2 | [BERT](https://arxiv.org/abs/1810.04805) | 2018 | L1 | 待读 |
| 3 | [GPT-3](https://arxiv.org/abs/2005.14165) | 2020 | L1 | 已读 |
| 4 | [Chain-of-Thought Prompting](https://arxiv.org/abs/2201.11903) | 2022 | L1/L4 | 待读 |
| 5 | [Self-Consistency](https://arxiv.org/abs/2203.11171) | 2022 | L1/L4 | 待读 |
| 6 | [Tree of Thoughts](https://arxiv.org/abs/2305.10601) | 2023 | L1/L4 | 待读 |
| 7 | [ReAct](https://arxiv.org/abs/2210.03629) | 2022 | L4 | 待读 |
| 8 | [Toolformer](https://arxiv.org/abs/2302.04761) | 2023 | L4 | 待读 |
| 9 | [MRKL Systems](https://arxiv.org/abs/2205.00445) | 2022 | L4 | 待读 |
| 10 | 待补 | — | — | — |
| 11 | 待补 | — | — | — |
| 12 | [Reflexion](https://arxiv.org/abs/2303.11366) | 2023 | L4 | 待读 |
| 13 | [Plan-and-Execute（类）](https://arxiv.org/abs/2305.04091) | 2022–2023 | L4 | 待读 |
| 14 | [Generative Agents](https://arxiv.org/abs/2304.03442) | 2023 | L4 | 待读 |

状态用：`待读` / `在读` / `已读` / `待下钻`。

## 维护规则

- 新增论文必须写清：链接、年份、所属层、一句话作用、读完能回答的问题、关联 topic
- 链接优先用 arXiv abs 页面或官方论文页；不要用转载和二手解读
- 编号只增不改；原清单的空位保留，不因为补录而重排
- 读完一篇，更新「进度总表」和对应条目的状态，并在关联 topic 里留下结论
- 每季度复核一次链接是否失效、结论是否仍成立
