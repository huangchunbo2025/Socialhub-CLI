# 记忆系统安全与合规研究

> 调研日期：2026-04-02  
> 覆盖：中国 PIPL + 企业数据治理 + 安全最佳实践

---

## 记忆数据 PII 分类

### 绝对禁止写入记忆的数据

| 数据类型 | 示例 | 原因 |
|----------|------|------|
| 客户手机号 | `13812345678` | PIPL 个人信息，禁止落盘 |
| 客户身份证号 | `110101199001011234` | PIPL 敏感个人信息 |
| 客户邮箱 | `user@example.com` | PIPL 个人信息 |
| 订单号（16位+）| `1234567890123456` | 可关联到具体交易和个人 |
| 客户姓名 | `张三` | PIPL 个人信息 |

**原则**：记忆系统只存储**聚合统计结论**，绝不存储**个人级数据**。

### 允许写入记忆的业务数据

| 数据类型 | 示例 | 原因 |
|----------|------|------|
| 聚合指标 | `渠道A GMV占比60%` | 无法反向识别个人 |
| 分析结论 | `女装品类周末转化率高40%` | 汇总统计，无 PII |
| 用户偏好 | `default_period: 7d` | 操作偏好，无客户数据 |
| 活动元数据 | `ACT001 持续7天，GMV +15%` | 汇总效果，无个人信息 |

### 写入前 PII 扫描

复用 `cli/ai/trace.py` 中已有的 `_mask_pii()` 函数：

```python
from cli.ai.trace import _build_pii_patterns, _mask_pii

# 写入记忆前必须经过 PII 扫描
content = _mask_pii(raw_content, patterns)
assert "[PHONE_MASKED]" not in content or log_warning()
```

**注意**：`_mask_pii()` 是 TraceLogger 内部函数，Memory 系统复用时需在 `trace.py` 中将其提升为模块级公开函数，或在 `memory/` 中独立实现相同逻辑。

---

## 访问控制设计建议

### 文件权限（沿用现有模式）

```python
# 与 SessionStore 和 TraceLogger 完全一致的写入模式
fd = os.open(str(file_path), os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w", encoding="utf-8") as f:
    yaml.dump(data, f)
```

**原则**：`0o600`（仅 owner 读写），从创建时即生效，消除 chmod TOCTOU 窗口。

### 目录权限

```python
memory_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
```

### 可选加密层（高安全场景）

```python
from cryptography.fernet import Fernet

# 密钥来自环境变量或系统 Keychain（不能硬编码）
key = os.environ.get("SOCIALHUB_MEMORY_KEY")
if key:
    f = Fernet(key)
    encrypted = f.encrypt(content.encode())
    file_path.write_bytes(encrypted)
```

**实现建议**：默认不加密（与 SessionStore 一致），企业高安全场景通过 `config.memory.encrypt=true` 启用。

### Skills 沙箱扩展

`cli/skills/sandbox/filesystem.py` 的 monkey-patch 需扩展，禁止 Skills 访问 memory 目录：

```python
PROTECTED_PATHS = [
    Path.home() / ".socialhub" / "memory",
    Path.home() / ".socialhub" / "sessions",
    # ... 已有保护路径
]
```

---

## 数据保留策略

| 层次 | TTL | 清理触发 |
|------|-----|---------|
| L1 工作记忆（session） | 24h | 每次加载时惰性清理（现有逻辑） |
| L2 情节记忆（session summaries） | 30天 | 每次 MemoryManager 初始化时扫描 |
| L3 语义记忆（analysis insights） | 90天活跃期，之后归档 | 每周一次后台清理（可选）|
| L4 程序性记忆（user_profile/business_context）| 永久 | 用户手动更新/删除 |

### 用户主动删除

```bash
sh memory clear --all                    # 清除所有记忆
sh memory clear --type=insights          # 只清除分析洞察
sh memory clear --before=2026-01-01      # 清除指定日期前的记忆
```

### PIPL 第47条合规：撤回同意立即删除

```python
def revoke_consent(self) -> None:
    """PIPL §47 — 用户撤回同意时立即全量删除个人相关记忆。"""
    shutil.rmtree(self.memory_dir / "session_summaries", ignore_errors=True)
    shutil.rmtree(self.memory_dir / "analysis_insights", ignore_errors=True)
    # 保留 user_profile（用户自己的偏好设置）和 business_context（企业数据）
    # 这两类不含个人信息，可选保留
```

---

## 审计能力要求

### 每条记忆写入事件需记录

```python
audit_event = {
    "ts": _utcnow(),
    "type": "memory_write",
    "memory_type": "insight",          # insight / preference / summary
    "content_hash": sha256(content),   # SHA-256 哈希（不存原文）
    "pii_masked": True,                 # 是否经过 PII 脱敏
    "session_id": current_session_id,   # 来源会话
    "trace_id": current_trace_id,       # 来源执行链
    "file_path": str(relative_path),    # 相对路径
}
# 写入现有 ai_trace.jsonl（复用 TraceLogger 基础设施）
trace_logger.log_memory_write(audit_event)
```

**注意**：审计日志记录文件路径和内容哈希，不记录内容本身（避免二次 PII 风险）。

### 完整执行链路

```
用户输入 → trace_id → session_id → memory_write (content_hash) → 文件路径
```

这样当审计员需要追查某条记忆的来源时，可以：
1. 在 `ai_trace.jsonl` 中找到 `memory_write` 事件
2. 通过 `trace_id` 找到对应的 `plan_start` 事件
3. 还原完整的 AI 决策链

---

## PIPL 合规注意点

| 条款 | 要求 | SocialHub 对应设计 |
|------|------|------------------|
| **第29条** | 敏感个人信息需单独取得同意 | 禁止写入个人级数据；写入前 PII 扫描 |
| **第38条** | 禁止向境外传输个人信息 | 记忆文件本地存储，不同步到 MCP Server |
| **第47条** | 用户撤回同意时须立即删除 | `sh memory clear --all` 命令 |
| **第55条** | 自动化决策需影响评估 | 记忆驱动的 AI 建议需标注"基于历史分析"来源 |
| **2025年合规审计** | 处理千万级数据需两年一审 | 记忆文件含内容哈希，支持审计员抽查 |

---

## 与现有安全机制集成

| 现有机制 | 集成方式 |
|----------|---------|
| `trace.py::_mask_pii()` | 记忆写入前复用此函数做 PII 扫描 |
| `SessionStore` 原子写入 + 0o600 | `MemoryStore` 完全复用相同模式 |
| `SessionStore.purge_expired()` | `MemoryStore` 实现类似的 `purge_expired(ttl_days)` |
| `TraceLogger._write()` | 扩展 `log_memory_write()` 方法记录审计事件 |
| `sandbox/filesystem.py` | 扩展 PROTECTED_PATHS 覆盖 memory 目录 |

---

## 来源 URL

- https://mem0.ai/blog/ai-memory-security-best-practices
- https://www.microsoft.com/en-us/security/blog/2026/03/20/secure-agentic-ai-end-to-end/
- https://securiti.ai/china-personal-information-protection-law-overview/
- https://www.mayerbrown.com/en/insights/publications/2025/04/china-finalises-the-measures-for-personal-information-protection-compliance-audits
- https://galileo.ai/blog/ai-agent-compliance-governance-audit-trails-risk-management
- https://arxiv.org/abs/2510.11558 (Zero Data Retention in LLM Enterprise AI)
- https://www.databricks.com/blog/agentic-ai-security-new-risks-and-controls-databricks-ai-security-framework-dasf-v30
