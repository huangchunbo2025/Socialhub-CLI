# Goal: SocialHub CLI 记忆系统升级设计

## 目标本质

研究并比较两套记忆系统：
1. **SocialHub CLI 当前记忆系统**（`cli/ai/session.py`, `cli/commands/history.py`, `cli/ai/trace.py`）
2. **Claude Code 本机记忆系统**（`~/.claude/projects/.../memory/` Markdown + frontmatter）

在深度理解两者设计理念后，**针对 SocialHub CLI 业务场景**提出一套全新的完整记忆系统解决方案。

---

## 项目上下文

### SocialHub CLI 是什么
- 面向电商/零售企业运营团队的 AI-powered CLI 工具
- 用户角色：运营经理、数据分析师、营销专员
- 核心能力：自然语言 → AI 解析 → 安全执行 → 洞察输出
- 技术栈：Python 3.10+, Typer+Rich, Azure OpenAI, MCP Server, Skills Store

### 当前记忆系统现状（已研究）

| 组件 | 路径 | 功能 | 局限 |
|------|------|------|------|
| SessionStore | `~/.socialhub/sessions/*.json` | 多轮对话持久化，TTL 24h，max 10 turns | 仅保存原始消息，无语义提取；24h 后全丢 |
| RunHistory | `~/.socialhub/runs/*.json` | 命令执行审计，含 sql_trace、exec_time_ms | 纯审计用途，AI 不可读；无结构化洞察 |
| TraceLogger | `~/.socialhub/ai_trace.jsonl` | AI 决策可观测性 NDJSON，PII 脱敏 | 运维日志，非业务记忆；AI 不感知 |
| Config | `~/.socialhub/config.json` | 静态配置 | 不是记忆，不随使用积累 |
| SkillRegistry | `~/.socialhub/skills/registry.json` | 已安装 Skills | 仅元数据，无使用偏好 |
| SYSTEM_PROMPT | `cli/ai/prompt.py` | 静态系统提示词 | 完全静态，无个性化，无业务上下文注入 |

**核心问题：AI 每次对话都从零开始。它不知道：**
- 这个企业常用哪些分析维度（channel / province / rfm）
- 用户上周做了什么分析、发现了什么问题
- 哪些 Skills 被频繁使用
- 企业的历史营销活动效果
- 用户的偏好输出格式（table / json / export csv）

### Claude Code 记忆系统现状（已研究）

| 特征 | 描述 |
|------|------|
| 存储格式 | Markdown 文件，YAML frontmatter（name/description/type） |
| 类型分类 | user（用户画像）/ feedback（行为指导）/ project（项目状态）/ reference（外部资源指针） |
| 加载机制 | MEMORY.md 索引文件自动注入 system context（前 200 行） |
| 写入触发 | AI 在对话中主动识别值得记录的信息后写入 |
| 结构规范 | 每条 feedback/project 记忆有 Why + How to apply 两个必要字段 |
| 跨会话持久 | 基于文件系统，跨 session、跨项目均可访问 |
| 版本可控 | 纯文本 Markdown，可 git 管理 |

**Claude Code 记忆系统的核心设计哲学：**
- 记忆是"行为指导"而非"历史档案"
- 区分短期（task/plan）和长期（memory）
- 强调"Why"让未来使用者判断边界情况
- 明确排除可以从代码/git 推导出来的信息

---

## 客户 / 利益相关方

| 角色 | 需求 |
|------|------|
| 运营经理（主要用户） | AI 记住我的分析习惯，不用每次重复说"按渠道分析" |
| 数据分析师 | AI 记住上次分析的结论，这次能接续讨论 |
| 营销专员 | AI 了解历史活动效果，给出有背景的建议 |
| IT 管理员 | 记忆数据安全（PII）、可审计、可清除 |
| 企业管理层 | 团队分析洞察积累，形成组织知识库 |

---

## 交付物

1. **完整设计方案文档**（PRD + 技术设计）
2. **Python 实现代码**（新增 `cli/memory/` 模块）
3. **SYSTEM_PROMPT 动态注入机制**
4. **单元测试套件**
5. **更新的 CLAUDE.md** 记录新模块约束

---

## 调研方向（Phase 2 使用）

1. **项目现状深扫**：现有记忆相关代码的完整调用链（session/history/trace 如何被 main.py 和 executor.py 使用）
2. **Claude Code 记忆系统原理**：本机文件结构、加载机制、frontmatter 规范、MEMORY.md 索引
3. **AI 个性化记忆系统业界方案**：LangChain Memory / MemGPT / Zep / mem0 等方案对比
4. **电商 CLI 工具个性化实践**：大型零售企业 CLI/BI 工具的用户偏好记忆设计
5. **向量语义记忆 vs 结构化记忆**：两种范式的取舍，在无向量数据库场景下的替代方案
6. **PII 安全 + 隐私合规**：企业场景下记忆数据的脱敏、访问控制、数据保留策略

---

## 假设

- [假设: 目标环境无向量数据库（ChromaDB/Pinecone），记忆方案必须基于本地文件]
- [假设: 用户规模为单租户 CLI（单人使用），不是多用户 SaaS 记忆系统]
- [假设: Azure OpenAI 可用，可用于记忆摘要提取]
- [假设: 记忆系统是 CLI-local 的，不同步到 MCP Server（多租户安全边界保持不变）]
