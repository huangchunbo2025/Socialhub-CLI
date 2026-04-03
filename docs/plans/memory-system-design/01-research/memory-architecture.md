# 记忆架构范式研究

> 调研日期：2026-04-02  
> 来源：23 篇技术文献

---

## 向量记忆 vs 结构化记忆对比

| 维度 | 向量语义记忆 | 结构化记忆（JSON/YAML/Markdown）|
|------|------------|-------------------------------|
| **检索精度** | 语义相似度；能找到"意思相近"的记忆 | 精确匹配；关键词/标签/时间过滤 |
| **基础设施依赖** | 需向量数据库（Qdrant/Chroma/Pinecone）| 本地文件（零依赖）|
| **写入成本** | 每条记忆需 embedding 调用 | 直接写文件，零 API 调用 |
| **可读性** | 无法直接阅读向量 | 人类可读，可直接编辑 |
| **更新策略** | 需重新 embedding | 直接修改文件 |
| **版本控制** | 不适合 git | 天然适合 git |
| **适合场景** | 大量非结构化记忆（>1000 条）| 分类明确的结构化偏好和结论（<500 条）|
| **SocialHub 适用** | ❌ 过度设计，无向量 DB | ✅ 完全满足需求 |

**结论**：SocialHub CLI 记忆量有限（用户偏好<50条，业务洞察<200条），结构化文件完全够用。

---

## 无向量数据库的检索策略

### 策略 1：BM25S 关键词语义检索（主策略）

```python
import bm25s

# 构建索引
corpus = [insight.content for insight in insights]
retriever = bm25s.BM25()
retriever.index(bm25s.tokenize(corpus))

# 查询
results = retriever.retrieve(bm25s.tokenize([query]), k=5)
```

**优势**：`bm25s` 纯 Python，无 C 依赖，pip 安装即用，性能接近向量检索。

### 策略 2：规则精确匹配（偏好层）

```python
# 直接结构化访问，无需检索
profile = yaml.safe_load(open("user_profile.yaml"))
default_period = profile["analysis"]["default_period"]  # "7d"
```

用户偏好是结构化的，直接按字段访问，无需检索。

### 策略 3：时间衰减过滤（洞察层）

```python
# 近期洞察权重更高
cutoff = datetime.now() - timedelta(days=30)
recent_insights = [i for i in insights if i.date > cutoff]
# 超出 token 预算时，按时间倒序截断
recent_insights = sorted(recent_insights, key=lambda x: x.date, reverse=True)[:5]
```

### 策略 4：标签索引（分类层）

```python
# 按主题标签快速过滤
topic_insights = [i for i in insights if query_topic in i.tags]
```

---

## 四层记忆架构（借鉴认知科学）

```
┌─────────────────────────────────────────────┐
│  L1: Working Memory（工作记忆）             │  ← 当前会话 session.messages
│  容量：当前对话历史（max_history=10）        │
│  TTL：会话结束即清                          │
├─────────────────────────────────────────────┤
│  L2: Episodic Memory（情节记忆）            │  ← session_summaries/
│  容量：最近 30 条会话摘要                   │
│  TTL：30 天，自动清理                       │
├─────────────────────────────────────────────┤
│  L3: Semantic Memory（语义记忆）            │  ← analysis_insights/
│  容量：结构化业务洞察（无数量上限）          │
│  TTL：90 天（降权），1 年（归档）            │
├─────────────────────────────────────────────┤
│  L4: Procedural Memory（程序性记忆）        │  ← user_profile.yaml + business_context.yaml
│  容量：用户偏好 + 业务上下文（~50 条记录）  │
│  TTL：永久（手动更新）                      │
└─────────────────────────────────────────────┘
```

### 各层 JSON Schema

**L4 - user_profile.yaml**
```yaml
version: "1.0"
updated_at: "2026-04-01T20:00:00Z"
analysis:
  default_period: "7d"
  preferred_dimensions: ["channel", "category"]
  key_metrics: ["gmv", "orders", "conversion_rate"]
  rfm_focus: ["Champions", "At-Risk"]
output:
  format: "table"          # table | json | csv
  precision: 1             # 小数位数
  show_yoy: true           # 是否显示同比
scope:
  channels: []             # [] = 全部
  provinces: []
role: "operations"         # operations | analyst | marketing
```

**L3 - analysis_insights/{date}-{slug}.json**
```json
{
  "id": "2026-04-01-channel-gmv",
  "date": "2026-04-01",
  "topic": "渠道GMV分析",
  "tags": ["channel", "gmv", "trend"],
  "conclusion": "天猫渠道GMV占比从45%上升至60%，主要来自会员复购",
  "data_period": "2026-03-01~2026-03-31",
  "confidence": "high",
  "source_session": "20260401T200000-abc1"
}
```

**L2 - session_summaries/{session_id}.json**
```json
{
  "session_id": "20260401T200000-abc1",
  "date": "2026-04-01",
  "summary": "分析了3月渠道GMV，发现天猫增长显著，并导出了月报",
  "commands_used": ["analytics overview", "analytics orders --by=channel"],
  "insights_generated": ["2026-04-01-channel-gmv"]
}
```

---

## 记忆压缩与摘要策略

| 策略 | 触发时机 | 实现 | 成本 |
|------|---------|------|------|
| **会话结束摘要** | 会话正常结束时 | 1 次 LLM 调用，structured output | 低（每会话1次）|
| **重要性评分** | 写入洞察时 | 规则评分（命令种类 + 用户确认 + 执行成功）| 零 LLM |
| **滑动窗口清理** | 每次启动时 | 删除 TTL 过期文件 | 零成本 |
| **层次化压缩** | 每月一次（可选）| 将 30 条旧洞察压缩为 1 条月度摘要 | 中（1次/月）|

### 会话结束摘要 Prompt 模板

```python
MEMORY_EXTRACTION_PROMPT = """
分析以下对话，提取值得长期记忆的信息，以 JSON 格式输出：

{conversation_history}

输出格式：
{
  "user_preferences_update": {
    // 发现的新偏好，只包含明确表达的，不要推测
  },
  "business_insights": [
    {"topic": "...", "conclusion": "...", "tags": [...]}
    // 只包含有业务价值的结论性发现
  ],
  "session_summary": "一句话总结（不超过50字）",
  "nothing_to_save": false  // 如果对话无记忆价值则为 true
}
"""
```

---

## Token 预算分配建议

### 标准场景（gpt-4o，128K context）

| 层次 | Token 预算 | 内容 |
|------|-----------|------|
| 系统角色定义 | ~500 | 固定 |
| L4 程序性记忆 | ~1,000 | user_profile + business_context 全量 |
| L3 语义记忆（动态）| ~2,000 | 最相关的 3-5 条洞察 |
| L2 情节记忆（动态）| ~1,000 | 最近 3 条会话摘要 |
| L1 工作记忆 | ~8,000 | 当前会话 10 轮历史 |
| 输出保留 | ~8,000 | 模型回复空间 |
| **总计** | **~20,500** | 留有充足余量 |

### 受限场景（gpt-3.5-turbo，16K context）

| 层次 | Token 预算 |
|------|-----------|
| 系统角色 + L4 | ~1,200 |
| L3 动态（精简到 2 条）| ~800 |
| L2 动态（精简到 1 条）| ~400 |
| L1 工作记忆（5 轮）| ~4,000 |
| 输出保留 | ~4,000 |
| **总计** | **~10,400** |

---

## SocialHub 推荐架构

```
cli/memory/
├── __init__.py
├── manager.py          # MemoryManager：统一入口，协调所有层
├── store.py            # 文件存储：读写 YAML/JSON/Markdown
├── retriever.py        # 检索：时间过滤 + BM25S（可选）+ 标签索引
├── extractor.py        # 会话结束摘要提炼（LLM structured output）
├── injector.py         # SYSTEM_PROMPT 动态构建，tiktoken 预算控制
└── models.py           # Pydantic 数据模型（UserProfile/BusinessContext/Insight）
```

**写入流程**：
```
会话结束
  → extractor.py 调用 LLM 提炼 JSON
  → store.py 更新 user_profile.yaml（合并偏好）
  → store.py 追加 analysis_insights/{date}-{slug}.json
  → store.py 追加 session_summaries/{session_id}.json
```

**读取流程**：
```
会话开始
  → store.py 加载 user_profile.yaml + business_context.yaml（全量）
  → retriever.py 按时间/标签过滤最近洞察（最多 5 条）
  → retriever.py 加载最近 3 条会话摘要
  → injector.py tiktoken 计数 → 构建动态 SYSTEM_PROMPT 注入
```

---

## 来源 URL

- https://arxiv.org/abs/2310.08560 (MemGPT 论文)
- https://www.letta.com/blog/agent-memory
- https://blog.langchain.com/context-engineering-for-agents/
- https://www.getmaxim.ai/articles/context-window-management-strategies-for-long-context-ai-agents-and-chatbots/
- https://github.com/bm25s/bm25s
- https://blog.jetbrains.com/research/2025/12/efficient-context-management/
- https://dev.to/iniyarajan86/building-persistent-ai-agent-memory-systems-that-actually-work-463o
