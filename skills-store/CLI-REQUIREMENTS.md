# SocialHub.AI CLI — Product Requirements

**Audience:** Data analysts working on customer, campaign, loyalty, and revenue data
**Scope:** CLI as the analyst's primary workbench within the SocialHub.AI CIP
**Version:** 2.0
**Date:** 2026-03-25

---

## The Core Idea

A data analyst in a modern CRM/loyalty business is not a report generator. Their real job is to move a business through a five-stage chain:

```
Data  →  Semantics  →  Analysis  →  Decision  →  Execution Feedback
```

At each stage they are providing a different form of value:

| Stage | What the analyst produces | Without the CLI |
|---|---|---|
| **Data** | Verified numbers from the right source | Manual SQL on unfamiliar tables |
| **Semantics** | Shared definitions everyone agrees on | Tribal knowledge; metric inconsistency |
| **Analysis** | Explanation of what happened and why | One-off charts; no trace |
| **Decision** | Evidence-backed recommendation | Verbal opinion; no supporting structure |
| **Execution Feedback** | Did the action work? | Post-hoc guess; attribution gap |

The CLI must support all five stages — not just the middle one.

---

## Who This Is For

### The Analyst Profile

This document is written from the perspective of a single user type: the **data analyst** at a retail or e-commerce company running CRM and loyalty programs on SocialHub.AI.

This analyst:

- Is comfortable in a terminal and writes SQL at a working level
- Is the person the business calls when a number looks wrong, a campaign needs validating, or a strategic decision requires evidence
- Produces outputs consumed by marketing managers, loyalty teams, finance, and the CEO — but is not themselves the decision-maker
- Works across customer, campaign, coupon, points, and messaging data daily
- Has no tolerance for clicking through dashboards to answer questions that should take one command

Their real frustration is not that analysis is hard. It is that **the infrastructure around analysis is broken**:

- The same metric is computed differently in different reports
- Running the same query twice produces different numbers with no explanation why
- Insight dies in a Slack message because there is no way to turn it into a scheduled, reproducible artifact
- The analyst knows the answer but has no formal way to attach it to the decision it supports

---

## Part I — Management Decision Analytics

> **Core goal: Answer one question — is the business healthy, and does something need to change?**

This is the top of the chain. The analyst is producing the signal that tells management whether to act. It must be fast, consistent, and comparable across time.

---

### Scenario 1.1 — KPI Health Check: Is the Business on Track?

**Business question:** "Give me one screen that tells me whether this week is better or worse than last week, across all dimensions."

The analyst runs:

```sh
sh analytics overview --period 30d
```

Output covers: GMV, order count, AOV, active customers, new customers, coupon redemption rate, points issued/consumed, message delivery rate. Each metric shows the current period value, prior period value, absolute delta, and a direction indicator (↑ ↓ →).

If anything has moved more than 10% in either direction, it is highlighted. The analyst does not need to decide which metrics to check — the overview is the contract.

**What the system must do:**
- All metrics in the overview are computed from consistent definitions (see §Governance)
- Prior period comparison uses the same-length window (30d vs prior 30d, not month-to-date vs full prior month)
- Output renders in under 10 seconds
- `--output weekly_pulse.md` produces a shareable Markdown artifact

---

### Scenario 1.2 — Growth Structure: Where Is Growth Coming From?

**Business question:** "GMV is up 12% but I don't know if that's sustainable. Is it new customers or returning ones? Is one channel carrying everyone else?"

The analyst decomposes:

```sh
sh analytics overview                          # total picture
sh analytics orders --period 30d              # new vs returning buyer split
sh analytics customers --source               # acquisition channel contribution
sh analytics stores --period 30d              # is one store driving the number?
```

The `orders` output separates new-buyer GMV from returning-buyer GMV, with counts and percentages. If 90% of GMV is returning buyers and new customer acquisition is flat, the growth is a retention effect, not expansion — a very different strategic implication.

**What the system must do:**
- `orders` output includes: total GMV, order count, new buyer count/GMV, returning buyer count/GMV, new buyer share %
- `customers --source` shows acquisition channel breakdown: channel name, new customer count, share of total new customers
- `stores` ranks by GMV with delta vs prior period
- All three run independently and compose naturally (no shared state or sequencing requirement)

---

### Scenario 1.3 — Risk Identification: Is the Promotions Cost Eroding Margins?

**Business question:** "We ran three campaigns this quarter. Did we actually generate incremental revenue, or did we give discounts to people who would have bought anyway?"

The analyst runs:

```sh
sh analytics coupons --period 90d --roi        # coupon cost vs attributed GMV
sh analytics points --period 90d --breakdown   # points cost by operation type
sh analytics campaigns --period 90d            # campaign participant conversion
```

If coupon redemption rate is high but attributed GMV per redemption is close to AOV — meaning customers who used a coupon spent roughly the same as they would have anyway — that is a flag for margin erosion. The analyst builds the case with numbers, not assertions.

**What the system must do:**
- `coupons --roi` includes: total face value issued, total redeemed, GMV in orders where a coupon was used, estimated incremental GMV (requires control group or time-based baseline)
- `points --breakdown` shows earn vs. redeem by operation type (purchase earn, promotion earn, redeem gift, redeem coupon, expired)
- Results are exportable to Markdown for inclusion in a strategy document

---

## Part II — Customer Intelligence

> **Core goal: Understand who customers are, how they are changing, and what they will do next.**

---

### Scenario 2.1 — Customer Structure: What Does the Base Look Like Today?

**Business question:** "How many real customers do we have, and are they the right kind?"

```sh
sh analytics customers --period 30d
sh analytics customers --gender
sh analytics customers --source
sh members tier-distribution
```

"Real customers" is not a single number. The analyst needs to see: total registered, total who have purchased at least once, total active in the last 30 days, member vs. non-member split, tier distribution, gender breakdown. Each number tells a different story about the health of the base.

**What the system must do:**
- `customers` shows: total registered, total buyers (period), active buyers (period), member vs. registered split
- `customers --gender` shows gender distribution with share % (from `ads_das_custs_gender_distribution_d`)
- `customers --source` shows acquisition channel breakdown (from `ads_das_custs_source_analysis_d`)
- `members tier-distribution` shows headcount and share per tier, with period-over-period delta

---

### Scenario 2.2 — Lifecycle Analysis: Where Do Customers Fall Off?

**Business question:** "We have a lot of new customers every month. Why aren't they becoming loyal?"

The analyst maps the lifecycle:

```sh
sh analytics funnel --period 90d
sh analytics retention --days 7,14,30,60,90
sh analytics ltv --period 365d
```

`funnel` shows the headcount at each stage: New → First Purchase → Repeat → Loyal → At-Risk → Churned. The analyst looks for the largest relative drop — if 40% of new customers never make a first purchase, that is an acquisition quality problem. If 60% of first-time buyers never buy again, that is an onboarding problem. They are different decisions.

`retention` shows the cohort survival curve. If 30-day retention is 45% but 60-day is 43%, retention stabilizes quickly — which means re-engagement campaigns need to fire in the first 30 days, not later.

**What the system must do:**
- `funnel` shows: headcount and % of prior stage at each lifecycle stage, with period-over-period comparison
- `retention` shows: cohort size, retained count, and retention % for each day window provided
- `ltv` shows: average GMV per customer by first-order month cohort, enabling trend comparison across cohorts
- All three commands support `--output` for Markdown or CSV export

---

### Scenario 2.3 — Customer Value: Who Are the High-Value Customers?

**Business question:** "If I had to protect one group of customers at all costs, who would it be?"

```sh
sh analytics rfm                              # RFM segment distribution
sh analytics rfm --segment high_value --top 50  # top 50 highest-scoring customers
sh members top --limit 50                     # top members by lifetime spend
```

`rfm` shows the segment distribution: how many customers are in each RFM bucket, their average spend, average order frequency, and average recency. The analyst immediately sees whether the "high value" segment is growing or shrinking quarter-over-quarter.

`rfm --top 50` lists the actual customers at the top of the scoring distribution — the ones a loyalty team should be calling, not emailing.

**What the system must do:**
- `rfm` segments are based on consistent R/F/M scoring definitions (see §Governance)
- `rfm --segment <code>` filters to a specific segment bucket
- `rfm --top N` lists customers ranked by combined RFM score with recency, frequency, and monetary values
- `members top` ranks members by lifetime spend (`dws_customer_base_metrics`) with tier, last order date, and total orders

---

### Scenario 2.4 — Churn and Retention: Who Is About to Leave?

**Business question:** "Which customers are showing early warning signs of churn, and what does their behavior look like before they leave?"

```sh
sh analytics funnel                           # how many are in at-risk stage today
sh analytics retention --days 30,60,90       # how quickly does active → silent happen?
sh analytics points --expiring-days 30 --at-risk-members --output churn_risk.csv
```

The `--at-risk-members` output is an action artifact — a list of customer codes that the campaign team can immediately import into a segment for a re-engagement campaign. The analyst is not just explaining churn; they are handing off a target list.

**What the system must do:**
- `funnel` shows pre-churn and churned headcount with % of total active base
- `points --at-risk-members` exports: customer code, points balance, expiry date, last order date — sorted by urgency
- The exported CSV is directly importable into the segmentation tool without column remapping

---

## Part III — Revenue and Transaction Analytics

> **Core goal: Understand where money comes from and what drives it.**

---

### Scenario 3.1 — Sales Structure Decomposition

**Business question:** "We know total GMV. Now break it apart until we find the driver."

```sh
sh analytics orders --period 30d
sh analytics orders --period 30d --by store
sh analytics products --period 30d
sh analytics repurchase --period 90d
```

The analyst decomposes revenue layer by layer: total → by store → by product category → by customer type (new vs. returning). At each layer they are looking for concentration risk and growth drivers. If one store accounts for 60% of GMV, that is a strategic risk. If one product category accounts for 80% of repeat purchases, that is a retention lever.

**What the system must do:**
- `orders` output: GMV, order count, AOV, new buyer GMV %, returning buyer GMV %
- `orders --by store` ranks stores by GMV, order count, unique customers, repeat rate
- `products` ranks categories and products by revenue and order count, with delta vs prior period
- `repurchase` shows: repurchase rate %, average days to second order, GMV contribution by first-time vs. repeat buyers

---

### Scenario 3.2 — Purchase Behavior Analysis

**Business question:** "How many times do customers buy per year? Is that number going up or down?"

```sh
sh analytics repurchase --period 365d
sh analytics repurchase-path --period 180d
sh analytics ltv --period 365d
```

`repurchase-path` shows the product category transition from first to second order — the categories that most reliably bring customers back. If "home goods" buyers return to "apparel" at a 40% rate but "apparel" buyers only return at 12%, the cross-sell direction matters for campaign design.

**What the system must do:**
- `repurchase` shows: % who bought more than once, median days to second order, distribution of days by decile
- `repurchase-path` shows: first-order category → second-order category transition matrix with frequency counts
- Results include sample size so the analyst can assess statistical reliability

---

### Scenario 3.3 — Returns and Loss Analysis

**Business question:** "Our net revenue is lower than gross. How much is returns? Which channels or products are driving it?"

```sh
sh analytics orders --period 30d --returns
sh analytics products --period 30d --returns
```

The `--returns` flag includes return orders (direction=1) in the analysis. The analyst sees: return rate by channel, return rate by product category, and the net GMV impact. A high return rate in one category against a low return rate in another tells a product quality story that becomes a sourcing decision input.

**What the system must do:**
- `orders --returns` shows: gross orders, return orders, return rate %, net GMV, return GMV by channel
- `products --returns` shows return rate per product/category alongside gross revenue
- Return rate thresholds can be set per command run for highlighting (default: >10% flagged)

---

## Part IV — Marketing Effectiveness Analytics

> **Core goal: Answer the honest question — did the marketing spend actually work?**

This is where most analytics teams fail. They measure activity (sends, clicks) instead of outcomes (incremental GMV, retained customers).

---

### Scenario 4.1 — Campaign Funnel Analysis

**Business question:** "We sent 80,000 messages. How many became orders? Where did we lose people?"

```sh
sh analytics campaigns --roi --campaign-id ACT2024Q4
sh analytics campaigns --canvas ACT2024CANVAS01
sh analytics report campaign --campaign-id ACT2024Q4 --output postmortem.md
```

`campaigns --roi` shows the full conversion funnel: participants entered → messages delivered → messages opened → coupons redeemed → orders placed → GMV. Each step shows the absolute count and the conversion rate from the prior step.

`campaigns --canvas` shows the per-node breakdown for journey campaigns: at each step, how many customers touched that node, how many passed it, and how many received a reward. The analyst identifies the specific node where most customers dropped off.

**What the system must do:**
- Campaign funnel covers all linked channels (SMS, WeChat, email, push) in a single view
- Per-node drop-off is calculated as (entered node − passed node) / entered node
- Attribution window is configurable (`--window 14` for 14-day post-campaign purchase window)
- Post-mortem Markdown report is structured for direct inclusion in a management review

---

### Scenario 4.2 — Coupon Effectiveness: Real Lift or Just Discount?

**Business question:** "We issued 12,000 coupons last month. Did they drive incremental orders, or did we discount existing intent?"

```sh
sh analytics coupons --period 30d
sh analytics coupons --period 30d --roi
sh analytics coupons --period 30d --anomaly
```

The analyst looks at: redemption rate (were coupons used?), face value vs. GMV in coupon-attributed orders (was the discount worth it?), and whether redemption rate spiked abnormally on certain days (a signal of misuse or reselling).

`coupons --anomaly` runs mean ± 2σ detection on daily redemption counts. A spike that is 3 standard deviations above baseline on a weekend, with no campaign active, is a reselling signal.

**What the system must do:**
- `coupons` base output: issued, redeemed, expired, redemption rate %, total face value, attributed GMV
- `coupons --roi` adds per-rule breakdown: which coupon rules have the best GMV-to-face-value ratio
- `coupons --anomaly` shows daily redemption counts with SPIKE / OK flags and identifies abnormal dates

---

### Scenario 4.3 — Points Program Health

**Business question:** "Is our points program healthy, or are we accumulating liability without driving behavior?"

```sh
sh analytics points --period 30d
sh analytics points --daily-trend --period 90d
sh analytics points --breakdown
sh analytics points --expiring-days 30
sh analytics loyalty
```

`points --breakdown` shows earn vs. redeem by operation type. If 80% of points are earned through purchases but only 20% are ever redeemed, the program has a low perceived value problem — customers are not motivated by points. If redemption is high but almost all redeems go to discounts (not experiences), that signals a transactional program that does not build loyalty.

**What the system must do:**
- `points` base: earned, redeemed, expired, net balance, redemption rate, active members
- `points --daily-trend` shows day-by-day earn vs redeem bars across the period
- `points --breakdown` shows earn/redeem split by operation type with counts and share %
- `points --expiring-days N` shows: total expiring, estimated CNY value, affected members
- `loyalty` shows points liability in CNY equivalent alongside enrollment and tier metrics

---

### Scenario 4.4 — Channel Reach Quality

**Business question:** "Which channels are actually reaching customers, and which ones are wasting send budget?"

```sh
sh messages health --period 30d
sh messages health --trend --period 30d
sh messages template-stats --period 30d --limit 30
sh messages attribution --period 30d --window 7
```

`messages health` ranks channels by failure rate, open rate, and click rate. A channel with 98% delivery but 0.3% open rate means messages are arriving but being ignored — a content or audience-fit problem. A channel with 15% failure rate is an infrastructure problem.

`messages attribution` answers the hardest question: did message recipients actually buy more? It compares the purchase rate of messaged customers vs. a baseline, within the attribution window.

**What the system must do:**
- `health` shows channel-level metrics with threshold flags: failure > 5%, bounce > 2%, unsubscribe > 1%
- `health --trend` outputs daily table with SPIKE / OK per day (mean ± 2σ on failure rate)
- `template-stats` ranks by volume with open rate, click rate, unsubscribe rate per template and channel
- `attribution` shows: messages sent, recipients, purchasers in window, conversion rate, attributed GMV

---

### Scenario 4.5 — A/B Test Readout

**Business question:** "We ran two versions of a campaign. Which one won, and by how much?"

The analyst compares two campaign IDs or two segments:

```sh
sh analytics campaigns --roi --campaign-id ACT_A
sh analytics campaigns --roi --campaign-id ACT_B
sh segments overlap --id1 <segment_A> --id2 <segment_B>   # confirm groups are distinct
```

They manually compare conversion rates, GMV per participant, and coupon cost per acquired order. The `segments overlap` check confirms the test and control groups were not contaminated (Jaccard similarity should be near 0).

**What the system must do:**
- Campaign metrics are comparable across runs (same metric definitions, same attribution logic)
- `overlap` output makes contamination visible: a Jaccard > 10% between test and control is flagged as a warning
- Both campaign outputs support `--output` to produce side-by-side Markdown tables

---

## Part V — Predictive and Intent Analytics

> **Core goal: Shift from explaining the past to anticipating the future.**

This is where the CLI's AI layer becomes a first-class participant, not just a formatting layer.

---

### Scenario 5.1 — Purchase Intent Signals

**Business question:** "Which customers are showing intent to buy but haven't converted yet?"

```sh
sh analytics rfm --segment high_recency_low_frequency   # recently active, not yet buying
sh analytics funnel                                      # how many are stuck at "active not buying"
sh analytics diagnose                                    # AI synthesis of intent signals
```

`diagnose` runs all major analyses, passes the aggregated results to the AI, and returns a synthesized view that identifies: which cohort is most likely to convert with minimal incentive, which cohort needs a stronger trigger, and which is unlikely to convert regardless of campaign intensity.

**What the system must do:**
- `diagnose` must identify top 1–3 actionable findings, not a list of all metrics
- Each finding must include the supporting evidence (which metric, which direction, which magnitude)
- The output ends with a "Recommended actions" section listing specific CLI commands the analyst should run next
- `diagnose` completes in under 45 seconds

---

### Scenario 5.2 — Churn Risk Prediction

**Business question:** "Which active customers are most likely to churn in the next 30 days?"

```sh
sh analytics funnel                              # current at-risk headcount
sh analytics retention --days 30,60             # how fast does active → churn happen?
sh analytics points --expiring-days 30 \
  --at-risk-members --output churn_candidates.csv
sh analytics rfm --segment at_risk
```

The combination of "points expiring soon" + "in at-risk RFM segment" + "no purchase in 45 days" is a strong churn signal composite. The analyst builds the case layer by layer and exports the intersection as a target list.

**What the system must do:**
- `--at-risk-members` export includes: customer code, tier, points balance, expiry date, last order date, RFM segment
- The analyst can combine outputs from multiple commands using customer code as the join key in their own tools
- Export format is CSV by default and JSON with `--output file.json`

---

### Scenario 5.3 — Promotion Dependency Detection

**Business question:** "Are we training customers to only buy when there is a discount?"

```sh
sh analytics orders --period 180d               # order volume trend
sh analytics coupons --period 180d --roi        # how much of GMV has a coupon attached?
sh analytics campaigns --period 180d            # what % of orders are campaign-linked?
sh analytics diagnose
```

If GMV is flat on non-campaign weeks but spikes sharply during promotions, the business is creating purchase dependency. The analyst quantifies this: "62% of orders in the last quarter were placed by customers who used a coupon or were enrolled in an active campaign."

**What the system must do:**
- `orders` output includes: campaign-linked order % vs. non-campaign order %
- `diagnose` specifically checks for promotion dependency pattern (high campaign-linked share + flat non-campaign baseline) and flags it as a risk
- Output includes a definition of the detection logic so the finding is auditable

---

### Scenario 5.4 — Customer Upgrade / Downgrade Prediction

**Business question:** "Which Silver members are close to upgrading to Gold, and which Gold members are at risk of dropping?"

```sh
sh members tier-distribution
sh members tier-transitions --period 90d
sh analytics rfm --segment silver_high_frequency
```

`tier-transitions` shows the flow between tiers — how many customers moved up, stayed, and fell down last quarter. Combined with the `rfm` filter, the analyst identifies the Silver members whose spend is tracking toward Gold threshold but who have not been incentivized to cross it.

**What the system must do:**
- `members tier-transitions` shows: upgrade count, downgrade count, stable count per tier, and net flow
- Transition data is period-filterable to identify whether the trend is improving or worsening
- Combined with RFM filter, the analyst can produce a "near-threshold" member list for targeted incentive design

---

## Part VI — Decision Intelligence

> **Core goal: Move from analysis to recommendation. The analyst is a decision partner, not a report printer.**

---

### Scenario 6.1 — Strategy Attribution

**Business question:** "Last quarter we ran three campaigns, changed the coupon policy, and increased points multipliers. Which of these actually drove the improvement in retention?"

```sh
sh analytics report campaign --campaign-id Q3_REENG
sh analytics report campaign --campaign-id Q3_NEWMEMBER
sh analytics report loyalty --period 90d
sh analytics diagnose
```

The analyst builds a timeline: when each initiative launched, what changed in the metrics, and whether the timing is consistent with the hypothesized cause. `diagnose` runs the synthesis and identifies which initiative correlates most strongly with the metric improvement.

**What the system must do:**
- All report outputs include exact date ranges so the analyst can align them with initiative timelines
- `diagnose` output explicitly mentions which metrics changed and in which time window relative to campaign launches
- The analyst can pass a natural language context string to `diagnose`: `sh analytics diagnose --context "Q3 ran three campaigns and points multiplier change in August"`

---

### Scenario 6.2 — Scenario Comparison

**Business question:** "Should we issue more coupons or increase points multipliers to hit the retention target? Which has better ROI?"

```sh
sh analytics coupons --period 90d --roi
sh analytics points --period 90d --breakdown
sh analytics loyalty --period 90d
sh ai chat "Compare the ROI of coupon campaigns vs points multiplier programs based on the last 90 days of data"
```

The analyst uses the AI chat interface for the synthesis question — not because the AI knows the answer, but because it can reason over the outputs of the three previous commands and produce a structured comparison. The analyst verifies the inputs and the logic before presenting.

**What the system must do:**
- `ai chat` is available as an explicit analytical conversation layer, not just a routing tool
- When given a comparison question, `ai chat` structures the response as: Metric A (coupon path) vs. Metric B (points path), assumptions stated, recommendation with confidence
- The AI identifies when it does not have enough data to compare and tells the analyst what additional analysis is needed

---

### Scenario 6.3 — Budget and Investment Prioritization

**Business question:** "We have budget for one re-engagement campaign this quarter. Should we target pre-churn customers, lapsing Gold members, or new customers who haven't made a second purchase?"

```sh
sh analytics funnel                               # how many in each cohort?
sh analytics retention --days 30,60,90           # which cohort responds best?
sh analytics rfm --segment pre_churn
sh analytics rfm --segment new_buyer_no_repeat
sh members tier-distribution                     # Gold lapsing count
sh analytics diagnose --context "Evaluating three re-engagement target cohorts for Q2 budget"
```

The analyst quantifies each cohort: size, estimated conversion rate based on historical response, revenue per convert, and estimated cost (coupon + message cost per person). `diagnose` synthesizes into a prioritized recommendation with the reasoning visible.

**What the system must do:**
- `diagnose --context` accepts a free-text string that scopes the AI synthesis
- Synthesized recommendation includes: recommended cohort, estimated reach, expected conversion rate basis, estimated GMV lift
- All estimates are flagged as estimates with the methodology stated (e.g., "based on prior campaign conversion rates from analytics campaigns history")

---

### Scenario 6.4 — Risk Assessment Before a Campaign Launch

**Business question:** "Before we launch this win-back campaign with heavy discounts, what could go wrong?"

```sh
sh analytics coupons --period 180d --anomaly     # any prior misuse patterns?
sh analytics customers --source                  # is the target cohort from a low-quality source?
sh analytics diagnose --context "Assessing risk of a heavy-discount win-back campaign on pre-churn segment"
```

`diagnose` in risk-assessment mode looks for: prior coupon abuse signals, segments with high return rates (discount seekers), channels with high unsubscribe rates (message fatigue risk), and whether the target cohort has responded well to prior campaigns.

**What the system must do:**
- `diagnose` recognizes risk-assessment context and structures output as: Identified risks, Evidence, Mitigation options
- Risk output is exportable to Markdown for inclusion in a campaign brief

---

## Part VII — Real-Time Operations Monitoring

> **Core goal: Catch the problem while there is still time to act.**

---

### Scenario 7.1 — Anomaly Detection: Something Just Broke

**Business question:** "We launched a campaign two hours ago. Is anything behaving abnormally?"

```sh
sh analytics anomaly --period 7d
sh messages health --trend --period 7d
sh analytics coupons --period 7d --anomaly
```

`analytics anomaly` scans all daily metrics and flags those more than 2 standard deviations from baseline. If message failure rate spiked today, or coupon redemptions are 4× normal, the analyst sees it in one command.

**What the system must do:**
- `anomaly` covers: GMV, order count, new customers, message failure rate, coupon redemption count, points issued — minimum 7 metrics
- Output ranks anomalies by deviation magnitude (most severe first)
- Each anomaly includes: metric name, today's value, baseline range (mean ± 2σ), first anomaly date
- If no anomalies exist: output is one line — no scrolling through empty results

---

### Scenario 7.2 — Live Campaign Monitoring

**Business question:** "Our campaign has been live for 3 days. Is it performing as expected at the halfway point?"

```sh
sh analytics campaigns --roi --campaign-id ACT2024Q4
sh messages health --period 3d
sh analytics coupons --period 3d
```

The analyst compares mid-campaign actuals against the pre-campaign plan. If message delivery is 94% but open rate is 40% below the historical benchmark for this channel, the campaign creative may need adjustment while there is still time.

**What the system must do:**
- All campaign analytics commands work on partial date ranges (the campaign does not need to be over)
- `campaigns --roi` shows progress against estimated targets if a target was configured at campaign creation
- Results can be compared to a prior campaign with `--compare-to <campaign_id>`

---

### Scenario 7.3 — Scheduled Anomaly Alerting

**Business question:** "I don't want to run anomaly detection manually every morning. Alert me when something is wrong."

```sh
sh heartbeat schedule \
  --name "Daily Anomaly Alert" \
  --cron "0 8 * * *" \
  --command "analytics anomaly --period 7d --output ~/alerts/anomaly_$(date +%Y%m%d).md" \
  --insights on
```

If the scheduled run detects anomalies, `--insights on` appends an AI-written summary: "Two metrics flagged today: message failure rate is 3.2σ above baseline (first deviation: yesterday at 14:00), and coupon redemptions on WeChat are 2.7σ above baseline. Possible causes: ..."

**What the system must do:**
- Scheduled tasks persist across sessions and survive terminal restarts
- `--insights on` only appends AI commentary when anomalies are present (no output on clean days unless `--always-comment` is set)
- Failed scheduled runs log the error; the analyst sees failure in `sh heartbeat list`

---

## Part VIII — Analysis Modes

The scenarios above can be approached in four different ways depending on the analyst's goal and time budget.

### Mode 1 — Structured Command (Primary)

Used when the analyst knows what they want. Direct, fast, scriptable.

```sh
sh analytics orders --period 30d --output orders.csv
sh analytics rfm --segment high_value --top 20
sh segments analyze 12345 --period 90d
```

Every command has `--period`, `--output`, and `--format` options. Results are reproducible. SQL is inspectable via `--show-sql` or `sh history show`.

### Mode 2 — Natural Language (For Exploration)

Used when the analyst has a business question but does not know which command maps to it.

```sh
sh which customers haven't bought in 90 days but still have active points
sh show me the campaigns with the worst ROI last quarter
sh why did new customer acquisition drop in February
```

The CLI routes these to AI smart mode. The AI maps the intent to CLI commands, shows the plan, waits for confirmation, and executes. The analyst learns the commands by watching the AI use them.

**Requirements for natural language mode:**
- Always shows the command it plans to run — never executes silently
- Produces the same output as if the analyst had typed the command directly
- For multi-step questions, proposes a numbered plan with one confirmation before starting

### Mode 3 — Report Templates (For Recurring Deliverables)

Used for predictable, scheduled outputs.

```sh
sh analytics report weekly --output weekly_$(date +%Y%m%d).md
sh analytics report campaign --campaign-id ACT2024Q4 --output postmortem.md
sh analytics report loyalty --period 30d --output loyalty_review.md
```

Report templates have fixed structures agreed upon by the business. The analyst does not design the layout each time — they run the command and get a consistent, shareable artifact.

**Requirements for report mode:**
- Weekly and monthly reports cover all major domains (customers, orders, coupons, points, messages, campaigns)
- Campaign post-mortem covers audience, messages, coupons, GMV attribution, canvas funnel (if applicable)
- All reports include a metadata footer: run time, period covered, database source, command used

### Mode 4 — AI Synthesis (For Decision Support)

Used when the analyst needs to connect findings across multiple domains into a recommendation.

```sh
sh analytics diagnose
sh analytics diagnose --context "Evaluating Q2 re-engagement strategy options"
sh ai chat "What is the most likely explanation for the GMV decline given the analysis I just ran?"
```

AI synthesis is the top of the chain. It consumes outputs from Modes 1–3 and produces a structured recommendation with explicit evidence. The analyst validates the evidence, not the AI's conclusion.

**Requirements for synthesis mode:**
- `diagnose` runs all major analytics commands internally and passes aggregates to the AI
- AI output is structured: Observation → Evidence → Interpretation → Recommended next command
- The AI never fabricates numbers; all figures it cites come from commands run in the same session

---

## Functional Requirements Summary

### Core Analytics

| Ref | Capability | Priority |
|---|---|---|
| A-01 | Business overview with period-over-period across all domains | P0 |
| A-02 | Statistical anomaly detection (mean ± 2σ) on ≥ 7 daily metrics | P0 |
| A-03 | AI-synthesized diagnosis with evidence + recommendations | P0 |
| A-04 | Customer lifecycle funnel (6 stages) | P0 |
| A-05 | Customer retention by configurable cohort windows | P0 |
| A-06 | RFM segment distribution with spend/frequency/recency | P0 |
| A-07 | Orders: GMV, AOV, new vs. returning buyer split | P0 |
| A-08 | Repurchase rate and first-to-second order timing | P1 |
| A-09 | Product and category revenue ranking with delta | P1 |
| A-10 | Store-level performance: revenue, ATV, unique customers | P1 |
| A-11 | Cohort-based LTV by first-order month | P1 |
| A-12 | Customer acquisition source breakdown | P1 |
| A-13 | Campaign funnel: participants → messages → redemptions → GMV | P0 |
| A-14 | Canvas per-node journey funnel with drop-off rates | P0 |
| A-15 | Coupon: issued/redeemed/expired + ROI breakdown per rule | P0 |
| A-16 | Coupon anomaly detection (daily redemption spikes) | P1 |
| A-17 | Points: earned/redeemed/expired + expiry risk + daily trend | P0 |
| A-18 | Loyalty program overview: enrollment, tier distribution, liability | P0 |
| A-19 | Message delivery: sent/delivered/failed/opened by channel | P0 |
| A-20 | Message daily trend with spike detection (mean ± 2σ) | P1 |
| A-21 | Template-level open/click/unsubscribe rates | P1 |
| A-22 | Message-to-purchase attribution within configurable window | P1 |
| A-23 | Segment size trend over time | P1 |
| A-24 | Segment purchase behavior analysis (cross-DB join) | P1 |
| A-25 | Segment overlap with Jaccard similarity | P1 |
| A-26 | Order returns breakdown by channel and category | P1 |
| A-27 | Recommendation engine analysis | P2 |
| A-28 | Gender distribution snapshot | P2 |

### Report Templates

| Ref | Capability | Priority |
|---|---|---|
| R-01 | Weekly and monthly business reports (all domains, Markdown output) | P0 |
| R-02 | Campaign post-mortem (audience, messages, coupons, GMV, canvas funnel) | P0 |
| R-03 | Loyalty program health review | P1 |
| R-04 | All reports support `--insights on` for AI commentary | P2 |

### Analysis Infrastructure

| Ref | Capability | Priority |
|---|---|---|
| I-01 | Auto-log every analytics run (command, args, SQL trace, exec time, artifact) | P0 |
| I-02 | Inspect any past run including full SQL trace | P0 |
| I-03 | Re-execute any past run exactly | P0 |
| I-04 | Natural language routing with plan display before execution | P0 |
| I-05 | Schema explorer: domains, search, table explain, field dictionary, metrics | P0 |
| I-06 | Scheduled task creation and management with cron | P1 |
| I-07 | All commands support --output (CSV, JSON, Markdown) | P0 |
| I-08 | --show-sql flag on all MCP-mode commands | P0 |

---

## Governance

### The Metric Contract

Every metric computed by the CLI must match this definition. Any deviation is a bug, not a variant.

| Metric | Definition |
|---|---|
| Active customer | Placed ≥ 1 order in the analysis window |
| Buyer | Placed ≥ 1 order in the analysis period |
| Churn | Previously active; 0 orders in last 90 days |
| Pre-churn | Previously active; 0 orders in last 30–90 days |
| New customer | First order date falls within the analysis period |
| ROI | (Campaign-attributed GMV − coupon cost − points cost) / total investment |
| Redeem rate | Coupons used ÷ coupons issued in the period |
| Message success rate | Delivered ÷ sent |
| Points redemption rate | Points consumed ÷ points earned in the period |

`sh schema metrics` surfaces these definitions. They are the authoritative version.

### DWS-First Query Policy

Commands must prefer pre-aggregated DWS/ADS layers over raw source tables. When the DWS table is available and current:

- `analytics points` → `dws_points_base_metrics_d` before `dwd_member_points_log`
- `analytics customers` → `dws_customer_base_metrics` before `dim_customer_info`
- `analytics coupons` → `ads_das_v_coupon_analysis_d` before `dwd_coupon_instance`
- `messages health/trend` → `dws_message_base_metrics_d` before `vdm_t_message_record`

When a fallback is used, the output footer says so: "Source: dwd_member_points_log (dws fallback unavailable)". The analyst always knows which layer their number came from.

### SQL Safety

- All user-supplied values (IDs, dates, strings) are sanitized before inclusion in any SQL query
- Orders queries always filter `delete_flag = 0 AND direction = 0` unless returns are explicitly requested
- Commands never execute DDL or DML (read-only by definition)

---

## Non-Functional Requirements

| Requirement | Target |
|---|---|
| `analytics overview` response time | < 10 seconds |
| Single-domain query (orders, coupons, points) | < 8 seconds |
| `analytics anomaly` (multi-metric scan) | < 20 seconds |
| `analytics diagnose` (full synthesis) | < 45 seconds |
| Report template generation | < 30 seconds |
| `schema` commands (local registry) | < 1 second |
| AI smart mode time-to-first-response | < 5 seconds |
| Database failure: clear, actionable error message | Mandatory |
| DWS fallback: silent with footer note | Mandatory |
| Windows / macOS / Linux compatibility | Mandatory |
| Terminal output readable at 80 char width (core metrics) | Mandatory |

---

## Open Questions

| # | Question | Owner |
|---|---|---|
| 1 | Should `diagnose` be opt-in (due to high DB call count) or always available? | Product |
| 2 | Can analysts access natural language mode without an external AI API key? | Platform |
| 3 | Are there domain-level access restrictions by analyst role? | Security |
| 4 | What is the agreed definition of "attributed GMV" for campaign ROI? | Business |
| 5 | Should anomaly detection thresholds (2σ) be configurable per metric per tenant? | Product |
