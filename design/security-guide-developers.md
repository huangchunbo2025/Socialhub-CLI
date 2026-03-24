# SocialHub.AI Skills 开发者安全指南

本文档为技能开发者提供安全开发最佳实践指南。

## 1. 权限最小化原则

### 1.1 只申请必要的权限

```yaml
# skill.yaml - 好的示例
permissions:
  - file:read      # 只读取文件
  - data:read      # 只读取数据

# 避免这样做
permissions:
  - file:read
  - file:write      # 不需要写入时不要申请
  - network:internet # 不需要网络时不要申请
  - execute         # 尽量避免使用
```

### 1.2 权限说明

| 权限 | 风险等级 | 说明 | 使用场景 |
|------|---------|------|---------|
| `file:read` | 低 | 读取文件 | 配置读取、数据导入 |
| `file:write` | 中 | 写入文件 | 导出报表、保存结果 |
| `data:read` | 低 | 读取客户数据 | 数据分析、查询 |
| `data:write` | 高 | 修改客户数据 | 数据更新、批量操作 |
| `network:local` | 中 | 本地网络 | 连接本地服务 |
| `network:internet` | 高 | 互联网访问 | API调用、数据同步 |
| `config:read` | 低 | 读取配置 | 获取用户设置 |
| `config:write` | 中 | 修改配置 | 保存用户偏好 |
| `execute` | 高 | 执行命令 | 仅在必要时使用 |

## 2. 安全编码规范

### 2.1 输入验证

```python
# 好的示例 - 验证输入
def export_data(output_path: str, **kwargs):
    # 验证路径
    path = Path(output_path)

    # 检查路径遍历攻击
    if ".." in str(path):
        raise ValueError("Invalid path: path traversal not allowed")

    # 检查文件扩展名
    allowed_extensions = {".csv", ".json", ".xlsx"}
    if path.suffix.lower() not in allowed_extensions:
        raise ValueError(f"Invalid file type. Allowed: {allowed_extensions}")

    # 执行导出
    _do_export(path)
```

### 2.2 防止路径遍历

```python
# 危险 - 不要这样做
def read_file(filename):
    with open(f"/data/{filename}") as f:  # 可能被 ../../etc/passwd 攻击
        return f.read()

# 安全 - 使用 resolve 和检查
def read_file_safe(filename):
    base_dir = Path("/data").resolve()
    file_path = (base_dir / filename).resolve()

    # 确保文件在基础目录内
    if not str(file_path).startswith(str(base_dir)):
        raise SecurityError("Access denied: path outside allowed directory")

    with open(file_path) as f:
        return f.read()
```

### 2.3 敏感数据处理

```python
# 不要在日志中记录敏感数据
logger.info(f"Processing customer: {customer_id}")  # OK
logger.info(f"Customer phone: {phone_number}")      # 危险！

# 使用掩码处理敏感数据
def mask_phone(phone: str) -> str:
    if len(phone) > 4:
        return "*" * (len(phone) - 4) + phone[-4:]
    return "****"

logger.info(f"Customer phone: {mask_phone(phone_number)}")  # 安全
```

### 2.4 避免命令注入

```python
# 危险 - 命令注入风险
import os
def process_file(filename):
    os.system(f"cat {filename}")  # 如果 filename = "; rm -rf /" 会很危险

# 安全 - 使用 subprocess 和参数列表
import subprocess
def process_file_safe(filename):
    # 参数作为列表传递，不会被 shell 解析
    result = subprocess.run(
        ["cat", filename],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout
```

## 3. 网络安全

### 3.1 使用 HTTPS

```python
# 始终使用 HTTPS
API_URL = "https://api.example.com/v1"  # 正确

# 不要使用 HTTP
API_URL = "http://api.example.com/v1"   # 危险！
```

### 3.2 验证证书

```python
import httpx

# 默认验证证书（推荐）
response = httpx.get("https://api.example.com")

# 不要禁用证书验证
response = httpx.get("https://api.example.com", verify=False)  # 危险！
```

### 3.3 处理 API 密钥

```python
# 不要硬编码密钥
API_KEY = "sk_live_xxxxx"  # 危险！

# 从环境变量或配置读取
import os
API_KEY = os.environ.get("API_KEY")

# 或从 CLI 配置读取
from socialhub.cli.config import Config
config = Config()
API_KEY = config.get("api_key")
```

## 4. 错误处理

### 4.1 不要泄露敏感信息

```python
# 危险 - 泄露内部路径和堆栈
try:
    process_data()
except Exception as e:
    return f"Error: {e}\n{traceback.format_exc()}"

# 安全 - 返回通用错误，记录详细日志
import logging
logger = logging.getLogger(__name__)

try:
    process_data()
except Exception as e:
    logger.exception("Data processing failed")  # 内部日志
    return "An error occurred while processing data"  # 用户消息
```

### 4.2 安全的异常处理

```python
def export_parquet(output: str, **kwargs) -> str:
    """导出为 Parquet 格式"""
    try:
        # 验证输入
        if not output:
            raise ValueError("Output path is required")

        # 执行导出
        _do_export(output)
        return f"Successfully exported to {output}"

    except PermissionError:
        return "Error: Permission denied. Check file permissions."
    except ValueError as e:
        return f"Error: Invalid input - {e}"
    except Exception:
        # 记录详细错误但返回通用消息
        logger.exception("Export failed")
        return "Error: Export failed. Please try again."
```

## 5. 技能清单最佳实践

### 5.1 完整的 skill.yaml

```yaml
name: "my-skill"
version: "1.0.0"
display_name: "我的技能"
description: "技能的详细描述，说明功能和用途"
author: "Your Name"
license: "MIT"
homepage: "https://github.com/your/skill"

category: "data"
tags:
  - export
  - analytics

compatibility:
  cli_version: ">=0.1.0"
  python_version: ">=3.10"

# 只申请必要的权限
permissions:
  - file:read
  - file:write

# 声明所有依赖
dependencies:
  python:
    - pandas>=2.0.0
    - pyarrow>=14.0.0

entrypoint: "main.py"
commands:
  - name: "export"
    description: "导出数据"
    function: "export_data"
    arguments:
      - name: "output"
        type: "string"
        required: true
        description: "输出文件路径"
```

### 5.2 版本管理

遵循语义化版本规范：
- `MAJOR.MINOR.PATCH`
- MAJOR: 不兼容的 API 变更
- MINOR: 向后兼容的功能添加
- PATCH: 向后兼容的问题修复

## 6. 测试要求

### 6.1 安全测试

```python
# tests/test_security.py
import pytest
from my_skill.main import export_data

def test_path_traversal_blocked():
    """测试路径遍历攻击被阻止"""
    with pytest.raises(ValueError):
        export_data("../../../etc/passwd")

def test_invalid_extension_blocked():
    """测试非法文件扩展名被阻止"""
    with pytest.raises(ValueError):
        export_data("output.exe")

def test_empty_path_rejected():
    """测试空路径被拒绝"""
    with pytest.raises(ValueError):
        export_data("")
```

### 6.2 权限测试

```python
def test_works_without_network():
    """测试在无网络权限下正常工作"""
    # 技能应该在没有 network:internet 权限时仍能工作
    # 或者明确失败并给出有用的错误信息
    pass

def test_minimal_file_access():
    """测试只访问必要的文件"""
    # 验证技能只访问它声明的目录
    pass
```

## 7. 提交审核清单

在提交技能审核前，请确认：

- [ ] 只申请了必要的权限
- [ ] 没有硬编码的凭据或密钥
- [ ] 所有用户输入都经过验证
- [ ] 没有路径遍历漏洞
- [ ] 没有命令注入漏洞
- [ ] 使用 HTTPS 进行网络请求
- [ ] 错误消息不泄露敏感信息
- [ ] 有完整的测试覆盖
- [ ] 文档完整准确
- [ ] 版本号正确更新

## 8. 常见安全问题

### 8.1 审核时被拒绝的常见原因

1. **过度权限请求** - 申请了不需要的权限
2. **硬编码凭据** - 代码中包含 API 密钥
3. **不安全的文件操作** - 没有验证文件路径
4. **命令注入风险** - 使用 os.system() 或未转义的命令
5. **不安全的网络请求** - 禁用 SSL 验证
6. **敏感数据泄露** - 在日志或错误中暴露用户数据

### 8.2 修复指南

如果您的技能被拒绝，请：

1. 仔细阅读审核反馈
2. 修复所有指出的问题
3. 添加相关的测试用例
4. 更新版本号
5. 重新提交审核

## 9. 联系方式

如有安全相关问题，请联系：
- 安全团队邮箱: security@socialhub.ai
- 文档反馈: docs@socialhub.ai

---

*文档版本: 1.0.0*
*最后更新: 2024-03-20*
