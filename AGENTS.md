# AGENTS.md

## 工程定位

这是一个 **AI 知识学习工程**，不是产品代码库。目标是把想了解的 AI 主题逐个拆成独立目录，边学边留下可复用的笔记、实验和结论。

学习方式遵循「概念先行、证据落地」：先建立领域地图和边界，再进入机制与实现，每个抽象至少落到一个可复现的证据上。规则背后的依据见 [learning-model.md](learning-model.md)。

## 目录约定

- **一级子目录 = 一个 topic**。每个目录代表一个想深入了解的主题（如 `llm-eval`、`rag`、`agent`）。
- 目录名用简短的 kebab-case 英文，语义明确；不要用 `tmp`、`test`、`notes1` 这类无意义名字。
- 每个 topic 目录以 `README.md` 作为入口，至少写清三件事：
  - 这个 topic 想解决/搞清楚什么问题
  - 当前的问题清单与学习路径
  - 已得出的结论、待验证的假设
- 每个 topic 的 `README.md` 顶部必须有「定位」段：层级、前置、后续、负责范围、不负责范围，并链接到 `ai-map/README.md`。
- 目录内部结构自由（笔记、代码 demo、图表、数据集都可以），但产物要能被单独看懂，不依赖对话上下文。
- 跨 topic 的元文档不参与 topic 编号：
  - [ai-map/](ai-map/)：AI 学习架构图、能力边界、时间线、变更记录
  - [learning-model.md](learning-model.md)：学习规则的理论依据
  - [papers.md](papers.md)：跨 topic 的论文阅读索引与进度
- 新增、重命名或删除 topic 时，**同步更新下面的索引表与 `ai-map/README.md`**。

## 学习路径与 Topic 规则

### 规则 1：Topic 按知识依赖排序

- 每个 topic 必须声明：层级、前置 topic、后续 topic、核心问题、边界。
- 本文件的索引按阶段排序，不按创建时间或热度排序。
- 允许因工作需要跳学，但必须先补前置的最小集，并在 topic 内记录跳学路径。
- topic 之间出现循环依赖时，将共享概念下沉到更基础的 topic，或拆出独立的基础 topic。

### 规则 2：新 Topic 先做归属判定

- 创建一级 topic 前，必须完成归属判定并取得确认。判定问题：
  1. 核心问题是否已被现有 topic 覆盖？
  2. 是否引入新的抽象层，或需要独立的实验与证据？
  3. 是否会改变现有 topic 的结论或边界？
  4. 它是新方向，还是现有方向的新实现？
- 默认归入现有 topic 的子目录；只有同时满足「新抽象层 + 独立证据 + 不改变父 topic 核心结论」才创建一级 topic。
- 新方向先写入 `ai-map/README.md` 的「观察中」，有稳定证据后再升级为 topic。
- 归属结论写入新 topic 的「定位」段，说明「为什么不是 X 的一部分」。

### 规则 3：概念先行，证据落地

- 每个 topic 按三层组织：
  1. **地图层**：在 `ai-map` 中的层级、解决的问题、边界、易混概念。
  2. **机制层**：输入输出、状态变化、失败模式、设计取舍。
  3. **证据层**：至少一个可复现证据（真实 payload、最小 demo、实验数据或代码路径）。
- 细节按需下钻；暂不学习的细节记为「待下钻」，并写明触发条件。
- 验收标准：能解释现象、能预测结果、能定位问题、能迁移；不以阅读量或覆盖率衡量。
- AI 可用于检索、对比、生成初稿；问题定义、边界判断、验证与取舍由人负责。
- 抽象必须至少有一个具体锚点，避免名词堆砌。

### 规则 4：维护 AI 学习架构图

- [ai-map/](ai-map/) 维护分层图、能力边界表、时间线、变更记录。
- 每个 topic 的 `README.md` 必须有「定位」段，声明层级与边界，并链接 `ai-map/README.md`。
- 触发更新：新增/重命名/合并/拆分 topic；新能力改变边界；季度复盘。
- 时间线只记录已发布、可验证的能力；预测与传闻单列「观察中」，标注所需证据与复核日期。
- 每次更新在「变更记录」追加：日期 / 变化 / 影响层与 topic / 证据 / 状态。

## 学习路径与索引

按知识依赖排序。状态用：`调研中` / `实验中` / `已沉淀`；尚未创建的 topic 标为 `待调研`。

| 阶段 | 层级 | Topic / 模块 | 前置 | 状态 | 一句话说明 |
| --- | --- | --- | --- | --- | --- |
| 0 | L0 基础 | [math-foundations](math-foundations/) | — | 实验中 | 余弦相似度：向量、点积、归一化；用 RAG demo 的真实分数做验算。概率与硬件仍待调研，只在上层现象需要解释时下钻 |
| 1 | L1 模型与生成 | [llm-foundations](llm-foundations/) | — | 已沉淀 | LLM 前置概念：ML 范式、生成式 AI、模型静态/运行时、token 生成与向量、few-shot / in-context learning，配四张概念区分图 |
| 1.5 | L1/L4 | [llm-foundations/cot-demo](llm-foundations/cot-demo/)（子模块） | llm-foundations | 实验中 | CoT 对照实验：同一模型的直接回答、零样本 CoT、few-shot CoT 原始输出与差异 |
| 1.6 | L1/L2 | [llm-foundations/thinking-demo](llm-foundations/thinking-demo/)（子模块） | llm-foundations | 实验中 | thinking 模型：`think` 开关、`message.thinking` / `content` 分离、流式相位、Engine 原始 `<think>` delta |
| 2 | L2 推理与服务 | [llm-serving-pipeline](llm-serving-pipeline/) | llm-foundations | 已沉淀 | 推理服务流水线：模型文本如何经 Renderer/Engine/Parser/Assembler/Encoder 变成 NDJSON |
| 3 | L3 知识与上下文 | `llm-foundations/rag-demo/`（子模块） | llm-foundations | 已沉淀 | 最小 RAG：BM25 与向量两版检索，观察检索片段如何进入 prompt |
| 4 | L4 行为与编排 | Agent（待建） | L2 + L3 | 待调研 | agent loop、planning、工具调用、MCP、多智能体 |
| 5 | L5 应用与治理 | Eval / observability（待建） | L4 | 待调研 | 评测、可观测性、安全、成本与用户体验 |

## Agent 协作约定

- 修改某个 topic 时，只动该目录内的内容；跨 topic 的改动先说明原因。
- 在这个工程里做讲解或写笔记时，默认按以下方式输出：
  - 先说明概念在 `ai-map` 的哪一层、解决什么问题、边界在哪（地图层）
  - 再给可操作的**具体步骤**，并说明每一步**为什么**要这么做（机制层）
  - 最后配**真实证据**：可复现脚本、真实 payload 或实验数据（证据层）
  - 用**工程类比**解释概念（例如 score config ≈ 一把尺子的定义，session ≈ 一个 conversation id）
- 讨论模块关联或边界变化时，先更新或引用 [ai-map/README.md](ai-map/README.md)，再写文字说明。
- 新增的代码示例、实验脚本、demo 统一用 **Python**；存量内容不因为语言偏好回改。
- 不写空泛的模板化内容；概念、结论要能落到具体文件或实验里。

## 维护说明

本文件是工程的长期约定入口。后续出现新的目录规范、命名约定、学习偏好或协作方式，及时补充到这里，并保持内容简短、可执行。修改学习规则时，同步检查 [learning-model.md](learning-model.md) 与 [ai-map/README.md](ai-map/README.md) 是否需要更新。
