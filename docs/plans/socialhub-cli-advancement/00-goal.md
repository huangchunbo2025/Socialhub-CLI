# SocialHub CLI 架构先进性与安全性提升

## 目标

以 Anthropic claude-code（TypeScript，~512K 行，业界最先进的 AI CLI）为参照系，
系统性地识别 SocialHub CLI 在架构设计、安全模型、可观测性、扩展性上与业界最佳实践的差距，
提出可落地的改进路径，使产品在 AI-Native CLI 赛道上保持技术领先性。

目标不是追求"更像 claude-code"，而是提取 claude-code 中经过大规模生产验证的架构模式，
结合 SocialHub CLI 的 CRM/电商/运营平台定位，给出适合当前阶段的改进优先级。

## 客户 / 利益相关方

| 角色 | 核心诉求 |
|------|---------|
| 电商/零售运营分析师 | 快速查询客户数据、不需要懂 SQL、AI 帮我分析 |
| 企业 IT 管理员 | 技能包安全可控、数据不出租户、可审计 |
| Skills 开发者 | 开发体验好、发布流程清晰、API 稳定 |
| Chunbo（产品负责人）| 架构先进、安全可信、可持续迭代 |
| 外部 AI Agent（M365/Claude Desktop）| MCP 工具调用稳定、描述准确、latency 低 |

## 项目上下文

### 当前能力（已实现，比初始评估更成熟）

- **安全链完整**：AI 命令 → validator.py → executor.py(shell=False) → subprocess
- **Skills 零信任沙箱**：Ed25519 签名 + SHA-256 哈希 + 三层沙箱（filesystem/network/execute）
- **MCP Server**：36+ 工具，tenant_id 隔离缓存，HTTP Streamable Transport，M365 集成
- **Skills Store**：FastAPI 后端 + React 前端 + JWT 认证 + 双账户表隔离
- **多数据源支持**：MCP / API / Local CSV 三模式
- **AI 执行链**：call_ai_api → extract_plan → validate → execute → insights
- **配置分层**：代码默认值 → config.json → 环境变量
- **告警架构**：SecurityAuditLogger 记录沙箱违规

### 技术栈

Python 3.10+, Typer, Rich, httpx, Pydantic v2, cryptography, FastAPI, SQLAlchemy, React 18

### 与 claude-code 对比的关键差距（调研方向）

1. **命令加载**：17 个模块在启动时全量 import，claude-code 用懒加载降低启动延迟
2. **Permission 模式**：无 auto/plan/ask/bypass 分级，所有操作同一审批逻辑
3. **AI 执行护栏**：无步骤上限、无 circuit breaker、无幂等性保障
4. **可观测性**：无 AI 决策链追踪（为什么选这个命令？哪步消耗了多少 token？）
5. **输出格式**：无 `--output-format json`，不支持程序化消费
6. **Skill 扩展**：静态 Skill，无参数化模板能力
7. **并发执行**：AI 多步计划串行执行，claude-code 工具调用并发
8. **Session 管理**：无对话历史/续接，每次 AI 调用独立
9. **MCP 异步模型**：threading + queue 模式，存在稳定性隐患

## 交付物

- [ ] 01-research/: 6个维度的定制调研
- [ ] 02-business-design.md: 改进优先级与业务价值分析
- [ ] 03-product-design.md: 具体功能/API 设计方案
- [ ] 04-customer-review.md: 用户视角的对抗审视
- [ ] 05-prd.md: 最终产品需求文档
- [ ] 06-technical-design.md: 技术实现方案（含改动清单）
- [ ] 07-cto-review.md: CTO 终审与开发计划

## 调研方向（Phase 2 的 6 个 Agent）

1. **project-status** — 扫描现有代码，精确定位可复用基建与改进切入点
2. **ai-native-cli-patterns** — claude-code 架构模式的深度提取与适配分析
3. **python-cli-security** — Python CLI 的安全最佳实践（沙箱逃逸、供应链、token 注入）
4. **mcp-protocol-advancement** — MCP 协议最新进展（2025 Q1）、工具描述优化、采样模式
5. **ai-agent-reliability** — AI Agent 可靠性模式（circuit breaker、幂等、retry、observability）
6. **competitive-landscape** — AI-Native CLI 竞品（Warp AI、GitHub CLI Copilot、AWS CLI AI）现状

## 假设

- [假设: 改进以不破坏现有红线（shell=False, 沙箱强制, Store URL 硬编码）为前提]
- [假设: 用户愿意接受轻量依赖新增，但不引入大型运行时（如 Bun/Node）]
- [假设: 改进按 P0/P1/P2 分优先级，P0 在下个版本落地，P1/P2 纳入 roadmap]
- [假设: docs/ 目录冻结约束继续保持，改进文档落在 docs/plans/]
