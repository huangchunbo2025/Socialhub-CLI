# 产品设计：SocialHub CLI 记忆系统

> 版本：v1.0  
> 日期：2026-04-02  
> 阶段：Phase 4 — 产品设计（含 3 轮自我对抗）  
> 依赖：`02-business-design.md`、`01-research/summary.md`、`01-research/ecommerce-personalization.md`

---

## 用户场景

### 场景 1：运营经理首次体验 — 冷启动到个性化（D0 → D1）

**用户画像**：天猫+京东双渠道运营经理，每周分析 GMV 趋势，按渠道拆分是她的默认习惯。

**D0（第一天，无记忆）**：
```
$ sh analytics overview --period=7d
[AI 分析结果：通用概览，未按渠道拆分]

─────────────────────────────────────────────────────────
 提示  当前为通用模式。运行 sh memory init（约 2 分钟）
       即可开启个性化 AI 体验，AI 将记住您的分析习惯。
─────────────────────────────────────────────────────────
```

**D0 → D1（执行 init，约 2 分钟）**：
```
$ sh memory init

欢迎使用 SocialHub AI 个性化记忆系统！
回答以下问题（全部可跳过），AI 将立即记住您的偏好。

? 您的主要职责是？ (运营/分析/营销/管理层) [运营]:  运营
? 最常使用的时间窗口？ (7d/30d/90d) [7d]:  7d
? 最常用的分析维度？ (多选，逗号分隔) channel,province,category [channel]: channel
? 您负责的渠道范围？ (all/指定渠道，逗号分隔) [all]: 天猫,京东

✓ 偏好已保存。下次对话 AI 将自动：
  · 默认分析最近 7 天数据
  · 按渠道拆分展示
  · 聚焦天猫和京东

运行 sh memory show 查看完整偏好配置。
```

**D1（第二天，有记忆）**：
```
$ sh analytics overview
[AI 自动使用 7d 窗口，按渠道拆分，聚焦天猫+京东]

[memory: 已应用 渠道偏好·时间窗口偏好]
```

**完整交互价值**：用户再也不需要每次手动加 `--period=7d --by=channel`，AI 理解了"这个人的工作方式"。

---

### 场景 2：营销专员在大促前登记活动背景

**用户画像**：营销专员，负责策划三八大促，希望大促结束后 AI 能自动关联分析。

**大促前（登记活动）**：
```
$ sh memory add-campaign

? 活动名称: 2026 三八大促
? 活动时间段（开始 YYYY-MM-DD）: 2026-03-08
? 活动时间段（结束 YYYY-MM-DD）: 2026-03-15
? 涉及渠道（逗号分隔，all=全部）: 天猫,京东
? 预期目标（简短描述）: GMV 环比增长 20%，重点带动女装品类
? 备注（可选）:

── 活动预览 ────────────────────────────────────────
  名称: 2026 三八大促
  时间: 2026-03-08 ~ 2026-03-15（8 天）
  渠道: 天猫、京东
  目标: GMV 环比增长 20%，重点带动女装品类
────────────────────────────────────────────────────
确认写入记忆？ [y/N]: y

✓ 活动已记录。大促期间的所有分析，AI 将自动关联此背景。
  大促结束后运行 sh analytics report campaign --id=ACT002 生成复盘报告。
```

**大促结束后的分析体验**：
```
$ sh analytics overview --period=7d

[AI 分析结果]
...天猫渠道本周 GMV 同比增长 62%，高峰出现在 3 月 10-12 日...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 活动关联  分析时段覆盖「2026 三八大促」（2026-03-08~15）
          本周 GMV 异常高峰已关联活动背景，非业务异常。
 [memory: 活动上下文·ACT002]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**完整交互价值**：AI 不会将大促驱动的 GMV 峰值误判为"异常"并发出错误警报。

---

### 场景 3：数据分析师跨会话接续分析

**用户画像**：数据分析师，上周做了 Q1 渠道复盘，本周希望继续深入。

**上周（会话 A）**：
```
$ sh analytics orders --period=90d --by=channel
[分析结果：天猫占 62%，京东客单价高 22%...]

[会话结束时 AI 自动保存摘要：Q1 渠道分析，发现天猫/京东差异...]
```

**本周（会话 B）**：
```
$ sh ai chat "根据上次 Q1 渠道分析的结论，Q2 应该如何调整投入策略？"

[AI 回答]
根据上周（2026-03-26）的 Q1 渠道分析：

• 天猫渠道 GMV 占比 62%，环比上升 8 个百分点
• 京东渠道客单价高于天猫 22%，但订单量少 40%
• 三八大促对天猫 GMV 有显著拉升效应

基于上述背景，Q2 策略建议：...

[memory: 会话摘要·2026-03-26-Q1渠道复盘]
```

**完整交互价值**：分析师无需重新描述上周的发现，AI 自然接续讨论。

---

### 场景 4：用户发现过时洞察并纠正

**用户画像**：运营经理，AI 引用了 2 个月前的洞察（当时拼多多渠道刚上线，数据不成熟）。

**发现过时洞察**：
```
$ sh ai chat "目前哪个渠道的转化率最高？"

[AI 回答]
根据历史分析（45 天前，2026-02-16），天猫渠道转化率约 3.2%，
高于京东的 2.8%。需注意此数据已超过 30 天，建议重新分析确认。

[memory: 分析洞察·2026-02-16·age=45d ⚠️ 超过30天]
```

**查看并纠正记忆**：
```
$ sh memory list --type=insights --stale

ID                              类型      日期         新鲜度    摘要
2026-02-16-channel-conversion   洞察      2026-02-16   45天前    天猫转化率 3.2%...
2026-01-28-rfm-champions        洞察      2026-01-28   63天前    Champions 群体...

$ sh memory delete 2026-02-16-channel-conversion

确认删除此洞察？（AI 将停止引用）
  "天猫转化率 3.2%，高于京东 2.8%（2026-02-16）"
[y/N]: y
✓ 已删除。

$ sh analytics orders --period=30d --by=channel
[AI 重新分析，产生新的洞察，自动写入记忆]
```

**完整交互价值**：用户有完整的"查找 → 定位 → 删除 → 更新"控制链路，不会被过时记忆误导。

---

### 场景 5：临时覆盖偏好（本次会话不用记忆）

**用户画像**：运营经理，平时看 7 天数据，但今天要做季度报告，临时需要 90 天窗口，不希望覆盖掉"默认 7 天"的偏好。

**临时覆盖（--no-memory 标志）**：
```
$ sh ai chat "分析 Q1 全季度的渠道销售趋势" --no-memory

[dim]记忆系统已在本次会话暂停。本次对话不注入记忆上下文，
结束后也不更新记忆。[/dim]

[AI 按照问题本身的 Q1 语义分析，不受"7 天偏好"干扰]
```

**或者：单条偏好临时覆盖（在查询中直接指定）**：
```
$ sh analytics overview --period=90d
[AI 使用 90d，忽略 user_profile 中的 7d 偏好，因为用户显式指定了]
[用户显式参数 > 记忆偏好，记忆不被修改]
```

**完整交互价值**：用户在需要一次性偏差分析时，不需要先修改偏好、做完再改回来。

---

### 场景 6：团队新成员使用团队共享上下文（预留场景）

**用户画像**：新加入团队的运营分析师，团队已有 `business_context.yaml` 在 git 仓库中。

```
$ git clone team-repo && cp team-repo/memory/business_context.yaml ~/.socialhub/memory/

$ sh ai chat "我们公司的主营品类是什么，有什么重要的历史促销活动？"

[AI 回答]
根据业务上下文，您公司：
• 主营品类：服装
• 核心 KPI：GMV、转化率、客单价、复购率
• 近期重要活动：2026 三八大促（天猫+京东，效果：GMV 环比+15%）

[memory: 业务上下文·business_context]
```

**完整交互价值**：新成员从第一天就享有团队积累的业务背景，无需口口相传。

---

## 功能清单（MoSCoW）

### Must Have（MVP v1.0 必须实现）

| 功能 | 描述 | 依赖 |
|------|------|------|
| M1 `sh memory init` | 交互式问卷，冷启动偏好引导，渐进式（最少 1 问有效） | Typer prompt |
| M2 `sh memory list` | 列出所有记忆条目，支持类型过滤（--type=insights/summaries/profile） | MemoryStore |
| M3 `sh memory show` | 显示指定记忆条目详情（或全部概览） | MemoryStore |
| M4 `sh memory set` | 手动更新 user_profile 字段（key=value 格式） | MemoryStore |
| M5 `sh memory delete` | 删除指定洞察或摘要条目 | MemoryStore |
| M6 `sh memory add-campaign` | 交互式添加营销活动到 business_context | Typer prompt |
| M7 偏好层（user_profile.yaml） | MVP 最小集：default_period、preferred_dimensions、output.format | MemoryStore |
| M8 业务上下文层（business_context.yaml） | key_metrics + campaigns 基础结构 | MemoryStore |
| M9 分析洞察自动写入 | insights.py 执行后钩子，写入 analysis_insights/ | MemoryStore + insights.py |
| M10 会话摘要自动写入 | 会话正常结束时触发，LLM 批量提炼写入 session_summaries/ | MemoryStore + main.py |
| M11 SYSTEM_PROMPT 动态注入 | `build_system_prompt(context)` 函数，按 token 预算分层注入 | prompt.py 重构 |
| M12 AI 回复记忆来源标注 | AI 使用记忆时，在终端输出底部标注 `[memory: 来源]` | 注入机制 |
| M13 冷启动弱提示 | 无 user_profile 时，在 analytics 命令结果底部显示一次引导提示 | main.py |
| M14 PII 扫描集成 | 记忆写入前调用 `_mask_pii()` 扫描，命中则整体丢弃 | trace.py |
| M15 TTL + 文件数量上限 | analysis_insights 最多 200 条，session_summaries 最多 60 条，惰性清理 | MemoryStore |
| M16 `sh memory clear` | 清除指定层或全部记忆，需二次确认 | MemoryStore |

### Should Have（v1.1 规划）

| 功能 | 描述 | 推迟原因 |
|------|------|---------|
| S1 `sh memory review` | 列出 medium/low 质量洞察供用户审阅确认 | 需要 confidence 评分机制先稳定 |
| S2 `sh memory show --used-in-last` | 显示上次对话用了哪些记忆 | 需要 ai_trace 记忆引用追踪先实现 |
| S3 `sh memory list --stale` | 过滤并显示超过30天的洞察（新鲜度标记） | 依赖 S2 追踪机制 |
| S4 偏好自动建议 | 跨 3 个不同会话检测到一致信号后，在终端提示用户确认 | 跨会话计数逻辑复杂，影响测试边界 |
| S5 洞察 confidence 评分 | high/medium/low 三级，low 不注入 SYSTEM_PROMPT | 需要命令执行结果解析逻辑 |
| S6 `sh memory add-context` | 手动添加业务上下文条目 | MVP 已有 add-campaign，先验证需求 |
| S7 Skills 使用频率统计 | AI 自动统计 frequently_used skills | 需要 executor.py Skills 调用记录 |

### Could Have（未来版本）

| 功能 | 描述 |
|------|------|
| C1 `sh memory migrate` | 检测记忆 schema 版本差异，提示用户补全新字段 |
| C2 团队 git 共享工作流 | `sh memory export/import`，business_context 团队共享 |
| C3 bm25s 语义检索 | 替代时间过滤，更精准定位相关洞察 |
| C4 RFM 焦点记忆 | 记忆用户关注的 RFM 细分群体 |
| C5 异常基线 | baselines 字段 + 波动阈值配置 |
| C6 `sh memory feedback` | 用户对 AI 回答质量打分，收集记忆命中率度量 |

### Won't Have（本期不做）

| 功能 | 原因 |
|------|------|
| 多用户/云端记忆同步 | 当前单租户 CLI 架构，多用户是 SaaS 转型，超出范围 |
| 向量数据库集成 | 假设目标环境无向量数据库，文件型已满足需求 |
| 工作流别名（记忆系统管理）| 由现有 heartbeat 调度器实现，不进记忆系统 |
| 洞察版本历史 | 记忆文件已可 git 管理，不做内置版本控制 |

---

## CLI API 设计（sh memory 子命令）

### 命令树总览

```
sh memory
  init              交互式冷启动引导
  list              列出记忆条目
  show              显示详情
  set               更新偏好字段
  delete            删除记忆条目
  clear             清除记忆层
  add-campaign      添加营销活动
  status            记忆系统健康概览
```

---

### `sh memory init`

**功能**：交互式问卷，收集基础偏好，写入 user_profile.yaml。渐进式设计：最少回答 1 题即写入有效记忆。

```bash
$ sh memory init
$ sh memory init --force   # 强制重新初始化（覆盖已有偏好）
```

**参数说明**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--force` | flag | False | 已有 user_profile 时强制覆盖，否则询问用户 |
| `--minimal` | flag | False | 只问第一个必填问题（用于自动化脚本） |

**交互流程**：见"冷启动引导 UX"章节。

---

### `sh memory list`

**功能**：列出所有记忆条目，支持多维度过滤和排序。

```bash
# 列出所有记忆（默认：按时间倒序，最多 20 条）
$ sh memory list

# 只看分析洞察
$ sh memory list --type=insights

# 只看会话摘要
$ sh memory list --type=summaries

# 只看偏好和业务上下文（静态层）
$ sh memory list --type=profile

# 列出过时洞察（超过 30 天）
$ sh memory list --type=insights --stale

# 关键词搜索（文本过滤）
$ sh memory list --search="渠道"

# 列出最近 7 天写入的记忆
$ sh memory list --since=7d

# 详细模式：显示所有字段，含最近注入时间
$ sh memory list --verbose

# 分页（每页 20 条）
$ sh memory list --page=2
```

**参数说明**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--type` | enum | all | insights / summaries / profile / all |
| `--stale` | flag | False | 只显示超过 30 天的洞察（过时内容） |
| `--search` | str | None | 在 topic/summary/key_findings 中全文匹配 |
| `--since` | str | None | 时间过滤（7d/30d/90d 或 YYYY-MM-DD） |
| `--verbose` | flag | False | 显示详细字段（confidence、pii_scanned、content_hash 等）|
| `--page` | int | 1 | 页码（每页 20 条） |
| `--format` | enum | table | table / json（json 便于脚本处理） |

**输出示例（table 模式）**：
```
 ID                              类型    日期         新鲜度   摘要
─────────────────────────────────────────────────────────────────────────
 profile/user_profile            偏好    2026-04-02   —        渠道偏好·7d窗口·表格输出
 context/business_context        上下文  2026-04-01   —        服装品类·3个活动记录
 insight/2026-04-02-channel-gmv  洞察    2026-04-02   1天前    天猫 GMV 占比 62%...
 insight/2026-03-20-rfm          洞察    2026-03-20   13天前   Champions 群体占比上升
 summary/2026-04-01-abc123       摘要    2026-04-01   1天前    Q1 渠道复盘（22分钟）
─────────────────────────────────────────────────────────────────────────
共 5 条  （sh memory list --help 查看过滤选项）
```

---

### `sh memory show`

**功能**：显示单条或指定类型的记忆详情。

```bash
# 显示 user_profile 完整内容
$ sh memory show profile

# 显示 business_context 完整内容
$ sh memory show context

# 显示所有已记录的活动
$ sh memory show campaigns

# 显示某条洞察的完整内容
$ sh memory show insight/2026-04-02-channel-gmv

# 显示某条会话摘要
$ sh memory show summary/2026-04-01-abc123

# 显示系统注入预览（下次对话会注入哪些记忆，消耗多少 token）
$ sh memory show --injection-preview
```

**--injection-preview 输出示例**：
```
下次对话的记忆注入预览：
─────────────────────────────────────────────────────────────────
 层级     来源                     Token 估算
 L4 偏好  user_profile.yaml        ~280 tokens
 L4 上下文 business_context.yaml   ~420 tokens
 L3 洞察  最近 5 条（30天内）       ~980 tokens
 L2 摘要  最近 3 条（7天内）        ~650 tokens
─────────────────────────────────────────────────────────────────
 合计：~2330 tokens（总预算 4000 tokens，剩余 1670）
```

---

### `sh memory set`

**功能**：直接更新 user_profile 中的字段。

```bash
# 更新时间窗口偏好
$ sh memory set analysis.default_period 30d

# 更新输出格式
$ sh memory set output.format json

# 更新偏好维度（逗号分隔）
$ sh memory set analysis.preferred_dimensions "channel,category"

# 更新渠道范围
$ sh memory set analysis.scope.channels "天猫,京东,拼多多"

# 更新小数精度
$ sh memory set output.precision 2

# 切换是否默认附带同比
$ sh memory set output.include_yoy true
```

**参数说明**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `KEY` | str（必填）| 点分字段路径（如 `analysis.default_period`） |
| `VALUE` | str（必填）| 新值（逗号分隔表示列表） |

**支持的 KEY 列表**：

| KEY | 允许值 | 说明 |
|-----|--------|------|
| `role` | 运营/分析/营销/管理层 | 用户职责角色 |
| `analysis.default_period` | 7d/30d/90d | 默认时间窗口 |
| `analysis.preferred_dimensions` | channel,province,category,... | 逗号分隔 |
| `analysis.scope.channels` | 天猫,京东,... / all | 责任渠道范围 |
| `output.format` | table/json/csv | 默认输出格式 |
| `output.precision` | 0-4（整数）| 小数位数 |
| `output.include_yoy` | true/false | 是否附带同比 |

---

### `sh memory delete`

**功能**：删除指定的洞察或会话摘要条目（不可删除 user_profile 和 business_context，这两者用 `sh memory clear --layer=profile` 清除）。

```bash
# 删除指定洞察
$ sh memory delete insight/2026-02-16-channel-conversion

# 删除指定会话摘要
$ sh memory delete summary/2026-03-26-abc123

# 批量删除（多个 ID，空格分隔）
$ sh memory delete insight/2026-02-16-channel-conversion insight/2026-01-28-rfm

# 删除所有超过 60 天的洞察（批量清理）
$ sh memory delete --older-than=60d --type=insights
```

**删除前必须二次确认**（非交互模式下 `--yes` 跳过）：
```
确认删除以下 1 条记忆？（操作不可逆）
  insight/2026-02-16-channel-conversion
  "天猫转化率 3.2%，高于京东 2.8%（2026-02-16 分析）"
[y/N]: y
✓ 已删除。
```

---

### `sh memory clear`

**功能**：清除指定记忆层或全部记忆。

```bash
# 清除所有分析洞察
$ sh memory clear --layer=insights

# 清除所有会话摘要
$ sh memory clear --layer=summaries

# 重置用户偏好（清除 user_profile，等效于重新 init）
$ sh memory clear --layer=profile

# 清除业务上下文（慎用）
$ sh memory clear --layer=context

# 清除全部记忆（核心数据，三次确认）
$ sh memory clear --all
```

**参数说明**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `--layer` | enum | insights / summaries / profile / context |
| `--all` | flag | 清除所有层（需要三次确认） |
| `--yes` | flag | 跳过确认（用于脚本自动化，慎用） |

---

### `sh memory add-campaign`

**功能**：交互式添加营销活动记录到 business_context.yaml。

```bash
$ sh memory add-campaign
```

**交互流程**：见"冷启动引导 UX"章节的活动登记部分。

---

### `sh memory status`

**功能**：记忆系统健康概览，快速了解当前记忆状态。

```bash
$ sh memory status
```

**输出示例**：
```
SocialHub 记忆系统状态
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  偏好层        ✓ 已配置（上次更新：2 天前）
  业务上下文    ✓ 已配置（3 个活动记录，1 个在活跃期）
  分析洞察      12 条（30天内有效 8 条，已降权 4 条）
  会话摘要      5 条（30天内有效 5 条）
  存储用量      ~240 KB
  注入预算      ~2330 / 4000 tokens（剩余 58%）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  运行 sh memory list 查看所有记忆条目
  运行 sh memory show --injection-preview 查看注入详情
```

---

### `sh ai chat` 新增参数

```bash
# 本次会话暂停记忆注入（不影响记忆数据，只是本次不使用）
$ sh ai chat "..." --no-memory

# 本次会话仅使用偏好层，不使用洞察（快速模式）
$ sh ai chat "..." --memory-level=profile-only
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `--no-memory` | flag | 本次对话完全不注入记忆上下文（临时覆盖） |
| `--memory-level` | enum | full（默认）/ profile-only / none（同 --no-memory）|

---

## AI 回复个性化体验设计

### 设计原则

**记忆不应只是"内部有"，用户必须感知到**。个性化体验通过三个层次实现：

1. **行为个性化**：AI 的分析视角和输出符合用户偏好
2. **语言个性化**：AI 的措辞反映对该用户业务背景的了解
3. **透明归因**：用户能看到 AI 使用了哪些记忆，并能追溯

---

### 层次一：行为个性化（无需用户开口）

用户设置渠道偏好后，AI 在任何分析中自动按渠道拆分，无需每次说"按渠道拆分"。

**对比示例**：

无记忆（通用模式）：
```
$ sh analytics overview
本月 GMV 为 1,250,000 元，同比增长 8%。
订单数 15,200 单，客单价 82 元。
```

有记忆（个性化模式，user_profile: preferred_dimensions=[channel]）：
```
$ sh analytics overview
本月各渠道 GMV 表现：
  天猫  782,000 元 (+12%)  占比 62.6%  ← 最强
  京东  468,000 元 (+2%)   占比 37.4%
合计  1,250,000 元 (+8%)

注：天猫增速高于京东 10 个百分点，渠道集中度仍在上升。

[memory: 渠道偏好]
```

**自动补全的参数类型**：
- 时间窗口（`default_period: 7d` → 默认不加 `--period` 时使用 7d）
- 分析维度（`preferred_dimensions` → AI 默认建议按这些维度拆分）
- 渠道过滤（`scope.channels` → 只聚焦用户负责的渠道）
- 输出格式（`output.format: table` → 默认表格输出）

---

### 层次二：语言个性化（AI 开口方式变了）

有了业务上下文，AI 的措辞会体现对企业背景的了解，而不是通用术语。

**无业务上下文**：
```
本周数据出现异常波动，建议调查原因。
```

**有活动上下文（business_context 有三八大促记录）**：
```
本周 GMV 峰值（3月10日）符合三八大促预期，活动期间（3/8-3/15）
天猫渠道 GMV 日均较非活动期高出 3.1 倍，这是活动拉升效应，
并非异常。

活动结束后（3月16日起）GMV 回落至正常水平，符合促销后效应规律。
```

**有会话摘要（接续上次对话）**：
```
根据上周（3月26日）的 Q1 渠道分析，您已发现天猫客单价低于京东
但订单量多 2.5 倍。结合这个背景，Q2 策略建议...
```

---

### 层次三：透明归因（记忆来源标注）

每次 AI 使用了记忆，在终端输出底部以轻量 dim 文字标注来源，用户可以：
- 知道 AI 在用哪些记忆
- 快速定位到对应记忆（用 `sh memory show` 查看详情）
- 发现错误记忆后立即 `sh memory delete` 纠正

**标注格式规范**：

```
[memory: 渠道偏好·7d窗口]                    ← 使用了偏好层
[memory: 活动上下文·三八大促(ACT002)]         ← 使用了活动上下文
[memory: 会话摘要·2026-03-26·Q1渠道复盘]     ← 使用了会话摘要
[memory: 分析洞察·2026-03-20·age=13d]        ← 使用了分析洞察（附新鲜度）
[memory: 3项来源 — sh memory show --used-in-last 查看详情]  ← 多来源简写
```

**标注展示位置**：
- AI 回答正文结束后，新起一行，用 `[dim]` 样式（灰色低调显示）
- 标注行用 `─` 分隔符与正文分开，避免视觉干扰
- 宽度不超过终端宽度 80%

**用户无记忆时的引导**：
```
[无个性化记忆] 运行 sh memory init 开启个性化 AI 体验
```

---

### 层次四：AI 主动提醒记忆过时（v1.1）

当 AI 注入的洞察超过 30 天时，在使用该洞察的回答中主动提示：

```
注意：以下参考数据来自 45 天前的分析，可能不反映当前状态。
建议运行 sh analytics orders --period=30d 获取最新数据。

[memory: 分析洞察·2026-02-16·age=45d ⚠️ 已超过30天]
```

---

## 冷启动引导 UX

### 设计原则

1. **渐进式**：第 1 问必填（角色），后续全部可跳过，即使只回答 1 题也写入有效记忆
2. **即时反馈**：每题回答后立即显示"AI 将如何使用这个偏好"
3. **非阻断**：不强制要求用户完成，任何时候 Ctrl+C 退出都保存已完成的答案
4. **可重做**：`sh memory init --force` 可随时重新初始化

---

### `sh memory init` 完整交互流程

```
$ sh memory init

╔══════════════════════════════════════════════════════════════╗
║         SocialHub AI 个性化记忆初始化（约 2 分钟）           ║
║  回答以下问题，AI 将记住您的分析习惯，下次对话自动应用。     ║
║  全部问题均可直接回车跳过。                                  ║
╚══════════════════════════════════════════════════════════════╝

── 第 1 步：您的角色（必填）──────────────────────────────────

  1. 运营经理   — 关注渠道 GMV、活动效果、日常运营指标
  2. 数据分析师 — 关注精确数据、RFM 分层、趋势分析
  3. 营销专员   — 关注活动效果、客群反应、拉新留存
  4. 管理层     — 关注 GMV 趋势、复购率、月度概览

? 请选择您的职责角色（输入序号或名称）: 1

  ✓ 已记录：运营经理
    AI 将默认关注渠道维度分析和活动效果追踪。

── 第 2 步：默认时间窗口 ─────────────────────────────────────

  AI 分析时的默认时间范围（显式指定 --period 时会覆盖此设置）。

? 最常使用的时间窗口 (7d/30d/90d) [7d]: 7d

  ✓ 已记录：最近 7 天
    无需每次输入 --period=7d

── 第 3 步：常用分析维度 ────────────────────────────────────

  AI 在概览分析时优先按这些维度拆分数据。

? 最常用的分析维度（多选，逗号分隔）
  可选项: channel（渠道）/ province（省份）/ category（品类）
  [channel]: channel,category

  ✓ 已记录：channel、category
    AI 在渠道分析时自动拆分并对比各品类表现。

── 第 4 步：责任渠道范围 ────────────────────────────────────

  如果您只负责特定渠道，设置后 AI 将聚焦这些渠道。

? 您负责的渠道范围（逗号分隔，all=全部渠道）[all]: 天猫,京东

  ✓ 已记录：天猫、京东
    AI 在分析时自动高亮这两个渠道的数据对比。

── 第 5 步：输出格式偏好 ────────────────────────────────────

? 默认输出格式 (table/json/csv) [table]: （回车跳过）

  ↷ 跳过，使用默认值：table

── 完成 ─────────────────────────────────────────────────────

✓ 偏好已保存至 ~/.socialhub/memory/user_profile.yaml

  下次对话 AI 将自动：
  · 角色：运营经理（关注渠道 + 活动）
  · 时间窗口：默认 7 天
  · 分析维度：渠道、品类双维度拆分
  · 渠道聚焦：天猫、京东

  下一步：
  · sh memory add-campaign  — 登记您的营销活动背景
  · sh memory show          — 查看完整偏好配置
  · sh memory set KEY VALUE — 随时调整单项偏好
```

---

### `sh memory add-campaign` 交互流程

```
$ sh memory add-campaign

── 登记营销活动 ─────────────────────────────────────────────

? 活动名称: 2026 三八大促
? 活动开始日期 (YYYY-MM-DD): 2026-03-08
? 活动结束日期 (YYYY-MM-DD): 2026-03-15
? 涉及渠道（逗号分隔，all=全部）[all]: 天猫,京东
? 活动目标或背景（简短描述，可跳过）: GMV 环比增长 20%，女装主推
? 备注（可跳过）:

── 活动预览 ─────────────────────────────────────────────────
  名称：2026 三八大促
  时间：2026-03-08 ~ 2026-03-15（8 天）
  渠道：天猫、京东
  目标：GMV 环比增长 20%，女装主推
  ID：  ACT003（自动生成）
─────────────────────────────────────────────────────────────

? 确认写入记忆？ [Y/n]: Y

✓ 活动已记录。
  大促期间（3/8-3/15）的所有分析，AI 将自动关联此活动背景。
  大促结束后可运行：
    sh analytics report campaign --id=ACT003
  生成完整活动复盘报告。
```

---

### 冷启动弱提示（无需 init 时的引导）

当用户从未执行过 `sh memory init` 时，在每次 `sh analytics` 系列命令结果底部显示一次（非阻断，每个 shell session 最多显示 1 次）：

```
─────────────────────────────────────────────────────────
 提示  当前为通用模式。运行 sh memory init（约 2 分钟）
       即可开启个性化 AI 体验，AI 将记住您的分析习惯。
─────────────────────────────────────────────────────────
```

**弱提示出现规则**：
- 每个进程生命周期内最多显示 1 次（不会每次分析都出现）
- 用户执行 `sh memory init` 后永久消失
- 用户可以 `sh memory set __hint_dismissed true` 永久关闭提示

---

## 信息架构（目录结构）

### 目录结构全景

```
~/.socialhub/memory/
├── user_profile.yaml              # L4 用户偏好层（个人，永久，不 git 提交）
├── business_context.yaml          # L4 业务上下文层（企业，可 git 提交）
├── analysis_insights/             # L3 语义记忆（90天有效，最多 200 条）
│   ├── INDEX.json                 # 洞察索引（避免每次扫描目录）
│   ├── 2026-04-02-channel-gmv.json
│   ├── 2026-03-26-rfm-analysis.json
│   └── ...（最多 200 个 JSON 文件）
└── session_summaries/             # L2 情节记忆（30天有效，最多 60 条）
    ├── INDEX.json                 # 会话摘要索引
    ├── 2026-04-02T09-30-00-abc123.json
    ├── 2026-04-01T14-20-00-def456.json
    └── ...（最多 60 个 JSON 文件）
```

---

### 文件详细说明

#### `user_profile.yaml`（L4 偏好层）

```yaml
# ~/.socialhub/memory/user_profile.yaml
# 个人分析偏好，不包含任何业务数据或客户信息
# 不应 git 提交（含个人工作习惯）

version: "1"
schema_version: "1.0"          # 用于 MemoryManager 版本兼容性检查
created_at: "2026-04-02T10:00:00Z"
updated_at: "2026-04-02T10:00:00Z"

role: "运营经理"

analysis:
  default_period: "7d"           # MVP 必须字段
  preferred_dimensions:          # MVP 必须字段
    - channel
    - category
  scope:
    channels:
      - 天猫
      - 京东
  rfm_focus:                     # v1.1 字段，缺失时不报错
    - At-Risk
    - Champions

output:
  format: "table"                # MVP 必须字段
  precision: 1
  include_yoy: true

skills:
  frequently_used: []            # v1.1 字段，AI 统计使用频率

_meta:
  hint_dismissed: false          # 是否关闭冷启动弱提示
  init_completed_at: "2026-04-02T10:00:00Z"
```

#### `business_context.yaml`（L4 业务上下文层）

```yaml
# ~/.socialhub/memory/business_context.yaml
# 企业级业务背景，可通过 git 在团队间共享
# 不包含任何个人信息或客户数据

version: "1"
schema_version: "1.0"
created_at: "2026-04-02T10:00:00Z"
updated_at: "2026-04-02T10:00:00Z"

business:
  primary_category: "服装"
  key_metrics:
    - GMV
    - 转化率
    - 客单价
    - 复购率
  fiscal_year_start_month: 1

campaigns:
  - id: "ACT001"
    name: "2026 三八大促"
    period_start: "2026-03-08"
    period_end: "2026-03-15"
    channels:
      - 天猫
      - 京东
    goal: "GMV 环比增长 20%，女装主推"
    effect_summary: ""              # 活动结束后由 AI 辅助填写
    notes: ""
    created_at: "2026-03-05T09:00:00Z"

baselines:                          # v1.1 字段，暂为空
  gmv_daily_avg_30d: null
  updated_at: null
```

#### `analysis_insights/INDEX.json`（洞察索引文件）

```json
{
  "version": "1",
  "last_updated": "2026-04-02T10:15:00Z",
  "total": 12,
  "entries": [
    {
      "id": "2026-04-02-channel-gmv",
      "file": "2026-04-02-channel-gmv.json",
      "created_at": "2026-04-02T10:15:00Z",
      "ttl_days": 90,
      "expires_at": "2026-07-01T10:15:00Z",
      "topic": "渠道 GMV 分析",
      "confidence": "high",
      "active": true
    }
  ]
}
```

索引文件的作用：MemoryManager 启动时只读 INDEX.json（O(1)），不扫描目录（避免在 200 文件场景下性能问题）。

#### `analysis_insights/{date}-{slug}.json`（单条洞察）

见业务设计文档 `02-business-design.md` 模型 3，结构不重复。

#### `session_summaries/INDEX.json` + `{session_id}.json`

类似洞察索引结构，TTL 30 天，最多 60 条。

---

### 文件权限与安全

| 文件 | 权限 | 原因 |
|------|------|------|
| `user_profile.yaml` | `0o600` | 个人偏好，仅本用户可读 |
| `business_context.yaml` | `0o600` | 企业上下文，防其他用户读取 |
| `analysis_insights/*.json` | `0o600` | 含聚合业务数据 |
| `session_summaries/*.json` | `0o600` | 含会话摘要 |
| `memory/` 目录 | `0o700` | 目录权限限制 |

全部文件使用**原子写入**（写入临时文件后 `os.replace()`），与现有 `session.py::SessionStore.save()` 模式一致。

---

## 非功能需求

### 性能需求

| 指标 | 目标值 | 测量方式 | 降级策略 |
|------|--------|---------|---------|
| 记忆加载时间（冷） | ≤ 150ms | `time.perf_counter()` 在 MemoryManager.load() 前后 | 超时则跳过记忆加载，以无个性化模式运行 |
| 记忆加载时间（热，INDEX 已缓存） | ≤ 50ms | 同上 | — |
| SYSTEM_PROMPT 构建时间 | ≤ 30ms | `build_system_prompt()` 内部计时 | — |
| 洞察写入时间 | ≤ 100ms | MemoryStore.write() 内部计时 | 写入失败不影响 AI 对话，记录错误日志 |
| 记忆注入 Token 消耗 | ≤ 4000 tokens | tiktoken 计数 | 按 L4 → L3 → L2 优先级裁剪，L1 工作记忆不裁剪 |
| 目录扫描启动开销 | O(1)（INDEX 文件） | 不遍历目录 | INDEX 损坏时降级为扫描目录（加警告日志）|

**性能设计决策**：

- **INDEX.json 缓存模式**：MemoryManager 不在每次 load 时扫描目录，而是读取 INDEX.json（单文件读取 ≈ 1ms）
- **懒加载 L2/L3**：user_profile（L4）在进程启动时加载；洞察和摘要在 AI 对话触发前才加载
- **Token 预算分配**：L4 偏好（~500 tokens）+ L4 上下文（~600 tokens）+ L3 洞察（~1800 tokens，最多 5 条）+ L2 摘要（~1100 tokens，最多 3 条）= ~4000 tokens 上限

---

### 可靠性需求

#### 记忆加载失败降级策略

| 故障类型 | 检测方式 | 降级行为 | 用户感知 |
|---------|---------|---------|---------|
| user_profile.yaml 不存在 | `Path.exists()` | 以无偏好模式运行，底部显示弱提示 | 看到引导提示 |
| user_profile.yaml 损坏（YAML 解析错误）| `yaml.safe_load()` 异常 | 忽略损坏文件，以无偏好模式运行，打印警告 | `[yellow]警告: 偏好文件损坏，已跳过。运行 sh memory init 重建。` |
| business_context.yaml 损坏 | 同上 | 忽略，以无业务上下文模式运行 | 同上警告，带文件路径 |
| INDEX.json 损坏 | JSON 解析异常 | 降级为目录扫描（O(n)），加 `[dim]` 级别警告 | 无感（仅性能略降） |
| analysis_insights/*.json 损坏 | JSON 解析异常 | 跳过损坏文件，继续加载其他洞察 | 无感 |
| 磁盘空间不足（写入失败） | `OSError` | 记录审计日志，返回失败，不影响当前对话 | 无感（当次洞察丢失，下次对话继续）|
| 记忆加载超时（> 500ms）| `asyncio.wait_for` 超时 | 中断加载，以无记忆模式运行，打印 `[dim]` 警告 | `[dim]记忆加载超时，本次使用通用模式[/dim]` |
| PII 扫描命中 | `_mask_pii()` 返回命中 | 整体丢弃该条记忆写入，记录审计日志 | 无感（用户不知道，仅审计日志可追踪）|

#### 写入失败保障

- 所有写入操作先写临时文件（同目录），成功后 `os.replace()` 原子替换
- `os.replace()` 失败（如跨卷移动）时 fallback 到直接写入，并记录警告
- 写入失败不抛出异常，只记录 `ai_trace.jsonl` 审计事件，不影响 AI 对话继续

#### 记忆数据完整性

- 每条写入记录 `content_hash`（SHA-256），用于审计追溯
- MemoryManager 不校验读取时的 content_hash（性能优先）
- `sh memory status` 可主动触发 hash 完整性验证（可选命令行选项 `--verify`）

---

### 安全约束

| 约束 | 实现 |
|------|------|
| 禁止写入 PII | 写入前调用 `trace.py::_mask_pii()` 扫描，命中则整体丢弃 |
| 文件权限 0o600 | 原子写入后立即 `os.chmod(path, 0o600)` |
| 内存中不缓存解密后的 PII | 记忆内容不含原始 PII，无需加密 |
| 不同步到 MCP Server | 记忆系统是 CLI-local，不经过网络 |
| 审计追踪 | 每次写入/删除操作记录到 `ai_trace.jsonl`（复用现有 TraceLogger）|

---

## 迭代记录（R1/R2/R3 对抗摘要及修正）

---

### R1 "挑剔用户" — 对抗与修正

**对抗问题 1：用户发现 AI 用了一条 2 个月前已过时的洞察给出错误建议**

> "AI 引用了 45 天前的渠道转化率数据给出了'重点投入天猫'的建议，但实际上业务格局已经完全变了（拼多多快速崛起）。用户怎么发现这个问题？发现后怎么纠正？"

**初始设计问题**：`sh memory list` 没有"新鲜度"标记，用户无法快速看出哪些洞察已经过时；删除操作不够直接，用户从发现问题到纠正路径太长。

**R1-1 修正**：

1. `sh memory list --type=insights` 在"新鲜度"列显示 `{N}天前`，超过 30 天标红警告
2. `sh memory list --stale` 快捷过滤：只显示超过 30 天的洞察
3. AI 在终端标注中明确标出 `age=45d ⚠️ 超过30天`，让用户在看到回答时就能察觉
4. `sh memory delete` 支持批量删除：`sh memory delete --older-than=60d --type=insights`

**纠正路径缩短为 3 步**：
```
$ sh memory list --stale                          # 发现过时洞察
$ sh memory delete --older-than=30d --type=insights  # 批量删除
$ sh analytics orders --period=30d --by=channel   # 重新分析，更新记忆
```

---

**对抗问题 2：`sh memory list` 输出 50 条记忆，用户如何快速找到特定记忆？**

> "50 条记忆在终端里显示是一面墙，用户根本不知道哪条是哪条，也无法快速定位到想要修改的那条。"

**初始设计问题**：`sh memory list` 缺乏有效的检索和过滤机制，只是按时间倒序列出。

**R1-2 修正**：

1. `--search="关键词"` 参数：在 topic/summary/key_findings 字段中全文匹配
2. `--type` 过滤：先缩小范围（只看 insights 或 summaries）
3. `--since=7d` 时间过滤：聚焦最近一段时间的记忆
4. 输出分页：默认每页 20 条（`--page=N`）
5. 输出中显示简短摘要（截断至 40 字），帮助用户快速识别

**快速定位路径**：
```
# 场景：找渠道相关的洞察
$ sh memory list --type=insights --search="渠道"
→ 通常返回 3-5 条，可以直接找到目标

# 场景：找 3 月份的会话摘要
$ sh memory list --type=summaries --since=2026-03-01
→ 按时间过滤后通常 5-10 条
```

---

**对抗问题 3：用户希望某条记忆"本次会话不用"（临时覆盖）**

> "用户今天要做一次全量季度复盘，不想被'默认 7 天'的偏好干扰。但他也不想改掉这个偏好，因为平时就是要用 7 天的。"

**初始设计问题**：没有"临时覆盖"机制，用户只能修改偏好再改回，体验差。

**R1-3 修正**：

1. `sh ai chat "..." --no-memory`：本次会话完全不注入记忆（最彻底的临时覆盖）
2. `sh ai chat "..." --memory-level=profile-only`：只用偏好层，不用洞察和摘要
3. **用户显式指定参数优先级高于记忆**：`sh analytics overview --period=90d` 时，`90d` 覆盖 `default_period: 7d`，记忆不被修改（现有逻辑，只需在文档中明确）
4. `--no-memory` 模式的终端提示清晰说明："本次对话不使用记忆，结束后也不写入新记忆"

---

### R2 "业务方" — 对照业务设计的对抗与修正

**对抗问题 1：业务设计中的"AI 建议偏好确认"机制在 CLI 界面如何实现（不能打断当前分析流程）**

> "业务设计要求 AI 检测到用户连续 3 次使用相同维度后，在终端提示'是否设为默认？[y/N]'。但这个 prompt 会出现在 AI 分析结果的中间，打断用户的阅读流程。怎么设计才不打断？"

**初始设计问题**：业务设计中的确认机制没有明确"提示出现的位置和时机"，容易被工程实现为阻断式弹窗。

**R2-1 修正**：

1. **提示位置**：AI 建议偏好确认提示，**只出现在当次对话完全结束后**（所有分析输出完毕，光标在命令行待输入状态），而不是打断在分析结果中间
2. **提示格式**（非阻断，可直接无视）：
   ```
   ──────────────────────────────────────────────────────
    💡 AI 建议  过去 3 次分析您都使用了渠道维度，
               是否将「渠道」设为默认分析维度？
               y=确认  n=忽略  s=30天内不再提示
   ──────────────────────────────────────────────────────
   > [用户在此输入 y/n/s，或直接运行下一条命令（自动视为 n）]
   ```
3. 如果用户直接运行下一条命令（而不是输入 y/n/s），**自动视为 n（忽略）**，不阻断
4. 提示需标注依据（"过去 3 次分析，最近一次：昨天"），避免误判

---

**对抗问题 2：活动背景注入（`sh memory add-campaign`）和 `heartbeat` 调度器如何联动？**

> "活动期间用户希望 heartbeat 自动生成的日报能关联活动背景，但 heartbeat 是独立调度运行的，它如何知道当前有活动在进行？"

**初始设计问题**：业务设计只说了 `add-campaign` 写入 business_context，但没有说明 heartbeat 任务在执行分析命令时是否会读取记忆，以及联动机制。

**R2-2 修正**：

1. **联动机制**：heartbeat 执行的任务命令最终走 `executor.py` → `build_system_prompt()` 路径，只要 `build_system_prompt()` 正确注入 business_context，heartbeat 任务自然获得活动背景

2. **heartbeat 任务中的活动关联**：当 heartbeat 执行 `sh analytics report` 系列命令时，SYSTEM_PROMPT 中已有活动上下文，AI 在报告中会自动关联活动

3. **无需特殊联动代码**：heartbeat 的命令执行路径和 `sh ai chat` 共享同一个 `build_system_prompt()` 函数，记忆注入是统一的

4. **用户操作建议（写入文档）**：在 `sh memory add-campaign` 成功写入后，提示用户：
   ```
   ✓ 活动已记录。heartbeat 调度的报告任务将自动关联此活动背景。
   ```

---

**对抗问题 3：度量指标（记忆命中率、偏好采纳率）如何从 CLI 工具层面收集？**

> "业务设计制定了'偏好重复说明率降低 80%'这类指标，但 CLI 工具是本地运行的，没有中央收集服务。这些指标怎么测量？"

**初始设计问题**：度量体系设计了业务价值指标，但没有说明"本地 CLI 工具如何实际采集这些数据"。

**R2-3 修正**：

1. **本地可采集指标**（写入 `ai_trace.jsonl`）：
   - 每次对话：记录注入了哪些记忆层（`memory_layers_injected: ["L4", "L3"]`）
   - 每次 AI 生成命令：标记参数是否来自记忆偏好（`param_source: "memory"` vs `"user"`）
   - 每次记忆写入：记录 `write_result: success/failed/pii_rejected`

2. **需用户主动操作的指标**（无法自动采集）：
   - `sh memory feedback` 命令（v1.1）：用户对上次 AI 回答打 1-5 分
   - NPS 问卷：每季度在 `sh memory status` 输出底部显示一次

3. **可通过日志分析的间接指标**：
   - 偏好重复说明率：统计 `ai_trace.jsonl` 中用户输入含偏好关键词（"按渠道"/"7天"等）且记忆中已有对应偏好的频率（需离线脚本分析，CLI 工具本身只记录原始数据）

4. **明确指标分层**（产品文档修正）：
   - **实时可采集**：洞察写入率、token 消耗、文件大小、注入失败率
   - **用户参与才可采集**：记忆命中主观感受、偏好采纳率
   - **需离线分析**：偏好重复说明率（从 trace 日志推导）

---

### R3 "工程师" — 可实现性对抗与修正

**对抗问题 1：`sh memory init` 的交互式问卷依赖 `typer.prompt()`，是否与现有 Typer 框架兼容？**

> "现有代码已大量使用 Typer，`sh memory init` 的多步交互式问卷是否可以用 `typer.prompt()` 实现？有没有坑？"

**现有代码验证**：`ai.py::ai_chat()` 中已使用 `typer.confirm("Execute this plan?", default=True)`，heartbeat.py 中无交互式 prompt，但 Typer 官方支持 `typer.prompt()` 和 `typer.confirm()`。

**R3-1 确认与注意事项**：

1. **兼容性确认**：`typer.prompt(text, default=None)` 与现有框架完全兼容，已有用例
2. **渐进式问卷实现**：每题用 `typer.prompt(default="")` + `if not answer: continue`，Ctrl+C 抛出 `typer.Abort()`，在 `except typer.Abort` 中保存已完成的答案
3. **多选题处理**：逗号分隔字符串解析，`[x.strip() for x in answer.split(",") if x.strip()]`
4. **注意事项**：
   - `typer.prompt()` 在 `--no-tty` 模式（如 CI 管道）下会失败，需要检测 `sys.stdin.isatty()` 并降级为 `--minimal` 模式
   - 列表选项的显示使用 `console.print()` 在 prompt 之前输出，而不是在 prompt 内（Typer prompt 不支持富文本）

**R3-1 修正**：在 `sh memory init` 命令实现中，冒头检测 TTY：
```python
if not sys.stdin.isatty():
    console.print("[yellow]非交互模式，跳过 init 问卷。请使用 sh memory set 手动设置偏好。")
    raise typer.Exit(0)
```

---

**对抗问题 2：记忆注入到 SYSTEM_PROMPT 的方案，与 `ai chat` 命令的无 session 路径如何统一？**

> "查看 ai.py 代码，`ai_chat()` 直接调用 `call_ai_api(query, api_key)`，没有 session 机制。记忆注入是要改 `call_ai_api()` 接口还是在调用前构建 SYSTEM_PROMPT？两条路径如何统一？"

**现有代码分析**：
- `call_ai_api(query, api_key)` 函数目前用 `prompt.py` 中的静态 `SYSTEM_PROMPT` 常量
- `main.py` 的 smart-mode 路径也调用同一个 `call_ai_api()`
- 目前没有 session 在 `ai chat` 中体现，注入必须在 SYSTEM_PROMPT 层

**R3-2 修正**：

1. **注入策略**：不修改 `call_ai_api()` 函数签名，而是在调用前构建好 SYSTEM_PROMPT，通过 `system_prompt` 参数传入：

   ```python
   # prompt.py 重构
   def build_system_prompt(memory_context: MemoryContext | None = None) -> str:
       base = STATIC_SYSTEM_PROMPT  # 原有静态内容
       if memory_context is None:
           return base
       return memory_context.inject(base)  # 在顶部或指定位置注入记忆
   
   # ai.py / main.py 调用点
   memory_ctx = MemoryManager.load()
   system_prompt = build_system_prompt(memory_ctx)
   response, _ = call_ai_api(query, api_key, system_prompt=system_prompt)
   ```

2. **`call_ai_api()` 修改**：增加可选参数 `system_prompt: str | None = None`，None 时使用默认静态常量，向后兼容

3. **统一路径**：`ai chat`、`main.py` smart-mode、heartbeat 执行的命令，全部走 `build_system_prompt(MemoryManager.load())` 同一路径

4. **无 session 路径的注意事项**：`ai chat` 目前无 session（每次对话独立），记忆注入是 SYSTEM_PROMPT 级别的（单次对话），不是 session 消息级别的——这完全可行，记忆注入不依赖 session

---

**对抗问题 3：`sh memory` 命令模块如何避免循环导入（memory 模块依赖 config，config 模块不能反向依赖 memory）？**

> "按照 CLAUDE.md 的架构原则，config.py 是基础层，不能被 memory 反向依赖。但 MemoryManager 需要读取 config（如存储路径、TTL 配置），cli/main.py 需要同时导入 config 和 memory。如何避免循环导入？"

**现有代码分析**：
- `cli/config.py` → Pydantic v2 Config 模型，`config.py` 不 import 任何 `cli/` 子模块
- `cli/commands/config_cmd.py` → import `cli/config.py`
- 需要新增 `cli/memory/` 模块

**R3-3 修正**：

**依赖方向**（严格单向）：
```
cli/config.py          ← 基础层（不依赖任何 cli/ 子模块）
    ↑
cli/memory/store.py    ← 读取 config，不被 config 反向依赖
    ↑
cli/memory/manager.py  ← 业务逻辑层
    ↑
cli/commands/memory_cmd.py  ← CLI 命令层（最外层，依赖 manager）
    ↑
cli/main.py            ← 入口，注册 memory_cmd.app
```

**具体措施**：

1. `cli/memory/` 是独立子包，内部 import 只允许向下（import config，不 import commands/）
2. `MemoryManager` 在 `__init__` 中通过 `from cli.config import load_config` 读取配置路径
3. `cli/ai/prompt.py` 中的 `build_system_prompt()` import `cli/memory/manager.py`，但 `manager.py` 不 import `prompt.py`（单向）
4. `cli/commands/memory_cmd.py` 是 CLI 入口层，只 import `cli/memory/manager.py`，不 import 其他命令模块
5. `cli/main.py` 中注册：`from .commands import memory_cmd`，`app.add_typer(memory_cmd.app, name="memory")`

**循环导入风险检查**：
- `config.py` ← `memory/store.py` ← `memory/manager.py` ← `commands/memory_cmd.py` ← `main.py` — 无循环
- `ai/prompt.py` ← `memory/manager.py` — prompt 依赖 memory，memory 不依赖 prompt — 无循环
- `commands/ai.py` 调用 `build_system_prompt()` — ai.py 依赖 prompt，prompt 依赖 memory — 单向，无循环

---

### 三轮对抗修正汇总表

| 编号 | 来源 | 问题 | 修正措施 | 影响章节 |
|------|------|------|---------|---------|
| R1-1 | 挑剔用户 | 过时洞察难以发现和纠正 | `--stale` 过滤 + `age=Nd ⚠️` 标注 + 批量删除命令 | CLI API 设计、个性化体验 |
| R1-2 | 挑剔用户 | 50 条记忆难以快速检索 | `--search` 全文搜索 + `--type` 过滤 + `--since` 时间过滤 + 分页 | CLI API 设计 |
| R1-3 | 挑剔用户 | 无临时覆盖机制 | `--no-memory` 和 `--memory-level` 参数 + 显式参数优先级规则 | CLI API 设计 |
| R2-1 | 业务方 | 偏好确认提示打断分析流程 | 提示移至对话完全结束后，可直接运行下一命令跳过 | 个性化体验、冷启动 UX |
| R2-2 | 业务方 | heartbeat 与活动背景联动不清晰 | 明确通过 `build_system_prompt()` 统一路径联动，无需特殊代码 | 信息架构、非功能需求 |
| R2-3 | 业务方 | 度量指标采集路径不明确 | 指标分为"实时可采集"/"用户参与"/"离线分析"三层，ai_trace 记录原始数据 | 非功能需求 |
| R3-1 | 工程师 | TTY 兼容性和渐进式问卷实现 | 冒头检测 `sys.stdin.isatty()`，非交互模式降级到 `sh memory set` | 冷启动引导 UX |
| R3-2 | 工程师 | 记忆注入与无 session 的 ai chat 如何统一 | `build_system_prompt(context)` + `call_ai_api(system_prompt=...)` 可选参数，向后兼容 | 信息架构、非功能需求 |
| R3-3 | 工程师 | 循环导入风险 | 严格单向依赖链：config → memory/store → memory/manager → commands/memory_cmd → main.py | 信息架构 |
