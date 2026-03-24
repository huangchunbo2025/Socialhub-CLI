# Scheduled Tasks (Heartbeat)

> The system checks this file hourly to execute pending scheduled tasks.
> Check time: Every hour on the hour

---

## Task Status Reference

| Status | Description |
|--------|-------------|
| `pending` | Waiting to execute |
| `running` | Currently executing |
| `done` | Completed |
| `paused` | Paused |
| `failed` | Execution failed |

---

## Scheduled Tasks

### 1. Daily Data Overview
- **ID**: daily-overview
- **Frequency**: Daily 09:00
- **Status**: `pending`
- **Command**:
  ```bash
  sh analytics overview --period=today
  ```
- **Description**: Morning business overview data
- **Output**: Console display

---

### 2. Daily Memory Archive
- **ID**: daily-memory-archive
- **Frequency**: Daily 23:00
- **Status**: `pending`
- **Actions**:
  - Summarize new content in Memory.md for the day
  - Update user habits to User.md
  - Clean up temporary records in Memory.md
- **Description**: Keep memory files organized

---

### 3. Weekly Report Generation
- **ID**: weekly-report
- **Frequency**: Weekly Monday 10:00
- **Status**: `pending`
- **Command**:
  ```bash
  sh analytics report --title="Weekly Analysis Report" --output=weekly_report.html
  ```
- **Description**: Auto-generate weekly data analysis report

---

### 4. Daily Channel Analysis Report
- **ID**: daily-channel-report
- **Frequency**: Daily 20:00
- **Status**: `pending`
- **Command**:
  ```bash
  sh analytics orders --by=channel && sh analytics report --title="Channel Analysis Report" --output=channel_report.html
  ```
- **Description**: Auto-generate channel analysis report daily at 8pm
- **AI Insights**: true

---

## Execution Log

| Time | Task ID | Status | Note |
|------|---------|--------|------|
| 2026-03-19 22:05 | daily-overview | done | Manual run |
| 2026-03-19 22:04 | daily-overview | failed | Manual run failed |
| 2026-03-19 22:02 | daily-overview | failed | Manual run failed |
| 2026-03-19 22:01 | daily-channel-report | failed | Manual run failed |
| - | - | - | No records |

---

## Add New Task Template

```markdown
### N. Task Name
- **ID**: task-id
- **Frequency**: Daily/Weekly/Hourly HH:MM
- **Status**: `pending`
- **Command**:
  ```bash
  sh <command>
  ```
- **Description**: Task description
```

---

## Heartbeat Check Record

| Check Time | Pending | Executed | Note |
|------------|---------|----------|------|
| 2026-03-19 22:01 | - | 1 | Task: daily-channel-report |

---

## Configuration

```yaml
heartbeat:
  enabled: true
  interval: 1h          # Check interval
  timezone: UTC
  notify_on_failure: true
  max_retries: 3
```

---

*Last updated: 2024-03-19*
*Next check: Waiting for trigger*
