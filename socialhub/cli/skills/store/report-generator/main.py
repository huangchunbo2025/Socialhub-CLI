"""Consulting-Grade Report Generator Skill.

A McKinsey/BCG/Bain-style AI report generation assistant that transforms
complex data and business scenarios into logically rigorous, visually
elegant, minimalist structured Markdown reports.

Now with automatic HTML and PDF generation!

Core Principles:
- MECE (Mutually Exclusive, Collectively Exhaustive)
- Pyramid Principle (Conclusion First)
- Insight-Driven Headlines
- Executive Insight Callouts
"""

import base64
import re
import subprocess
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# Try to import MCP client for data-driven reports
try:
    from socialhub.cli.config import load_config
    from socialhub.cli.api.mcp_client import MCPClient, MCPConfig as MCPClientConfig
    HAS_MCP = True
except ImportError:
    HAS_MCP = False

# Check for optional dependencies
try:
    import markdown
    from markdown.extensions.tables import TableExtension
    from markdown.extensions.fenced_code import FencedCodeExtension
    from markdown.extensions.toc import TocExtension
    HAS_MARKDOWN = True
except ImportError:
    HAS_MARKDOWN = False

try:
    from pygments import highlight
    from pygments.lexers import get_lexer_by_name
    from pygments.formatters import HtmlFormatter
    HAS_PYGMENTS = True
except ImportError:
    HAS_PYGMENTS = False


# =============================================================================
# CONFIGURATION & CONSTANTS
# =============================================================================

SYSTEM_ROLE = """You are an AI report generation assistant trained by senior
consultants from McKinsey, BCG, and Bain. Your task is to transform complex
data and business scenarios into logically rigorous, visually elegant,
minimalist structured Markdown reports."""

FRAMEWORKS = {
    "strategic": ["PESTEL", "Porter's Five Forces", "SWOT"],
    "business": ["Value Chain", "BCG Matrix", "4P/4C"],
    "execution": ["5W2H", "Golden Circle"],
}

INDICATORS = {
    "strength": "✅",
    "weakness": "⚠️",
    "opportunity": "🚀",
    "threat": "🔴",
    "high": "●●●",
    "medium": "●●○",
    "low": "●○○",
}

# Professional CSS for HTML/PDF output
CONSULTING_CSS = """
:root {
    --primary-color: #1e3a5f;
    --accent-color: #00C9A7;
    --text-color: #1a1a2e;
    --bg-color: #ffffff;
    --card-bg: #f8fafc;
    --border-color: #e2e8f0;
}

* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, 'Microsoft YaHei', sans-serif;
    font-size: 11pt;
    line-height: 1.8;
    color: var(--text-color);
    background: var(--bg-color);
    max-width: 210mm;
    margin: 0 auto;
    padding: 20mm;
}

/* Headers */
h1 {
    font-size: 24pt;
    color: var(--primary-color);
    border-bottom: 3px solid var(--accent-color);
    padding-bottom: 12px;
    margin-bottom: 24px;
    margin-top: 0;
}

h2 {
    font-size: 16pt;
    color: var(--primary-color);
    margin-top: 36px;
    margin-bottom: 16px;
    padding-bottom: 8px;
    border-bottom: 2px solid var(--accent-color);
}

h3 {
    font-size: 13pt;
    color: var(--primary-color);
    margin-top: 24px;
    margin-bottom: 12px;
}

h4 {
    font-size: 11pt;
    color: var(--primary-color);
    margin-top: 16px;
    margin-bottom: 8px;
}

/* Paragraphs and spacing */
p {
    margin-bottom: 12px;
    text-align: justify;
}

/* Tables - Consulting Style */
table {
    width: 100%;
    border-collapse: collapse;
    margin: 16px 0;
    font-size: 10pt;
}

th {
    background: var(--primary-color);
    color: white;
    padding: 12px 16px;
    text-align: left;
    font-weight: 600;
}

td {
    padding: 10px 16px;
    border-bottom: 1px solid var(--border-color);
}

tr:nth-child(even) {
    background: var(--card-bg);
}

tr:hover {
    background: #e8f4f8;
}

/* Blockquotes - Executive Insight */
blockquote {
    background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%);
    border-left: 4px solid var(--accent-color);
    padding: 16px 20px;
    margin: 20px 0;
    border-radius: 0 8px 8px 0;
}

blockquote strong {
    color: var(--primary-color);
}

/* Code blocks - Mermaid placeholder */
pre {
    background: var(--card-bg);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 16px;
    overflow-x: auto;
    margin: 16px 0;
    font-family: 'Consolas', 'Monaco', monospace;
    font-size: 9pt;
}

code {
    font-family: 'Consolas', 'Monaco', monospace;
    background: var(--card-bg);
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 9pt;
}

pre code {
    background: transparent;
    padding: 0;
}

/* Lists */
ul, ol {
    margin: 12px 0;
    padding-left: 24px;
}

li {
    margin-bottom: 6px;
}

/* Horizontal rule */
hr {
    border: none;
    height: 2px;
    background: linear-gradient(to right, var(--accent-color), transparent);
    margin: 32px 0;
}

/* Strong/Bold */
strong {
    color: var(--primary-color);
    font-weight: 600;
}

/* Links */
a {
    color: var(--accent-color);
    text-decoration: none;
}

a:hover {
    text-decoration: underline;
}

/* Mermaid diagrams container - Unified Design */
.mermaid {
    text-align: center;
    margin: 24px 0;
    padding: 24px;
    background: linear-gradient(135deg, #f8fafc 0%, #f0f9ff 100%);
    border-radius: 12px;
    border: 1px solid #e2e8f0;
    box-shadow: 0 2px 8px rgba(30, 58, 95, 0.06);
}

.mermaid svg {
    max-width: 100%;
    height: auto;
}

/* Mermaid text styling */
.mermaid .nodeLabel,
.mermaid .label,
.mermaid text {
    font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif !important;
}

/* Pie chart enhancements */
.mermaid .pieTitleText {
    font-weight: 600 !important;
    fill: #1e3a5f !important;
}

.mermaid .slice {
    stroke-width: 2px;
}

/* Flowchart enhancements */
.mermaid .node rect,
.mermaid .node circle,
.mermaid .node polygon {
    stroke-width: 2px;
}

.mermaid .edgePath path {
    stroke-width: 2px;
}

/* Mindmap enhancements */
.mermaid .mindmap-node rect {
    rx: 8px;
    ry: 8px;
}

/* Gantt chart enhancements */
.mermaid .section {
    font-weight: 600;
}

/* Print styles */
@media print {
    body {
        padding: 15mm;
    }

    h1, h2, h3 {
        page-break-after: avoid;
    }

    table, blockquote, pre {
        page-break-inside: avoid;
    }

    @page {
        size: A4;
        margin: 15mm;
    }
}

/* YAML frontmatter - hide */
.frontmatter {
    display: none;
}

/* Header info table */
table:first-of-type {
    margin-top: 0;
}

/* Visual indicator styles */
.indicator-high { color: #059669; }
.indicator-medium { color: #d97706; }
.indicator-low { color: #dc2626; }
"""

# HTML template with Mermaid support - Unified Design Theme
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
{css}
    </style>
    <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
    <script>
        mermaid.initialize({{
            startOnLoad: true,
            securityLevel: 'loose',
            theme: 'base',
            themeVariables: {{
                // Primary palette - matches report design
                primaryColor: '#1e3a5f',
                primaryTextColor: '#ffffff',
                primaryBorderColor: '#1e3a5f',

                // Secondary/Accent colors
                secondaryColor: '#00C9A7',
                secondaryTextColor: '#1a1a2e',
                secondaryBorderColor: '#00C9A7',

                // Tertiary colors
                tertiaryColor: '#f8fafc',
                tertiaryTextColor: '#1a1a2e',
                tertiaryBorderColor: '#e2e8f0',

                // Background and text
                background: '#ffffff',
                mainBkg: '#f8fafc',
                textColor: '#1a1a2e',
                lineColor: '#1e3a5f',

                // Node colors
                nodeBorder: '#1e3a5f',
                nodeTextColor: '#1a1a2e',

                // Fonts
                fontFamily: 'Segoe UI, Microsoft YaHei, sans-serif',
                fontSize: '14px',

                // Flowchart specific
                edgeLabelBackground: '#ffffff',
                clusterBkg: '#f0fdf4',
                clusterBorder: '#00C9A7',

                // Pie chart
                pie1: '#1e3a5f',
                pie2: '#00C9A7',
                pie3: '#3b82f6',
                pie4: '#f59e0b',
                pie5: '#ef4444',
                pie6: '#8b5cf6',
                pie7: '#ec4899',
                pie8: '#14b8a6',
                pieStrokeColor: '#ffffff',
                pieStrokeWidth: '2px',
                pieTitleTextColor: '#1a1a2e',
                pieSectionTextColor: '#ffffff',
                pieLegendTextColor: '#1a1a2e',
                pieOpacity: '0.9',

                // Gantt chart
                gridColor: '#e2e8f0',
                todayLineColor: '#ef4444',
                taskBorderColor: '#1e3a5f',
                taskBkgColor: '#1e3a5f',
                activeTaskBorderColor: '#00C9A7',
                activeTaskBkgColor: '#00C9A7',
                doneTaskBorderColor: '#9ca3af',
                doneTaskBkgColor: '#9ca3af',
                critBorderColor: '#ef4444',
                critBkgColor: '#fef2f2',
                sectionBkgColor: '#f8fafc',
                altSectionBkgColor: '#ffffff',
                sectionBkgColor2: '#e0f2fe',

                // Sequence diagram
                actorBorder: '#1e3a5f',
                actorBkg: '#f8fafc',
                actorTextColor: '#1a1a2e',
                actorLineColor: '#1e3a5f',
                signalColor: '#1a1a2e',
                signalTextColor: '#1a1a2e',
                labelBoxBkgColor: '#f8fafc',
                labelBoxBorderColor: '#1e3a5f',
                labelTextColor: '#1a1a2e',
                loopTextColor: '#1a1a2e',
                noteBorderColor: '#00C9A7',
                noteBkgColor: '#f0fdf4',
                noteTextColor: '#1a1a2e',

                // State diagram
                labelColor: '#1a1a2e',
                altBackground: '#f8fafc'
            }},
            flowchart: {{
                useMaxWidth: true,
                htmlLabels: true,
                curve: 'basis',
                padding: 15,
                nodeSpacing: 50,
                rankSpacing: 50
            }},
            pie: {{
                useMaxWidth: true,
                textPosition: 0.75
            }},
            gantt: {{
                useMaxWidth: true,
                barHeight: 30,
                barGap: 8,
                topPadding: 50,
                leftPadding: 100,
                gridLineStartPadding: 35,
                fontSize: 12,
                sectionFontSize: 14,
                numberSectionStyles: 4
            }},
            mindmap: {{
                useMaxWidth: true,
                padding: 20
            }}
        }});
    </script>
</head>
<body>
{content}
<footer style="margin-top: 48px; padding-top: 24px; border-top: 1px solid #e2e8f0; text-align: center; color: #718096; font-size: 9pt;">
    <p>Generated by SocialHub.AI Consulting Report Generator v3.1</p>
    <p>Methodology: MECE + Pyramid Principle</p>
</footer>
</body>
</html>
"""

# PDF-optimized HTML template (no external scripts, Mermaid as images)
PDF_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    <style>
{css}
    </style>
</head>
<body>
{content}
<footer style="margin-top: 48px; padding-top: 24px; border-top: 1px solid #e2e8f0; text-align: center; color: #718096; font-size: 9pt;">
    <p>Generated by SocialHub.AI Consulting Report Generator v3.1</p>
    <p>Methodology: MECE + Pyramid Principle</p>
</footer>
</body>
</html>
"""


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def _validate_output_path(output: str, allowed_extensions: set[str] = None) -> Path:
    """Validate and sanitize output path.

    SECURITY: Prevents path traversal attacks by:
    1. Resolving to absolute path
    2. Checking for dangerous patterns
    3. Validating against allowed directories
    4. Checking file extension
    """
    import os

    if allowed_extensions is None:
        allowed_extensions = {".md", ".markdown", ".txt", ".html", ".pdf"}

    # Basic input validation
    if not output or not output.strip():
        raise ValueError("Output path cannot be empty")

    path = Path(output.strip())

    # SECURITY: Check for path traversal patterns
    dangerous_patterns = ["..", "~", "$", "%"]
    path_str = str(path)
    for pattern in dangerous_patterns:
        if pattern in path_str:
            raise ValueError(f"Invalid path: contains disallowed pattern '{pattern}'")

    # SECURITY: Resolve to absolute path
    try:
        resolved = path.resolve()
    except (OSError, RuntimeError) as e:
        raise ValueError(f"Invalid path: {e}")

    # SECURITY: Check if it's within user's home or current directory
    cwd = Path.cwd().resolve()
    home = Path.home().resolve()

    # Allow paths under current working directory or home directory
    try:
        resolved.relative_to(cwd)
    except ValueError:
        try:
            resolved.relative_to(home)
        except ValueError:
            raise ValueError(
                f"Output path must be within current directory ({cwd}) "
                f"or home directory ({home})"
            )

    # SECURITY: Block system directories (platform-specific)
    blocked_dirs = ["/etc", "/bin", "/sbin", "/usr", "/var", "/root",
                    "C:\\Windows", "C:\\Program Files", "C:\\System32"]
    resolved_str = str(resolved)
    for blocked in blocked_dirs:
        if resolved_str.lower().startswith(blocked.lower()):
            raise ValueError(f"Cannot write to system directory: {blocked}")

    # Validate file extension
    if path.suffix.lower() not in allowed_extensions:
        raise ValueError(f"Invalid file type '{path.suffix}'. Allowed: {allowed_extensions}")

    return path


def _get_date() -> str:
    """Get formatted current date."""
    return datetime.now().strftime("%Y-%m-%d")


def _detect_context(topic: str) -> str:
    """Auto-detect analysis context from topic keywords."""
    topic_lower = topic.lower()

    external_keywords = ["market", "macro", "environment", "trend", "政策", "宏观", "环境"]
    competitive_keywords = ["competitor", "competitive", "versus", "vs", "竞争", "对比", "优势"]
    process_keywords = ["process", "workflow", "flow", "how", "流程", "步骤", "方法"]
    action_keywords = ["plan", "action", "implement", "execute", "计划", "方案", "执行"]

    if any(kw in topic_lower for kw in external_keywords):
        return "external"
    elif any(kw in topic_lower for kw in competitive_keywords):
        return "competitive"
    elif any(kw in topic_lower for kw in process_keywords):
        return "process"
    elif any(kw in topic_lower for kw in action_keywords):
        return "action"
    return "comprehensive"


def _executive_insight(content: str) -> str:
    """Format an Executive Insight callout."""
    return f'\n> **Executive Insight:** {content}\n'


def _section_divider() -> str:
    """Return a visual section divider."""
    return "\n---\n\n"


def _parse_formats(formats: str = None) -> set[str]:
    """Parse output formats string."""
    if formats is None or formats.lower() == "all":
        return {"md", "html", "pdf"}
    return {f.strip().lower() for f in formats.split(",")}


# =============================================================================
# MARKDOWN TO HTML CONVERSION
# =============================================================================

def _convert_mermaid_blocks(html_content: str) -> str:
    """Convert Mermaid code blocks to div elements for rendering."""
    # Pattern to match ```mermaid ... ``` blocks in pre/code tags
    pattern = r'<pre><code class="language-mermaid">(.*?)</code></pre>'

    def replace_mermaid(match):
        mermaid_code = match.group(1)
        # Unescape HTML entities
        mermaid_code = mermaid_code.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
        return f'<div class="mermaid">\n{mermaid_code}\n</div>'

    result = re.sub(pattern, replace_mermaid, html_content, flags=re.DOTALL)

    # Also handle plain pre blocks containing mermaid
    pattern2 = r'<pre><code>(```mermaid\n)(.*?)(```)</code></pre>'
    result = re.sub(pattern2, lambda m: f'<div class="mermaid">\n{m.group(2)}\n</div>', result, flags=re.DOTALL)

    return result


def _remove_frontmatter(md_content: str) -> tuple[str, dict]:
    """Remove YAML frontmatter and return content and metadata."""
    if md_content.startswith('---'):
        parts = md_content.split('---', 2)
        if len(parts) >= 3:
            frontmatter = parts[1].strip()
            content = parts[2].strip()
            # Parse simple frontmatter
            metadata = {}
            for line in frontmatter.split('\n'):
                if ':' in line:
                    key, value = line.split(':', 1)
                    metadata[key.strip()] = value.strip().strip('"\'')
            return content, metadata
    return md_content, {}


def markdown_to_html(md_content: str, title: str = "Report") -> str:
    """Convert Markdown content to styled HTML."""
    if not HAS_MARKDOWN:
        # Fallback: basic conversion
        html_content = md_content.replace('\n', '<br>\n')
        html_content = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html_content, flags=re.MULTILINE)
        html_content = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html_content, flags=re.MULTILINE)
        html_content = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html_content, flags=re.MULTILINE)
        html_content = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html_content)
    else:
        # Use markdown library with extensions
        # Note: nl2br removed as it interferes with tables and code blocks
        md = markdown.Markdown(extensions=[
            'tables',
            'fenced_code',
            'toc',
            'sane_lists',
        ])

        # Remove frontmatter before conversion
        content, metadata = _remove_frontmatter(md_content)
        if 'title' in metadata:
            title = metadata['title']

        html_content = md.convert(content)

    # Convert Mermaid blocks
    html_content = _convert_mermaid_blocks(html_content)

    # Wrap in template
    return HTML_TEMPLATE.format(
        title=title,
        css=CONSULTING_CSS,
        content=html_content,
    )


def markdown_to_pdf_html(md_content: str, title: str = "Report") -> str:
    """Convert Markdown to PDF-optimized HTML (no external scripts)."""
    if not HAS_MARKDOWN:
        html_content = md_content.replace('\n', '<br>\n')
    else:
        md = markdown.Markdown(extensions=[
            'tables',
            'fenced_code',
            'toc',
            'sane_lists',
        ])
        content, metadata = _remove_frontmatter(md_content)
        if 'title' in metadata:
            title = metadata['title']
        html_content = md.convert(content)

    # For PDF, replace Mermaid blocks with placeholder text
    # (Mermaid requires JS which doesn't work in PDF)
    pattern = r'<pre><code class="language-mermaid">(.*?)</code></pre>'
    html_content = re.sub(
        pattern,
        r'<div class="mermaid" style="background:#f8fafc;padding:20px;border-radius:8px;text-align:center;color:#718096;"><p><em>[Mermaid Diagram - View in HTML version]</em></p><pre style="text-align:left;font-size:8pt;color:#475569;">\1</pre></div>',
        html_content,
        flags=re.DOTALL
    )

    return PDF_HTML_TEMPLATE.format(
        title=title,
        css=CONSULTING_CSS,
        content=html_content,
    )


def html_to_pdf(html_path: Path, pdf_path: Path) -> bool:
    """Convert HTML to PDF using available tools."""
    # Try weasyprint first
    try:
        from weasyprint import HTML
        HTML(filename=str(html_path)).write_pdf(str(pdf_path))
        return True
    except ImportError:
        pass
    except Exception as e:
        print(f"WeasyPrint failed: {e}")

    # Try wkhtmltopdf
    try:
        result = subprocess.run(
            ['wkhtmltopdf', '--enable-local-file-access', str(html_path), str(pdf_path)],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            return True
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"wkhtmltopdf failed: {e}")

    # Try Chrome/Chromium headless
    for chrome_cmd in ['google-chrome', 'chromium', 'chrome']:
        try:
            result = subprocess.run(
                [chrome_cmd, '--headless', '--disable-gpu', f'--print-to-pdf={pdf_path}', str(html_path)],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                return True
        except FileNotFoundError:
            continue
        except Exception:
            continue

    return False


def _generate_outputs(md_content: str, base_path: Path, title: str, formats: set[str]) -> list[str]:
    """Generate outputs in requested formats."""
    outputs = []

    # Always save Markdown if requested
    if "md" in formats:
        md_path = base_path.with_suffix('.md')
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(md_content, encoding='utf-8')
        outputs.append(f"MD:  {md_path.absolute()}")

    # Generate HTML if requested
    if "html" in formats or "pdf" in formats:
        html_content = markdown_to_html(md_content, title)
        html_path = base_path.with_suffix('.html')
        html_path.write_text(html_content, encoding='utf-8')
        if "html" in formats:
            outputs.append(f"HTML: {html_path.absolute()}")

    # Generate PDF if requested
    if "pdf" in formats:
        pdf_path = base_path.with_suffix('.pdf')

        # Create PDF-optimized HTML (no external scripts)
        pdf_html_content = markdown_to_pdf_html(md_content, title)
        pdf_html_path = base_path.with_suffix('.pdf.html')
        pdf_html_path.write_text(pdf_html_content, encoding='utf-8')

        # Try to convert to PDF
        if html_to_pdf(pdf_html_path, pdf_path):
            outputs.append(f"PDF: {pdf_path.absolute()}")
            # Clean up temporary PDF HTML
            pdf_html_path.unlink(missing_ok=True)
        else:
            outputs.append(f"PDF: Conversion tools not available. Use the HTML file to print as PDF.")
            outputs.append(f"     Install weasyprint: pip install weasyprint")

    return outputs


# =============================================================================
# REPORT HEADER
# =============================================================================

def _generate_header(title: str, frameworks_used: list[str]) -> str:
    """Generate consulting-style report header."""
    frameworks_str = " | ".join(frameworks_used)

    return f"""---
title: "{title}"
author: "SocialHub.AI Strategy Consulting"
date: "{_get_date()}"
frameworks: "{frameworks_str}"
methodology: "MECE + Pyramid Principle"
---

# {title}

<br/>

| **Report Date** | **Methodology** | **Frameworks Applied** |
|-----------------|-----------------|------------------------|
| {_get_date()} | MECE + Pyramid Principle | {frameworks_str} |

<br/>

"""


# =============================================================================
# FRAMEWORK GENERATORS (Unchanged from v3.0)
# =============================================================================

def _generate_pestel(topic: str, data: dict = None) -> str:
    """Generate PESTEL macro-environment analysis."""
    data = data or {}

    return f"""## 宏观环境深度扫描：六维度解构 {topic} 的外部驱动力

### PESTEL 分析框架

```mermaid
mindmap
  root(({topic}))
    Political 政治
      政策导向
      监管环境
      政府支持
    Economic 经济
      市场规模
      增长趋势
      成本结构
    Social 社会
      消费习惯
      人口结构
      价值观变迁
    Technological 技术
      技术成熟度
      创新机会
      数字化程度
    Environmental 环境
      可持续性要求
      碳中和趋势
      资源约束
    Legal 法律
      合规要求
      知识产权
      行业标准
```

<br/>

### 六维度深度分析

| 维度 | 关键因素 | 影响评估 | 机会/威胁 |
|------|----------|----------|-----------|
| **P** 政治 | {data.get('political', '政策支持力度加大，监管趋于规范化')} | {INDICATORS['high']} | 🚀 机会 |
| **E** 经济 | {data.get('economic', '市场进入成熟期，增速放缓但规模可观')} | {INDICATORS['medium']} | ⚠️ 双刃剑 |
| **S** 社会 | {data.get('social', '消费升级趋势明显，年轻群体成为主力')} | {INDICATORS['high']} | 🚀 机会 |
| **T** 技术 | {data.get('technological', '数字化转型加速，AI应用场景扩展')} | {INDICATORS['high']} | 🚀 机会 |
| **E** 环境 | {data.get('environmental', '可持续发展成为刚需，绿色溢价显现')} | {INDICATORS['medium']} | 🚀 机会 |
| **L** 法律 | {data.get('legal', '合规成本上升，但利好头部企业')} | {INDICATORS['low']} | ⚠️ 双刃剑 |

{_executive_insight(f"从 PESTEL 六维度分析，{topic} 面临的外部环境整体向好，技术变革和社会变迁是最大的结构性机会，需重点关注政策和合规的边际变化。")}

"""


def _generate_porter(industry: str, data: dict = None) -> str:
    """Generate Porter's Five Forces industry analysis."""
    data = data or {}

    return f"""## 行业结构性分析：五力模型透视 {industry} 竞争格局

### Porter's Five Forces 框架

```mermaid
flowchart TB
    subgraph 核心竞争
        A[<b>行业内竞争</b><br/>现有企业间的竞争强度]
    end

    B[<b>新进入者威胁</b><br/>进入壁垒高度] --> A
    C[<b>替代品威胁</b><br/>替代方案可行性] --> A
    D[<b>供应商议价能力</b><br/>上游话语权] --> A
    E[<b>买方议价能力</b><br/>客户集中度] --> A

    style A fill:#1e3a5f,color:#fff,stroke:#1e3a5f,stroke-width:2px
    style B fill:#00C9A7,color:#fff,stroke:#00C9A7,stroke-width:2px
    style C fill:#00C9A7,color:#fff,stroke:#00C9A7,stroke-width:2px
    style D fill:#3b82f6,color:#fff,stroke:#3b82f6,stroke-width:2px
    style E fill:#3b82f6,color:#fff,stroke:#3b82f6,stroke-width:2px
```

<br/>

### 五力强度评估矩阵

| 竞争力量 | 强度 | 关键驱动因素 | 战略启示 |
|----------|------|--------------|----------|
| **现有竞争** | {data.get('rivalry', INDICATORS['high'])} | 行业集中度、差异化程度、退出壁垒 | 差异化竞争，避免价格战 |
| **新进入者威胁** | {data.get('new_entrants', INDICATORS['medium'])} | 资本门槛、规模经济、品牌忠诚度 | 筑高护城河，强化品牌 |
| **替代品威胁** | {data.get('substitutes', INDICATORS['medium'])} | 替代品性价比、转换成本 | 持续创新，提升转换成本 |
| **供应商议价** | {data.get('suppliers', INDICATORS['low'])} | 供应商集中度、差异化程度 | 多元化采购，战略合作 |
| **买方议价** | {data.get('buyers', INDICATORS['medium'])} | 客户集中度、信息透明度 | 提升产品价值，锁定客户 |

<br/>

### 行业吸引力综合判断

```mermaid
quadrantChart
    title {industry} 行业吸引力矩阵
    x-axis 竞争强度低 --> 竞争强度高
    y-axis 盈利能力低 --> 盈利能力高
    quadrant-1 明星行业
    quadrant-2 金牛行业
    quadrant-3 问题行业
    quadrant-4 瘦狗行业
    当前定位: [0.6, 0.7]
```

{_executive_insight(f"{industry} 行业整体呈现「高竞争、高回报」特征，属于典型的明星行业。核心竞争策略应聚焦于差异化定位和客户锁定，而非成本领先。")}

"""


def _generate_swot(subject: str, data: dict = None) -> str:
    """Generate SWOT analysis with visual indicators."""
    data = data or {}

    strengths = data.get('strengths', [
        ("核心技术壁垒深厚", "high"),
        ("品牌认知度领先", "high"),
        ("供应链整合能力强", "medium"),
        ("人才储备充足", "medium"),
    ])

    weaknesses = data.get('weaknesses', [
        ("国际化经验不足", "high"),
        ("产品线过于集中", "medium"),
        ("数字化转型滞后", "medium"),
        ("组织效率有待提升", "low"),
    ])

    opportunities = data.get('opportunities', [
        ("下沉市场空间巨大", "high"),
        ("政策红利持续释放", "high"),
        ("新技术应用场景拓展", "medium"),
        ("跨界合作机会涌现", "medium"),
    ])

    threats = data.get('threats', [
        ("头部竞争加剧", "high"),
        ("原材料价格波动", "medium"),
        ("人才竞争白热化", "medium"),
        ("监管政策不确定性", "low"),
    ])

    def format_items(items, indicator):
        lines = []
        for item, level in items:
            level_indicator = INDICATORS.get(level, INDICATORS['medium'])
            lines.append(f"| {indicator} | {item} | {level_indicator} |")
        return "\n".join(lines)

    return f"""## 战略态势诊断：{subject} 的 SWOT 全景扫描

### 核心结论（金字塔原理 - 结论先行）

**{subject} 处于「攻守兼备」的战略态势**：内部优势突出但存在结构性短板，外部机会大于威胁但需警惕竞争升级。

<br/>

### SWOT 矩阵可视化

```mermaid
quadrantChart
    title {subject} SWOT 态势图
    x-axis 内部因素 --> 外部因素
    y-axis 不利因素 --> 有利因素
    quadrant-1 Opportunities 机会
    quadrant-2 Strengths 优势
    quadrant-3 Weaknesses 劣势
    quadrant-4 Threats 威胁
```

<br/>

### 优势分析 Strengths

| 指标 | 优势项 | 重要度 |
|------|--------|--------|
{format_items(strengths, INDICATORS['strength'])}

<br/>

### 劣势分析 Weaknesses

| 指标 | 劣势项 | 紧迫度 |
|------|--------|--------|
{format_items(weaknesses, INDICATORS['weakness'])}

<br/>

### 机会分析 Opportunities

| 指标 | 机会项 | 吸引力 |
|------|--------|--------|
{format_items(opportunities, INDICATORS['opportunity'])}

<br/>

### 威胁分析 Threats

| 指标 | 威胁项 | 风险度 |
|------|--------|--------|
{format_items(threats, INDICATORS['threat'])}

<br/>

### SWOT 战略组合矩阵

| 战略类型 | 组合逻辑 | 推荐策略 | 优先级 |
|----------|----------|----------|--------|
| **SO 增长型** | 优势 × 机会 | 利用核心优势抢占下沉市场 | ⭐⭐⭐ |
| **WO 扭转型** | 劣势 × 机会 | 借政策红利加速数字化转型 | ⭐⭐ |
| **ST 多元型** | 优势 × 威胁 | 以技术壁垒构建竞争护城河 | ⭐⭐ |
| **WT 防御型** | 劣势 × 威胁 | 补齐国际化短板，分散风险 | ⭐ |

{_executive_insight(f"建议 {subject} 采取「SO 增长型」战略为主线，同步推进「WO 扭转型」战略补齐数字化短板。核心优势与市场机会的结合点在下沉市场的快速渗透。")}

"""


def _generate_valuechain(company: str, data: dict = None) -> str:
    """Generate Value Chain analysis."""
    data = data or {}

    return f"""## 价值创造解构：{company} 价值链深度诊断

### 价值链架构图

```mermaid
flowchart LR
    subgraph 支持活动
        A1[企业基础设施]
        A2[人力资源管理]
        A3[技术研发]
        A4[采购管理]
    end

    subgraph 基本活动
        B1[进向物流] --> B2[生产运营] --> B3[出向物流] --> B4[市场营销] --> B5[售后服务]
    end

    A1 -.-> B1
    A2 -.-> B2
    A3 -.-> B3
    A4 -.-> B4

    B5 --> M[利润空间]

    style A1 fill:#f8fafc,color:#1a1a2e,stroke:#1e3a5f,stroke-width:1px
    style A2 fill:#f8fafc,color:#1a1a2e,stroke:#1e3a5f,stroke-width:1px
    style A3 fill:#f8fafc,color:#1a1a2e,stroke:#1e3a5f,stroke-width:1px
    style A4 fill:#f8fafc,color:#1a1a2e,stroke:#1e3a5f,stroke-width:1px
    style B1 fill:#1e3a5f,color:#fff,stroke:#1e3a5f,stroke-width:2px
    style B2 fill:#1e3a5f,color:#fff,stroke:#1e3a5f,stroke-width:2px
    style B3 fill:#1e3a5f,color:#fff,stroke:#1e3a5f,stroke-width:2px
    style B4 fill:#1e3a5f,color:#fff,stroke:#1e3a5f,stroke-width:2px
    style B5 fill:#1e3a5f,color:#fff,stroke:#1e3a5f,stroke-width:2px
    style M fill:#00C9A7,color:#fff,stroke:#00C9A7,stroke-width:3px
```

<br/>

### 价值活动诊断矩阵

| 活动环节 | 当前成熟度 | 价值贡献 | 改进空间 | 优先级 |
|----------|------------|----------|----------|--------|
| **研发创新** | {INDICATORS['high']} | 35% | 技术商业化效率 | ⭐⭐⭐ |
| **采购供应** | {INDICATORS['medium']} | 15% | 供应商协同深度 | ⭐⭐ |
| **生产制造** | {INDICATORS['high']} | 20% | 智能化升级 | ⭐⭐ |
| **物流配送** | {INDICATORS['medium']} | 10% | 最后一公里效率 | ⭐ |
| **市场销售** | {INDICATORS['medium']} | 15% | 数字化营销 | ⭐⭐⭐ |
| **客户服务** | {INDICATORS['low']} | 5% | 全生命周期运营 | ⭐⭐⭐ |

<br/>

### 价值链优化路径

```mermaid
flowchart TD
    A[价值链诊断] --> B{{核心瓶颈识别}}
    B --> C[研发商业化效率低]
    B --> D[客户服务薄弱]
    B --> E[数字化营销滞后]

    C --> F[解法: 建立技术转化机制]
    D --> G[解法: 客户成功体系建设]
    E --> H[解法: 营销自动化投入]

    F --> I[预期: 研发ROI提升30%]
    G --> J[预期: 客户LTV提升50%]
    H --> K[预期: 获客成本降低25%]

    style A fill:#1e3a5f,color:#fff,stroke:#1e3a5f,stroke-width:2px
    style B fill:#f8fafc,color:#1a1a2e,stroke:#1e3a5f,stroke-width:2px
    style C fill:#ef4444,color:#fff,stroke:#ef4444,stroke-width:1px
    style D fill:#ef4444,color:#fff,stroke:#ef4444,stroke-width:1px
    style E fill:#ef4444,color:#fff,stroke:#ef4444,stroke-width:1px
    style F fill:#3b82f6,color:#fff,stroke:#3b82f6,stroke-width:1px
    style G fill:#3b82f6,color:#fff,stroke:#3b82f6,stroke-width:1px
    style H fill:#3b82f6,color:#fff,stroke:#3b82f6,stroke-width:1px
    style I fill:#00C9A7,color:#fff,stroke:#00C9A7,stroke-width:2px
    style J fill:#00C9A7,color:#fff,stroke:#00C9A7,stroke-width:2px
    style K fill:#00C9A7,color:#fff,stroke:#00C9A7,stroke-width:2px
```

{_executive_insight(f"{company} 的价值链存在「微笑曲线两端薄弱」的典型问题——研发商业化和客户服务是最大的价值泄漏点。建议优先投资客户成功体系，预期可带来 50%+ 的客户 LTV 提升。")}

"""


def _generate_5w2h(initiative: str, data: dict = None) -> str:
    """Generate 5W2H action matrix with Gantt chart."""
    data = data or {}

    return f"""## 行动方案落地：{initiative} 的 5W2H 执行矩阵

### Golden Circle 战略逻辑（Why-How-What）

```mermaid
flowchart TB
    subgraph WHY[为什么做]
        W1[战略意图: 抢占市场窗口期]
        W2[核心价值: 建立差异化优势]
    end

    subgraph HOW[怎么做]
        H1[方法论: 敏捷迭代 + 精益运营]
        H2[资源配置: 聚焦核心环节]
    end

    subgraph WHAT[做什么]
        T1[产品: MVP快速验证]
        T2[市场: 种子用户获取]
        T3[组织: 专项团队组建]
    end

    WHY --> HOW --> WHAT

    style WHY fill:#1e3a5f,color:#fff,stroke:#1e3a5f,stroke-width:2px
    style HOW fill:#00C9A7,color:#fff,stroke:#00C9A7,stroke-width:2px
    style WHAT fill:#3b82f6,color:#fff,stroke:#3b82f6,stroke-width:2px
    style W1 fill:#f0f9ff,color:#1a1a2e,stroke:#1e3a5f,stroke-width:1px
    style W2 fill:#f0f9ff,color:#1a1a2e,stroke:#1e3a5f,stroke-width:1px
    style H1 fill:#f0fdf4,color:#1a1a2e,stroke:#00C9A7,stroke-width:1px
    style H2 fill:#f0fdf4,color:#1a1a2e,stroke:#00C9A7,stroke-width:1px
    style T1 fill:#eff6ff,color:#1a1a2e,stroke:#3b82f6,stroke-width:1px
    style T2 fill:#eff6ff,color:#1a1a2e,stroke:#3b82f6,stroke-width:1px
    style T3 fill:#eff6ff,color:#1a1a2e,stroke:#3b82f6,stroke-width:1px
```

<br/>

### 5W2H 责任矩阵

| 维度 | 问题 | 定义 |
|------|------|------|
| **What** | 做什么 | {data.get('what', f'完成 {initiative} 的全周期落地')} |
| **Why** | 为什么 | {data.get('why', '抓住市场窗口期，建立先发优势')} |
| **Who** | 谁负责 | {data.get('who', '战略PMO + 业务单元联合作战')} |
| **When** | 何时完成 | {data.get('when', 'Q1-Q2 MVP验证，Q3-Q4 规模化')} |
| **Where** | 在哪里 | {data.get('where', '一线城市试点 → 全国推广')} |
| **How** | 怎么做 | {data.get('how', '敏捷迭代，双周sprint，月度复盘')} |
| **How Much** | 投入多少 | {data.get('how_much', '预算: 500万；人力: 15人专项团队')} |

<br/>

### 甘特图：关键里程碑

```mermaid
gantt
    title {initiative} 实施路线图
    dateFormat  YYYY-MM-DD
    section 第一阶段: 准备期
    需求调研与分析     :a1, 2024-04-01, 15d
    方案设计与评审     :a2, after a1, 10d
    资源筹备与团队组建  :a3, after a2, 10d

    section 第二阶段: 验证期
    MVP开发          :b1, after a3, 30d
    种子用户测试      :b2, after b1, 20d
    迭代优化         :b3, after b2, 15d

    section 第三阶段: 规模化
    市场推广启动      :c1, after b3, 20d
    运营体系搭建      :c2, after b3, 30d
    效果评估与复盘    :c3, after c1, 10d
```

<br/>

### 风险与应对预案

| 风险类型 | 风险描述 | 概率 | 影响 | 应对策略 |
|----------|----------|------|------|----------|
| **执行风险** | 团队协同效率不足 | {INDICATORS['medium']} | {INDICATORS['high']} | 建立日站会机制，强化信息透明 |
| **市场风险** | 竞品快速跟进 | {INDICATORS['high']} | {INDICATORS['medium']} | 加速MVP验证，缩短上市时间 |
| **资源风险** | 预算超支 | {INDICATORS['low']} | {INDICATORS['medium']} | 分阶段投入，设置止损线 |
| **技术风险** | 技术方案可行性 | {INDICATORS['medium']} | {INDICATORS['high']} | 提前POC验证，预留技术缓冲 |

{_executive_insight(f"{initiative} 的核心成功因素是「速度」——必须在竞品反应前完成 MVP 验证并锁定种子用户。建议将整体时间压缩 20%，采用「战时机制」推进。")}

"""


def _generate_bcg_matrix(company: str, products: list = None) -> str:
    """Generate BCG Matrix analysis."""
    products = products or [
        ("核心产品A", 0.8, 0.85, "star"),
        ("成熟产品B", 0.3, 0.7, "cash_cow"),
        ("新品C", 0.9, 0.3, "question"),
        ("边缘产品D", 0.2, 0.2, "dog"),
    ]

    return f"""## 产品组合诊断：{company} 的 BCG 矩阵分析

### BCG 矩阵可视化

```mermaid
quadrantChart
    title {company} 产品组合矩阵
    x-axis 低市场份额 --> 高市场份额
    y-axis 低增长率 --> 高增长率
    quadrant-1 ⭐ 明星产品
    quadrant-2 ❓ 问题产品
    quadrant-3 🐕 瘦狗产品
    quadrant-4 🐄 金牛产品
    核心产品A: [0.8, 0.85]
    成熟产品B: [0.7, 0.3]
    新品C: [0.3, 0.9]
    边缘产品D: [0.2, 0.2]
```

<br/>

### 产品组合策略建议

| 产品 | 象限 | 市场增长率 | 相对份额 | 战略建议 |
|------|------|------------|----------|----------|
| 核心产品A | ⭐ 明星 | 高 | 高 | **加大投资**，巩固领先地位 |
| 成熟产品B | 🐄 金牛 | 低 | 高 | **收割利润**，支持其他业务 |
| 新品C | ❓ 问题 | 高 | 低 | **选择性投资**或快速退出 |
| 边缘产品D | 🐕 瘦狗 | 低 | 低 | **考虑剥离**，释放资源 |

<br/>

### 资源再配置建议

```mermaid
flowchart LR
    A[🐄 金牛产品B<br/>现金流入] -->|利润转移| B[⭐ 明星产品A<br/>维持投资]
    A -->|选择性投资| C[❓ 问题产品C<br/>验证潜力]
    D[🐕 瘦狗产品D<br/>释放资源] -->|资源回收| C

    style A fill:#00C9A7,color:#fff,stroke:#00C9A7,stroke-width:2px
    style B fill:#1e3a5f,color:#fff,stroke:#1e3a5f,stroke-width:2px
    style C fill:#3b82f6,color:#fff,stroke:#3b82f6,stroke-width:2px
    style D fill:#9ca3af,color:#fff,stroke:#9ca3af,stroke-width:2px
```

{_executive_insight(f"{company} 的产品组合呈现「一星一牛一问一狗」的经典结构。建议将金牛产品 B 的利润用于支持明星产品 A 的扩张，同时给予问题产品 C 一个季度的验证期——如无明显突破，应果断止损。")}

"""


# =============================================================================
# MAIN REPORT GENERATORS (Updated with HTML/PDF output)
# =============================================================================

def generate_consulting_report(
    topic: str,
    output: str,
    context: str = None,
    industry: str = None,
    formats: str = "all",
    **kwargs
) -> str:
    """Generate a comprehensive consulting-grade report with MD, HTML, and PDF outputs."""
    base_path = _validate_output_path(output)
    output_formats = _parse_formats(formats)

    # Auto-detect context if not specified
    if not context:
        context = _detect_context(topic)

    # Select frameworks based on context
    frameworks_used = []
    sections = []

    if context == "external":
        frameworks_used = ["PESTEL", "Porter's Five Forces"]
        method_note = f"将结合 **PESTEL** 宏观环境分析和 **Porter's Five Forces** 行业结构分析为您诊断 {topic} 的外部环境。"
        sections.append(_generate_pestel(topic))
        sections.append(_generate_porter(industry or topic))

    elif context == "competitive":
        frameworks_used = ["SWOT", "BCG Matrix"]
        method_note = f"将结合 **SWOT** 态势分析和 **BCG Matrix** 产品组合分析为您诊断 {topic} 的竞争态势。"
        sections.append(_generate_swot(topic))
        sections.append(_generate_bcg_matrix(topic))

    elif context == "process":
        frameworks_used = ["Value Chain", "Golden Circle"]
        method_note = f"将结合 **价值链分析** 和 **黄金圈理论** 为您解构 {topic} 的流程与逻辑。"
        sections.append(_generate_valuechain(topic))

    elif context == "action":
        frameworks_used = ["5W2H", "Gantt Chart"]
        method_note = f"将结合 **5W2H 责任矩阵** 和 **甘特图** 为您制定 {topic} 的行动方案。"
        sections.append(_generate_5w2h(topic))

    else:  # comprehensive
        frameworks_used = ["PESTEL", "SWOT", "Value Chain", "5W2H"]
        method_note = f"将综合运用 **PESTEL**、**SWOT**、**价值链** 和 **5W2H** 框架为您全方位诊断 {topic}。"
        sections.append(_generate_pestel(topic))
        sections.append(_generate_swot(topic))
        sections.append(_generate_valuechain(topic))
        sections.append(_generate_5w2h(topic))

    # Build full report
    intro = f"""## 方法论说明

{method_note}

**底层逻辑**：本报告严格遵循 **MECE 原则**（不重叠、不遗漏）和 **金字塔原理**（结论先行），确保分析的完整性和逻辑严密性。

{_section_divider()}
"""

    title = f"战略诊断报告：{topic}"
    content = [
        _generate_header(title, frameworks_used),
        intro,
    ]
    content.extend(sections)

    # Closing section
    closing = f"""## 附录

### 方法论说明

| 框架 | 用途 | 本报告应用 |
|------|------|------------|
| MECE | 确保分析完整性 | 全文贯穿 |
| 金字塔原理 | 结论先行，逻辑清晰 | 每节开头 |
| {' | '.join(frameworks_used)} | 专项分析 | 主体内容 |

### 免责声明

本报告基于公开信息和行业经验生成，仅供决策参考。具体战略制定需结合企业实际情况。

---

*Generated by SocialHub.AI Consulting Report Generator v3.1*

*Methodology: MECE + Pyramid Principle | Frameworks: {', '.join(frameworks_used)}*
"""
    content.append(closing)

    # Generate outputs
    md_content = "\n".join(content)
    outputs = _generate_outputs(md_content, base_path, title, output_formats)

    result = f"Consulting report generated!\nFrameworks: {', '.join(frameworks_used)}\n\nOutputs:\n"
    result += "\n".join(f"  {o}" for o in outputs)
    return result


def generate_pestel_report(topic: str, output: str, formats: str = "all", **kwargs) -> str:
    """Generate PESTEL macro-environment analysis report."""
    base_path = _validate_output_path(output)
    output_formats = _parse_formats(formats)

    title = f"PESTEL 宏观环境分析：{topic}"
    content = [
        _generate_header(title, ["PESTEL"]),
        _generate_pestel(topic),
    ]

    md_content = "\n".join(content)
    outputs = _generate_outputs(md_content, base_path, title, output_formats)

    return "PESTEL report generated!\n\nOutputs:\n" + "\n".join(f"  {o}" for o in outputs)


def generate_porter_report(industry: str, output: str, formats: str = "all", **kwargs) -> str:
    """Generate Porter's Five Forces industry analysis report."""
    base_path = _validate_output_path(output)
    output_formats = _parse_formats(formats)

    title = f"Porter's Five Forces 行业分析：{industry}"
    content = [
        _generate_header(title, ["Porter's Five Forces"]),
        _generate_porter(industry),
    ]

    md_content = "\n".join(content)
    outputs = _generate_outputs(md_content, base_path, title, output_formats)

    return "Porter's Five Forces report generated!\n\nOutputs:\n" + "\n".join(f"  {o}" for o in outputs)


def generate_swot_report(subject: str, output: str, formats: str = "all", **kwargs) -> str:
    """Generate SWOT competitive analysis report."""
    base_path = _validate_output_path(output)
    output_formats = _parse_formats(formats)

    title = f"SWOT 战略态势分析：{subject}"
    content = [
        _generate_header(title, ["SWOT"]),
        _generate_swot(subject),
    ]

    md_content = "\n".join(content)
    outputs = _generate_outputs(md_content, base_path, title, output_formats)

    return "SWOT report generated!\n\nOutputs:\n" + "\n".join(f"  {o}" for o in outputs)


def generate_valuechain_report(company: str, output: str, formats: str = "all", **kwargs) -> str:
    """Generate Value Chain analysis report."""
    base_path = _validate_output_path(output)
    output_formats = _parse_formats(formats)

    title = f"价值链诊断：{company}"
    content = [
        _generate_header(title, ["Value Chain"]),
        _generate_valuechain(company),
    ]

    md_content = "\n".join(content)
    outputs = _generate_outputs(md_content, base_path, title, output_formats)

    return "Value Chain report generated!\n\nOutputs:\n" + "\n".join(f"  {o}" for o in outputs)


def generate_action_report(initiative: str, output: str, formats: str = "all", **kwargs) -> str:
    """Generate action plan with 5W2H and Gantt chart."""
    base_path = _validate_output_path(output)
    output_formats = _parse_formats(formats)

    title = f"行动方案：{initiative}"
    content = [
        _generate_header(title, ["5W2H", "Golden Circle", "Gantt Chart"]),
        _generate_5w2h(initiative),
    ]

    md_content = "\n".join(content)
    outputs = _generate_outputs(md_content, base_path, title, output_formats)

    return "Action plan report generated!\n\nOutputs:\n" + "\n".join(f"  {o}" for o in outputs)


def generate_demo_report(output: str, formats: str = "all", **kwargs) -> str:
    """Generate a demo report showcasing all frameworks."""
    topic = "新能源汽车出海战略"

    return generate_consulting_report(
        topic=topic,
        output=output,
        context="comprehensive",
        industry="新能源汽车",
        formats=formats,
    )


def convert_report(input: str, formats: str = "all", **kwargs) -> str:
    """Convert existing Markdown file to HTML and/or PDF."""
    input_path = Path(input)
    if not input_path.exists():
        raise ValueError(f"Input file not found: {input}")

    md_content = input_path.read_text(encoding='utf-8')

    # Extract title from frontmatter or first heading
    title = "Report"
    if md_content.startswith('---'):
        _, metadata = _remove_frontmatter(md_content)
        if 'title' in metadata:
            title = metadata['title']
    else:
        # Try to find first h1
        match = re.search(r'^# (.+)$', md_content, re.MULTILINE)
        if match:
            title = match.group(1)

    output_formats = _parse_formats(formats)
    output_formats.discard('md')  # Don't overwrite the source

    base_path = input_path.with_suffix('')
    outputs = _generate_outputs(md_content, base_path, title, output_formats)

    return "Conversion complete!\n\nOutputs:\n" + "\n".join(f"  {o}" for o in outputs)


# =============================================================================
# DATA-DRIVEN REPORT GENERATION
# =============================================================================

def _fetch_analytics_data(period: str = "365d") -> dict:
    """Fetch analytics data from MCP database.

    NOTE: This function may fail when called from within the skill sandbox
    due to permission restrictions. Use 'sh analytics report' instead,
    which fetches data outside the sandbox and passes it to this skill.
    """
    if not HAS_MCP:
        return None

    try:
        config = load_config()
        if config.mode != "mcp":
            return None

        today = datetime.now().date()
        days_map = {"7d": 7, "30d": 30, "90d": 90, "365d": 365}
        days = days_map.get(period, 365)
        start_date = today - timedelta(days=days)

        mcp_config = MCPClientConfig(
            sse_url=config.mcp.sse_url,
            post_url=config.mcp.post_url,
            tenant_id=config.mcp.tenant_id,
        )
        database = config.mcp.database

        data = {}

        with MCPClient(mcp_config) as client:
            client.initialize()

            # 1. Overview data
            customer_result = client.query(
                "SELECT COUNT(*) as total FROM dim_customer_info",
                database=database
            )
            data['total_customers'] = customer_result[0].get("total", 0) if customer_result else 0

            overview_result = client.query(f"""
                SELECT
                    SUM(add_custs_num) as new_customers,
                    SUM(total_order_num) as total_orders,
                    SUM(total_transaction_amt) as total_revenue
                FROM ads_das_business_overview_d
                WHERE biz_date >= '{start_date}'
            """, database=database)

            if overview_result and len(overview_result) > 0:
                row = overview_result[0]
                data['new_customers'] = row.get("new_customers") or 0
                data['total_orders'] = row.get("total_orders") or 0
                data['total_revenue'] = float(row.get("total_revenue") or 0)

            # Active customers
            active_result = client.query(f"""
                SELECT COUNT(DISTINCT customer_code) as active
                FROM dwd_v_order
                WHERE order_date >= '{start_date}'
            """, database=database)
            data['active_customers'] = active_result[0].get("active", 0) if active_result else 0

            # 2. Channel distribution
            channel_result = client.query(f"""
                SELECT
                    channel_name as channel,
                    COUNT(*) as order_count,
                    SUM(order_amt) as total_sales,
                    AVG(order_amt) as avg_order_value
                FROM dwd_v_order
                WHERE order_date >= '{start_date}'
                GROUP BY channel_name
                ORDER BY total_sales DESC
                LIMIT 15
            """, database=database)
            data['channels'] = channel_result if channel_result else []

            # 3. Store/Region distribution
            store_result = client.query(f"""
                SELECT
                    store_name as store,
                    COUNT(*) as order_count,
                    SUM(order_amt) as total_sales
                FROM dwd_v_order
                WHERE order_date >= '{start_date}'
                GROUP BY store_name
                ORDER BY total_sales DESC
                LIMIT 20
            """, database=database)
            data['stores'] = store_result if store_result else []

            # 4. Retention data
            retention_result = []
            for days_period in [7, 30, 90]:
                period_start = today - timedelta(days=days_period)
                ret_result = client.query(f"""
                    SELECT
                        COUNT(DISTINCT CASE WHEN first_order_date >= '{period_start}' THEN customer_code END) as cohort_size,
                        COUNT(DISTINCT CASE WHEN first_order_date >= '{period_start}' AND order_count > 1 THEN customer_code END) as retained_count
                    FROM (
                        SELECT
                            customer_code,
                            MIN(order_date) as first_order_date,
                            COUNT(*) as order_count
                        FROM dwd_v_order
                        GROUP BY customer_code
                    ) t
                """, database=database)

                if ret_result and len(ret_result) > 0:
                    cohort_size = ret_result[0].get("cohort_size", 0) or 0
                    retained = ret_result[0].get("retained_count", 0) or 0
                    rate = (retained / cohort_size * 100) if cohort_size > 0 else 0
                    retention_result.append({
                        "period_days": days_period,
                        "cohort_size": cohort_size,
                        "retained_count": retained,
                        "retention_rate": rate
                    })
            data['retention'] = retention_result

        return data

    except Exception as e:
        print(f"Error fetching data: {e}")
        return None


def _analyze_topic_sections(topic: str) -> dict:
    """Analyze topic to determine which sections to include in the report.

    Returns a dict with section flags based on what the user's question/topic implies.
    """
    topic_lower = topic.lower()

    # Define keywords for each section
    keywords = {
        'customer': ['客户', '会员', '用户', 'customer', 'member', 'user', '活跃', '沉睡', '新增'],
        'channel': ['渠道', '来源', 'channel', 'source', '分布', '销售渠道'],
        'retention': ['留存', '复购', '忠诚', 'retention', 'loyalty', '回购', '粘性'],
        'order': ['订单', '销售', 'order', 'sales', '交易', '收入', '营收', 'revenue', '金额'],
        'overview': ['概览', '全面', '全部', '所有', '综合', 'overview', 'all', '总体', '整体', '分析报告'],
    }

    # Determine which sections to include
    sections = {
        'summary': True,  # Always include executive summary
        'key_metrics': True,  # Always include key metrics
        'customer': False,
        'channel': False,
        'retention': False,
        'order': False,
        'recommendations': True,  # Always include recommendations
    }

    # Check if topic mentions specific areas
    for section, kws in keywords.items():
        for kw in kws:
            if kw in topic_lower:
                if section == 'overview':
                    # If overview/all keywords found, include all sections
                    sections['customer'] = True
                    sections['channel'] = True
                    sections['retention'] = True
                    sections['order'] = True
                else:
                    sections[section] = True
                break

    # If no specific section matched, include all main sections (default comprehensive)
    if not any([sections['customer'], sections['channel'], sections['retention'], sections['order']]):
        sections['customer'] = True
        sections['channel'] = True
        sections['retention'] = True
        sections['order'] = True

    return sections


def _generate_data_insights(data: dict, topic: str = "") -> str:
    """Generate insights section based on actual data and topic.

    The sections generated are dynamically determined by the topic/question.
    """
    if not data:
        return ""

    # Ensure data is a dict
    if not isinstance(data, dict):
        raise TypeError(f"Expected dict but got {type(data).__name__}: {str(data)[:200]}")

    # Analyze topic to determine sections
    sections_to_include = _analyze_topic_sections(topic)

    total = data.get('total_customers', 0)
    active = data.get('active_customers', 0)
    sleeping = total - active
    active_rate = (active / total * 100) if total > 0 else 0

    revenue = data.get('total_revenue', 0)
    orders = data.get('total_orders', 0)
    avg_order = revenue / orders if orders > 0 else 0

    channels = data.get('channels', [])
    if not isinstance(channels, list):
        channels = []
    top_channel = channels[0] if channels and isinstance(channels[0], dict) else {}

    retention = data.get('retention', [])
    if not isinstance(retention, list):
        retention = []
    ret_30d = next((r for r in retention if isinstance(r, dict) and r.get('period_days') == 30), {})
    ret_rate = ret_30d.get('retention_rate', 0) if isinstance(ret_30d, dict) else 0

    # Determine health status
    active_status = "🟢 健康" if active_rate > 25 else ("🟡 偏低" if active_rate > 15 else "🔴 严重偏低")
    retention_status = "🟢 健康" if ret_rate > 8 else ("🟡 偏低" if ret_rate > 3 else "🔴 危险")

    # Build dynamic executive summary based on included sections
    summary_parts = []
    if sections_to_include['customer']:
        summary_parts.append(f"客户活跃度{'严重不足' if active_rate < 15 else '有待提升'}（{active_rate:.1f}%）")
    if sections_to_include['retention']:
        summary_parts.append(f"{'留存率极低' if ret_rate < 3 else '留存率偏低'}（30天 {ret_rate:.2f}%）")
    if sections_to_include['channel']:
        summary_parts.append(f"{'渠道分布健康' if len(channels) > 5 else '渠道相对集中'}")
    if sections_to_include['order']:
        summary_parts.append(f"客单价稳定（¥{avg_order:,.0f}）")

    summary_text = "、".join(summary_parts) if summary_parts else f"数据覆盖 {total:,} 名客户"

    # Build key metrics flowchart based on included sections
    flowchart_nodes = []
    flowchart_styles = []
    flowchart_connections = []

    # Root node
    flowchart_nodes.append("    ROOT((数据全景))")
    flowchart_styles.append("    style ROOT fill:#1e3a5f,color:#fff,stroke:#1e3a5f,stroke-width:3px")

    subgraph_idx = 0
    if sections_to_include['customer']:
        flowchart_nodes.append(f"""
    subgraph 客户指标
        direction LR
        A1((总客户<br/>{total:,}))
        A2((活跃客户<br/>{active:,}))
        A3((活跃率<br/>{active_rate:.1f}%))
    end""")
        flowchart_connections.append("    ROOT --> 客户指标")
        flowchart_styles.extend([
            "    style A1 fill:#00C9A7,color:#fff,stroke:#00C9A7,stroke-width:2px",
            "    style A2 fill:#00C9A7,color:#fff,stroke:#00C9A7,stroke-width:2px",
            "    style A3 fill:#00C9A7,color:#fff,stroke:#00C9A7,stroke-width:2px",
        ])

    if sections_to_include['order']:
        flowchart_nodes.append(f"""
    subgraph 交易指标
        direction LR
        B1((总收入<br/>¥{revenue/10000:.1f}万))
        B2((订单数<br/>{orders:,}))
        B3((客单价<br/>¥{avg_order:,.0f}))
    end""")
        flowchart_connections.append("    ROOT --> 交易指标")
        flowchart_styles.extend([
            "    style B1 fill:#3b82f6,color:#fff,stroke:#3b82f6,stroke-width:2px",
            "    style B2 fill:#3b82f6,color:#fff,stroke:#3b82f6,stroke-width:2px",
            "    style B3 fill:#3b82f6,color:#fff,stroke:#3b82f6,stroke-width:2px",
        ])

    if sections_to_include['retention']:
        flowchart_nodes.append(f"""
    subgraph 留存指标
        direction LR
        C1((30天留存<br/>{ret_rate:.2f}%))
    end""")
        flowchart_connections.append("    ROOT --> 留存指标")
        flowchart_styles.append("    style C1 fill:#8b5cf6,color:#fff,stroke:#8b5cf6,stroke-width:2px")

    if sections_to_include['channel'] and channels:
        top_ch_name = top_channel.get('channel', 'N/A') if top_channel else 'N/A'
        flowchart_nodes.append(f"""
    subgraph 渠道指标
        direction LR
        D1((渠道数<br/>{len(channels)}))
        D2((Top渠道<br/>{top_ch_name[:8]}))
    end""")
        flowchart_connections.append("    ROOT --> 渠道指标")
        flowchart_styles.extend([
            "    style D1 fill:#f59e0b,color:#fff,stroke:#f59e0b,stroke-width:2px",
            "    style D2 fill:#f59e0b,color:#fff,stroke:#f59e0b,stroke-width:2px",
        ])

    flowchart = "```mermaid\nflowchart TB\n" + "\n".join(flowchart_nodes) + "\n\n" + "\n".join(flowchart_connections) + "\n\n" + "\n".join(flowchart_styles) + "\n```"

    insights = f"""
## 执行摘要

基于对 **{total:,}** 名客户的数据分析，针对「{topic}」主题，本报告揭示了以下核心发现：

> **核心洞察：** {summary_text}。

### 关键数据一览

{flowchart}

"""

    # Dynamic section numbering
    section_num = 1

    # Customer section (conditional)
    if sections_to_include['customer']:
        new_customer_count = data.get('new_customers', 0)
        new_customer_ratio = new_customer_count / total if total > 0 else 0
        insights += f"""---

## {_cn_num(section_num)}、客户规模与活跃度分析

### {section_num}.1 客户总量结构

| 指标 | 数值 | 占比 | 健康度评估 |
|------|------|------|-----------|
| **总客户数** | {total:,} | 100% | - |
| **新客户** | {new_customer_count:,} | {new_customer_ratio*100:.1f}% | {'⚠️ 新客占比高' if new_customer_ratio > 0.5 else '✅ 正常'} |
| **活跃客户** | {active:,} | {active_rate:.1f}% | {active_status} |
| **沉睡客户** | {sleeping:,} | {100-active_rate:.1f}% | {'🔴 亟需激活' if sleeping/total > 0.7 else '⚠️ 需关注'} |

### {section_num}.2 活跃度诊断

```mermaid
pie title 客户活跃状态分布
    "活跃客户 ({active_rate:.1f}%)" : {active}
    "沉睡客户 ({100-active_rate:.1f}%)" : {sleeping}
```

{_executive_insight(f"活跃率 **{active_rate:.1f}%** {'远低于行业基准（25-35%）' if active_rate < 25 else '接近行业基准'}。{'近 **{sleeping:,}** 名沉睡客户是最大的增长金矿。' if sleeping > total * 0.7 else ''}")}

"""
        section_num += 1

    # Channel section (conditional)
    if sections_to_include['channel']:
        insights += f"""---

## {_cn_num(section_num)}、渠道分布深度分析

### {section_num}.1 渠道业绩排名

| 排名 | 渠道 | 订单数 | 销售额 | 客单价 | 表现评级 |
|------|------|--------|--------|--------|---------|
"""
        # Add channel data
        for i, ch in enumerate(channels[:10], 1):
            if not isinstance(ch, dict):
                continue
            channel_name = ch.get('channel', 'Unknown')
            order_count = ch.get('order_count', 0) or 0
            total_sales = ch.get('total_sales', 0) or 0
            avg_val = ch.get('avg_order_value', 0) or 0
            rating = "⭐⭐⭐" if i <= 3 else ("⭐⭐" if i <= 7 else "⭐")
            insights += f"| {i} | {'**' + str(channel_name) + '**' if i == 1 else str(channel_name)} | {int(order_count):,} | ¥{float(total_sales):,.0f} | ¥{float(avg_val):,.0f} | {rating} |\n"

        if channels and isinstance(top_channel, dict) and top_channel:
            insights += f"""
### {section_num}.2 渠道洞察

{_executive_insight(f"渠道分布{'健康' if len(channels) > 5 else '较为集中'}，**{top_channel.get('channel', 'N/A')}** 领跑。")}

"""
        else:
            insights += """
| (暂无渠道数据) | - | - | - | - | - |

"""
        section_num += 1

    # Retention section (conditional)
    if sections_to_include['retention']:
        insights += f"""---

## {_cn_num(section_num)}、客户留存分析

### {section_num}.1 留存率数据

| 留存周期 | 队列规模 | 留存人数 | 留存率 | 行业基准 | 状态 |
|----------|----------|----------|--------|----------|------|
"""
        benchmarks = {7: "15-20%", 30: "8-12%", 90: "5-8%"}
        for r in retention:
            if not isinstance(r, dict):
                continue
            period_days = r.get('period_days', 0) or 0
            cohort = r.get('cohort_size', 0) or 0
            retained = r.get('retained_count', 0) or 0
            rate = r.get('retention_rate', 0) or 0
            status = "🔴 危险" if rate < 3 else ("🟡 偏低" if rate < 8 else "🟢 健康")
            insights += f"| **{int(period_days)}天** | {int(cohort):,} | {int(retained):,} | {float(rate):.2f}% | {benchmarks.get(int(period_days), 'N/A')} | {status} |\n"

        insights += f"""
{_executive_insight(f"留存率处于{'**危险区间**' if ret_rate < 3 else '偏低水平'}，{'需要立即采取行动提升客户粘性' if ret_rate < 3 else '建议加强客户运营'}。")}

"""
        section_num += 1

    # Recommendations section (always included, but content based on included sections)
    insights += f"""---

## {_cn_num(section_num)}、战略建议

### {section_num}.1 优先行动项

| 优先级 | 举措 | 预期收益 | 实施建议 |
|--------|------|----------|----------|
"""
    if sections_to_include['customer']:
        insights += f"| ⭐⭐⭐ | **{'沉睡客户唤醒' if sleeping > total * 0.5 else '提升活跃度'}** | +¥{sleeping * avg_order * 0.05 / 10000:.0f}万收入 | 立即启动 |\n"
    if sections_to_include['retention']:
        insights += "| ⭐⭐⭐ | **会员忠诚度体系** | 留存率+5-10% | 2-3个月内上线 |\n"
    if sections_to_include['channel']:
        insights += "| ⭐⭐ | **渠道优化** | GMV+10-15% | 持续优化 |\n"
    if sections_to_include['order']:
        insights += "| ⭐⭐ | **提升客单价** | 客单价+10% | 交叉销售策略 |\n"

    insights += f"""
{_executive_insight("基于数据分析，建议优先聚焦以上行动项，实现业务增长。")}

"""

    return insights


def _cn_num(n: int) -> str:
    """Convert number to Chinese numeral for section headers."""
    cn_nums = {1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六", 7: "七", 8: "八", 9: "九", 10: "十"}
    return cn_nums.get(n, str(n))


def generate_data_report(
    topic: str,
    output: str,
    period: str = "365d",
    formats: str = "all",
    data_json: str = None,
    **kwargs
) -> str:
    """Generate a data-driven analysis report based on actual data.

    This function can either:
    1. Accept pre-fetched data via data_json parameter
    2. Fetch data from MCP database if data_json is not provided

    Args:
        topic: Report topic
        output: Output file path
        period: Data period (7d, 30d, 90d, 365d)
        formats: Output formats (md, html, pdf, all)
        data_json: Pre-fetched data as JSON string (optional)
    """
    import json as json_module

    base_path = _validate_output_path(output)
    output_formats = _parse_formats(formats)

    # Use provided data or fetch from MCP
    data = None
    if data_json:
        try:
            data = json_module.loads(data_json)
            # Validate parsed data is a dict
            if not isinstance(data, dict):
                return f"Error: Expected dict but got {type(data).__name__}. First 200 chars: {str(data)[:200]}"
        except json_module.JSONDecodeError as e:
            return f"Error parsing data_json (JSONDecodeError): {e}"
        except Exception as e:
            return f"Error parsing data_json: {type(e).__name__}: {e}"
    else:
        data = _fetch_analytics_data(period)

    if not data:
        return """Error: Unable to fetch data.

This skill cannot access MCP directly due to sandbox restrictions.
Please use the CLI command instead:

    sh analytics report --topic="Your Topic" --output=report.md --period=365d

This command fetches data and generates the report in one step."""

    if not isinstance(data, dict):
        return f"Error: Data must be a dict, got {type(data).__name__}"

    # Generate report header
    today = datetime.now().strftime("%Y-%m-%d")

    header = f"""---
title: "数据驱动分析报告：{topic}"
author: "SocialHub.AI 数据分析团队"
date: "{today}"
data_source: "MCP Analytics Database"
period: "{period}"
methodology: "数据驱动洞察 + MECE原则"
---

# 数据驱动分析报告：{topic}

| **报告日期** | **数据周期** | **分析方法** |
|-------------|-------------|-------------|
| {today} | {period} | 数据驱动洞察 |

---
"""

    # Generate insights based on data
    insights = _generate_data_insights(data, topic)

    # Generate appendix
    appendix = f"""
---

## 附录：数据来源

| 数据项 | 来源 | 更新时间 |
|--------|------|----------|
| 客户数据 | MCP Analytics | {today} |
| 渠道数据 | MCP Analytics | {today} |
| 留存数据 | MCP Analytics | {today} |

---

*Generated by SocialHub.AI Consulting Report Generator v3.1*

*基于 {data.get('total_customers', 0):,} 名客户、{data.get('total_orders', 0):,} 笔订单、¥{data.get('total_revenue', 0)/10000:.1f}万 交易额的全量数据分析*
"""

    # Combine all sections
    md_content = header + insights + appendix

    # Generate outputs
    title = f"数据驱动分析报告：{topic}"
    outputs = _generate_outputs(md_content, base_path, title, output_formats)

    # Return result message (avoid ¥ symbol for console compatibility)
    revenue_wan = data.get('total_revenue', 0) / 10000
    result = f"""Data-driven report generated!
Based on: {data.get('total_customers', 0):,} customers, {data.get('total_orders', 0):,} orders, RMB {revenue_wan:,.1f}wan revenue

Outputs:
"""
    result += "\n".join(f"  {o}" for o in outputs)

    return result
