# 调研汇总

> 生成日期：2026-04-02  
> 覆盖：6 个方向调研文件

---

## 核心共识

### 1. 现有系统的根本问题：AI 永久失忆
- `SYSTEM_PROMPT` 完全静态，无个性化注入
- `insights.py` 产生的业务洞察只打印到终端，秒消失
- `history.save_run()` 是死代码，审计基础设施从未被调用
- 24h 后 session 全部丢失，AI 永远是陌生人

### 2. 最优技术方案：混合文件型记忆
来自 3 个独立调研方向（业界方案 / 架构研究 / Claude Code 分析）的共同结论：
- **存储**：本地 YAML/JSON 文件（零依赖，人类可读，git 友好）
- **检索**：规则过滤（偏好层）+ 时间衰减（洞察层），可选 bm25s 语义搜索
- **提炼**：会话结束 1 次 LLM 批量提炼（而非每轮高频调用）
- **注入**：tiktoken 预算控制，分层注入 SYSTEM_PROMPT

### 3. 四层记忆架构
```
L4 程序性记忆（永久）  → user_profile.yaml + business_context.yaml
L3 语义记忆（90天）    → analysis_insights/{date}-{slug}.json
L2 情节记忆（30天）    → session_summaries/{session_id}.json
L1 工作记忆（会话内）  → session.messages（现有）
```

### 4. 安全设计原则清晰
- 禁止写入个人级数据（手机/邮箱/身份证/订单号）
- 写入前复用 `_mask_pii()` 扫描
- 文件权限 0o600，原子写入（现有模式）
- 审计追踪：每条写入事件记录 content_hash + trace_id

---

## 关键分歧

| 分歧点 | 方案 A | 方案 B | 建议 |
|--------|--------|--------|------|
| 洞察检索 | 纯时间过滤（简单） | bm25s 语义检索（精确）| MVP 先用时间过滤，按需升级 |
| 偏好更新 | 用户手动 `sh memory set` | LLM 自动推断偏好变化 | 初期手动为主 + AI 建议确认 |
| 团队共享 | 仅个人本地使用 | 通过 git 共享 business_context | 设计支持，不强制 |

---

## 关键洞察

1. **Claude Code 的 MEMORY.md 模式是绝佳参考**：索引 + 独立文件 + frontmatter + Why/How 结构，完全可迁移到 SocialHub 业务场景
2. **最有价值的 10 种记忆**已被识别（见 ecommerce-personalization.md），优先级清晰
3. **history.save_run() 是死代码**——修复这个技术债本身就能建立完整的命令审计基础
4. **Token 预算**：L4(~1000) + L3(~2000) + L2(~1000) + L1(~8000) ≈ 12,000 tokens，在 gpt-4o 128K 范围内完全无压力
5. **PIPL 合规**：只要记忆系统坚持"聚合结论，禁止个人数据"原则，合规风险极低

---

## 可复用资源

| 资源 | 位置 | 用途 |
|------|------|------|
| 原子写入 + 0o600 模式 | `session.py::SessionStore.save()` | MemoryStore 直接复用 |
| PII 脱敏引擎 | `trace.py::_mask_pii()` | 记忆写入前扫描 |
| TTL + purge 模式 | `session.py::purge_expired()` | MemoryStore 记忆清理 |
| TraceLogger 写入基础设施 | `trace.py::TraceLogger._write()` | 审计事件写入 |
| Config Pydantic 模式 | `config.py::SessionConfig` | MemoryConfig 设计范式 |
| Skills Registry 模式 | `skills/registry.py` | JSON 注册表可复用于 business_context 索引 |

---

## Phase 3-8 的输入建议

**业务设计（Phase 3）**需重点解决：
- 运营团队如何信任 AI 的"记忆"（避免 AI 基于过时记忆给错误建议）
- 记忆更新的"确认机制"设计（AI 发现新偏好时是静默更新还是提示用户确认？）

**产品设计（Phase 4）**需重点解决：
- `sh memory` 命令 UX（list/show/clear/init/set）
- 冷启动引导（`sh memory init` 交互式问卷）
- 记忆注入后的 AI 回复如何体现个性化（不能只是内部有记忆，用户感知不到）

**技术设计（Phase 7）**关键决策：
- `cli/memory/` 模块的文件结构
- SYSTEM_PROMPT 从常量改为 `build_system_prompt(memory_context)` 函数
- `history.save_run()` 的接入点（executor.py）
- 会话结束摘要提炼的触发时机（main.py 中何处 hook）
