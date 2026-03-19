# 定时任务 (Heartbeat)

> AI 每小时检查此文件，执行待处理的定时任务。
> 检查时间: 每小时整点

---

## 任务状态说明

| 状态 | 说明 |
|------|------|
| `pending` | 等待执行 |
| `running` | 正在执行 |
| `done` | 已完成 |
| `paused` | 暂停 |
| `failed` | 执行失败 |

---

## 定时任务列表

### 1. 每日数据概览
- **ID**: daily-overview
- **频率**: 每天 09:00
- **状态**: `pending`
- **命令**:
  ```bash
  sh analytics overview --period=today
  ```
- **说明**: 每日早间查看业务概览数据
- **输出**: 控制台显示

---

### 2. 每日 Memory 归档
- **ID**: daily-memory-archive
- **频率**: 每天 23:00
- **状态**: `pending`
- **动作**:
  - 总结当天 Memory.md 中的新增内容
  - 归纳用户操作习惯更新到 User.md
  - 清理 Memory.md 中的临时记录
- **说明**: 保持记忆文件整洁有序

---

### 3. 每周报告生成
- **ID**: weekly-report
- **频率**: 每周一 10:00
- **状态**: `pending`
- **命令**:
  ```bash
  sh analytics report --title="周度分析报告" --output=weekly_report.html
  ```
- **说明**: 自动生成上周数据分析报告

---


### 4. 每日渠道分析报告
- **ID**: daily-channel-report
- **频率**: 每天 20:00
- **状态**: `pending`
- **命令**:
  ```bash
  sh analytics orders --by=channel && sh analytics report --title="渠道分析报告" --output=channel_report.html
  ```
- **说明**: 每天晚上8点自动生成客户渠道分析报告
- **AI洞察**: true

---

## 执行日志

| 时间 | 任务ID | 状态 | 备注 |
|------|--------|------|------|
| 2026-03-19 22:05 | daily-overview | done | Manual run |
| 2026-03-19 22:04 | daily-overview | failed | Manual run failed |
| 2026-03-19 22:02 | daily-overview | failed | Manual run failed |
| 2026-03-19 22:01 | daily-channel-report | failed | Manual run failed |
| - | - | - | 暂无执行记录 |

---

## 添加新任务模板

```markdown
### N. 任务名称
- **ID**: task-id
- **频率**: 每天/每周/每小时 HH:MM
- **状态**: `pending`
- **命令**:
  ```bash
  sh <command>
  ```
- **说明**: 任务描述
```

---

## 心跳检查记录

| 检查时间 | 待执行任务数 | 执行任务数 | 备注 |
|----------|--------------|------------|------|
| 2026-03-19 22:01 | - | 1 | Task: daily-channel-report |

---

## 配置

```yaml
heartbeat:
  enabled: true
  interval: 1h          # 检查间隔
  timezone: Asia/Shanghai
  notify_on_failure: true
  max_retries: 3
```

---

*最后更新: 2024-03-19*
*下次检查: 等待下次触发*
