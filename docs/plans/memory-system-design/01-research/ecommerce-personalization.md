# 电商 CLI 工具个性化记忆实践

> 调研日期：2026-04-02

---

## 业界案例分析

### Tableau — 角色感知个性化
- 用户属性函数（JWT 传入角色/地区/时区），仪表盘按角色自动过滤
- Tableau Pulse：指标订阅推送，用户可选择关注哪些 KPI
- **启示**：运营关注渠道、分析师关注 RFM、管理层关注 GMV — 记忆需按角色分层

### Metabase — Saved Questions 团队知识积累
- 个人查询可"发布"为团队可复用资产
- 支持查询嵌套引用（Saved Question 作为子查询）
- **启示**：个人分析结论 → 团队共享洞察 的升级路径

### dbt CLI — 本地偏好与项目配置分离
- `~/.dbt/profiles.yml`：个人环境偏好（dev target、schema 命名）
- 项目 `dbt_project.yml`：团队共享配置
- `dbt init` 交互式引导一次性收集偏好
- **启示**：个人偏好文件（`~/.socialhub/memory/`）与项目业务上下文分离

### ThoughtSpot / AI 分析助手 — 意图预测
- 基于历史查询模式预测下一步分析
- 跨会话记住"用户通常如何分析这个指标"
- **启示**：记忆不只是复现，而是预测和引导

### 电商个性化引擎（Algolia/MoEngage）— RFM 是核心语言
- RFM 分层是电商运营的通用语言（Champions/Loyal/At-Risk/...）
- 用户的"关注客群"是高度个性化的（有人只看 Champions，有人专注 At-Risk）
- **启示**：记忆用户关注的 RFM 细分群体是高价值偏好

---

## 最有价值的 10 种业务记忆类型（按价值排序）

| # | 记忆类型 | 示例值 | 核心原因 |
|---|----------|--------|---------|
| 1 | **默认时间窗口偏好** | `default_period: "7d"` | 每次查询必选，角色差异大（运营看周/管理层看月）|
| 2 | **核心指标关注集** | `key_metrics: [GMV, 转化率, 客单价]` | 决定"概览"命令的默认内容 |
| 3 | **默认分析维度偏好** | `preferred_dimensions: [channel, province]` | 同一问题对不同角色有截然不同的拆分需求 |
| 4 | **RFM 分层关注点** | `rfm_focus: [Champions, At-Risk]` | 用户只关注部分 RFM 群体，记住后自动聚焦 |
| 5 | **责任域过滤** | `scope: {channels: [天猫, 京东]}` | 区域/渠道运营每次查询都要手动过滤 |
| 6 | **报告格式与输出偏好** | `output: {format: table, precision: 1, yoy: true}` | 分析师要精确数字，管理层要趋势结论 |
| 7 | **历史分析洞察（Insight Log）** | `"渠道A在Q4 GMV占比超过60%"` | 避免重复踩坑，为 AI 提供分析基准 |
| 8 | **营销活动上下文** | `{id: ACT001, period: "2026-03-08~15", effect: "+15% GMV"}` | AI 能将指标波动关联活动背景，避免误判异常 |
| 9 | **异常基线与阈值** | `{gmv_daily_baseline: 500000, alert_drop_pct: 20}` | 智能判断哪些波动值得提醒 |
| 10 | **工作流快捷方式** | `aliases: {周报: "sh analytics report weekly --output=weekly.md"}` | 将每周固定报表固化为一键命令 |

---

## 用户偏好 vs 业务上下文 vs 分析结论 的区分

```
用户偏好（User Preferences）
  → 个人化，稳定，跨业务周期有效
  → 例：默认看7天数据、喜欢按渠道拆分、输出表格格式
  → TTL：长期（90天+）或永久

业务上下文（Business Context）
  → 企业级，团队共享，随业务演进缓慢变化
  → 例：主营品类、促销日历、核心 KPI 定义、RFM 标签映射
  → TTL：90天，团队共享

分析结论（Insight Log）
  → 时效性强，随时间失效，但积累形成知识库
  → 例：某次分析发现"女装品类在周末转化率高40%"
  → TTL：30天（近期高权重），之后降权保留
```

---

## 团队知识积累模式

### 个人 → 团队的升级路径

```
个人偏好文件（~/.socialhub/memory/user_profile.yaml）
    ↓ 用户手动"发布"
项目级业务上下文（~/.socialhub/memory/business_context.yaml）
    ↓ git commit + push
团队共享的业务知识库（git 仓库中的 memory/ 目录）
```

### 建议：区分个人文件和团队文件

```
~/.socialhub/memory/
├── user_profile.yaml          # 个人偏好（不 git 提交）
├── business_context.yaml      # 团队业务上下文（可 git 提交）
├── analysis_insights/         # 分析结论（可选择性 git 提交）
└── session_summaries/         # 会话摘要（个人，不提交）
```

---

## 冷启动设计建议

**问题**：新用户没有任何记忆，AI 首次对话完全陌生。

**方案**：`sh memory init` 交互式引导（参考 `dbt init`）

```
? 你主要关注哪个时间窗口的数据？ (7d/30d/90d) → 7d
? 你最常使用的分析维度是？ (channel/province/category) → channel, category
? 你的主要职责是什么？ (运营/分析/营销) → 运营
? 你的责任渠道范围？ (all/天猫/京东/...) → 天猫, 京东
```

一次交互写入 `user_profile.yaml`，后续对话即享有个性化体验。

---

## SocialHub 场景特化建议

1. **优先实现偏好层**（第1-6条记忆）：ROI 最高，实现最简单
2. **第7-8条（洞察 + 活动上下文）需 AI 自动提炼**：会话结束时触发
3. **第9条（异常基线）需用户手动配置**：不同企业差异太大，不适合 AI 自动推断
4. **第10条（工作流别名）可通过 `heartbeat` 调度器已有能力实现**

---

## 来源 URL

- https://help.tableau.com/current/pro/desktop/en-us/functions_functions_user.htm
- https://www.metabase.com/docs/latest/questions/sharing/answers
- https://docs.getdbt.com/docs/core/connect-data-platform/profiles.yml
- https://www.algolia.com/blog/ecommerce/ecommerce-personalization/
- https://moengage.com/blog/rfm-analysis/
