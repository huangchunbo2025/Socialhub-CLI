"""AI-powered natural language command interface."""

import json
import os
from typing import Optional

import httpx
import typer
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

from ..config import load_config

app = typer.Typer(help="AI assistant for natural language queries")
console = Console()


def get_ai_config() -> dict:
    """Get AI configuration from config file or environment."""
    config = load_config()
    ai_config = config.ai

    return {
        "provider": os.getenv("AI_PROVIDER", ai_config.provider),
        "azure_endpoint": os.getenv("AZURE_OPENAI_ENDPOINT", ai_config.azure_endpoint),
        "azure_api_key": os.getenv("AZURE_OPENAI_API_KEY", ai_config.azure_api_key),
        "azure_deployment": os.getenv("AZURE_OPENAI_DEPLOYMENT", ai_config.azure_deployment),
        "azure_api_version": os.getenv("AZURE_OPENAI_API_VERSION", ai_config.azure_api_version),
        "openai_api_key": os.getenv("OPENAI_API_KEY", ai_config.openai_api_key),
        "openai_model": os.getenv("OPENAI_MODEL", ai_config.openai_model),
    }

SYSTEM_PROMPT = """你是 SocialHub.AI CLI 的智能助手，帮助用户使用命令行工具进行数据分析和营销管理。

所有命令都必须以 "sh " 前缀开头！

可用的命令包括：
1. 数据分析 (analytics)
   - sh analytics overview --period=7d|30d|365d  # 概览分析
   - sh analytics customers --period=30d  # 客户分析
   - sh analytics retention --days=7,14,30  # 留存分析
   - sh analytics orders --period=30d --by=channel|province  # 订单分析
   - sh analytics chart bar --data=customers --group=customer_type --output=chart.png  # 生成柱状图
   - sh analytics chart pie --data=customers --group=customer_type --output=pie.png  # 生成饼图
   - sh analytics chart dashboard --output=dashboard.png  # 生成分析仪表板
   - sh analytics chart funnel --output=funnel.png  # 生成漏斗图
   - sh analytics report --output=report.html  # 生成HTML分析报告（可打印为PDF）
   - sh analytics report --title="月度分析报告" --output=monthly.html  # 自定义标题的报告

2. 客户管理 (customers)
   - sh customers list --type=member|registered|visitor  # 客户列表
   - sh customers search --phone=xxx --email=xxx  # 搜索客户
   - sh customers get <customer_id>  # 客户详情
   - sh customers export --output=file.csv  # 导出客户

3. 分群管理 (segments)
   - sh segments list  # 分群列表
   - sh segments create --name="名称" --rules='{"key":"value"}'  # 创建分群
   - sh segments export <segment_id> --output=file.csv  # 导出分群

4. 标签管理 (tags)
   - sh tags list --type=rfm|aipl|static  # 标签列表
   - sh tags create --name="标签名" --type=static --values="值1,值2"  # 创建标签

5. 营销活动 (campaigns)
   - sh campaigns list --status=draft|running|finished  # 活动列表
   - sh campaigns analysis <campaign_id> --funnel  # 活动分析
   - sh campaigns calendar --month=2024-03  # 营销日历

6. 优惠券 (coupons)
   - sh coupons rules list  # 优惠券规则
   - sh coupons list --status=unused|used|expired  # 优惠券列表
   - sh coupons analysis <rule_id>  # 优惠券分析

7. 积分 (points)
   - sh points rules list  # 积分规则
   - sh points balance <member_id>  # 积分余额
   - sh points history <member_id>  # 积分历史

8. 消息 (messages)
   - sh messages templates list --channel=sms|email|wechat  # 消息模板
   - sh messages records --status=success|failed  # 发送记录
   - sh messages stats --period=7d  # 消息统计

根据用户的自然语言请求，返回：
1. 对应的 CLI 命令（以 ```bash 代码块格式，命令必须以 "sh " 开头，例如 "sh customers list --type=member"）
2. 简要说明命令的作用
3. 如果用户的请求不清楚，询问更多信息

重要：所有命令必须以 "sh " 前缀开头！

回复使用中文。
"""


def call_ai_api(user_message: str, api_key: Optional[str] = None) -> str:
    """Call AI API to process natural language (supports Azure OpenAI and OpenAI)."""
    ai_config = get_ai_config()
    provider = ai_config["provider"]

    try:
        if provider == "azure":
            # Azure OpenAI
            key = api_key or ai_config["azure_api_key"]
            if not key:
                return "错误：未配置 Azure OpenAI API Key。请运行 'sh config set ai.azure_api_key YOUR_KEY' 或设置环境变量 AZURE_OPENAI_API_KEY。"

            endpoint = ai_config["azure_endpoint"]
            deployment = ai_config["azure_deployment"]
            api_version = ai_config["azure_api_version"]

            url = f"{endpoint}/openai/deployments/{deployment}/chat/completions?api-version={api_version}"

            response = httpx.post(
                url,
                headers={
                    "api-key": key,
                    "Content-Type": "application/json",
                },
                json={
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_message},
                    ],
                    "temperature": 0.7,
                    "max_tokens": 1000,
                },
                timeout=60,
            )
        else:
            # Standard OpenAI
            key = api_key or ai_config["openai_api_key"]
            if not key:
                return "错误：未配置 OpenAI API Key。请运行 'sh config set ai.openai_api_key YOUR_KEY' 或设置环境变量 OPENAI_API_KEY。"

            response = httpx.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": ai_config["openai_model"],
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_message},
                    ],
                    "temperature": 0.7,
                    "max_tokens": 1000,
                },
                timeout=60,
            )

        if response.status_code != 200:
            return f"API 错误: {response.status_code} - {response.text}"

        result = response.json()
        return result["choices"][0]["message"]["content"]

    except httpx.TimeoutException:
        return "错误：API 请求超时，请重试。"
    except Exception as e:
        return f"错误：{str(e)}"


@app.command("chat")
def ai_chat(
    query: str = typer.Argument(..., help="自然语言查询"),
    api_key: Optional[str] = typer.Option(None, "--api-key", "-k", help="OpenAI API Key"),
    execute: bool = typer.Option(False, "--execute", "-e", help="自动执行生成的命令"),
) -> None:
    """
    使用自然语言与 CLI 交互。

    示例:
        ai chat "分析最近30天的客户留存"
        ai chat "查看所有VIP会员"
        ai chat "导出高价值客户到Excel"
    """
    console.print(f"\n[dim]正在分析: {query}[/dim]\n")

    response = call_ai_api(query, api_key)

    # Display response as markdown
    console.print(Panel(Markdown(response), title="AI 助手", border_style="cyan"))

    # Extract and optionally execute command
    if execute and "```bash" in response:
        import re
        import sys
        commands = re.findall(r"```bash\n(.*?)\n```", response, re.DOTALL)
        if commands:
            cmd = commands[0].strip()
            if typer.confirm(f"\n执行命令: {cmd}?"):
                import subprocess
                # Replace 'sh' with full python path
                python_exe = sys.executable
                if cmd.startswith("sh "):
                    cmd = cmd.replace("sh ", f'"{python_exe}" -m socialhub.cli.main ', 1)
                console.print(f"\n[dim]执行: {cmd}[/dim]\n")
                subprocess.run(cmd, shell=True)


@app.command("help")
def ai_help(
    topic: str = typer.Argument("general", help="帮助主题"),
) -> None:
    """获取特定功能的帮助说明。"""
    help_topics = {
        "general": """
## SocialHub.AI CLI 使用指南

### 快速开始
```bash
# 查看所有命令
python -m socialhub.cli.main --help

# 数据分析
python -m socialhub.cli.main analytics overview

# 客户管理
python -m socialhub.cli.main customers list
```

### AI 助手
使用自然语言与 CLI 交互：
```bash
python -m socialhub.cli.main ai chat "你的问题"
```
        """,
        "analytics": """
## 数据分析命令

### 概览分析
```bash
python -m socialhub.cli.main analytics overview --period=7d
python -m socialhub.cli.main analytics overview --from=2024-01-01 --to=2024-03-01
```

### 客户分析
```bash
python -m socialhub.cli.main analytics customers --period=30d
python -m socialhub.cli.main analytics retention --days=7,14,30
```

### 订单分析
```bash
python -m socialhub.cli.main analytics orders --period=30d
python -m socialhub.cli.main analytics orders --by=channel
```
        """,
        "customers": """
## 客户管理命令

### 查询客户
```bash
python -m socialhub.cli.main customers list --type=member
python -m socialhub.cli.main customers search --phone=138
python -m socialhub.cli.main customers get C001
```

### 导出客户
```bash
python -m socialhub.cli.main customers export --output=customers.csv
python -m socialhub.cli.main customers export --type=member --output=members.xlsx
```
        """,
    }

    content = help_topics.get(topic, help_topics["general"])
    console.print(Markdown(content))


# Shortcuts for common queries
@app.command("分析")
def analyze_shortcut(
    target: str = typer.Argument("概览", help="分析目标: 概览/客户/订单/留存"),
    period: str = typer.Option("30d", "--period", "-p", help="时间周期"),
) -> None:
    """快捷分析命令（中文）。"""
    from . import analytics

    target_map = {
        "概览": lambda: analytics.analytics_overview(period=period, format="table", from_date=None, to_date=None, customer_type="all", output=None),
        "客户": lambda: analytics.analytics_customers(period=period, channel="all", format="table", output=None),
        "订单": lambda: analytics.analytics_orders(period=period, metric="sales", repurchase_rate=False, by=None, format="table", output=None),
        "留存": lambda: analytics.analytics_retention(days="7,14,30", format="table", output=None),
    }

    if target in target_map:
        target_map[target]()
    else:
        console.print(f"[yellow]未知分析目标: {target}[/yellow]")
        console.print("可选: 概览, 客户, 订单, 留存")
