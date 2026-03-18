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

# AI configuration
AI_CONFIG = {
    "api_url": os.getenv("OPENAI_API_URL", "https://api.openai.com/v1/chat/completions"),
    "api_key": os.getenv("OPENAI_API_KEY", ""),
    "model": os.getenv("OPENAI_MODEL", "gpt-3.5-turbo"),
}

SYSTEM_PROMPT = """你是 SocialHub.AI CLI 的智能助手，帮助用户使用命令行工具进行数据分析和营销管理。

可用的命令包括：
1. 数据分析 (analytics)
   - analytics overview --period=7d|30d|365d  # 概览分析
   - analytics customers --period=30d  # 客户分析
   - analytics retention --days=7,14,30  # 留存分析
   - analytics orders --period=30d --by=channel|province  # 订单分析

2. 客户管理 (customers)
   - customers list --type=member|registered|visitor  # 客户列表
   - customers search --phone=xxx --email=xxx  # 搜索客户
   - customers get <customer_id>  # 客户详情
   - customers export --output=file.csv  # 导出客户

3. 分群管理 (segments)
   - segments list  # 分群列表
   - segments create --name="名称" --rules='{"key":"value"}'  # 创建分群
   - segments export <segment_id> --output=file.csv  # 导出分群

4. 标签管理 (tags)
   - tags list --type=rfm|aipl|static  # 标签列表
   - tags create --name="标签名" --type=static --values="值1,值2"  # 创建标签

5. 营销活动 (campaigns)
   - campaigns list --status=draft|running|finished  # 活动列表
   - campaigns analysis <campaign_id> --funnel  # 活动分析
   - campaigns calendar --month=2024-03  # 营销日历

6. 优惠券 (coupons)
   - coupons rules list  # 优惠券规则
   - coupons list --status=unused|used|expired  # 优惠券列表
   - coupons analysis <rule_id>  # 优惠券分析

7. 积分 (points)
   - points rules list  # 积分规则
   - points balance <member_id>  # 积分余额
   - points history <member_id>  # 积分历史

8. 消息 (messages)
   - messages templates list --channel=sms|email|wechat  # 消息模板
   - messages records --status=success|failed  # 发送记录
   - messages stats --period=7d  # 消息统计

根据用户的自然语言请求，返回：
1. 对应的 CLI 命令（以 ```bash 代码块格式）
2. 简要说明命令的作用
3. 如果用户的请求不清楚，询问更多信息

回复使用中文。
"""


def call_ai_api(user_message: str, api_key: Optional[str] = None) -> str:
    """Call AI API to process natural language."""
    key = api_key or AI_CONFIG["api_key"]

    if not key:
        return "错误：未配置 AI API Key。请设置环境变量 OPENAI_API_KEY 或使用 --api-key 参数。"

    try:
        response = httpx.post(
            AI_CONFIG["api_url"],
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json={
                "model": AI_CONFIG["model"],
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                "temperature": 0.7,
                "max_tokens": 1000,
            },
            timeout=30,
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
        commands = re.findall(r"```bash\n(.*?)\n```", response, re.DOTALL)
        if commands:
            cmd = commands[0].strip()
            if typer.confirm(f"\n执行命令: {cmd}?"):
                import subprocess
                # Replace 'sh' with python module call
                if cmd.startswith("sh "):
                    cmd = cmd.replace("sh ", "python -m socialhub.cli.main ", 1)
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
