# Analyst CLI Requirements

## Purpose

This document defines the product requirements for a data-analyst-oriented CLI experience built on top of the existing SocialHub CLI, Skills system, and the `das_demoen` warehouse schema.

The goal is not only to let analysts install and run skills, but to let them:

- discover available data domains
- understand table grain and field meaning
- run repeatable business analysis workflows
- produce operational outputs such as reports, summaries, and investigation results

This document is intended to guide:

- product planning
- skill design
- CLI feature implementation
- analytics skill acceptance criteria

## Context

### Current baseline

Already available:

- Skills Store backend
- React storefront and skill detail pages
- CLI skill install / uninstall / enable / disable flow
- shared web user library contract
- a sample report-generation skill

The warehouse schema provided in `das_demoen_schema.md` indicates a mature analytics warehouse with domains including:

- activity
- customer
- order / transaction
- coupon
- points
- messaging
- recommendation

### Key observation

The current CLI is a good skills runtime foundation, but it is not yet a complete analyst workbench.

For analysts, the missing layer is:

- semantic data discovery
- metric guidance
- domain-oriented analysis workflows
- explainable and reproducible outputs

## Target users

### Primary user: Data Analyst

Typical responsibilities:

- investigate business performance
- explain changes in customer, transaction, and campaign outcomes
- prepare weekly or monthly reports
- validate marketing or loyalty program results
- answer ad hoc management questions

### Secondary users

- CRM / loyalty operations analysts
- marketing analysts
- campaign managers with SQL-assisted workflows
- data product managers

### Out of scope users

- raw platform engineers managing the warehouse itself
- admin users reviewing skills in the store
- developers publishing skills

## Product goals

1. Let analysts discover relevant tables, views, and fields without reading raw schema dumps.
2. Let analysts ask domain questions in business language and map them to the right skills or templates.
3. Let analysts run standardized workflows for recurring analysis tasks.
4. Let analysts generate reusable outputs, not only console text.
5. Ensure every analytics skill is explainable, governed, and safe for enterprise use.

## Non-goals

1. Replacing a full BI platform.
2. Replacing raw SQL notebooks for deep exploratory modeling.
3. Turning the CLI into a generic unrestricted query console without governance.
4. Supporting arbitrary code execution against production data without security controls.

## Data model understanding requirements

The warehouse follows a layered analytical pattern:

- `dim_*`: dimension tables
- `dwd_*`: detail / atomic warehouse layer
- `dws_*`: summary / subject-level metrics
- `ads_*`: application-facing analytical aggregates
- `*_v_*` or `v_*`: views

The CLI must surface this model clearly for analysts.

### Required schema understanding capabilities

1. Domain browsing
   - activity
   - customer
   - order
   - coupon
   - points
   - message
   - recommendation

2. Table detail inspection
   - table purpose
   - grain
   - key columns
   - date fields
   - metric fields
   - bitmap fields
   - distribution / partition hints where relevant

3. Field detail inspection
   - field name
   - type
   - nullable
   - business meaning
   - whether the field is a dimension, metric, identifier, or bitmap set

4. Relationship guidance
   - “if you want X, start from these tables”
   - “for detail, join Y”
   - “for dashboard-ready aggregates, use Z”

## Analyst workflow requirements

The system should support the full workflow below.

1. Clarify the business question
2. Discover the correct domain and tables
3. Select a skill or analysis template
4. Execute with constrained, explainable parameters
5. Inspect result, SQL, assumptions, and time window
6. Export or publish the result
7. Re-run later with the same logic

## Functional requirements

### A. Schema discovery and semantic navigation

#### A1. Schema search

Analysts need to search tables, views, and fields by business keywords.

Examples:

- search `activity`
- search `rfm`
- search `coupon redeem`
- search `pre churn`

Requirements:

- support keyword search across table names and field descriptions
- return domain, layer, and short explanation
- rank likely tables/views for a business question

#### A2. Table explain

The CLI must explain a table in analyst language.

Required output:

- what the table is for
- row grain
- key dimensions
- key metrics
- important caveats
- likely use cases

#### A3. Field dictionary

The CLI must show field-level business meaning.

Required output:

- field type
- nullable
- description
- category:
  - dimension
  - metric
  - identifier
  - bitmap
  - control/version field

#### A4. Domain map

The CLI must group warehouse assets by business domain.

Minimum domains:

- activity
- customer
- transaction
- coupon
- points
- messaging
- recommendation

### B. Reusable analysis skills

The system should provide domain-oriented analysis skills instead of raw generic querying only.

#### B1. Activity analysis skill

Data sources likely include:

- `ads_das_activity_analysis_d`
- `ads_das_activity_canvas_analysis_d`
- `ads_das_activity_node_canvas_analysis_d`
- related activity views

Required capabilities:

- activity performance summary
- activity ROI trend
- touch / pass / reward funnel
- per-node journey analysis
- campaign comparison over a date range
- associated order / reward / message outcomes

#### B2. Customer analysis skill

Data sources likely include:

- `dws_customer_base_metrics`
- `dws_customer_cube_metrics_d`
- `ads_das_custs_gender_distribution_d`
- `ads_das_custs_source_analysis_d`
- `ads_das_custs_tier_distribution_d`
- `ads_v_rfm`

Required capabilities:

- customer growth
- active / buyer / churn / pre-churn analysis
- source contribution
- gender and tier distribution
- RFM segmentation
- high-value / at-risk customer identification

#### B3. Transaction analysis skill

Data sources likely include:

- `dws_order_base_metrics_d`
- `dws_order_customer_metrics_d`
- `ads_das_v_transaction_analysis_d`
- `ads_v_order_detail_d`

Required capabilities:

- GMV trend
- order trend
- AOV
- item quantity trend
- new vs returning customer purchase contribution
- anomaly detection on transaction movement

#### B4. Coupon analysis skill

Data sources likely include:

- `dws_coupon_base_metrics_d`
- `ads_das_v_coupon_analysis_d`
- `ads_v_coupon_detail_d`

Required capabilities:

- issue volume
- redeem volume
- redeem value
- coupon-linked order amount
- coupon performance by campaign
- abnormal redeem behavior detection

#### B5. Points analysis skill

Data sources likely include:

- `dws_points_base_metrics_d`
- `dws_points_summary_metrics_d`
- `ads_das_v_points_summary_analysis_d`
- `ads_v_points_detail_d`

Required capabilities:

- points issued
- points consumed
- points in transit
- points expired
- points health and liability view
- points cost and engagement impact

#### B6. Messaging analysis skill

Data sources likely include:

- `ads_das_v_message_analysis_d`
- `dws_message_base_metrics_d`
- `ads_v_message_detail_d`

Required capabilities:

- send / success / fail by channel
- template-level performance
- delivery quality trends
- cross-channel comparison
- suspicious delivery failure spikes

#### B7. Recommendation analysis skill

Data sources likely include:

- `dwd_rec_user_product_rating`
- `dws_rec_user_recs`
- `dws_rec_product_to_prdocut_rating`
- purchase affinity temp tables

Required capabilities:

- recommendation output inspection
- user-level recommendation analysis
- product-to-product association analysis
- recommendation quality evaluation
- conversion correlation checks

### C. Natural-language task framing

Analysts should not be forced to know the warehouse by memory.

The CLI should support business-language task framing such as:

- “Show the worst-performing campaigns by ROI in the last 30 days”
- “Compare churn risk by loyalty tier”
- “Which coupon campaigns generated the highest redeem amount this month?”

Requirements:

- map natural language into a domain skill
- show chosen tables and assumptions
- ask for missing parameters when needed
- keep the final execution path explainable

### D. Templates and repeatable analysis

#### D1. Standard templates

Must support repeatable workflows such as:

- weekly business report
- monthly business review
- campaign post-mortem
- loyalty program health review
- customer segment review
- transaction anomaly review

#### D2. Parameterized execution

Templates must accept:

- date range
- channel
- identity type
- activity code
- campaign / template / loyalty program / tier

#### D3. Saved runs / reproducibility

Every run should be reproducible.

The system should retain:

- selected skill/template
- parameters
- time window
- generated SQL
- execution time
- output artifact path

### E. Output formats

Analysts need more than terminal summaries.

Required output options:

- concise console summary
- markdown report
- CSV export
- JSON structured output
- chart-friendly dataset
- slide/report draft material

Stretch options:

- PPTX
- PDF
- dashboard handoff JSON

### F. Explainability and governance

#### F1. SQL transparency

For every analytics skill run, the analyst should be able to view:

- which tables were used
- selected grain
- generated SQL
- derived metrics and assumptions

#### F2. Metric definition governance

The system must define and standardize important business metrics, such as:

- active customer
- buyer
- churn
- pre-churn
- ROI
- redeem rate
- message success rate

Skills must not silently invent inconsistent definitions.

#### F3. Data access safety

The system should support governed behavior such as:

- aggregate-first outputs by default
- optional detail mode only when allowed
- masking for sensitive customer data
- tenant / brand / region isolation when needed

#### F4. Auditability

Every skill run should be traceable by:

- who ran it
- when
- with what parameters
- against which data window
- what artifacts were produced

### G. Analyst experience requirements

#### G1. Low-friction discovery

Analysts should be able to answer:

- which skill should I use?
- which table should I start from?
- what does this metric mean?

Without reading full schema docs manually.

#### G2. Guided execution

If a question is underspecified, the system should ask for:

- date range
- domain
- segment
- granularity

#### G3. Decision-ready outputs

The default result should answer:

- what happened
- why it likely happened
- what changed
- what needs attention next

#### G4. Analyst-friendly language

The system should speak in business language first, then expose SQL and schema detail second.

## CLI capability requirements

### Required command families

1. Schema
   - search schema
   - show table
   - show field
   - show domain map

2. Analysis
   - run skill by domain
   - run standard template
   - ask natural-language question

3. Output
   - export markdown
   - export csv
   - export json
   - export presentation-ready dataset

4. Governance
   - show SQL
   - show metric definitions
   - show assumptions
   - show execution metadata

## Skill publishing requirements for analytics skills

Every analytics skill should include:

- purpose
- supported business questions
- required parameters
- tables/views used
- grain assumptions
- metric definitions
- output schema
- example runs
- test cases

## Acceptance criteria

### Schema exploration

- Analyst can search for `activity`, `coupon`, `rfm`, `churn`
- Analyst can inspect a table and understand its grain
- Analyst can inspect a field and see business meaning

### Analysis skills

- Activity analysis skill produces usable campaign performance output
- Customer analysis skill produces segmentation and churn insights
- Transaction analysis skill explains movement in orders / GMV
- Coupon analysis skill shows issue/redeem/effectiveness
- Points analysis skill shows issuance/consumption/liability health
- Messaging analysis skill shows send/success/failure by channel

### Reproducibility

- A saved run can be rerun with the same parameters
- Generated SQL can be inspected
- Output artifacts can be exported

### Governance

- Metric definitions are visible
- Sensitive detail can be restricted or masked
- Execution metadata is preserved

## Prioritization

### P0

- Schema explorer
- Domain map
- Activity analysis skill
- Customer analysis skill
- Transaction analysis skill
- Markdown / CSV export
- SQL explain output

### P1

- Coupon analysis skill
- Points analysis skill
- Messaging analysis skill
- Standard report templates
- Saved run metadata

### P2

- Recommendation analysis skill
- Advanced anomaly detection
- PPT / PDF generation
- Rich governance and masking rules

## Implementation guidance

### For CLI / skill design

- prefer domain-oriented commands over raw table-first commands
- default to business explanation before raw SQL
- expose SQL and metric logic as an explicit secondary layer

### For safety

- avoid unrestricted free-form SQL execution without guardrails
- enforce parameterized query templates where possible
- maintain auditability for every analysis run

### For UX

- keep analyst workflows short
- optimize for “question to answer” speed
- avoid forcing users to memorize warehouse layers or table names

## Recommended next step

Build the first analyst package around:

1. schema explorer
2. activity analysis
3. customer / RFM analysis
4. transaction analysis
5. markdown / csv report output

This gives the highest value with the lowest ambiguity and maps directly to the strongest visible domains in the `das_demoen` warehouse.

---

## Implementation Status

> Last updated: 2026-03-25
> Commit: `bd379f2` — feat: analyst workbench — schema explorer, anomaly detection, report templates, history, and recommendation analysis

### A. Schema Discovery and Semantic Navigation

| Requirement | Command | Status |
|---|---|---|
| A1. Schema search — keyword across tables + fields | `sh schema search <keyword>` | ✅ Done |
| A2. Table explain — grain, columns, caveats, use cases | `sh schema show <table>` | ✅ Done |
| A3. Field dictionary — type, nullable, category, meaning | `sh schema fields <table>` | ✅ Done |
| A4. Domain map — group warehouse assets by business domain | `sh schema domains` | ✅ Done |

`cli/commands/schema.py` covers 17 key tables, 7 domains (activity, customer, order, coupon, points, message, recommendation), and a `schema metrics` sub-command exposing 13 standardized metric definitions (F2 governance).

---

### B. Reusable Analysis Skills

| Requirement | Command | Status |
|---|---|---|
| B1. Activity analysis — campaign performance, ROI, journey funnel | `sh analytics campaigns [--canvas <id>]` | ✅ Done |
| B1. Per-node journey analysis | `sh analytics campaigns --canvas <canvas_id>` | ✅ Done |
| B2. Customer analysis — growth, active/churn/pre-churn, RFM | `sh analytics customers` | ✅ Done |
| B2. Tier / gender distribution | `sh analytics customers` (included) | ✅ Done |
| B2. Customer lifecycle funnel | `sh analytics funnel` | ✅ Done |
| B2. Retention rates | `sh analytics retention` | ✅ Done |
| B3. Transaction analysis — GMV, AOV, order trend, new vs returning | `sh analytics orders` | ✅ Done |
| B3. Anomaly detection on transaction movement | `sh analytics anomaly` | ✅ Done |
| B3. Product and category revenue | `sh analytics products` (MCP) | ✅ Done |
| B3. Store-level performance | `sh analytics stores` (MCP) | ✅ Done |
| B3. Cohort LTV | `sh analytics ltv` (MCP) | ✅ Done |
| B4. Coupon analysis — issue, redeem, value, campaign performance | `sh analytics coupons` | ✅ Done |
| B4. Abnormal redeem behavior detection | `sh analytics coupons --anomaly` | ✅ Done |
| B5. Points analysis — issued, consumed, expired, liability | `sh analytics points` | ✅ Done |
| B5. Loyalty program health — enrollment, tier distribution | `sh analytics loyalty` | ✅ Done |
| B6. Messaging analysis — send/success/fail by channel, templates | `sh messages health` | ✅ Done |
| B6. Delivery quality trend + spike detection | `sh messages health --trend` | ✅ Done |
| B7. Recommendation analysis — top products, user recs, affinity | `sh analytics recommend` | ✅ Done |

---

### C. Natural-Language Task Framing

| Requirement | Command | Status |
|---|---|---|
| Map natural language to a domain skill | `sh <free-text query>` (smart mode) | ✅ Done |
| Show chosen tables and assumptions | Shown in AI response before execution | ✅ Done |
| Ask for missing parameters | AI prompts for clarification | ✅ Done |
| Explainable execution path | Plan steps shown before confirm | ✅ Done |

Smart mode is implemented in `cli/main.py` — any unrecognized first token is routed to `call_ai_api()` which maps it to CLI commands and shows a plan for analyst approval.

---

### D. Templates and Repeatable Analysis

| Requirement | Command | Status |
|---|---|---|
| D1. Weekly business report | `sh analytics report weekly` | ✅ Done |
| D1. Monthly business review | `sh analytics report monthly` | ✅ Done |
| D1. Campaign post-mortem | `sh analytics report campaign --campaign-id <id>` | ✅ Done |
| D1. Loyalty program health review | `sh analytics report loyalty` | ✅ Done |
| D1. Customer segment review | `sh analytics customers` + `sh analytics funnel` | ✅ Done (via existing commands) |
| D1. Transaction anomaly review | `sh analytics anomaly` | ✅ Done |
| D2. Date range parameter | `--period`, `--start`, `--end` on most commands | ✅ Done |
| D2. Channel parameter | `--channel` on messages, campaigns | ✅ Done |
| D2. Campaign / activity code | `--campaign-id`, `--canvas` | ✅ Done |
| D3. Saved runs / reproducibility | `sh history list/show/rerun` | ✅ Done |

Every `analytics report` sub-command accepts `--output <file.md>` and writes a structured Markdown artifact.

---

### E. Output Formats

| Format | How | Status |
|---|---|---|
| Console summary | Default for all commands | ✅ Done |
| Markdown report | `--output file.md` on analytics/report commands | ✅ Done |
| CSV export | `--output file.csv` via `cli/output/export.py` | ✅ Done |
| JSON structured output | `--output file.json` | ✅ Done |
| Chart-friendly dataset | CSV is chart-tool importable | ✅ Done |
| PPTX / PDF | — | ❌ Out of scope (P2, not implemented) |
| Dashboard handoff JSON | — | ❌ Not implemented |

---

### F. Explainability and Governance

| Requirement | Implementation | Status |
|---|---|---|
| F1. SQL transparency — tables used, SQL, assumptions | `_sql_trace_ctx()` captures all queries; `sh history show <run_id>` displays full SQL trace | ✅ Done |
| F2. Metric definition governance — standardized definitions | `sh schema metrics [<name>]` — 13 canonical definitions (active_customer, buyer, churn, pre_churn, roi, redeem_rate, message_success_rate, ...) | ✅ Done |
| F3. Data access safety — aggregate-first, parameterized | All analytics commands produce aggregated outputs by default; `_sanitize_string_input()` applied to all user-supplied IDs; no free-form SQL execution | ✅ Done |
| F4. Auditability — who, when, params, data window, artifacts | `history.save_run()` records `run_id`, `timestamp`, `command`, `args`, `sql_trace`, `exec_time_ms`, `output_artifact` in `~/.socialhub/runs/*.json` | ✅ Done |

---

### G. Analyst Experience

| Requirement | Implementation | Status |
|---|---|---|
| G1. Low-friction discovery | `sh schema search <term>` answers "which table / skill"; `sh schema metrics` answers "what does this metric mean" | ✅ Done |
| G2. Guided execution — prompts for missing params | Smart mode AI asks for date range / domain / segment when underspecified; typer options with defaults and help text | ✅ Partial (AI path fully guided; direct commands use typer defaults) |
| G3. Decision-ready outputs — what happened, why, what changed | `sh analytics diagnose` produces AI-synthesized health diagnosis across all domains | ✅ Done |
| G4. Analyst-friendly language | All command output leads with business narrative; schema and SQL shown only via explicit flags or `history show` | ✅ Done |

---

### Summary by Priority

| Priority | Items | Status |
|---|---|---|
| **P0** | Schema explorer, domain map, activity/customer/transaction analysis skills, markdown+CSV export, SQL explain | ✅ **All done** |
| **P1** | Coupon + points + messaging analysis skills, standard report templates, saved run metadata | ✅ **All done** |
| **P2** | Recommendation analysis, anomaly detection | ✅ **All done** |
| **P2 stretch** | PPT/PDF generation, rich governance masking | ❌ Not implemented — genuine stretch goals, no warehouse support for masking rules yet |

All P0 and P1 requirements are fully implemented. P2 core items (recommendation analysis, anomaly detection) are also done. Only the stretch output formats (PPTX, PDF) and advanced masking remain out of scope.

### Key files

| File | Role |
|---|---|
| `cli/commands/analytics.py` | All analytics sub-commands (~6 000 lines) |
| `cli/commands/schema.py` | Schema explorer — domains / search / show / fields / metrics |
| `cli/commands/history.py` | Run history persistence — list / show / rerun / clear |
| `cli/commands/messages.py` | Messaging analysis including delivery trend + spike detection |
| `cli/output/export.py` | CSV / JSON / Markdown export helpers |
| `cli/main.py` | Entry point — smart mode NL routing, command registration |
