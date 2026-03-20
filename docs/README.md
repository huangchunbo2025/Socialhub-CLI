# SocialHub.AI CLI Product Documentation

<p align="center">
  <img src="../web/skills-store/logo.png" alt="SocialHub.AI" width="120">
</p>

<p align="center">
  <strong>Customer Intelligence Platform</strong><br>
  <em>Stop Adding AI, We Are AI.</em>
</p>

<p align="center">
  <a href="https://github.com/huangchunbo2025/Socialhub-CLI">GitHub</a> •
  <a href="https://huangchunbo2025.github.io/Socialhub-CLI/">Skills Store</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#command-reference">Command Reference</a>
</p>

---

## Table of Contents

- [Product Overview](#product-overview)
- [Core Features](#core-features)
- [System Requirements](#system-requirements)
- [Installation Guide](#installation-guide)
- [Quick Start](#quick-start)
- [Command Reference](#command-reference)
- [MCP Database](#mcp-database)
- [AI Assistant](#ai-assistant)
- [Scheduled Tasks (Heartbeat)](#scheduled-tasks-heartbeat)
- [Charts and Reports](#charts-and-reports)
- [Skills Store](#skills-store)
- [Configuration Management](#configuration-management)
- [FAQ](#faq)

---

## Product Overview

**SocialHub.AI CLI** is a command-line tool designed for data analysts and marketing managers, providing powerful CLI capabilities for the SocialHub.AI Customer Intelligence Platform (CIP).

### Target Users

| Role | Use Cases |
|------|-----------|
| **Data Analysts** | Data queries, report generation, customer analysis, retention analysis |
| **Marketing Managers** | Campaign management, customer segmentation, coupon management, messaging |
| **Operations Staff** | Customer management, tag management, points management |
| **Developers** | API integration, automation scripts, data export |

### Product Features

- **Smart Interaction** - Natural language input with AI-powered command parsing
- **MCP Database** - Direct connection to StarRocks analytics database for real-time queries
- **Multi-step Execution** - AI generates execution plans, auto-executes after confirmation
- **AI Insights** - Automatic data insights and business recommendations after execution
- **Scheduled Tasks** - Heartbeat scheduler for automated task execution
- **Visual Output** - Terminal tables, chart generation, HTML reports
- **Skills Extension** - Install official certified plugins via Skills Store

---

## Core Features

### 1. Data Analytics

| Feature | Description |
|---------|-------------|
| Overview | KPI cards, business summary |
| Customer Analysis | New customers, active customers, customer profiles |
| Order Analysis | Sales, average order value, channel analysis |
| Retention Analysis | 7/14/30 day retention rates |
| Chart Generation | Bar, pie, line charts, dashboards |
| Report Generation | HTML analytics reports, exportable to PDF |

### 2. MCP Database

- Direct connection to StarRocks analytics database
- Interactive SQL queries
- Table schema viewing
- Real-time data analysis

### 3. Customer Management

- Customer search and queries
- Customer detail viewing
- 360-degree customer profiles
- Customer data export

### 4. Marketing Tools

- Campaign management
- Customer segmentation
- Tag management
- Coupon management
- Points management
- Message management

### 5. Scheduled Tasks (Heartbeat)

- Scheduled report generation
- Daily data overview
- Automatic Memory archiving
- Windows Task Scheduler integration

### 6. AI Assistant

- Natural language command parsing
- Multi-step plan execution
- Automatic data insights
- API timeout auto-retry

---

## System Requirements

| Item | Requirement |
|------|-------------|
| **Operating System** | Windows 10+, macOS 10.14+, Linux |
| **Python** | 3.10 or higher |
| **Memory** | 4GB+ recommended |
| **Network** | Required for MCP/API mode |

### Dependencies

```
typer[all]      # CLI framework
rich            # Terminal styling
httpx           # HTTP client
pandas          # Data processing
pydantic        # Data validation
matplotlib      # Chart generation (optional)
```

---

## Installation Guide

### Method 1: Install from Source (Recommended)

```bash
# 1. Clone repository
git clone https://github.com/huangchunbo2025/Socialhub-CLI.git
cd Socialhub-CLI

# 2. Install dependencies
pip install -e .

# 3. Install chart support (optional)
pip install matplotlib
```

### Verify Installation

```bash
socialhub --version
```

Run `socialhub` to see the welcome screen:

```
  ____             _       _ _   _       _        _    ___
 / ___|  ___   ___(_) __ _| | | | |_   _| |__    / \  |_ _|
 \___ \ / _ \ / __| |/ _` | | |_| | | | | '_ \  / _ \  | |
  ___) | (_) | (__| | (_| | |  _  | |_| | |_) |/ ___ \ | |
 |____/ \___/ \___|_|\__,_|_|_| |_|\__,_|_.__//_/   \_\___|

                v0.1.0 | Customer Intelligence Platform

+------------------------------- Quick Start --------------------------------+
|   socialhub analytics overview    Business overview                        |
|   socialhub analytics orders      Order analysis                           |
|   socialhub mcp sql               Interactive SQL                          |
|   socialhub ai chat "..."         AI assistant                             |
|   socialhub <query>               Smart mode                               |
|   socialhub --help                All commands                             |
+----------------------------------------------------------------------------+
```

### Windows PowerShell Alias Setup

```powershell
# Open PowerShell profile
notepad $PROFILE

# Add the following
Set-Alias -Name sh -Value "C:\Users\<username>\AppData\Local\Python\pythoncore-3.14-64\Scripts\socialhub.exe"

# Reload after saving
. $PROFILE
```

---

## Quick Start

### Initialize Configuration

```bash
# Initialize config file
socialhub config init

# View current configuration
socialhub config show
```

### First Command

```bash
# View data overview (MCP mode)
socialhub analytics overview --period=30d

# Using natural language
socialhub show sales data for the last 30 days
```

### Generate Report

```bash
# Generate HTML analytics report (saved to Doc/ folder)
socialhub analytics report --title="Monthly Analysis Report"
```

---

## Command Reference

### Data Analytics (analytics)

| Command | Description | Example |
|---------|-------------|---------|
| `overview` | Data overview | `socialhub analytics overview --period=30d` |
| `customers` | Customer analysis | `socialhub analytics customers --period=30d` |
| `orders` | Order analysis | `socialhub analytics orders --by=channel` |
| `retention` | Retention analysis | `socialhub analytics retention --days=7,14,30` |
| `chart` | Generate chart | `socialhub analytics chart pie --data=customers` |
| `report` | Generate report | `socialhub analytics report --output=Doc/report.html` |

#### Order Analysis Options

```bash
# By channel
socialhub analytics orders --by=channel

# By store
socialhub analytics orders --by=province

# Specify time period
socialhub analytics orders --period=7d
socialhub analytics orders --period=30d
socialhub analytics orders --period=90d
```

#### Chart Types

```bash
# Bar chart
socialhub analytics chart bar --data=customers --group=customer_type

# Pie chart
socialhub analytics chart pie --data=customers --group=customer_type

# Line chart
socialhub analytics chart line --data=orders

# Dashboard
socialhub analytics chart dashboard --output=Doc/dashboard.png
```

---

## MCP Database

MCP (Model Context Protocol) directly connects to StarRocks analytics database for real-time data queries.

### Basic Commands

```bash
# List all tables
socialhub mcp tables --database=das_demoen

# View table schema
socialhub mcp schema dwd_v_order --database=das_demoen

# Interactive SQL
socialhub mcp sql

# Execute query
socialhub mcp query "SELECT COUNT(*) FROM dwd_v_order" --database=das_demoen
```

### Common Tables

| Table | Description |
|-------|-------------|
| `dwd_v_order` | Order details table |
| `dim_customer_info` | Customer info table |
| `dim_member_info` | Member info table |
| `dwd_v_coupon_record` | Coupon records |
| `dwd_v_points_record` | Points records |

### dwd_v_order Table Schema

| Field | Type | Description |
|-------|------|-------------|
| `code` | varchar | Order ID |
| `order_date` | datetime | Order date |
| `customer_code` | varchar | Customer code |
| `store_name` | varchar | Store name |
| `source_name` | varchar | Channel name |
| `total_amount` | decimal | Order amount |
| `qty` | int | Item quantity |

---

## AI Assistant

### Natural Language Interaction (Smart Mode)

Enter natural language directly, the system auto-detects and calls AI:

```bash
socialhub analyze sales trends for the last 30 days
socialhub show order distribution by channel
socialhub what fields are in the customer table
socialhub set up a daily report task at 8am
```

### Multi-step Execution

AI generates an execution plan, auto-executes all steps after confirmation:

```bash
socialhub ai chat "comprehensive analysis of business for the last 30 days" --auto
```

Execution flow:
1. AI generates multi-step analysis plan
2. User confirms execution
3. Auto-executes each step sequentially
4. Generates AI insights after completion

### AI Insights

After multi-step execution completes, auto-generates:
- Key findings (2-3 points)
- Trend analysis
- Business recommendations (actionable suggestions)

### API Timeout Retry

Auto-retries 3 times on network timeout:

```
API request timeout, retrying in 2s (1/3)...
API request timeout, retrying in 4s (2/3)...
```

### AI Configuration

```bash
# Azure OpenAI configuration
socialhub config set ai.provider azure
socialhub config set ai.azure_endpoint https://your-resource.openai.azure.com
socialhub config set ai.azure_api_key YOUR_API_KEY
socialhub config set ai.azure_deployment gpt-4o

# OpenAI configuration
socialhub config set ai.provider openai
socialhub config set ai.openai_api_key YOUR_API_KEY
```

---

## Scheduled Tasks (Heartbeat)

Heartbeat is the built-in scheduled task system for automated periodic task execution.

### Command List

```bash
# List all scheduled tasks
socialhub heartbeat list

# Check and execute due tasks
socialhub heartbeat check

# Force execute all pending tasks
socialhub heartbeat check --force

# Preview tasks to be executed (dry run)
socialhub heartbeat check --dry-run

# Manually run specific task
socialhub heartbeat run daily-overview

# View Windows Task Scheduler setup guide
socialhub heartbeat setup
```

### Task Configuration File

Tasks are configured in `~/socialhub/Heartbeat.md`:

```markdown
### 1. Daily Data Overview
- **ID**: daily-overview
- **Frequency**: Daily 09:00
- **Status**: `pending`
- **Command**:
  ```bash
  sh analytics overview --period=today
  ```
```

### Setting Up Windows Auto-Execution

Run in PowerShell:

```powershell
$action = New-ScheduledTaskAction -Execute "C:\Users\<username>\AppData\Local\Python\pythoncore-3.14-64\Scripts\socialhub.exe" -Argument "heartbeat check"
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration ([TimeSpan]::MaxValue)
Register-ScheduledTask -TaskName "SocialHub Heartbeat" -Action $action -Trigger $trigger -Description "Hourly heartbeat check"
```

---

## Charts and Reports

### Chart Generation

Supports 5 chart types:

| Type | Command | Description |
|------|---------|-------------|
| Bar Chart | `chart bar` | Category comparison |
| Pie Chart | `chart pie` | Distribution |
| Line Chart | `chart line` | Trend changes |
| Funnel Chart | `chart funnel` | Conversion analysis |
| Dashboard | `chart dashboard` | Comprehensive view |

### HTML Reports

```bash
# Generate report (saved to Doc/ folder by default)
socialhub analytics report --title="Monthly Analysis Report"

# Custom output path
socialhub analytics report --output=Doc/monthly_report.html

# Without customer list
socialhub analytics report --no-customers
```

#### Export to PDF

1. After report generation, it auto-opens in browser
2. Press `Ctrl + P` to open print dialog
3. Select "Save as PDF"

---

## Skills Store

Skills Store provides official certified skill plugins to extend CLI functionality.

### Browse and Install

```bash
# Browse all skills
socialhub skills browse

# Install a skill
socialhub skills install data-export-plus

# View installed skills
socialhub skills list
```

### Online Store

Visit: https://huangchunbo2025.github.io/Socialhub-CLI/

---

## Configuration Management

### Config File Location

- Windows: `C:\Users\<username>\.socialhub\config.json`
- macOS/Linux: `~/.socialhub/config.json`

### Common Config Commands

```bash
# View all configuration
socialhub config show

# Set MCP mode (default)
socialhub config set mode mcp

# Set local mode
socialhub config set mode local
socialhub config set local.data_dir ./data

# Set AI configuration
socialhub config set ai.azure_endpoint https://your-resource.openai.azure.com
socialhub config set ai.azure_api_key YOUR_API_KEY
```

---

## FAQ

### Q: What to do when API request times out?

**A:** The system auto-retries 3 times. If still failing, check network connection or try again later.

### Q: How to view customer table fields?

**A:** Use MCP query:

```bash
socialhub mcp query "SELECT COLUMN_NAME, DATA_TYPE FROM information_schema.COLUMNS WHERE TABLE_NAME = 'dim_customer_info'" --database=das_demoen
```

### Q: Scheduled tasks not executing?

**A:** You need to set up Windows Task Scheduler or run manually:

```bash
socialhub heartbeat check
socialhub heartbeat setup  # View setup guide
```

### Q: Where are reports saved?

**A:** By default, saved to the project's `Doc/` folder.

---

## Support

- **GitHub Issues**: https://github.com/huangchunbo2025/Socialhub-CLI/issues
- **Skills Store**: https://huangchunbo2025.github.io/Socialhub-CLI/

---

<p align="center">
  <strong>SocialHub.AI</strong><br>
  Customer Intelligence Platform<br>
  <em>Stop Adding AI, We Are AI.</em>
</p>

<p align="center">
  &copy; 2024 SocialHub.AI. All rights reserved.
</p>
