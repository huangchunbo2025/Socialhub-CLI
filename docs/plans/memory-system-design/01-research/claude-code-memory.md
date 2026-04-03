# Claude Code 记忆系统分析

> 调研日期：2026-04-02  
> 来源：本机文件扫描 + 官方文档 + 源码分析

---

## 实际文件结构（本机扫描）

```
~/.claude/projects/C--Users-86185/memory/
├── MEMORY.md                     # 索引文件（自动注入 system prompt，前 200 行）
├── project_m365_agent.md         # type: project
└── feedback_asyncio_patterns.md  # type: feedback
```

### 实际 frontmatter 格式

```yaml
---
name: M365 Declarative Agent 集成
description: SocialHub MCP Server M365 Copilot 集成，HTTP Transport + API Key 认证 + Teams App 包
type: project
---
```

### feedback 类型结构
```markdown
---
name: asyncio 中同步阻塞调用的处理模式
description: 在 async lifespan/context 中调用同步阻塞函数必须用 asyncio.to_thread()
type: feedback
---

规则正文...

**Why:** 具体原因（事故/强偏好）
**How to apply:** 何时/何处触发此规则
```

### MEMORY.md 索引格式
```markdown
# Memory Index

## Project
- [file.md](file.md) — 一行 hook（≤150 字符）

## Feedback
- [file.md](file.md) — 一行 hook
```

---

## 设计哲学提炼

| 原则 | 描述 |
|------|------|
| **记忆是行为指导，非历史档案** | 记忆的目的是改变 AI 未来的行为，不是记录过去发生了什么 |
| **Why 是核心** | 每条 feedback/project 记忆必须有 Why 字段，让未来判断边界情况 |
| **明确不记录什么** | 代码模式、git 历史、文件路径、架构快照 — 这些从代码推导更准确 |
| **短期 vs 长期分离** | task/plan 用于当前对话追踪；memory 只存跨对话有价值的信息 |
| **索引 + 内容分离** | MEMORY.md 是轻量索引（200 行限制），内容在独立文件中 |
| **人类可读** | 纯 Markdown，可 git 版本控制，人工可直接编辑 |
| **主动写入** | AI 在对话中识别到值得记录的信息后主动写入，不是被动记录 |

---

## 类型分类设计的价值

| 类型 | 用途 | 加载策略 |
|------|------|---------|
| **user** | 用户角色、技能水平、偏好 → 调整响应风格 | 始终加载 |
| **feedback** | 行为规则（避免/重复某种做法） → 改变操作方式 | 始终加载 |
| **project** | 项目状态、决策、里程碑 → 提供上下文 | 始终加载（time-decay 适用） |
| **reference** | 外部资源指针（URL/工具/文档路径） → 知道去哪找 | 按需加载 |

**关键设计**：4 种类型对应 4 种不同的"行为影响方式"，不是按内容主题分类。

---

## MEMORY.md 索引机制

**加载方式**（源码发现）：
- 文件路径硬编码：`var U_ = "MEMORY.md"`
- 注入行数上限：`pZ = 200`
- **注入位置**：system prompt（非 user message）
- 超过 200 行的内容被截断，**不报错**

**安全更新**（v2.1.50）：
- 记忆文件从 system prompt 位置移除以降低 prompt injection 风险
- 改为特定的内存隔离区域注入

**子 Agent 记忆作用域**：
- `user` 级：`~/.claude/agent-memory/<name>/`（跨项目）
- `project` 级：`.claude/agent-memory/<name>/`（项目内）
- `local` 级：`.claude/agent-memory-local/<name>/`（本地不提交）

---

## 与 SocialHub 业务场景的对比

| 维度 | Claude Code 记忆系统 | SocialHub CLI 需求 |
|------|---------------------|-------------------|
| **用户数量** | 单用户 | 单用户（CLI 本地）|
| **记忆主体** | 开发者偏好 + 代码库上下文 | 运营偏好 + 业务数据上下文 |
| **时效性** | 大多数记忆长期有效 | 业务洞察有时效性（趋势会变）|
| **写入触发** | AI 主动识别 | AI 主动 + 会话结束自动提炼 |
| **检索策略** | 全量注入（200 行）| 需要按相关度选择性注入 |
| **类型分类** | user/feedback/project/reference | 需要额外：business_context/insight/preference |
| **PII 要求** | 开发者 context 无 PII | 业务数据含 PII，需脱敏层 |
| **团队共享** | 项目级 memory 可 git 共享 | 同样可用文件 + git 实现团队共享 |
| **TTL** | 无 TTL（手动管理） | 业务洞察需 TTL（30-90 天）|

---

## 可借鉴的设计模式

1. **MEMORY.md 索引 + 独立内容文件**的双层结构 → 索引快速加载，内容按需读取
2. **frontmatter 元数据**（name/description/type）→ 支持程序化过滤和分类加载
3. **Why + How to apply 结构** → 确保记忆在边界情况下可判断
4. **明确排除清单** → 防止记忆系统膨胀成无用信息垃圾桶
5. **主动写入触发机制** → AI 对话结束时判断是否值得写入，而非盲目全记
6. **跨项目 vs 项目内** → user 级偏好跨项目有效；business context 项目内有效

---

## 来源 URL

- Claude Code 官方文档: https://docs.anthropic.com/en/docs/claude-code/memory
- Claude Code Sub-agents 文档: https://docs.anthropic.com/en/docs/claude-code/sub-agents
- Claude Code v2.1.50 更新日志（安全修复）
