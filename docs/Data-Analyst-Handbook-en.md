# SocialHub.AI CLI Data Analyst Handbook

## A Practical Guide to Moving from Data Queries to AI-Driven Insight

---

**Version:** v1.0  
**Audience:** Data Analysts, Operations Analysts, BI Engineers  
**Last Updated:** April 2026  
**Prerequisites:** Basic command-line familiarity and a working understanding of core ecommerce metrics

---

## Table of Contents

1. [What This Handbook Helps You Do](#1-what-this-handbook-helps-you-do)
2. [Quick Start: Run Your First Analysis in 10 Minutes](#2-quick-start-run-your-first-analysis-in-10-minutes)
3. [Core Concepts: How the CLI Works](#3-core-concepts-how-the-cli-works)
4. [Daily Analysis Workflows](#4-daily-analysis-workflows)
5. [Advanced Analysis: The Art of Combining Commands](#5-advanced-analysis-the-art-of-combining-commands)
6. [Natural Language Mode: Let AI Build the Command Path](#6-natural-language-mode-let-ai-build-the-command-path)
7. [Multi-Turn Analysis: Ask AI Like You Would Ask a Teammate](#7-multi-turn-analysis-ask-ai-like-you-would-ask-a-teammate)
8. [Scheduled Jobs: Automate Recurring Analysis](#8-scheduled-jobs-automate-recurring-analysis)
9. [Skills: Extend Your Analytical Capability](#9-skills-extend-your-analytical-capability)
10. [Exports and Report Generation](#10-exports-and-report-generation)
11. [Direct MCP Database Access: Advanced SQL Workflows](#11-direct-mcp-database-access-advanced-sql-workflows)
12. [Troubleshooting](#12-troubleshooting)
13. [Scenario Quick Reference](#13-scenario-quick-reference)
14. [Appendix: Metric Definitions and Reporting Conventions](#14-appendix-metric-definitions-and-reporting-conventions)
15. [Conclusion](#15-conclusion)

---

## 1. What This Handbook Helps You Do

### What your current workflow may look like

- You spend 30 to 60 minutes every morning pulling data from BI systems, cleaning Excel files, and sending daily updates.
- A business stakeholder asks for repeat purchase rate by channel for last Wednesday, and you have to write SQL in StarRocks, wait for the query, and manually package the answer.
- A campaign recap requires five dashboards, multiple manual checks, and spreadsheet pivots before you can explain what happened.
- Leadership asks why GMV is down this week, and it takes several cuts of the data before the root cause is clear.

### What changes with this toolkit

```bash
# Get the daily topline view in under 30 seconds
sh analytics overview --period=today --compare

# Answer a retention question directly
sh analytics retention --days=7 --period=last_week

# Run a campaign recap in one command
sh analytics campaigns --campaign-id=C2026031 --include-roi

# Ask AI to investigate a decline
sh "GMV is down 15% versus last week. Analyze the likely drivers across channel, product, and customer segments."
```

This handbook shows you how to:
- Use the core analytics commands efficiently
- Turn natural-language requests into structured analytical workflows
- Automate daily and weekly reporting
- Extend your toolkit with Skills
- Run direct SQL workflows when a standard command is not enough

---

## 2. Quick Start: Run Your First Analysis in 10 Minutes

### 2.1 Install

```bash
pip install socialhub-cli

sh --version
# Expected output: SocialHub CLI v2.x.x
```

### 2.2 Configure

```bash
# Inspect your current config
sh config show

# Set MCP connection endpoints
sh config set mcp.sse_url "https://your-mcp-server/sse"
sh config set mcp.post_url "https://your-mcp-server/messages"
sh config set mcp.tenant_id "your-tenant-id"

# Authenticate if your organization uses OAuth
sh auth login
```

### 2.3 Run your first query

```bash
sh analytics overview --period=7d
```

Expected output includes:
- GMV and period-over-period change
- Order volume
- AOV
- New customers
- Active buyers
- Coupon redemption rate

If this command succeeds, you already have a functioning baseline environment for daily analysis.

---

## 3. Core Concepts: How the CLI Works

### 3.1 Two usage modes

The CLI supports two working styles.

**Mode 1: Command Mode**

```bash
sh analytics orders --period=30d --group=channel
```

Use this when:
- You know which metric set you want
- You need precise parameter control
- You want a repeatable query pattern

**Mode 2: Smart Mode**

```bash
sh "Analyze order trends by channel over the last 30 days"
```

Use this when:
- The problem is exploratory
- You are not sure which command path to use
- You need a multi-step analytical flow

### 3.2 Shared parameters

Most analytics commands support the same parameter pattern.

| Parameter | Meaning | Common Values | Default |
|---|---|---|---|
| `--period` | Time range | `today`, `7d`, `30d`, `90d`, `365d`, `ytd`, `last_week`, `last_month` | `30d` |
| `--compare` | Compare with previous period | flag | off |
| `--output-format` | Output format | `text`, `json`, `csv` | `text` |
| `--export` | File export path | local file path | none |

### 3.3 Output formats

```bash
sh analytics overview
sh analytics overview --output-format=json
sh analytics overview --output-format=json --export=./data/overview_20260402.json
```

Recommended use:
- `text` for interactive work in the terminal
- `json` for automation, archival, or downstream processing
- `csv` when the output is headed into spreadsheets

### 3.4 Command help

```bash
sh analytics --help
sh analytics orders --help
sh customers --help
```

Treat the built-in help system as the fastest way to confirm parameters, output structure, and valid combinations.

---

## 4. Daily Analysis Workflows

### 4.1 Business overview (`analytics overview`)

Use this for daily updates, weekly recaps, and monthly executive summaries.

```bash
sh analytics overview
sh analytics overview --period=today
sh analytics overview --period=7d --compare
sh analytics overview --period=ytd --compare
```

Key metrics typically included:
- GMV
- Orders
- AOV
- New customers
- Active buyers
- Points earned and redeemed
- Coupon redemption rate

### 4.2 Orders and sales analysis (`analytics orders`)

Use this for channel comparison, geographic splits, product performance, and returns.

```bash
sh analytics orders
sh analytics orders --period=30d --group=channel
sh analytics orders --period=30d --group=province
sh analytics orders --period=30d --group=product
sh analytics orders --period=30d --include-returns
sh analytics orders --period=30d --group=channel --include-returns --compare
```

Best practice: when GMV declines, start with `--group=channel`, then narrow the time range to `7d` to isolate the most recent change pattern.

### 4.3 Retention analysis (`analytics retention`)

Use this for repeat rate monitoring, cohort health, and retention-cycle diagnostics.

```bash
sh analytics retention
sh analytics retention --days=30
sh analytics retention --days=7,30,90
sh analytics retention --days=30 --comparison-period=90d
sh analytics retention --period=last_month --days=30,90
```

This output is most useful when paired with operating thresholds that your team agrees on in advance.

### 4.4 RFM segmentation (`analytics rfm`)

Use this to identify VIPs, growth segments, churn-risk customers, and inactive cohorts.

```bash
sh analytics rfm
sh analytics rfm --segment-filter=at-risk
sh analytics rfm --segment-filter=vip --top-limit=200
sh analytics rfm --segment-filter=at-risk --top-limit=500 --export=./data/at_risk_customers.csv
```

Typical segmentation labels:
- `vip`
- `loyal`
- `potential`
- `new`
- `at-risk`
- `sleeping`
- `lost`

### 4.5 Campaign analysis (`analytics campaigns`)

Use this for performance review, ROI measurement, and campaign-level attribution.

```bash
sh analytics campaigns
sh analytics campaigns --campaign-id=C2026031
sh analytics campaigns --name-filter="Double 11"
sh analytics campaigns --period=30d --include-roi
sh analytics campaigns --campaign-id=C2026031 --attribution-window-days=14
```

Core outputs usually include:
- Reach and reach rate
- Click-through rate
- Conversion rate
- Attributed GMV
- Coupon or points cost
- ROI

### 4.6 Anomaly detection (`analytics anomaly`)

Use this for daily inspection, peak-event monitoring, and early-warning workflows.

```bash
sh analytics anomaly
sh analytics anomaly --metric=gmv
sh analytics anomaly --metric=orders --sensitivity=3
sh analytics anomaly --period=7d --metric=gmv
```

Operational use case:
- Schedule a daily anomaly check before the workday starts
- Escalate only material exceptions
- Investigate with follow-on orders, campaign, and funnel views

### 4.7 Lifecycle funnel analysis (`analytics funnel`)

Use this to find where customers are dropping out of the lifecycle.

```bash
sh analytics funnel
sh analytics funnel --period=90d
```

Typical lifecycle flow:
- New
- First Purchase
- Repeat
- Loyal
- At-Risk
- Churned

### 4.8 LTV analysis (`analytics ltv`)

Use this when you need a longer-horizon value view by acquisition cohort, segment, or product behavior.

```bash
sh analytics ltv
sh analytics ltv --period=90d
sh analytics ltv --group=channel
```

This is especially useful for acquisition efficiency reviews and channel-quality comparisons.

---

## 5. Advanced Analysis: The Art of Combining Commands

### 5.1 Scenario: A complete peak-event recap

A strong peak-event review usually combines:
- `analytics overview`
- `analytics orders --group=channel`
- `analytics campaigns --include-roi`
- `analytics retention`
- `analytics anomaly`

The goal is not just to describe the event, but to explain:
- where the uplift came from
- what margin trade-offs were made
- whether the event created repeatable customer value

### 5.2 Scenario: Root-cause analysis for a GMV decline

A practical path:
1. Confirm the decline in the overview view.
2. Break down by channel.
3. Inspect campaign performance and inventory or returns effects.
4. Review funnel health and retention trends.
5. Ask Smart Mode to propose a ranked list of likely drivers.

### 5.3 Scenario: Tracking a new product launch

The minimum useful pack is:
- order trend
- product-level split
- customer mix
- campaign traffic and conversion
- anomaly checks during launch week

### 5.4 Scenario: Evaluating membership program health

Focus on:
- active member count
- points liability movement
- repeat purchase by member tier
- coupon or points redemption quality
- retention by member cohort

---

## 6. Natural Language Mode: Let AI Build the Command Path

### 6.1 When to use natural language mode

Smart Mode works best when:
- the question is broad
- the analytical path is not obvious
- you need multiple commands chained together
- you want a first pass before tightening the logic yourself

### 6.2 Prompting techniques that work

Good prompts usually specify:
- the time range
- the business question
- the dimensions you care about
- whether you want explanation, ranking, or next steps

Examples:

```bash
sh "Analyze the drivers of repeat purchase decline over the last 30 days. Prioritize channel, product category, and customer segment."

sh "Compare campaign efficiency for the last four weeks and identify which programs produced the highest incremental GMV."
```

### 6.3 How AI multi-step planning works

In practice, Smart Mode typically follows this pattern:
1. Understand the question.
2. Select candidate commands.
3. Execute them in sequence.
4. Summarize the results.
5. Recommend follow-up checks when needed.

You still own the judgment. AI accelerates the path to the answer, but analysts should validate the output before sharing it broadly.

### 6.4 Reusable prompt templates

- “Summarize the business trend over the last 7 days and highlight the top three changes.”
- “Explain the likely causes of the decline and rank them by confidence.”
- “Compare segment performance before and after the campaign.”
- “Generate a concise executive recap with risks and recommended actions.”

---

## 7. Multi-Turn Analysis: Ask AI Like You Would Ask a Teammate

### 7.1 Start a session

Use session mode when the question evolves over time and each step depends on the previous one.

```bash
sh chat start
```

### 7.2 Manage sessions

Keep a session when:
- the context matters
- the logic is layered
- you want to refine the question iteratively

End or reset a session when:
- the topic changes
- the time window changes materially
- you need a clean analytical path

### 7.3 Best practices for multi-turn work

- Keep each follow-up specific.
- Ask one analytical question at a time.
- Confirm assumptions before exporting a result.
- Treat the final answer as a draft until it is checked against underlying data.

---

## 8. Scheduled Jobs: Automate Recurring Analysis

### 8.1 Heartbeat scheduler overview

Heartbeat is designed for recurring analytical tasks such as:
- daily business snapshots
- anomaly detection
- scheduled exports
- recurring campaign summaries

### 8.2 Core usage

```bash
sh heartbeat list
sh heartbeat add --name=daily-overview --cron="0 8 * * *" --command="sh analytics overview --period=today --compare"
```

### 8.3 Cron quick reference

Use cron when the reporting rhythm is fixed:
- daily
- weekly
- monthly
- event monitoring windows

### 8.4 Natural-language scheduling

Use AI if you prefer describing the cadence in plain English:

```bash
sh "Create a daily 8 AM report that runs overview and anomaly detection and saves the output."
```

### 8.5 Peak-event monitoring

For major commercial events, schedule:
- frequent overview refreshes
- anomaly checks
- channel-level order splits
- campaign efficiency snapshots

---

## 9. Skills: Extend Your Analytical Capability

### 9.1 What Skills are

Skills package reusable business logic on top of the CLI:
- prompt guidance
- tool selection
- execution sequencing
- result validation

### 9.2 Discover and install Skills

Use Skills when the standard command set is not enough for a repeat use case.

Typical examples:
- campaign recap packaging
- churn-risk triage
- executive summary generation
- category-level merchandising review

### 9.3 Use Skills in practice

Skills are most valuable when they reduce repetitive analytical setup work and standardize how a team answers the same business question.

### 9.4 Skill safety

In a controlled enterprise setting, Skills should be:
- reviewed
- permission-bounded
- traceable
- versioned

This is what makes them reusable without losing governance.

---

## 10. Exports and Report Generation

### 10.1 Built-in export options

```bash
sh analytics overview --output-format=json --export=./exports/overview.json
sh analytics orders --output-format=csv --export=./exports/orders.csv
```

### 10.2 HTML report generation

Use HTML output when the deliverable needs to be shared in a management-friendly format.

### 10.3 Chart generation

Charts are useful when:
- the trend matters more than the raw table
- the audience is executive or cross-functional
- the report needs fast scanning rather than row-level inspection

### 10.4 Automated reporting

Pair exports with scheduled jobs to create:
- daily operational recaps
- weekly marketing reviews
- monthly leadership packs

---

## 11. Direct MCP Database Access: Advanced SQL Workflows

### 11.1 When direct MCP access makes sense

Use direct MCP access when:
- the standard command does not expose a needed slice
- you need custom joins or derived logic
- the question is exploratory and highly specific

### 11.2 Explore the schema

Start with discovery before writing large queries:
- inspect available tables
- confirm key fields
- identify join paths
- validate date and channel conventions

### 11.3 Execute SQL queries

Use direct SQL carefully and keep queries auditable.

```bash
sh mcp sql "SELECT channel, SUM(gmv) FROM orders WHERE order_date >= CURRENT_DATE - INTERVAL 30 DAY GROUP BY channel"
```

### 11.4 Reusable SQL analysis templates

Good templates usually cover:
- channel contribution
- product mix
- cohort retention
- LTV by source
- campaign attribution windows

Use SQL templates to accelerate thinking, not to bypass governance.

---

## 12. Troubleshooting

### 12.1 Connection issues

Check:
- MCP endpoints
- tenant ID
- authentication state
- network reachability

### 12.2 Data issues

Validate:
- date range selection
- metric definition
- grouping field
- comparison window
- filter scope

### 12.3 AI mode issues

If Smart Mode gives weak output:
- narrow the question
- specify the time window
- name the dimensions you want checked
- ask for ranked causes rather than a broad explanation

### 12.4 Practical shortcuts

- Start broad, then tighten.
- Export only once the logic is stable.
- Use direct commands for repeat tasks.
- Use AI mode for exploratory work.

---

## 13. Scenario Quick Reference

### Scenario A: Daily five-minute inspection

Start with overview, anomaly detection, and channel orders.

### Scenario B: Daily report at 9 AM

Automate overview export plus a short recap.

### Scenario C: Weekly business recap

Add channel, campaign, and retention sections.

### Scenario D: Monthly performance pack

Include cohort movement, LTV, and segment shifts.

### Scenario E: Peak-event preparation

Define baseline metrics, channel split, campaign windows, and alert thresholds.

### Scenario F: Peak-event live monitoring

Use overview, anomaly, and orders by channel in tighter intervals.

### Scenario G: Peak-event recap

Combine business overview, channel decomposition, campaign ROI, and retention impact.

### Scenario H: Churn warning and win-back

Use RFM plus retention to identify high-value at-risk cohorts.

### Scenario I: Campaign evaluation

Measure reach, conversion, cost, attributed GMV, and post-campaign behavior.

### Scenario J: Product analysis

Focus on product-level mix, order quality, returns, and repeat signals.

---

## 14. Appendix: Metric Definitions and Reporting Conventions

### A. Core metric definitions

At minimum, align the team on:
- GMV
- Orders
- AOV
- Active buyers
- New customers
- Retention rate
- LTV
- ROI

### B. Time-window conventions

Teams should explicitly agree on how they define:
- rolling windows
- calendar months
- YTD views
- campaign attribution windows

### C. Standard channel codes

Use a standard channel dictionary to avoid naming drift across reports.

### D. Quick command card

Keep a short set of analyst defaults for:
- overview
- orders
- retention
- RFM
- campaigns
- anomaly
- funnel
- exports

---

## 15. Conclusion

The value of this CLI is not just speed. Its real value is that it compresses the path from question to evidence to action.

For analysts, that means less time spent pulling data and formatting spreadsheets, and more time spent diagnosing the business, surfacing risk, and helping teams make better decisions.

Used well, this toolkit does not replace analytical judgment. It increases the scale, speed, and consistency of analytical work.
