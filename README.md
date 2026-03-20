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
  <a href="docs/README.md">Full Documentation</a>
</p>

---

## Features

- **Smart Interaction** - Natural language input with AI-powered command parsing
- **MCP Database** - Direct connection to StarRocks analytics database for real-time queries
- **Data Analytics** - Overview, customer analysis, order analysis, retention analysis, channel analysis
- **Customer Management** - Query, search, profiles, segments, tags
- **Marketing Tools** - Campaign management, coupons, points, messages
- **Visualization** - Chart generation (bar, pie, line, dashboard)
- **Report Generation** - HTML analytics reports, exportable to PDF
- **Scheduled Tasks** - Heartbeat scheduler for automated task execution
- **Skills Extension** - Official certified plugins via Skills Store
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
socialhub skills install wechat-analytics
socialhub skills list
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
socialhub config set ai.azure_endpoint https://your-resource.openai.azure.com
socialhub config set ai.azure_api_key YOUR_API_KEY
```

## Project Structure

```
socialhub/
├── cli/
│   ├── main.py              # Entry point + smart routing + welcome screen
│   ├── config.py            # Configuration management
│   ├── commands/
│   │   ├── analytics.py     # Data analytics commands (MCP)
│   │   ├── ai.py            # AI assistant + multi-step execution
│   │   ├── heartbeat.py     # Scheduled task scheduler
│   │   ├── mcp.py           # MCP database commands
│   │   └── ...
│   ├── api/
│   │   ├── client.py        # API client
│   │   └── mcp_client.py    # MCP client (SSE)
│   └── output/
│       ├── table.py         # Table output
│       ├── chart.py         # Chart generation
│       ├── export.py        # Export functions
│       └── report.py        # HTML reports
├── Doc/                      # Generated reports and charts
├── Memory.md                 # Project memory
├── Heartbeat.md              # Scheduled task configuration
└── docs/                     # Documentation
```

## Documentation

- [Full Product Documentation](docs/README.md) - Detailed command reference and usage guide
- [Technical Design Document](docs/DESIGN.md) - Architecture design and implementation details
- [Skills Store](https://huangchunbo2025.github.io/Socialhub-CLI/) - Online skills store

## Tech Stack

| Component | Technology |
|-----------|------------|
| CLI Framework | Typer |
| Terminal Styling | Rich |
| Data Processing | Pandas |
| Chart Generation | Matplotlib |
| HTTP Client | httpx |
| AI Assistant | Azure OpenAI |
| Database | StarRocks (MCP) |

## License

MIT License

---

<p align="center">
  <strong>SocialHub.AI</strong><br>
  Customer Intelligence Platform<br>
  <em>Stop Adding AI, We Are AI.</em>
</p>
