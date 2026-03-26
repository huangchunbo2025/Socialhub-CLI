# SocialHub.AI CLI — Data Analyst User Guide

**Audience:** Data analysts
**CLI prefix:** `sh` (shorthand for `python -m cli.main`)

---

## Table of Contents

1. [Getting Started](#1-getting-started)
2. [Core Concepts](#2-core-concepts)
3. [Schema Discovery](#3-schema-discovery)
4. [Business Health Monitoring](#4-business-health-monitoring)
5. [Customer Analytics](#5-customer-analytics)
6. [Revenue and Transaction Analytics](#6-revenue-and-transaction-analytics)
7. [Marketing Effectiveness](#7-marketing-effectiveness)
8. [Segment Analytics](#8-segment-analytics)
9. [Reports and Scheduled Tasks](#9-reports-and-scheduled-tasks)
10. [Run History and Reproducibility](#10-run-history-and-reproducibility)
11. [Natural Language Mode](#11-natural-language-mode)
12. [Quick Reference](#12-quick-reference)

---

## 1. Getting Started

### Connect to the analytics database

Most analytical commands require MCP mode — a direct connection to the SocialHub.AI warehouse (`das_demoen`).

```sh
sh mcp connect
```

Verify the connection is active:

```sh
sh mcp status
```

If you see `Connected` your commands will draw from the full warehouse. Without a connection, commands fall back to the API layer, which returns less data.

### Test your setup

```sh
sh analytics overview --period 7d
```

If this returns a KPI table, you are ready to go.

---

## 2. Core Concepts

### Time periods

All analytics commands accept a `--period` flag:

| Value | Meaning |
|---|---|
| `today` | Today only |
| `7d` | Last 7 days |
| `30d` | Last 30 days |
| `90d` | Last 90 days |
| `365d` | Last 365 days |
| `ytd` | Year to date |

You can also specify exact dates:

```sh
sh analytics orders --from 2026-01-01 --to 2026-03-31
```

### Output formats

Every analytics command supports `--output` to export results:

```sh
sh analytics overview --output overview.md        # Markdown report
sh analytics customers --output customers.csv     # CSV (spreadsheet-ready)
sh analytics rfm --output rfm.json               # JSON (structured)
```

Use `--format json` to print JSON to the terminal instead of a table.

### SQL visibility

If you want to see the exact SQL being run:

```sh
sh analytics orders --period 30d --show-sql
```

Full SQL traces for any past run are also available in `history show` (see §10).

### Data source layer

When available, commands query pre-aggregated summary tables (DWS/ADS layer) for speed. If those tables are unavailable, the command falls back to the raw detail layer. The output footer always tells you which source was used:

```
Source: dws_order_base_metrics_d
```

or

```
Source: dwd_v_order (DWS layer unavailable)
```

---

## 3. Schema Discovery

Use these commands when you need to understand what data is available before running an analysis.

### Browse by business domain

```sh
sh schema domains
```

Lists all 7 domains: activity, customer, order, coupon, points, messaging, recommendation — with their key tables.

### Search by keyword

```sh
sh schema search rfm
sh schema search coupon redeem
sh schema search pre-churn
sh schema search repurchase
```

Returns matching tables and fields with a plain-language explanation. Use this when you know the business concept but not the table name.

### Inspect a specific table

```sh
sh schema show ads_v_rfm
sh schema show dws_order_base_metrics_d
```

Output covers: table purpose, row grain, key dimensions, key metrics, caveats, and which CLI command uses this table.

### Inspect fields in a table

```sh
sh schema fields dws_customer_base_metrics
```

Shows each field with type, nullable status, category (dimension / metric / identifier / bitmap), and business meaning.

### Look up metric definitions

```sh
sh schema metrics               # list all canonical metric definitions
sh schema metrics churn         # definition for one metric
```

These are the authoritative definitions. If a number looks wrong, check here first.

---

## 4. Business Health Monitoring

### Overview dashboard

Get a snapshot of all major KPIs for a period, with prior-period comparison:

```sh
sh analytics overview --period 30d
sh analytics overview --period 30d --compare
```

Covers: GMV, order count, AOV, active customers, new customers, coupon redemption rate, points issued/consumed, message delivery rate. Metrics with more than 10% movement are highlighted.

Export as a shareable report:

```sh
sh analytics overview --period 30d --output pulse.md
```

### Anomaly detection

Scan daily business metrics for statistical outliers (mean ± 2σ):

```sh
sh analytics anomaly                              # GMV anomalies, last 7 days
sh analytics anomaly --metric orders --days 14   # order count, last 14 days
sh analytics anomaly --metric new_buyers          # new customer acquisition
```

Available metrics: `gmv`, `orders`, `aov`, `new_buyers`

Output ranks anomalies by severity. Each entry shows today's value, the normal range, and the first date the deviation appeared.

### AI health diagnosis

Get an AI-synthesized assessment of business health across all domains:

```sh
sh analytics diagnose
```

The command gathers data from overview, orders, customers, campaigns, and points, then returns:

- Top 1–3 actionable findings with supporting evidence
- Interpretation of what likely caused each finding
- Specific CLI commands to run next

Scope the diagnosis to a specific decision:

```sh
sh analytics diagnose --context "Evaluating three re-engagement campaign options for Q2"
sh analytics diagnose --context "Investigating why GMV dropped in the last two weeks"
```

Save the output:

```sh
sh analytics diagnose --output diagnosis.md
```

> Requires MCP connection and a configured AI API key.

---

## 5. Customer Analytics

### Customer base metrics

```sh
sh analytics customers --period 30d
```

Shows: total registered, total buyers, active buyers (ordered in period), member vs non-member split.

**Acquisition source breakdown:**

```sh
sh analytics customers --source
```

Shows which channels (WeChat, app, web, etc.) are bringing in new customers, with share %.

**Gender distribution:**

```sh
sh analytics customers --gender
```

Shows gender breakdown (Male / Female / Unknown) with share %.

### Customer lifecycle funnel

```sh
sh analytics funnel --period 30d
```

Maps customers across 6 stages: New → First Purchase → Repeat → Loyal → At-Risk → Churned. Shows headcount and conversion rate at each stage.

Use this to identify where customers drop off. A large gap between "New" and "First Purchase" is an acquisition quality problem. A large gap between "First Purchase" and "Repeat" is an onboarding problem.

### Retention analysis

```sh
sh analytics retention --days 7,14,30,60,90
```

Shows cohort survival at each day window: cohort size, retained count, and retention %. Adjust the window list to match your business cycle.

### RFM segmentation

```sh
sh analytics rfm                                  # full segment distribution
sh analytics rfm --segment high_value             # one segment only
sh analytics rfm --top 50                         # top 50 customers by RFM score
sh analytics rfm --segment at_risk --top 100 --output at_risk.json
```

Each segment row shows: headcount, average spend, average order count, average recency (days since last order).

`--top N` lists individual customers with their R, F, M values — useful for handing a target list to the loyalty team.

### Member-level analytics

```sh
sh members overview                               # total, active, buying, new, pre-churn, churned
sh members tier-distribution                      # headcount per loyalty tier
sh members growth --period 90d                    # new member trend by week
sh members churn                                  # pre-churn and churned count per tier
sh members at-risk                                # pre-churn members ranked by tier
sh members top --limit 50                         # top 50 members by lifetime spend
sh members upgrade-candidates                     # members closest to next tier threshold
sh members tier-transitions --period 90d          # net flow between tiers
```

### Cohort-based LTV

```sh
sh analytics ltv --period 365d
```

Shows average GMV per customer grouped by first-order month. Lets you compare whether newer cohorts are more or less valuable than older ones.

---

## 6. Revenue and Transaction Analytics

### Order metrics

```sh
sh analytics orders --period 30d
sh analytics orders --period 30d --compare         # vs prior 30 days
```

Shows: GMV, order count, AOV, new buyer count/GMV, returning buyer count/GMV, new buyer share %.

**Group by dimension:**

```sh
sh analytics orders --by channel
sh analytics orders --by province
```

**Return analysis:**

```sh
sh analytics orders --returns
```

Adds: gross orders, return orders, return rate %, net GMV, and return GMV by channel.

### Store-level performance

```sh
sh analytics stores --period 30d
```

Ranks stores by GMV with: order count, unique customers, repeat purchase rate, and delta vs prior period.

### Product and category analysis

```sh
sh analytics products --period 30d
```

Ranks product categories and products by revenue and order count, with period-over-period delta.

### Repurchase analysis

```sh
sh analytics repurchase --period 90d
```

Shows: repurchase rate %, median days from first to second order, distribution of first-to-second order timing.

**Category transition path:**

```sh
sh analytics repurchase-path --period 180d
```

Shows which product categories most reliably bring customers back for a second purchase.

---

## 7. Marketing Effectiveness

### Campaign funnel analysis

```sh
sh analytics campaigns --period 30d               # overview of all campaigns
sh analytics campaigns --id ACT2024Q4             # single campaign detail
sh analytics campaigns --id ACT2024Q4 --funnel    # conversion funnel
sh analytics campaigns --roi --period 90d         # attributed GMV per campaign
sh analytics campaigns --roi --id ACT2024Q4 --window 14   # 14-day attribution window
```

The funnel shows: participants → messages delivered → messages opened → coupons redeemed → orders → GMV, with conversion rate at each step.

**Canvas journey analysis:**

```sh
sh analytics campaigns --canvas ACT_CANVAS_001
```

For journey-based campaigns: shows per-node headcount, pass rate, and drop-off rate. Identifies which node lost the most customers.

**Campaign audience breakdown:**

```sh
sh analytics campaigns --id ACT2024Q4 --audience
```

Shows participant distribution by loyalty tier.

### Coupon effectiveness

```sh
sh analytics coupons --period 30d                  # base: issued, redeemed, expired, redemption rate
sh analytics coupons --roi                         # face value vs attributed GMV
sh analytics coupons --by-rule --period 90d        # per-rule GMV and ROI breakdown
sh analytics coupons --lift --period 30d           # coupon users vs non-users comparison
sh analytics coupons --anomaly                     # daily redemption spike detection
```

The `--anomaly` flag applies mean ± 2σ detection to daily redemption counts. A spike 3σ above baseline on a weekend with no active campaign is a potential misuse signal.

### Points program

```sh
sh analytics points --period 30d                   # earned, redeemed, expired, redemption rate
sh analytics points --breakdown                    # earn/redeem split by operation type
sh analytics points --daily-trend --period 90d     # day-by-day earn vs redeem chart
sh analytics points --expiring-days 30             # points expiring in the next 30 days: volume, value, members
```

**Churn risk export (points-based signal):**

```sh
sh analytics points --expiring-days 30 --at-risk-members --output churn_candidates.csv
```

Exports a member list with: customer code, points balance, expiry date, last order date — sorted by urgency. This file can be imported directly into the segment tool.

**Loyalty program overview:**

```sh
sh analytics loyalty
```

Enrollment rate, tier distribution, points liability in CNY equivalent.

### Message delivery quality

```sh
sh messages health                                 # per-channel: failure rate, bounce, unsubscribe
sh messages health --period 7d --trend             # daily trend with spike detection
sh messages template-stats --period 30d            # per-template: open, click, unsubscribe rates
sh messages attribution --period 30d --window 7    # message → purchase conversion rate
```

Threshold flags: failure > 5% / bounce > 2% / unsubscribe > 1% are highlighted in red.

`--trend` applies mean ± 2σ detection to daily failure rate per channel.

---

## 8. Segment Analytics

### View and manage segments

```sh
sh segments list                                   # all segments with size and status
sh segments get <group_id>                         # detail for one segment
sh segments preview <group_id>                     # sample members
sh segments export <group_id> --output members.csv
```

### Purchase behavior analysis

Analyze how customers in a segment actually buy:

```sh
sh segments analyze <group_id> --period 90d
```

Returns: buy rate, total GMV, AOV, orders per buyer, and a top 10 buyers list. If the segment exceeds 2,000 members the analysis runs on a sample, which is noted in the output.

```sh
sh segments analyze 12345 --period 90d --output segment_12345.json
```

### Segment overlap

Check whether two segments share members — useful for validating A/B test groups:

```sh
sh segments overlap --id1 101 --id2 205
```

Shows: members in A only, B only, intersection A∩B, union A∪B, Jaccard similarity coefficient. A Jaccard > 10% is flagged as a warning (test group contamination risk).

### Segment size trend

```sh
sh segments growth <group_id> --period 90d
```

Daily headcount trend for a segment over time.

---

## 9. Reports and Scheduled Tasks

### Standard report templates

All reports write a structured Markdown file with a metadata footer (run time, period, data source, command used).

```sh
sh analytics report weekly --output weekly_2026-03-26.md
sh analytics report monthly --output monthly_march.md
sh analytics report campaign --id ACT2024Q4 --output campaign_postmortem.md
sh analytics report loyalty --output loyalty_review.md
```

Each report covers all relevant domains for that context. The campaign post-mortem includes audience, messages, coupons, GMV attribution, and canvas funnel if applicable.

### Scheduled execution

Set up a task to run automatically on a cron schedule:

```sh
sh heartbeat list                                              # see existing tasks
sh heartbeat run <task_id>                                     # run a task manually
sh heartbeat setup                                             # Windows Task Scheduler setup instructions
```

Scheduled tasks survive terminal restarts. Failed runs log the error and are visible in `heartbeat list`.

---

## 10. Run History and Reproducibility

Every analytics command is automatically logged. Nothing needs to be configured.

### View recent runs

```sh
sh history list                   # last 20 runs
sh history list --limit 50        # last 50 runs
sh history list --status error    # only failed runs
```

### Inspect a past run

```sh
sh history show <run_id>
```

Shows: the full command, arguments, execution time, output artifact path, and the complete SQL trace. Use this to verify exactly which tables were queried and how metrics were computed.

### Rerun a past command

```sh
sh history rerun <run_id>
```

Re-executes the command with exactly the same arguments. Useful for repeating last week's analysis with identical logic.

---

## 11. Natural Language Mode

If you have a business question but are not sure which command to use, type it directly:

```sh
sh which customers haven't bought in 90 days but still have points expiring
sh show me the campaigns with the worst ROI last quarter
sh why did new customer acquisition drop in February
sh compare coupon ROI vs points multiplier effectiveness
```

The CLI maps your question to one or more commands, shows you the plan, and waits for your confirmation before executing.

Rules:
- The plan is always shown before anything runs — never silent execution
- For multi-step questions, a numbered plan is proposed with one confirmation
- The output is identical to running the mapped commands directly
- If the question is underspecified, the CLI asks for the missing parameter (date range, segment, channel, etc.)

---

## 12. Quick Reference

### Most common analyst workflows

**Morning health check:**
```sh
sh analytics overview --period 7d --compare
sh analytics anomaly --days 3
```

**Campaign post-mortem:**
```sh
sh analytics campaigns --id <id> --funnel
sh analytics campaigns --id <id> --roi --window 14
sh analytics report campaign --id <id> --output postmortem.md
```

**Churn risk identification:**
```sh
sh analytics funnel
sh analytics rfm --segment at_risk
sh analytics points --expiring-days 30 --at-risk-members --output churn_targets.csv
```

**Customer base deep-dive:**
```sh
sh analytics customers --period 30d
sh analytics customers --source
sh analytics customers --gender
sh members tier-distribution
sh analytics funnel
sh analytics retention --days 7,14,30,60,90
```

**Marketing ROI comparison:**
```sh
sh analytics campaigns --roi --period 90d
sh analytics coupons --roi --period 90d
sh analytics coupons --by-rule
sh analytics points --breakdown
sh analytics diagnose --context "Comparing coupon vs points ROI for Q1"
```

**A/B test validation:**
```sh
sh segments overlap --id1 <test_group> --id2 <control_group>
sh analytics campaigns --roi --id <campaign_A>
sh analytics campaigns --roi --id <campaign_B>
```

**Schema exploration (before a new analysis):**
```sh
sh schema search <keyword>
sh schema show <table_name>
sh schema metrics
```

---

### Common flags across all analytics commands

| Flag | Effect |
|---|---|
| `--period 30d` | Set the analysis window |
| `--from / --to` | Exact date range |
| `--output file.md` | Export to Markdown |
| `--output file.csv` | Export to CSV |
| `--output file.json` | Export to JSON |
| `--format json` | Print JSON to terminal |
| `--show-sql` | Show generated SQL |
| `--compare` | Add prior-period comparison |

---

### Metric definitions (quick reference)

| Metric | Definition |
|---|---|
| Active customer | Placed ≥ 1 order in the analysis window |
| New customer | First order date falls within the analysis period |
| Churn | Previously active; 0 orders in last 90 days |
| Pre-churn | Previously active; 0 orders in last 30–90 days |
| Redeem rate | Coupons used ÷ coupons issued in the period |
| Message success rate | Delivered ÷ sent |
| Points redemption rate | Points consumed ÷ points earned in the period |

Full definitions: `sh schema metrics`
