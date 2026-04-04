# SocialHub.AI CLI

<p align="center">
  <img src="docs/logo.png" alt="SocialHub.AI" width="100">
</p>

<p align="center">
  <strong>Customer Intelligence Platform CLI</strong><br>
  <em>Stop Adding AI, We Are AI.</em>
</p>

<p align="center">
  <a href="#features">Features</a> •
  <a href="#quick-install">Quick Install</a> •
  <a href="#usage-examples">Usage Examples</a> •
  <a href="docs/README.md">Full Documentation</a> •
  <a href="docs/DESIGN.md">Design Document</a>
</p>

---

## Features

- **Smart Interaction** - Natural language input with AI-powered command parsing and multi-step plan execution
- **MCP Database** - Direct SSE connection to StarRocks analytics database for real-time queries
- **Data Analytics** - Overview, customer analysis, order analysis, retention analysis, channel analysis
- **Customer Management** - Query, search, profiles, segments, tags
- **Marketing Tools** - Campaign management, coupons, points, messages
- **Visualization** - Chart generation (bar, pie, line, funnel, dashboard)
- **Report Generation** - HTML analytics reports, exportable to PDF
- **Scheduled Tasks** - Heartbeat scheduler for automated task execution with compound command support
- **Skills Extension** - Official certified plugins via Skills Store with Ed25519 signature verification, sandbox isolation, and declarative permission model
- **AI Insights** - Automatic data insights after multi-step execution

## Quick Install

```bash
# Clone repository
git clone https://github.com/huangchunbo2025/Socialhub-CLI.git
cd Socialhub-CLI

# Install
pip install -e .

# Install chart support (optional)
pip install matplotlib
```

After installation, run `socialhub` to see the welcome screen:

```
  ____             _       _ _   _       _        _    ___
 / ___|  ___   ___(_) __ _| | | | |_   _| |__    / \  |_ _|
 \___ \ / _ \ / __| |/ _` | | |_| | | | | '_ \  / _ \  | |
  ___) | (_) | (__| | (_| | |  _  | |_| | |_) |/ ___ \ | |
 |____/ \___/ \___|_|\__,_|_|_| |_|\__,_|_.__//_/   \_\___|

                v0.1.0 | Customer Intelligence Platform
```

## Authentication

CLI requires authentication before use. On first run, you will be prompted to log in:

```bash
# Interactive login (prompts for Tenant ID, Account, Password)
socialhub auth login

# Or pass credentials directly
socialhub auth login --tenant YOUR_TENANT --account YOUR_ACCOUNT --password YOUR_PASSWORD

# Check authentication status
socialhub auth status

# Log out (clear local token)
socialhub auth logout
```

Enable the auth gate and configure the auth server:

```bash
socialhub config set oauth.enabled true
socialhub config set oauth.auth_url "https://s1.socialhub.ai/openapi-prod"
```

Once authenticated, the token is cached locally (`~/.socialhub/oauth_token.json`) and refreshed automatically when expired.

## Usage Examples

### Natural Language Interaction (Smart Mode)

```bash
socialhub analyze sales trends for the last 30 days
socialhub show order distribution by channel
socialhub set up a daily report at 8am
socialhub what fields are in the customer table
```

### MCP Database Queries

```bash
socialhub mcp tables                    # List all tables
socialhub mcp schema dwd_v_order        # View table schema
socialhub mcp sql                       # Interactive SQL
socialhub mcp query "SELECT COUNT(*) FROM dwd_v_order"
```

### Data Analytics

```bash
socialhub analytics overview --period=30d
socialhub analytics orders --period=30d
socialhub analytics orders --by=channel     # By channel
socialhub analytics orders --by=province    # By store
socialhub analytics customers --period=30d
socialhub analytics retention --days=7,14,30
```

### Chart Generation

```bash
socialhub analytics chart bar --data=customers --group=customer_type
socialhub analytics chart pie --data=customers --group=customer_type
socialhub analytics chart dashboard --output=Doc/dashboard.png
```

### Report Generation

```bash
socialhub analytics report --title="Monthly Analysis Report"
# Reports are saved to Doc/ folder by default
```

### Scheduled Tasks (Heartbeat)

```bash
socialhub heartbeat list                # List all scheduled tasks
socialhub heartbeat check               # Check and execute due tasks
socialhub heartbeat check --force       # Force execute all pending tasks
socialhub heartbeat run daily-overview  # Manually run specific task
socialhub heartbeat setup               # Windows Task Scheduler setup guide
```

### Snowflake Sync

```bash
socialhub-sync-snowflake --once
socialhub-sync-snowflake --interval 60
```

Environment variables used by the sync script:

```bash
SNOWFLAKE_ACCOUNT=ZUNLHUV-KC42628
SNOWFLAKE_USER=CHUNBO
SNOWFLAKE_PASSWORD=your_password
SNOWFLAKE_WAREHOUSE=COMPUTE_WH
SNOWFLAKE_DATABASE=MVP_DB
SNOWFLAKE_SCHEMA=PUBLIC
SNOWFLAKE_ROLE=ACCOUNTADMIN
SNOWFLAKE_SYNC_TABLE=MEMBERS_MVP
```

### Customer Management

```bash
socialhub customers list --type=member
socialhub customers get C001
socialhub customers search --phone=138
socialhub customers export --output=Doc/customers.csv
```

### AI Assistant

```bash
socialhub ai chat "analyze order trends" --auto  # Auto-execute multi-step plan
```

### Skills Store

```bash
socialhub skills browse
socialhub skills install report-generator
socialhub skills list
socialhub skills run report-generator generate-report --output=Doc/report.md
```

## Configuration

```bash
# Initialize configuration
socialhub config init

# View current configuration
socialhub config show

# Set MCP mode (default)
socialhub config set mode mcp

# Set local mode
socialhub config set mode local
socialhub config set local.data_dir ./data

# Configure AI (Azure OpenAI)
socialhub config set ai.provider azure
socialhub config set ai.azure_endpoint https://your-resource.openai.azure.com
socialhub config set ai.azure_api_key YOUR_API_KEY
socialhub config set ai.azure_deployment gpt-4o

# Configure MCP
socialhub config set mcp.sse_url https://your-mcp-server/sse
socialhub config set mcp.tenant_id your-tenant-id
```

## Project Structure

```
socialhub/
├── cli/
│   ├── main.py              # Entry point + smart routing + welcome screen
│   ├── config.py            # Configuration management (Pydantic v2)
│   ├── auth/
│   │   ├── oauth_client.py  # SocialHub auth HTTP client
│   │   ├── token_store.py   # Token cache (~/.socialhub/oauth_token.json)
│   │   └── gate.py          # Auth gate (runs before every command)
│   ├── commands/
│   │   ├── auth.py          # Authentication commands (login/logout/status)
│   │   ├── analytics.py     # Data analytics commands (MCP)
│   │   ├── ai.py            # AI assistant + multi-step execution + insights
│   │   ├── heartbeat.py     # Scheduled task scheduler (&&-chained commands)
│   │   ├── mcp.py           # MCP database commands
│   │   ├── customers.py     # Customer management
│   │   ├── segments.py      # Segment management
│   │   ├── tags.py          # Tag management
│   │   ├── campaigns.py     # Marketing campaigns
│   │   ├── coupons.py       # Coupon management
│   │   ├── points.py        # Points management
│   │   ├── messages.py      # Message management
│   │   ├── skills.py        # Skills management commands
│   │   └── config_cmd.py    # Configuration commands
│   ├── api/
│   │   ├── client.py        # HTTP API client (retry logic)
│   │   ├── mcp_client.py    # MCP SSE client (threading.Event sync)
│   │   └── models.py        # API data models
│   ├── local/
│   │   ├── reader.py        # Local data file reader
│   │   └── processor.py     # Data processor
│   ├── output/
│   │   ├── table.py         # Rich table output
│   │   ├── chart.py         # Matplotlib chart generation
│   │   ├── export.py        # CSV/JSON export
│   │   └── report.py        # HTML report generation
│   └── skills/              # Skills subsystem
│       ├── models.py        # SkillManifest, InstalledSkill (Pydantic v2)
│       ├── registry.py      # Local skill registry (registry.json)
│       ├── store_client.py  # Skills Store API client
│       ├── security.py      # Ed25519 verification, CRL, permissions, audit
│       ├── manager.py       # 10-step install pipeline
│       ├── loader.py        # importlib dynamic loading + sandboxed execution
│       ├── version_manager.py  # SemVer parsing and update checking
│       ├── sandbox/
│       │   ├── manager.py   # Sandbox coordinator
│       │   ├── filesystem.py  # builtins.open intercept
│       │   ├── network.py   # socket.socket intercept
│       │   └── execute.py   # subprocess.* / os.system intercept
│       └── store/
│           └── report-generator/  # Built-in skill
│               └── skill.yaml
├── Doc/                      # Generated reports and charts
├── Memory.md                 # Project memory
├── Heartbeat.md              # Scheduled task configuration
├── User.md                   # User profile
└── docs/                     # Documentation
    ├── README.md             # Full product documentation
    ├── DESIGN.md             # Architecture and design document
    ├── skills-technical-spec.md  # Skills subsystem technical spec
    ├── skills-store-design.md    # Skills Store platform design
    ├── SKILLS-DEVELOPMENT-PLAN.md
    ├── SECURITY-GUIDE-DEVELOPERS.md
    └── SECURITY-GUIDE-USERS.md
```

## Documentation

- [Architecture Reference (EN)](docs/Architecture-Reference-en.md) - Architecture design and technical reference
- [Architecture Reference (中文)](docs/Architecture-Reference.md) - 架构参考手册
- [Data Analyst Handbook (EN)](docs/Data-Analyst-Handbook-en.md) - Practical guide for data analysts
- [Data Analyst Handbook (中文)](docs/Data-Analyst-Handbook.md) - 数据分析师业务指导手册
- [CIO Technical Report](docs/AI-Frontier-CIO-Technical-Report.md) - AI Frontier 平台架构白皮书
- [CMO Playbook](docs/CMO-AI-Frontier-Playbook.md) - CMO AI 营销战略手册
- [Installation Guide](docs/安装指南.md) - 安装指南
- [Skills Store](https://huangchunbo2025.github.io/Socialhub-CLI/) - Online skills store

## Tech Stack

| Component | Technology |
|-----------|------------|
| CLI Framework | Typer |
| Terminal Styling | Rich |
| Data Processing | Pandas |
| Chart Generation | Matplotlib |
| HTTP Client | httpx |
| Data Validation | Pydantic v2 |
| AI Assistant | Azure OpenAI / OpenAI |
| Database | StarRocks (via MCP/SSE) |
| Skill Signing | Ed25519 (cryptography) |
| Skill Sandboxing | Python monkey-patching |

## License

MIT License

---

<p align="center">
  <strong>SocialHub.AI</strong><br>
  Customer Intelligence Platform<br>
  <em>Stop Adding AI, We Are AI.</em>
</p>
