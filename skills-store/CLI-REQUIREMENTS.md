# SocialHub.AI CLI — Data Analyst Requirements

## Purpose

This document defines the product requirements for the SocialHub.AI CLI as a data analyst workbench.

The goal is to support the complete analyst workflow from raw data to business decision:

```
Data  →  Semantics  →  Analysis  →  Decision  →  Execution Feedback
```

At each stage the analyst needs a different form of support:

- **Data**: verified, consistently defined numbers from the right source layer
- **Semantics**: shared metric definitions; no tribal knowledge required
- **Analysis**: reproducible, explainable outputs with full SQL visibility
- **Decision**: AI-synthesized findings with supporting evidence, not just charts
- **Execution Feedback**: post-campaign measurement that closes the loop

This document guides product planning, command design, and acceptance criteria.

---

## Context

### Current baseline

Already implemented:

- Analytics commands covering customers, orders, coupons, points, messaging, campaigns, loyalty
- Schema explorer with domain map, table explain, field dictionary, metric definitions
- AI synthesis via `analytics diagnose` and natural-language smart mode
- Run history with full SQL trace and rerun capability
- Report templates: weekly, monthly, campaign post-mortem, loyalty review
- Statistical anomaly detection on daily business metrics
- DWS-first query policy with transparent fallback notation

### Key observation

The CLI has solid coverage for individual analytical questions. The gaps are in the higher-order workflow:

- No structured path from "I have a finding" to "here is my recommendation"
- Campaign effectiveness still requires manual cross-referencing of multiple outputs
- Churn signal construction requires combining several commands with no guided flow
- Decision-support synthesis lacks contextual scoping by the analyst

---

## Target user

### Primary user: Data Analyst

This document is written for a single user type: the data analyst at a retail or e-commerce company running CRM and loyalty programs on SocialHub.AI.

This analyst:

- Is comfortable in a terminal and writes SQL at a working level
- Is the person the business calls when a number looks wrong, a campaign needs validating, or a strategic decision requires evidence
- Produces outputs consumed by marketing managers, loyalty teams, finance, and senior leadership — but is not the decision-maker
- Works across customer, campaign, coupon, points, and messaging data daily
- Has no tolerance for clicking through dashboards to answer questions that should take one command

### Out of scope

- Platform engineers managing the warehouse
- Campaign managers executing campaigns
- Admin users reviewing skills in the store
- Developers publishing skills

---

## Product goals

1. Let analysts answer any recurring business question in a single command with consistent, governed results.
2. Let analysts discover the right domain, table, and metric without reading raw schema documentation.
3. Let analysts compose findings across domains into a structured, evidence-backed recommendation.
4. Let analysts produce shareable artifacts — reports, CSVs, Markdown — without additional tooling.
5. Ensure every analytical result is traceable: which tables, which SQL, which assumptions.
6. Close the execution feedback loop: after a campaign runs, the analyst can measure what changed.

## Non-goals

1. Replacing a BI platform or SQL notebook for exploratory modeling.
2. Turning the CLI into an unrestricted query console without governance.
3. Supporting arbitrary code execution against production data.
4. Generating PPTX or PDF reports (out of scope for current phase).

---

## Analyst workflow

The CLI must support this seven-stage workflow end-to-end:

1. **Frame the question** — the analyst starts with a business question, not a table name
2. **Discover the domain** — find the right data domain, tables, and metric definitions
3. **Select the approach** — choose a command, template, or natural-language framing
4. **Execute with visibility** — run with explainable parameters; see the SQL if needed
5. **Interpret the result** — understand what happened and why, not just the number
6. **Form a recommendation** — AI synthesis connects findings to a decision
7. **Measure the outcome** — after action is taken, measure the delta

---

## Functional requirements

### A. Schema discovery and semantic navigation

Analysts must be able to navigate the data warehouse without memorizing table names or layer conventions.

#### A1. Schema search

Analysts search by business keyword, not table name.

Examples:
- `schema search activity`
- `schema search rfm`
- `schema search coupon redeem`
- `schema search pre-churn`

Requirements:
- match across table names, field names, and descriptions
- return domain, layer, and a plain-language explanation of purpose
- surface the most relevant table for a business question

#### A2. Table explain

The CLI explains any table in analyst language.

Required output:
- what the table is for
- row grain
- key dimensions and metrics
- important caveats (e.g. bitmap fields, partitioning behavior)
- typical use cases
- which CLI command uses this table

#### A3. Field dictionary

The CLI shows field-level business meaning.

Required output:
- field type and nullable status
- business description
- category: dimension / metric / identifier / bitmap / control field

#### A4. Domain map

The CLI groups warehouse assets by business domain.

Required domains:
- activity (campaign / canvas)
- customer
- order / transaction
- coupon
- points
- messaging
- recommendation

#### A5. Metric definitions

The CLI surfaces standardized definitions for all business metrics.

Requirements:
- `schema metrics` lists all canonical metric definitions
- `schema metrics <name>` explains one metric: definition, formula, filters, source table
- Skills must not silently use different definitions

---

### B. Business performance monitoring

Analysts need a consistent, fast view of business health across all domains.

#### B1. Business overview

A single command covers all major KPIs for a given period.

Required output:
- GMV, order count, AOV
- active customers, new customers
- coupon redemption rate
- points issued and consumed
- message delivery rate

Requirements:
- current period vs prior same-length period, with delta and direction indicator
- metrics exceeding 10% delta are highlighted
- all metrics use canonical definitions (see §Governance)
- runs in under 10 seconds

#### B2. Statistical anomaly detection

The system detects abnormal movement in daily business metrics.

Requirements:
- covers minimum 7 metrics: GMV, order count, new customers, message failure rate, coupon redemption count, points issued, coupon-linked GMV
- uses mean ± 2σ baseline from the prior 30 days
- output ranks anomalies by deviation magnitude
- each anomaly shows: metric name, today's value, baseline range, first deviation date
- if no anomalies exist: output is one line

#### B3. AI diagnosis

The system synthesizes findings across all domains into a business health assessment.

Requirements:
- `analytics diagnose` runs all major analytics commands internally
- output is structured: Observation → Evidence → Interpretation → Recommended next command
- identifies top 1–3 actionable findings, not a list of all metrics
- analyst can scope synthesis: `analytics diagnose --context "<free text>"`
- the AI cites only numbers produced by commands run in the same session
- completes in under 45 seconds

---

### C. Customer analytics

Analysts need to understand who customers are, how they are changing, and where they fall off.

#### C1. Customer base metrics

Required output:
- total registered, total buyers, active buyers, member vs non-member split
- period-over-period delta for each

#### C2. Acquisition source analysis

Required output:
- acquisition channel breakdown: channel name, new customer count, share of total
- period filter support

#### C3. Gender distribution

Required output:
- gender breakdown with share %
- snapshot at latest available date

#### C4. Tier distribution

Required output:
- headcount and share per loyalty tier
- period-over-period delta

#### C5. Customer lifecycle funnel

Required output:
- headcount at each stage: New → First Purchase → Repeat → Loyal → At-Risk → Churned
- conversion rate from each stage to the next
- period-over-period comparison

#### C6. Retention analysis

Required output:
- cohort survival at configurable day windows (e.g. 7, 14, 30, 60, 90)
- cohort size and retained count per window

#### C7. RFM segmentation

Required output:
- segment distribution: headcount, average spend, average frequency, average recency per bucket
- `--segment <code>` to filter to a specific bucket
- `--top N` to list top-scoring customers with recency, frequency, monetary values

#### C8. Cohort-based LTV

Required output:
- average GMV per customer grouped by first-order month cohort
- enables trend comparison across cohorts

---

### D. Revenue and transaction analytics

Analysts need to decompose where revenue comes from and what drives change.

#### D1. Order metrics

Required output:
- GMV, order count, AOV, item quantity
- new buyer vs returning buyer split: count, GMV, share %
- campaign-linked order share vs organic

#### D2. Store-level performance

Required output:
- per-store: GMV, order count, unique customers, repeat purchase rate
- ranked by GMV with delta vs prior period

#### D3. Product and category analysis

Required output:
- revenue and order count by product category and product
- delta vs prior period

#### D4. Repurchase analysis

Required output:
- repurchase rate %
- median days from first to second order
- distribution of first-to-second order timing by decile

#### D5. Return analysis

When `--returns` flag is used:
- return rate by channel and product category
- gross GMV, return GMV, net GMV impact
- return rate above threshold (default >10%) is flagged

---

### E. Marketing effectiveness analytics

Analysts need honest answers to whether marketing spend drove incremental outcomes.

#### E1. Campaign funnel analysis

Required output:
- participants entered → messages delivered → messages opened → coupons redeemed → orders placed → GMV
- conversion rate at each step
- attribution window configurable (`--window N` days)

#### E2. Canvas per-node journey analysis

Required output:
- per-node: customers entered, customers passed, drop-off rate, rewards issued
- identifies the node with the highest drop-off

#### E3. Coupon effectiveness

Required output:
- issued, redeemed, expired, redemption rate %
- total face value, total attributed GMV
- `--roi`: per-rule breakdown — which coupon rules have the best GMV-to-face-value ratio
- `--anomaly`: daily redemption counts with SPIKE / OK flags

#### E4. Points program health

Required output:
- points earned, redeemed, expired, net balance
- redemption rate %
- `--breakdown`: earn and redeem split by operation type with counts and share %
- `--daily-trend`: day-by-day earn vs redeem chart across the period
- `--expiring-days N`: total expiring, estimated value, affected member count

#### E5. Message delivery quality

Required output:
- per-channel: sent, delivered, failed, opened, clicked counts and rates
- threshold flags: failure > 5%, bounce > 2%, unsubscribe > 1%
- `--trend`: daily delivery quality with mean ± 2σ spike detection per channel

#### E6. Template-level messaging performance

Required output:
- per-template: send volume, open rate, click rate, unsubscribe rate
- filterable by channel and period

---

### F. Segment analytics

Analysts need to understand and work with customer segments as analytical units.

#### F1. Segment size trend

Required output:
- segment headcount over time with period-over-period delta

#### F2. Segment purchase behavior

For a given segment, analyze its members as a purchasing cohort.

Required output:
- buy rate, GMV, AOV, orders per buyer within a configurable period
- top buyers list
- labeled as "sampled" if segment exceeds safe query size

#### F3. Segment overlap

Required output:
- shared member count between two segments
- Jaccard similarity coefficient
- Jaccard > 10% flagged as a warning (relevant for A/B test contamination checks)

---

### G. Predictive and decision support

Analysts need to move from explaining the past to supporting forward decisions.

#### G1. Churn risk target list

Required output:
- export: customer code, tier, points balance, expiry date, last order date, RFM segment
- sorted by urgency
- directly importable into the segmentation tool without column remapping

#### G2. Promotion dependency detection

The system identifies whether customers are conditioned to buy only during promotions.

Requirements:
- `analytics diagnose` checks: campaign-linked order share, non-campaign GMV baseline, coupon attach rate
- flags promotion dependency when campaign-linked share is high and non-campaign baseline is flat
- detection logic is stated explicitly in output so findings are auditable

#### G3. Contextual AI synthesis for decisions

Required capabilities:
- `analytics diagnose --context "<free text>"` scopes the AI synthesis to a specific decision
- AI output when given a comparison question is structured: Option A vs Option B, assumptions stated, recommendation with confidence
- AI identifies when it lacks sufficient data and names what additional analysis is needed
- recommended output includes specific CLI commands for the analyst to run next

---

### H. Report templates and recurring outputs

Analysts produce recurring deliverables that must be consistent across runs.

#### H1. Standard report templates

Required templates:
- `analytics report weekly` — all domains, period-over-period, Markdown output
- `analytics report monthly` — same coverage as weekly with monthly grain
- `analytics report campaign --campaign-id <id>` — audience, messages, coupons, GMV, canvas funnel if applicable
- `analytics report loyalty` — enrollment, tier distribution, points liability, program health

Requirements:
- every report includes a metadata footer: run time, period covered, data source, command used
- `--output <file.md>` produces a shareable artifact
- `--insights on` appends AI commentary when notable findings exist

#### H2. Scheduled execution

Requirements:
- scheduled tasks persist across sessions and survive terminal restarts
- failed scheduled runs log the error and are visible in `heartbeat list`
- `--insights on` on a scheduled run only appends AI commentary when anomalies are present

---

### I. Analysis infrastructure

#### I1. Run history and reproducibility

Every analytics run is logged automatically.

Required metadata:
- run ID, timestamp, command, arguments, full SQL trace, execution time, output artifact path

Required operations:
- `history list` — show recent runs
- `history show <run_id>` — full output including SQL trace
- `history rerun <run_id>` — re-execute identically

#### I2. Output formats

All analytics commands support:
- `--output file.md` — Markdown report
- `--output file.csv` — CSV export
- `--output file.json` — JSON structured output

#### I3. Natural-language routing

Analysts can ask questions in business language.

Examples:
- `sh which customers haven't bought in 90 days but still have active points`
- `sh show me the campaigns with the worst ROI last quarter`

Requirements:
- the CLI shows the commands it plans to run — never executes silently
- for multi-step questions, proposes a numbered plan and waits for confirmation
- produces identical output to running the mapped command directly
- asks for missing parameters when the question is underspecified

#### I4. SQL visibility

All analytics commands support `--show-sql` to display the generated query before or alongside output.

---

## Governance

### The metric contract

Every metric computed by the CLI must match this definition. Any deviation is a bug, not a variant.

| Metric | Definition |
|---|---|
| Active customer | Placed ≥ 1 order in the analysis window |
| Buyer | Placed ≥ 1 order in the analysis period |
| New customer | First order date falls within the analysis period |
| Churn | Previously active; 0 orders in last 90 days |
| Pre-churn | Previously active; 0 orders in last 30–90 days |
| ROI | (Campaign-attributed GMV − coupon cost − points cost) / total investment |
| Redeem rate | Coupons used ÷ coupons issued in the period |
| Message success rate | Delivered ÷ sent |
| Points redemption rate | Points consumed ÷ points earned in the period |

`schema metrics` is the authoritative source for all definitions.

### DWS-first query policy

Commands must prefer pre-aggregated summary layers over raw source tables. When a fallback to a lower layer is used, the output footer states: `"Source: <table> (preferred layer unavailable)"`. The analyst always knows which layer their number came from.

### SQL safety

- All user-supplied values are sanitized before SQL inclusion
- Order queries always filter `delete_flag = 0 AND direction = 0` unless returns are explicitly requested
- Commands never execute DDL or DML

---

## Acceptance criteria

### Schema and discovery

- Analyst can search `activity`, `rfm`, `churn`, `coupon redeem` and receive a relevant table with explanation
- Analyst can inspect any table and understand its grain without reading raw schema files
- `schema metrics` shows canonical definitions for all 9 core business metrics

### Analytics coverage

- Overview command covers all 7 KPIs with period-over-period delta in under 10 seconds
- Customer funnel shows 6 lifecycle stages with conversion rates
- Campaign command shows full participant → message → redemption → GMV funnel
- Anomaly detection scans ≥ 7 metrics and ranks findings by deviation magnitude
- `analytics diagnose` returns a structured recommendation in under 45 seconds

### Decision support

- `analytics diagnose --context "<text>"` produces a scoped recommendation with named supporting evidence
- Churn risk export is directly importable into the segment tool
- A/B test contamination is visible via segment overlap Jaccard score

### Reproducibility and governance

- Every analytics run is logged with full SQL trace
- Any past run can be re-executed identically via its run ID
- SQL for any command is inspectable via `--show-sql` or `history show`
- `schema metrics` definitions match what commands actually compute

---

## Prioritization

### P0

- Business overview with period-over-period across all domains
- Statistical anomaly detection on daily metrics
- AI diagnosis with scoped context support
- Customer lifecycle funnel and retention
- RFM segmentation
- Campaign funnel including canvas per-node
- Order metrics with new vs returning buyer split
- Coupon and points analytics
- Message delivery quality
- Schema explorer (search, explain, field dictionary, domain map, metrics)
- Run history (log, show, rerun)
- Markdown and CSV export
- Natural-language routing with plan display

### P1

- Store-level performance
- Product and category revenue
- Cohort-based LTV
- Repurchase rate and timing
- Segment purchase behavior analysis
- Segment overlap with Jaccard similarity
- Message template performance
- Points expiry risk with member export
- Standard report templates (weekly, monthly, campaign, loyalty)
- Scheduled task execution

### P2

- Return analysis
- Recommendation engine analysis
- Campaign comparison (`--compare-to`)
- Scheduled anomaly alerting with AI commentary
- Message attribution (message → purchase conversion)
- Promotion dependency detection in `diagnose`

---

## Non-functional requirements

| Requirement | Target |
|---|---|
| `analytics overview` | < 10 seconds |
| Single-domain query (orders, coupons, points) | < 8 seconds |
| `analytics anomaly` | < 20 seconds |
| `analytics diagnose` | < 45 seconds |
| Report template generation | < 30 seconds |
| `schema` commands (local registry) | < 1 second |
| Natural-language time-to-first-response | < 5 seconds |
| DWS fallback | Silent, with footer note |
| Database failure | Clear, actionable error message |
| Terminal output at 80 char width (core metrics) | Mandatory |
| Windows / macOS / Linux | Mandatory |

---

## Open questions

| # | Question | Owner |
|---|---|---|
| 1 | Should `diagnose` be opt-in due to high DB call count, or always available? | Product |
| 2 | What is the agreed definition of "attributed GMV" for campaign ROI? | Business |
| 3 | Should anomaly detection thresholds (2σ) be configurable per metric or per tenant? | Product |
| 4 | Are there domain-level access restrictions by analyst role? | Security |
| 5 | Can natural-language mode run without an external AI API key configured? | Platform |
