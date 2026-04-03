# SocialHub CLI 记忆系统 PRD

> 版本：v1.0  
> 日期：2026-04-02  
> 阶段：Phase 6 — 客户审视对抗回应 + 最终 PRD  
> 依赖：00-goal.md / 01-research/summary.md / 02-business-design.md / 03-product-design.md / 04-customer-review.md

---

## 产品概述

SocialHub CLI 记忆系统让 AI 助手跨会话记住运营团队的分析习惯、企业业务背景和历史洞察，彻底解决"AI 永久失忆"问题。系统通过四层结构（偏好 / 业务上下文 / 洞察 / 会话摘要）自动积累知识，并在每次对话前动态注入 SYSTEM_PROMPT，使 AI 从陌生人变成懂业务的搭档。

---

## 目标用户与核心场景

### 角色 1：运营经理

**核心诉求**：AI 记住分析习惯，不再每次重复"按渠道分析、看最近 7 天"。

| 场景 | 描述 |
|------|------|
| 1-A 冷启动个性化 | 首次运行 `sh memory init`，30 秒内完成角色选择 + 预设模板填充，次日起 AI 自动按渠道拆分 |
| 1-B 临时覆盖偏好 | 季度报告时加 `--no-memory` 暂停记忆，报告结束后自动恢复，无需手动改回偏好 |
| 1-C 了解 AI 记住了什么 | 会话结束收到摘要写入提示，可即时 `sh memory show summary/<ID>` 查看并纠正 |

### 角色 2：数据分析师

**核心诉求**：上次分析的结论不必重述，AI 能接续讨论；发现错误记忆能一步删除。

| 场景 | 描述 |
|------|------|
| 2-A 跨会话接续分析 | 本周问"根据上次 Q1 渠道复盘，Q2 如何调整？"，AI 直接引用上周摘要而非让用户重述 |
| 2-B 一步删除错误洞察 | AI 回复底部标注 `[memory: insight/2026-02-16-channel-conversion · 45天前]`，用户复制 ID 直接 `sh memory delete <ID>` |
| 2-C 注入预览检查 | 重要分析前执行 `sh memory show --injection-preview`，确认 AI 将携带哪些背景进入对话 |

### 角色 3：营销专员

**核心诉求**：AI 了解历史活动背景，活动结束后不再误判大促驱动的指标为异常。

| 场景 | 描述 |
|------|------|
| 3-A 活动登记与状态管理 | 大促前 `sh memory add-campaign` 登记；结束次日自动归档，`sh memory show campaigns` 显示"已归档"状态 |
| 3-B 活动效果数据补填 | 大促结束后 `sh memory update-campaign --id=ACT001` 交互式补填实际 GMV 增幅、转化率等效果数据 |
| 3-C 活动背景精准关联 | 大促期间分析结果底部出现"活动关联"标注，活动结束次日归档后 AI 仅在用户明确询问时才调取该活动背景 |

---

## 功能需求（MoSCoW）

### Must Have — MVP v1.0 必须实现

| ID | 功能 | 说明 |
|----|------|------|
| M1 | `sh memory init` | 角色选择后**预填对应模板**（运营/分析/营销/管理层各一套默认值），用户可逐题修改或直接回车确认；渐进式，最少 1 题有效 |
| M2 | `sh memory list`（分组视图） | 无参数默认按类型分组展示（偏好摘要 1 行 + 上下文摘要 1 行 + 最近 3 条洞察 + 最近 3 条摘要）；`--sort=time` 切换时间倒序混排；支持 `--type` / `--search` / `--since` 过滤 |
| M3 | `sh memory show` | 显示指定条目详情；`--injection-preview` 显示下次对话的注入预览及 token 用量 |
| M4 | `sh memory set` | 更新 user_profile 指定字段（key=value，点分路径） |
| M5 | `sh memory delete` | 删除洞察或摘要，二次确认；支持 `--older-than=Nd --type=insights` 批量删除 |
| M6 | `sh memory clear` | 按层或全量清除，`--all` 三次确认 |
| M7 | `sh memory add-campaign` | 交互式新增营销活动；新增 `sh memory update-campaign --id=<ID>` 支持编辑已有活动效果数据 |
| M8 | `sh memory status` | 记忆系统健康概览：各层状态、活跃/归档活动数量、token 用量 |
| M9 | 活动状态：活跃 / 已归档 | `period.end` 当日 24:00 后自动切换为"已归档"；归档活动不注入 SYSTEM_PROMPT，仅在用户明确查询时调取；`sh memory show campaigns` 显示状态列 |
| M10 | 会话摘要写入提示 | 会话结束后在终端输出低调提示：`已记录本次会话摘要 · sh memory show summary/<ID> 查看`；不需用户确认，但让用户知道有东西被记住 |
| M11 | `[memory: ...]` 标注含可执行 ID | 标注格式：`[memory: insight/<ID> · age=45d]`；ID 与 `sh memory list` 输出完全一致，用户可直接复制执行 `sh memory delete <ID>` |
| M12 | `sh memory show summary/<ID>` | MVP 必须包含，查看单条摘要全文（M 级别，不推迟到 v1.1） |
| M13 | 偏好层（user_profile.yaml） | MVP 最小集：role / default_period / preferred_dimensions / scope.channels / output.format |
| M14 | 业务上下文层（business_context.yaml） | key_metrics + campaigns（含 status: active/archived 字段） |
| M15 | 分析洞察自动写入（L3） | insights.py 末尾钩子；写入前 PII 扫描；扫描命中时终端输出低调提示而非静默丢弃 |
| M16 | 会话摘要自动写入（L2） | 会话正常结束时触发 LLM 批量提炼；结果写入 session_summaries/；完成后输出 M10 提示 |
| M17 | SYSTEM_PROMPT 动态注入 | `build_system_prompt(memory_context)` 替换静态常量；按 token 预算分层注入（L4 优先）；归档活动不注入 |
| M18 | AI 回复记忆来源标注 | 使用记忆时在终端输出底部标注 `[memory: <层级>/<ID> · age=Nd]`；超 30 天加 `⚠️` |
| M19 | 冷启动弱提示 | 无 user_profile 时，analytics 命令结果底部显示一次弱提示（文案改为"约 1 分钟，全部问题可跳过"）；每进程最多 1 次 |
| M20 | PII 扫描集成 + 可见提示 | 写入前调用 `_mask_pii()` 扫描；**命中时在终端输出 `[dim]本次洞察因包含敏感信息，已跳过记录（符合隐私保护规则）[/dim]`，不静默丢弃** |
| M21 | TTL + 文件数量上限 | analysis_insights 最多 200 条 / 90 天；session_summaries 最多 60 条 / 30 天；惰性清理 |
| M22 | `--no-memory` 临时覆盖 | `sh ai chat "..." --no-memory` 本次会话不注入记忆、不写入摘要 |
| M23 | `sh memory --help` 内嵌说明 | 命令列表上方 3-4 行人话说明："记忆系统让 AI 记住您的分析习惯和企业业务背景。第一次使用：sh memory init ..."  |

### Should Have — v1.1 规划

| ID | 功能 | 推迟原因 |
|----|------|---------|
| S1 | `sh memory review` | 依赖 confidence 评分机制先稳定 |
| S2 | `sh memory show --used-in-last` | 依赖 ai_trace 记忆引用追踪实现 |
| S3 | 偏好自动建议（跨 3 会话触发） | 跨会话计数逻辑复杂；区分主动 N（30天静默）和未响应忽略（7天内最多 1 次再提示） |
| S4 | 洞察 confidence 评分（high/medium/low） | 需命令执行结果解析逻辑 |
| S5 | `sh memory add-context` | MVP 已有 add-campaign，先验证需求 |
| S6 | Skills 使用频率统计 | 需 executor.py Skills 调用记录 |
| S7 | `sh memory list --stale` | 依赖 S2 追踪机制 |

### Won't Have — 本期不做

| 功能 | 原因 |
|------|------|
| 多用户 / 云端记忆同步 | 当前单租户 CLI 架构，SaaS 转型超出范围 |
| 向量数据库集成 | 假设目标环境无向量数据库，文件型已满足需求 |
| 洞察版本历史 | 记忆文件可 git 管理，不做内置版本控制 |
| `sh analytics report campaign` 复盘报告 | 设计文档多处引用但无规格——**从所有文档中删除此引用**，避免用户期待落空（已在客户审视中确认为缺失功能） |

---

## 非功能需求

### 性能

| 指标 | 要求 |
|------|------|
| 记忆加载延迟 | `MemoryManager.load()` ≤ 100ms（本地文件读取，无网络请求） |
| SYSTEM_PROMPT 构建延迟 | `build_system_prompt()` ≤ 50ms（含 token 计数） |
| 会话摘要提炼延迟 | LLM 调用异步执行，不阻塞用户看到分析结果；超时 30s 则跳过本次摘要写入 |
| Token 预算 | L4(~1000) + L3(~2000) + L2(~1000) ≤ 4000 tokens；超出时按层优先级裁剪（L4 > L2 > L3） |

### 可靠性

| 指标 | 要求 |
|------|------|
| 原子写入 | 所有写操作使用临时文件 + `os.replace()` 原子替换，避免文件损坏 |
| 记忆读取失败不阻断主流程 | 任何记忆读取异常必须 catch，降级到无记忆模式运行，不抛出给用户 |
| PII 扫描失败不阻断写入 | 扫描器异常时，整体跳过本次洞察写入并记录审计日志，不崩溃 |
| 文件权限 | 所有记忆文件创建时设置 `0o600`，仅当前用户可读 |

### 安全

| 指标 | 要求 |
|------|------|
| 禁止写入个人级数据 | 记忆内容只允许聚合 / 统计性结论，禁止手机号、邮箱、订单号、客户 ID |
| PII 扫描强制前置 | 所有自动写入路径（洞察 / 摘要）必须先过 `_mask_pii()` |
| 审计追踪 | 每条写入事件记录 content_hash + trace_id 到 ai_trace.jsonl |
| PIPL 合规原则 | "聚合结论，禁止个人数据"——满足此原则后无需额外合规层 |

---

## 业务规则

以下规则可直接转化为代码层断言（`assert` 或 Pydantic validator）：

```
BR-01  campaign.status = "archived"  当且仅当  date.today() > campaign.period.end
BR-02  archived 活动不出现在 build_system_prompt() 的注入上下文中
BR-03  [memory: ...] 标注中的 ID 与 sh memory list 输出的 ID 字段值完全相同（字符级）
BR-04  sh memory show summary/<ID> 在 MVP v1.0 中必须可用（M 级别，不可推迟）
BR-05  PII 扫描命中时，终端必须输出 dim 提示，禁止静默丢弃
BR-06  会话摘要写入后，当次会话终端必须输出 summary/<ID> 提示
BR-07  update-campaign 不修改 created_at / campaign_id，只允许更新 effect_summary 及 updated_at
BR-08  sh memory init 显示的冷启动估时文案必须为"约 1 分钟，全部问题可跳过"
BR-09  sh memory init 选择角色后必须预填对应角色模板默认值，用户可逐题修改
BR-10  sh memory list（无参数）默认按类型分组显示，不按时间混排
BR-11  analysis_insights TTL=90天，上限 200 条；session_summaries TTL=30天，上限 60 条
BR-12  用户显式参数（如 --period=90d）优先级高于记忆偏好，且不触发记忆修改
BR-13  --no-memory 模式下，本次会话既不注入记忆也不写入摘要和洞察
BR-14  所有记忆文件权限创建时设置 0o600
BR-15  会话摘要 LLM 提炼超时 30s 则跳过本次写入，不阻塞用户
```

---

## 客户审视对抗回应

### 致命问题 1：活动降权太慢（90 天后才降权）

**决定：接受**

**理由**：客户反映准确——"活动结束后仍有 3 个月背景干扰"会使活动背景注入这一核心功能适得其反，对营销专员造成持续的误导性噪音。原设计的 90 天降权逻辑出于"历史分析参考价值"的考虑，但混淆了两个不同需求：**活动背景自动关联**（应即时）和**活动效果历史查阅**（可按需）。

**修正方向**（已写入 BR-01 / BR-02）：
- `period.end` 当日 24:00 后，`campaign.status` 自动切换为 `archived`
- `archived` 活动不注入 `SYSTEM_PROMPT`（即不主动进入 AI 背景）
- `archived` 活动保留在文件中，仅在用户明确查询（如"上次大促效果怎么样"）时按需调取
- `sh memory show campaigns` 必须显示 `status` 列（active / archived）和归档日期

---

### 致命问题 2：错误记忆纠正路径 4-5 步，ID 格式不一致

**决定：接受**

**理由**：记忆系统的可信度完全依赖"发现错误后能快速纠正"。4-5 步的纠正路径、以及 `[memory: ...]` 标注和 `sh memory list` ID 不一致，会导致用户宁可加 `--no-memory` 关掉整个系统，而不是花时间定位错误条目。原设计的问题根源在于标注格式和存储 ID 是两套设计，没有被强制统一。

**修正方向**（已写入 BR-03 / M11）：
- `[memory: ...]` 标注中的 ID 字段（如 `insight/2026-02-16-channel-conversion`）必须与 `sh memory list` 中显示的 `ID` 列值完全一致，字符级相同
- 标注格式调整为：`[memory: insight/2026-02-16-channel-conversion · 45天前]`
- 用户发现问题后的操作缩减为 2 步：**复制 ID** → `sh memory delete insight/2026-02-16-channel-conversion`
- 不需要"先 list 再搜索再对应"，路径从 4-5 步降到 2 步

---

### 致命问题 3：会话摘要静默写入，MVP 阶段不可查

**决定：部分接受**

**接受部分**：
- 摘要写入后必须在终端输出低调提示（不强制确认，但用户必须知道有东西被记住了）
- `sh memory show summary/<ID>` 在 MVP v1.0 中必须可用（已从 Should Have 升级为 Must Have，写入 M12 / BR-04）
- 当次会话的 summary ID 必须在会话结束时打印，让用户能立即查看

**拒绝部分**：摘要写入**不需要用户确认**，仍然保持自动写入。

**拒绝理由**：L2 会话摘要是记忆系统"零操作成本自动积累"价值主张的核心。如果改为确认模式，运营经理每次关闭 CLI 都要多一次交互，会产生疲惫感并习惯性按 N 拒绝，导致这层记忆形同虚设。客户的真实诉求是"透明"而不是"控制写入"——低调提示 + 可查看就已经满足透明度需求，无需升级为阻断式确认。

---

### 重要偏差 1：冷启动估时"约 2 分钟"制造心理阻力

**决定：接受**

文案修正为"约 1 分钟，全部问题可跳过"（已写入 BR-08）。更真实，且"可跳过"明确降低心理门槛。

---

### 重要偏差 2：`sh memory list` 默认按时间混排不直觉

**决定：接受**

无参数默认视图改为按类型分组（偏好摘要 1 行 + 上下文摘要 1 行 + 最近 3 条洞察 + 最近 3 条摘要）；`--sort=time` 切换回时间倒序混排（已写入 M2 / BR-10）。

---

### 重要偏差 3：`sh memory add-campaign` 无法编辑已有活动

**决定：接受**

新增 `sh memory update-campaign --id=<ID>` 命令，支持交互式编辑已有活动的 `effect_summary` 字段（已写入 M7 / BR-07）。`created_at`、`campaign_id` 不可修改，保留元数据完整性。

---

### 重要偏差 4：偏好建议"自动 n"和"主动 n"处理逻辑相同

**决定：接受（推迟至 S3 实现）**

区分两种忽略语义：
- **主动选 N**：30 天内不再为该偏好提示
- **未响应自动忽略**（用户直接输入下一条命令）：7 天内最多再提示 1 次

此功能依赖偏好自动建议机制（S3），已纳入 v1.1 规划，与 S3 一并实现。

---

### 重要偏差 5：PII 扫描命中静默丢弃，用户无感知

**决定：接受**

PII 命中时终端输出低调但可见提示（已写入 M20 / BR-05）：
```
[dim]本次洞察因包含敏感信息，已跳过记录（符合隐私保护规则）[/dim]
```
不静默丢弃，让用户能区分"系统 bug"和"隐私保护规则触发"。

---

### 缺失功能 1：活动复盘命令 `sh analytics report campaign` 无设计规格

**决定：接受（从文档删除引用）**

该命令在设计文档中多处被引用，但从未有规格定义，是空头支票。MVP 范围内不实现，且**从所有文档和 UX 文案中删除对此命令的引用**，避免营销专员期待落空（已写入 Won't Have）。

---

### 缺失功能 2：角色选择后缺乏模板快速初始化

**决定：接受**

`sh memory init` 第一步选择角色后，自动预填对应角色模板默认值（已写入 M1 / BR-09）：
- 运营：7d / channel+category / table / include_yoy=true
- 分析：30d / channel+province / json / include_yoy=true  
- 营销：30d / channel / table / include_yoy=false
- 管理层：90d / channel / table / include_yoy=true

用户可逐题修改或全程回车确认，极端快速用户 15 秒内完成。

---

### 缺失功能 3：`open_questions` 字段未被主动提示

**决定：部分接受（推迟）**

接受设计方向：会话开始时若存在 7 天内的 open_questions，AI 在第一个回复中附带提示。推迟到 v1.1 实现，因为 MVP 阶段优先保证摘要写入和查看的基础能力，`open_questions` 的主动提醒是增强体验，不是必要路径。

---

### 缺失功能 4：`sh memory --help` 缺乏人话说明

**决定：接受**

在命令列表上方添加 3-4 行人话说明（已写入 M23）。

---

## 成功指标

| 指标 | 目标值 | 测量方式 |
|------|--------|---------|
| 偏好重复说明率 | 首次 `sh memory init` 后 7 天内，用户手动加 `--period` / `--by` 参数的频率下降 ≥ 70% | ai_trace.jsonl 中命令参数使用统计 |
| 摘要查看率 | 会话结束摘要提示发出后，用户 7 天内至少查看一次摘要的比例 ≥ 40% | `sh memory show summary/<ID>` 调用记录 |
| 错误记忆删除路径步数 | 用户从看到 `[memory: ...]` 标注到成功删除目标条目的操作步数 ≤ 2 步 | UX 可用性测试（5名目标用户） |

---

## MVP 范围

### MVP v1.0 包含（Must Have 全部，共 23 项）

- `sh memory` 全部子命令：init / list / show / set / delete / clear / add-campaign / update-campaign / status
- 四层记忆结构：user_profile.yaml / business_context.yaml / analysis_insights/ / session_summaries/
- 活动即时归档（period.end 次日切换 archived，不注入 SYSTEM_PROMPT）
- 会话摘要写入提示（低调，不阻断）
- `sh memory show summary/<ID>`（MVP 必须，不推迟）
- `[memory: ...]` 标注 ID 与 list 输出完全一致
- PII 扫描命中可见提示（非静默）
- SYSTEM_PROMPT 动态注入（`build_system_prompt()`）
- 角色模板预填（sh memory init 选角色后自动填充默认值）
- sh memory list 默认分组视图
- sh memory update-campaign
- `--no-memory` 临时覆盖
- `sh memory --help` 内嵌人话说明

### MVP v1.0 不包含（推迟至 v1.1 或更晚）

- 偏好自动建议（跨会话检测，区分主动 N / 未响应忽略）
- 洞察 confidence 评分（high/medium/low）
- `sh memory show --used-in-last`（上次对话用了哪些记忆）
- `sh memory list --stale`（过时洞察过滤）
- `sh memory add-context`（手动添加业务上下文条目）
- Skills 使用频率统计
- open_questions 主动提醒
- `sh analytics report campaign` 复盘命令（不做，且从文档删除引用）
- bm25s 语义检索
- 团队 git 共享工作流（export / import）

---

## CLI API 规格（sh memory 子命令完整规格）

### 命令树

```
sh memory
  init              交互式冷启动，角色模板预填，渐进式（最少 1 题有效）
  list              记忆条目列表（默认分组视图）
  show              显示详情 / 注入预览
  set               更新 user_profile 字段
  delete            删除洞察或摘要
  clear             按层或全量清除
  add-campaign      交互式新增营销活动
  update-campaign   编辑已有活动效果数据
  status            记忆系统健康概览
```

---

### `sh memory init`

```bash
sh memory init
sh memory init --force     # 已有 user_profile 时强制覆盖
sh memory init --minimal   # 只问第一题（脚本自动化用）
```

**参数**：

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `--force` | flag | False | 强制覆盖已有 user_profile |
| `--minimal` | flag | False | 只问角色一题 |

**行为约束**：
- 第一题选择角色后，立即预填对应模板默认值
- 每题显示默认值，用户直接回车即接受
- 冷启动估时文案：`约 1 分钟，全部问题可跳过`

---

### `sh memory list`

```bash
sh memory list                          # 默认：分组视图
sh memory list --type=insights          # 只看洞察
sh memory list --type=summaries         # 只看会话摘要
sh memory list --type=profile           # 只看偏好和业务上下文
sh memory list --sort=time              # 切换时间倒序混排
sh memory list --search="渠道"          # 全文搜索
sh memory list --since=7d              # 过滤最近 7 天写入
sh memory list --verbose               # 详细字段（含 pii_scanned / content_hash）
sh memory list --page=2                # 分页
sh memory list --format=json           # JSON 输出（脚本用）
```

**参数**：

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `--type` | enum | all | insights / summaries / profile / all |
| `--sort` | enum | grouped | grouped / time |
| `--search` | str | None | 全文匹配 topic / summary / key_findings |
| `--since` | str | None | 7d / 30d / 90d 或 YYYY-MM-DD |
| `--verbose` | flag | False | 显示详细字段 |
| `--page` | int | 1 | 分页页码（每页 20 条） |
| `--format` | enum | table | table / json |

**默认分组视图输出示例**：
```
SocialHub 记忆概览
────────────────────────────────────────────────────────
 偏好层     渠道偏好·7d窗口·表格输出（更新：2天前）
 业务上下文  服装品类·2个活动（1活跃 / 1已归档）
────────────────────────────────────────────────────────
 最近洞察（共12条）
 insight/2026-04-02-channel-gmv    1天前    天猫 GMV 占比 62%...
 insight/2026-03-20-rfm            13天前   Champions 群体占比上升
 insight/2026-03-10-conversion     23天前   女装转化率周末高 40%
────────────────────────────────────────────────────────
 最近摘要（共5条）
 summary/2026-04-01-abc123         1天前    Q1 渠道复盘（22分钟）
 summary/2026-03-26-def456         6天前    RFM 深度分析（35分钟）
 summary/2026-03-20-ghi789         12天前   天猫大促效果分析
────────────────────────────────────────────────────────
运行 sh memory list --sort=time 查看全部按时间排序
```

---

### `sh memory show`

```bash
sh memory show profile                          # user_profile 完整内容
sh memory show context                          # business_context 完整内容
sh memory show campaigns                        # 所有营销活动（含状态列）
sh memory show insight/<ID>                     # 指定洞察详情
sh memory show summary/<ID>                     # 指定摘要详情（MVP 必须）
sh memory show --injection-preview              # 下次对话注入预览
```

**`--injection-preview` 输出格式**：
```
下次对话的记忆注入预览
─────────────────────────────────────────────────────────
 层级      来源                      Token 估算
 L4 偏好   user_profile.yaml         ~280 tokens
 L4 上下文  business_context.yaml    ~420 tokens
 L3 洞察   最近 5 条（30 天内）       ~980 tokens
 L2 摘要   最近 3 条（7 天内）        ~650 tokens
─────────────────────────────────────────────────────────
 合计：~2330 tokens（预算 4000 tokens，剩余 58%）
```

**`sh memory show campaigns` 输出格式（含状态列）**：
```
 ID       名称             时间段                    状态     归档日期
──────────────────────────────────────────────────────────────────────
 ACT001   2026 三八大促    2026-03-08 ~ 2026-03-15   已归档   2026-03-16
 ACT002   2026 五一大促    2026-04-29 ~ 2026-05-05   活跃     —
```

---

### `sh memory set`

```bash
sh memory set analysis.default_period 30d
sh memory set output.format json
sh memory set analysis.preferred_dimensions "channel,category"
sh memory set analysis.scope.channels "天猫,京东,拼多多"
sh memory set output.precision 2
sh memory set output.include_yoy true
```

**支持的 KEY（点分路径）**：

| KEY | 允许值 |
|-----|--------|
| `role` | 运营 / 分析 / 营销 / 管理层 |
| `analysis.default_period` | 7d / 30d / 90d |
| `analysis.preferred_dimensions` | channel / province / category（逗号分隔）|
| `analysis.scope.channels` | all 或渠道名称逗号分隔 |
| `output.format` | table / json / csv |
| `output.precision` | 0-4 整数 |
| `output.include_yoy` | true / false |

---

### `sh memory delete`

```bash
sh memory delete insight/2026-02-16-channel-conversion
sh memory delete summary/2026-03-26-abc123
sh memory delete insight/A insight/B                     # 批量
sh memory delete --older-than=60d --type=insights        # 批量清理
```

**参数**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `ID [ID ...]` | str（位置参数，可多个）| 要删除的记忆 ID |
| `--older-than` | str | Nd 格式，配合 --type 批量删除 |
| `--type` | enum | 配合 --older-than 使用 |
| `--yes` | flag | 跳过确认（脚本用，慎用）|

**确认提示**：
```
确认删除以下 1 条记忆？（操作不可逆）
  insight/2026-02-16-channel-conversion
  "天猫转化率 3.2%，高于京东 2.8%（2026-02-16 分析）"
[y/N]: 
```

---

### `sh memory clear`

```bash
sh memory clear --layer=insights       # 清除所有洞察
sh memory clear --layer=summaries      # 清除所有摘要
sh memory clear --layer=profile        # 重置用户偏好
sh memory clear --layer=context        # 清除业务上下文（慎用）
sh memory clear --all                  # 清除全部（三次确认）
```

**参数**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `--layer` | enum | insights / summaries / profile / context |
| `--all` | flag | 清除所有层（三次确认）|
| `--yes` | flag | 跳过确认（脚本用，慎用）|

---

### `sh memory add-campaign`

```bash
sh memory add-campaign
```

**交互流程（5 个问题，约 1 分钟）**：
1. 活动名称
2. 活动开始日期（YYYY-MM-DD）
3. 活动结束日期（YYYY-MM-DD）
4. 涉及渠道（逗号分隔，all=全部）
5. 预期目标（简短描述，可回车跳过）

**写入字段**：`campaign_id`（自动生成 ACT001、ACT002...）/ `name` / `period.start` / `period.end` / `channels` / `goal` / `effect_summary`（空字符串，待 update-campaign 补填）/ `status`（自动根据日期计算）/ `created_at`

---

### `sh memory update-campaign`

```bash
sh memory update-campaign --id=ACT001
```

**参数**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `--id` | str（必填）| 要编辑的活动 ID（如 ACT001）|

**交互流程**：显示当前 `effect_summary` 字段，提示用户输入新值（如"GMV 环比+15%，转化率+8%"）。`created_at` 和 `campaign_id` 不可修改，自动更新 `updated_at`。

---

### `sh memory status`

```bash
sh memory status
```

**输出示例**：
```
SocialHub 记忆系统状态
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  偏好层        ✓ 已配置（上次更新：2 天前）
  业务上下文    ✓ 已配置（2 个活动：1 活跃 / 1 已归档）
  分析洞察      12 条（30 天内有效 8 条）
  会话摘要      5 条（7 天内有效 5 条）
  存储用量      ~240 KB
  注入预算      ~2330 / 4000 tokens（剩余 58%）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  运行 sh memory list 查看所有记忆条目
  运行 sh memory show --injection-preview 查看注入详情
```

---

### `sh ai chat` 新增参数

```bash
sh ai chat "..." --no-memory              # 完全不注入记忆，不写入摘要
sh ai chat "..." --memory-level=profile-only   # 只注入偏好层
```

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `--no-memory` | flag | False | 本次对话完全跳过记忆注入和摘要写入 |
| `--memory-level` | enum | full | full / profile-only / none（同 --no-memory）|

---

### AI 回复 `[memory: ...]` 标注规格

**格式**：
```
[memory: <层级>/<ID> · <age>天前]
[memory: <层级>/<ID> · <age>天前 ⚠️ 超过30天]     # 超过 30 天加警示
[memory: 活动上下文·<campaign_id>]                  # 活动背景引用
[memory: 已应用 渠道偏好·时间窗口偏好]               # 偏好层引用
```

**约束**：
- ID 字段必须与 `sh memory list` 输出的 `ID` 列完全一致（BR-03）
- 超过 30 天的洞察必须加 `⚠️` 警示
- 多条记忆引用时合并为一行，逗号分隔

---

### 会话结束摘要提示规格

**触发时机**：`main.py` 会话退出钩子，LLM 摘要提炼完成后。

**输出格式**：
```
[dim]已记录本次会话摘要 · sh memory show summary/2026-04-02-abc123 查看[/dim]
```

**约束**：
- 使用 Rich `[dim]` 样式（低调，不抢眼）
- 必须打印 `summary/<ID>`，用户可直接复制执行（BR-06）
- LLM 提炼失败或超时时，静默跳过（不打印提示，不影响用户体验）

---

*文档结束*
