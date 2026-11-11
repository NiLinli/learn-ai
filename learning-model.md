# 学习模型：为什么这样组织这个工程

这份文档记录 `AGENTS.md` 里四条学习规则的依据。规则本体保持简短、可执行；这里解释**为什么**是这四条，以及它们各自对应哪些认知科学、软件工程和知识管理的研究。

## 一句话结论

程序员日常面对的多数细节，属于 Brooks 所说的 **偶发复杂度（accidental complexity）**；AI 把获取这类细节的边际成本压到接近零。真正稀缺的是 **本质复杂度（essential complexity）**：问题定义、抽象边界、权衡和验证。

专家研究也表明，专家的优势不在记忆量，而在**知识的组织方式**。所以「自顶向下、概念优先」不是偷懒，而是把有限的学习时间投向迁移性更高的部分。

## 规则 1：Topic 按知识依赖排序

### 依据

- **Knowledge Space Theory**（Doignon & Falmagne, 1985）用偏序关系描述知识状态与前置依赖：某些知识必须先掌握，另一些才能被理解。它给「topic 依赖图」提供了一个形式化模型。
- **学习进阶（learning progressions）** 研究（Heritage, 2008）主张把学习目标拆成有先后关系的阶梯，而不是一堆并列主题。
- **门槛概念（threshold concepts）**（Meyer & Land, 2003）指出，少数概念会改变整个领域的理解方式；识别它们，并放在合适的顺序上，比平均用力更重要。

### 对应的工程做法

- 每个 topic 声明层级、前置、后续、核心问题和边界。
- 索引按阶段排序，不按创建时间或热度排序。
- 允许跳学，但必须补前置的最小集，并记录跳学路径。
- 互相依赖时，把共享概念下沉到更基础的 topic，避免循环依赖。

## 规则 2：新 Topic 先做归属判定

### 依据

- **概念图（concept maps）**（Novak & Gowin, 1984）强调知识应按层级和交叉关系组织；新节点要么挂在已有节点下，要么明确说明为什么需要一个新的根。
- **门槛概念**同样适用于边界判断：真正需要独立 topic 的，通常是引入了新的抽象层或新的「门槛」；只是换了一个实现或工具，通常属于已有 topic。
- 这条规则同时是对 **topic 蔓延**的约束。每出现一个新名词就新建目录，会让索引失去结构，也让前置关系无法维护。

### 对应的工程做法

新建一级 topic 前回答四个问题：

1. 核心问题是否已被现有 topic 覆盖？
2. 是否引入了新的抽象层，或需要独立的实验与证据？
3. 是否会改变现有 topic 的结论或边界？
4. 它是新方向，还是现有方向的新实现？

默认归入现有 topic 的子目录；只有同时满足「新抽象层 + 独立证据 + 不改变父 topic 核心结论」才建一级 topic。新的发展方向先进入 `ai-map` 的「观察中」列表，稳定后再升级为 topic。

## 规则 3：概念先行，证据落地

这是「抽象很重要」的正式表述。它由三部分组成：地图层、机制层、证据层。

### 依据

- **Brooks,《No Silver Bullet》(1986)**：软件的大部分细节是偶发复杂度，来自工具、语言和实现；本质复杂度来自问题本身。AI 大幅降低了偶发复杂度的获取成本，人的价值上移到问题定义、边界判断和权衡。
- **Chi, Feltovich & Glaser (1981)**：专家按深层原理（如能量守恒）组织物理问题，新手按表面特征（如斜面、弹簧）组织。抽象不是专家的副产品，而是专家之所以成为专家的原因。
- **Sweller 的认知负荷理论（1988）** 与 **Miller (1956)、Chase & Simon (1973) 的组块研究**：工作记忆容量有限；schema 和组块把多个细节压成一个可操作单元，从而释放认知资源。抽象的作用，是降低「同时要记住的东西」的数量。
- **Ausubel 的先行组织者（1960）** 与 **Bruner 的螺旋课程（1960）**：先给认知框架，再逐层深入；同一概念可以在更高层级反复回来。这直接对应「先地图、后机制、再证据」。
- **Bransford 等《How People Learn》(2000)**：迁移依赖概念框架，不依赖零散事实。学得深不等于记得多，而是能在新情境中调用正确的结构。
- **Risko & Gilbert 的认知外包（cognitive offloading, 2016）**：人会把记忆和检索外包给外部工具。AI 让这种外包变得极其便宜，但判断、验证和责任不能一起外包。
- **反向约束：Ericsson 的刻意练习（1993）与 Bjork 的「合意困难」**：抽象必须经过具体练习、检索和反馈，否则只是名词堆砌。这就是为什么规则 3 要求「证据层」，而不是只写概念。

### 对应的工程做法

- **地图层**：这个知识在架构图的哪一层、解决什么问题、边界在哪、和哪些概念容易混。
- **机制层**：关键输入输出、状态变化、失败模式、设计取舍；能用白话说清「为什么这样设计」。
- **证据层**：至少一个可复现的证据——真实 payload、最小 demo、实验数据或代码路径。
- 细节按需下钻；暂时不学的细节记为「待下钻」，并写明触发条件。
- 验收标准是能解释现象、能预测结果、能定位问题、能迁移，不是读了多少文档。
- AI 负责检索、对比、生成初稿；问题定义、边界判断、验证和取舍由人负责。

## 规则 4：维护 AI 学习架构图

### 依据

- **抽象泄漏（Spolsky, 2002）**：所有非平凡的抽象都会泄漏。边界不是一次画完就固定的，必须持续观察哪里漏了、哪里被替换了。
- **Wardley Map**（Simon Wardley）：把组件放在「 Genesis → 自定义 → 产品 → 商品/基础设施」的演化轴上，能看清能力如何 commoditize、价值如何沿价值链上移。这正好解释「LLM 在吃 agent 开发」：通用编排和协议细节被模型/运行时吸收，应用层的价值上移到领域工作流、权限责任和评测。
- **门槛概念与学习进阶**：边界变化会改变学习顺序。原来属于应用层的知识，可能因为被吸收而不再值得深入；原来边缘的概念，可能因为成为瓶颈而升级为核心。

### 对应的工程做法

- 维护 `ai-map/`：分层图、能力边界表、时间线、变更记录。
- 每个 topic 声明自己在图中的层级和边界。
- 时间线只记已发布、可验证的能力；预测单列「观察中」。
- 每季度做一次边界复盘，检查哪些「应用层能力」已经被吸收。

## 口语版 → 规则版

| 口语表达 | 规则化表述 |
| --- | --- |
| 知识细节学不完 | 学习以可迁移的概念框架和问题求解能力为主，细节按任务需要下钻 |
| 知道一些概念、会解决问题更重要 | 先建立领域地图和依赖关系，再进入机制与实现；每个抽象需落到可验证证据 |
| 自顶向下更有效 | 地图层 → 机制层 → 证据层；允许跳学，但必须补前置的最小集 |
| 有了 AI 之后更是如此 | 把记忆和检索委托给工具，把时间投向问题定义、边界判断、验证与迁移 |

## 三条使用原则

1. **抽象不是跳过细节，而是给细节一个位置。** 没有位置的细节是噪音，有位置的细节才是知识。
2. **每个抽象至少有一个具体锚点。** 一个真实 payload、一次实验、一段代码路径，都能防止抽象退化成名词。
3. **能用 AI 查到的，不背；不能外包的，练。** 检索、对比、初稿可以外包；判断、验证、取舍和责任感必须自己建立。

## 参考资料

- Brooks, F. P. (1986). *No Silver Bullet: Essence and Accidents of Software Engineering*.
- Chi, M. T. H., Feltovich, P. J., & Glaser, R. (1981). Categorization and representation of physics problems by experts and novices. *Cognitive Science*.
- Sweller, J. (1988). Cognitive load during problem solving: Effects on learning. *Cognitive Science*.
- Miller, G. A. (1956). The magical number seven, plus or minus two. *Psychological Review*.
- Chase, W. G., & Simon, H. A. (1973). Perception in chess. *Cognitive Science*.
- Ausubel, D. P. (1960). The use of advance organizers in the learning and retention of meaningful verbal material. *Journal of Educational Psychology*.
- Bruner, J. S. (1960). *The Process of Education*.
- Bransford, J. D., Brown, A. L., & Cocking, R. R. (Eds.). (2000). *How People Learn*.
- Doignon, J.-P., & Falmagne, J.-C. (1985). Spaces for the assessment of knowledge. *International Journal of Man-Machine Studies*.
- Meyer, J. H. F., & Land, R. (2003). *Threshold Concepts and Troublesome Knowledge*.
- Risko, E. F., & Gilbert, S. J. (2016). Cognitive offloading. *Trends in Cognitive Sciences*.
- Ericsson, K. A., Krampe, R. T., & Tesch-Römer, C. (1993). The role of deliberate practice in the acquisition of expert performance. *Psychological Review*.
- Bjork, R. A., & Bjork, E. L. (2011). Making things hard on yourself, but in a good way: Creating desirable difficulties to enhance learning.
- Spolsky, J. (2002). The Law of Leaky Abstractions.
- Wardley, S. (2016). *Wardley Maps*.

## 和 AGENTS.md 的关系

`AGENTS.md` 是执行入口：新增 topic、排序、写笔记时按那里的规则做。这份文档是解释层：当规则看起来像个人偏好时，回来看看它对应的研究与实践依据。
