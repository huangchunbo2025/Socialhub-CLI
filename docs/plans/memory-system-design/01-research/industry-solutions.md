# AI 记忆系统业界方案调研

> 调研日期：2026-04-02  
> 适用项目：SocialHub CLI（本地 CLI 工具，Azure OpenAI，无服务器依赖）

---

## 主流方案对比表

| 方案 | 核心机制 | 存储方式 | 检索方式 | 优势 | 劣势 | 适用场景 |
|------|----------|----------|----------|------|------|----------|
| **Mem0** | 混合存储：向量 DB + KV + 图数据库；LLM 自动提炼事实 | Qdrant（默认）/ 24+ 向量库 + SQLite 审计 | 语义向量检索 | 精度高（比 OpenAI memory 高 26%）；90% token 节省 | 默认依赖向量数据库 | 云端多用户 AI 产品 |
| **MemGPT / Letta** | OS 分页：Core Memory（RAM）+ Recall + Archival（磁盘）；Agent 自驱动 tool call 管理 | 可配置外部存储 | Agent 主动调用 search_archival | 无限上下文；自管理能力强 | 运行开销大；过度设计 | 复杂长期对话 Agent |
| **Zep / Graphiti** | 时态知识图谱；动态合并结构化 + 非结构化数据 | 图数据库 + 向量搜索 | 图遍历 + 语义检索；sub-200ms | 精度提升 18.5%；延迟降低 90% | 依赖图数据库基础设施 | 企业级生产 Agent |
| **LangChain ConversationBufferMemory** | 原始对话历史全量传入 | 内存（可持久化） | 无检索，全量加载 | 实现极简；信息无损 | Token 线性增长；长对话溢出 | 短对话原型验证 |
| **LangChain ConversationSummaryMemory** | 每轮对话后 LLM 渐进摘要 | 内存 + 摘要字符串 | 无检索，摘要全量注入 | Token 增长受控 | 细节损失；额外 LLM 调用 | 中长对话 Chatbot |
| **ConversationSummaryBufferMemory** | 近期保留原文；超出阈值自动摘要 | 内存 | 混合加载 | 兼顾细节与 token 控制 | 需调参；无跨会话 | 单会话中长对话 |
| **文件型记忆（自定义）** | YAML/JSON/Markdown 分类存储；LLM 或规则提炼写入 | 本地文件（无依赖） | 按类别/时间规则检索 | 零依赖；完全可控；人类可读 | 无语义检索；需自行管理 | **本地 CLI 工具 ✓** |
| **SQLite + FTS5** | SQLite 内置 BM25 全文检索；可选 sqlite-vec 向量 | 单 .db 文件 | 关键词全文检索 | 单文件；Python 标准库 | 关键词不匹配召回率低 | 轻量本地工具 |

---

## 无向量数据库的轻量级方案

### 方案 A：结构化 YAML/Markdown 文件记忆（推荐基线）

```
~/.socialhub/memory/
├── user_profile.yaml        # 用户偏好（分析维度、输出格式、关注指标）
├── business_context.yaml    # 业务上下文（产品线、促销周期规律、基准值）
├── analysis_insights/       # 历史分析结论（按日期/主题归档）
│   └── 2026-04-01-gmv-trend.md
└── session_summaries/       # 历史会话摘要（LLM 自动生成）
    └── 20260401T200000-abc1.json
```

- `user_profile.yaml` + `business_context.yaml`：**全量注入**（~500-1000 tokens）
- `analysis_insights/`：按**时间范围**或**关键词**过滤后注入最近 N 条
- `session_summaries/`：注入**最近 5 条**（滑动窗口）

**优势**：零依赖，Python 标准库，人类可读，支持 git 版本控制。

### 方案 B：SQLite + FTS5 全文检索

使用 SQLite 内置 FTS5（BM25）引擎，Python `sqlite3` 标准库内置，单文件部署。支持结构化过滤 + 全文检索联合查询。适合记忆量大（>1000 条）时的检索需求。

### 方案 C：bm25s 轻量语义检索

`bm25s` 包（纯 Python，无 C 依赖）可在本地文件上构建 BM25 索引，实现近似语义检索，无需向量数据库。

---

## Token 预算管理最佳实践

**关键研究发现**：即使是 1M tokens 容量的模型，在 50K tokens 时也已出现"context rot"（上下文质量退化）。

### 分层预算模型（128K context 示例）

```
固定层        ~2,000 tokens
├── 角色定义 + 工具说明
└── 核心记忆（用户画像 + 业务上下文）：~1,000 tokens

动态记忆层    ~3,000-5,000 tokens
├── 相关历史分析结论：~2,000 tokens（最多 5 条）
└── 近期会话摘要：~1,000 tokens（最近 3 条）

当前会话历史  ~10,000 tokens（滑动窗口 max_history=10）

模型输出保留  ~8,000 tokens
```

### 核心策略

1. **分层固定 + 动态预算**：核心记忆固定注入上限 1000 tokens，动态记忆设上限 3000 tokens
2. **滑动窗口**：只保留最近 K=10 轮对话原文，旧对话触发摘要
3. **渐进式摘要**：每 N 轮或 token 阈值触发 LLM 摘要，Token 增长从线性变对数级
4. **tiktoken 主动计数**：每次请求前精确计数，设置 70% 阈值告警
5. **定期清理**：时间 > 90 天且无引用的低价值记忆定期归档/删除

---

## 记忆摘要提取策略

| 策略 | 机制 | 优势 | 劣势 | 适用 |
|------|------|------|------|------|
| **LLM 渐进摘要** | 会话结束后调用 LLM 生成结构化摘要 | 质量高；捕捉隐性偏好 | 额外 LLM 调用成本 | 质量要求高的长期记忆 |
| **规则提取** | 正则/关键词匹配提取固定字段 | 零成本；确定性强 | 灵活性差 | 结构化偏好字段 |
| **LLM 事实提炼（Mem0 模式）** | 每轮对话后提炼增量事实 | 粒度细；实时更新 | 高频调用；成本高 | 云端高频产品 |
| **混合策略** | 规则提取固定字段 + LLM 摘要自由文本 | 兼顾成本和质量 | 实现复杂度中等 | **SocialHub CLI（推荐）** |

### SocialHub CLI 推荐：会话结束批量提炼

**时机**：每次会话结束时触发 1 次 LLM 调用（成本极低），提炼结构化 JSON：

```json
{
  "user_preferences_update": {
    "default_period": "7d",
    "preferred_dimensions": ["channel"],
    "output_format": "table"
  },
  "business_insights": [
    {"date": "2026-04-01", "topic": "GMV趋势", "conclusion": "渠道A贡献占比上升至60%"}
  ],
  "business_context_updates": {
    "peak_season": "Q4"
  },
  "session_summary": "用户分析了过去7天渠道GMV，发现渠道A增长显著"
}
```

---

## 推荐方向

**SocialHub CLI 最优方案：混合文件型记忆**

| 层次 | 实现 | 职责 |
|------|------|------|
| 存储层 | YAML + JSON 文件（本地文件系统） | 持久化用户画像、业务上下文、分析结论、会话摘要 |
| 检索层 | pathlib + yaml + 时间/标签过滤 | 固定记忆全量加载；历史结论按时间/关键词过滤 |
| 提炼层 | 会话结束 LLM 批量提炼（JSON structured output） | 自动更新偏好、归档结论、生成摘要 |
| 注入层 | tiktoken 预算控制；分层注入到 SYSTEM_PROMPT | 固定层 ~1000 tokens + 动态层 ~3000 tokens |

**技术选型**：PyYAML + pathlib（零额外依赖）+ tiktoken（Token 计数）+ Azure OpenAI（摘要提炼）

**不推荐**：Mem0（默认需向量库）、Zep（需图数据库）、MemGPT（CLI 工具过度设计）

---

## 来源 URL

- https://github.com/mem0ai/mem0
- https://docs.mem0.ai/introduction
- https://arxiv.org/abs/2310.08560 (MemGPT)
- https://www.letta.com/blog/agent-memory
- https://www.pinecone.io/learn/series/langchain/langchain-conversational-memory/
- https://www.getzep.com/
- https://arxiv.org/abs/2501.13956 (Zep/Graphiti)
- https://dev.to/iniyarajan86/building-persistent-ai-agent-memory-systems-that-actually-work-463o
- https://blog.langchain.com/context-engineering-for-agents/
- https://blog.jetbrains.com/research/2025/12/efficient-context-management/
