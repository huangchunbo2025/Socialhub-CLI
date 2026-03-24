# SocialHub.AI Skills 安全系统开发计划

## 项目概述

基于现有 Skills Store 设计文档和代码分析，制定完整的安全系统开发计划。

### 当前状态评估

| 模块 | 完成度 | 安全等级 | 优先级 |
|------|--------|---------|--------|
| 数据模型 (models.py) | 100% | ✅ 安全 | - |
| 本地注册表 (registry.py) | 100% | ✅ 安全 | - |
| CLI命令 (commands/skills.py) | 100% | ✅ 安全 | - |
| 商店客户端 (store_client.py) | 100% | ✅ 安全 | - |
| 运行时加载 (loader.py) | 100% | ⚠️ 需加固 | 高 |
| 安装管理 (manager.py) | 100% | ⚠️ 需加固 | 高 |
| **签名验证 (security.py)** | **60%** | **❌ 严重漏洞** | **紧急** |

### 关键安全漏洞

```python
# security.py:92-93 - 签名验证被绕过!
def _verify_signature(self, name, version, signature) -> bool:
    if not signature:
        return False
    return True  # ← 危险：总是返回 True
```

---

## 开发阶段规划

```
┌─────────────────────────────────────────────────────────────────────┐
│  Phase 1: 紧急安全修复                                               │
│  [██████████] 签名验证 + 哈希校验                                    │
├─────────────────────────────────────────────────────────────────────┤
│  Phase 2: 权限系统强化                                               │
│  [████████░░] 用户确认 + 运行时检查                                  │
├─────────────────────────────────────────────────────────────────────┤
│  Phase 3: 沙箱隔离实现                                               │
│  [██████░░░░] 文件/网络/命令限制                                     │
├─────────────────────────────────────────────────────────────────────┤
│  Phase 4: 审核与监控                                                 │
│  [████░░░░░░] 审计日志 + 撤销列表                                    │
├─────────────────────────────────────────────────────────────────────┤
│  Phase 5: 测试与文档                                                 │
│  [██░░░░░░░░] 单元测试 + 安全文档                                    │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Phase 1: 紧急安全修复

### 1.1 实现 Ed25519 签名验证

**目标**: 修复签名验证绕过漏洞

**文件**: `socialhub/cli/skills/security.py`

**任务清单**:

- [ ] **Task 1.1.1**: 添加 cryptography 依赖
  ```bash
  # pyproject.toml 或 requirements.txt
  cryptography>=41.0.0
  ```

- [ ] **Task 1.1.2**: 实现密钥管理类
  ```python
  class KeyManager:
      """管理官方公钥和证书"""

      # 官方公钥存储位置
      OFFICIAL_KEY_PATH = "~/.socialhub/keys/official_public.pem"
      BACKUP_KEY_URL = "https://keys.socialhub.ai/official_public.pem"

      def __init__(self):
          self._public_key: Optional[Ed25519PublicKey] = None

      def load_public_key(self) -> Ed25519PublicKey:
          """加载官方公钥"""
          pass

      def update_public_key(self) -> bool:
          """从官方服务器更新公钥"""
          pass

      def verify_key_fingerprint(self, key: bytes) -> bool:
          """验证公钥指纹"""
          pass
  ```

- [ ] **Task 1.1.3**: 重写签名验证逻辑
  ```python
  from cryptography.hazmat.primitives.asymmetric import ed25519
  from cryptography.exceptions import InvalidSignature

  def _verify_signature(
      self,
      name: str,
      version: str,
      signature: str,
  ) -> bool:
      """使用 Ed25519 验证签名"""
      try:
          # 1. 解码 base64 签名
          signature_bytes = base64.b64decode(signature)

          # 2. 重构签名数据
          signed_data = self._build_signed_data(name, version)

          # 3. 加载公钥
          public_key = self.key_manager.load_public_key()

          # 4. 验证签名
          public_key.verify(signature_bytes, signed_data)
          return True

      except InvalidSignature:
          raise SecurityError(f"Invalid signature for {name}@{version}")
      except Exception as e:
          raise SecurityError(f"Signature verification failed: {e}")

  def _build_signed_data(self, name: str, version: str) -> bytes:
      """构建待签名数据"""
      # 规范化的签名数据格式
      data = {
          "name": name,
          "version": version,
          "timestamp": self._get_certification_time(),
      }
      # 使用 canonical JSON 确保一致性
      return json.dumps(data, sort_keys=True, separators=(',', ':')).encode()
  ```

- [ ] **Task 1.1.4**: 添加签名验证测试
  ```python
  # tests/test_security.py
  class TestSignatureVerifier:
      def test_valid_signature(self):
          """测试有效签名验证"""
          pass

      def test_invalid_signature_rejected(self):
          """测试无效签名被拒绝"""
          pass

      def test_tampered_data_rejected(self):
          """测试篡改数据被拒绝"""
          pass

      def test_expired_certificate_rejected(self):
          """测试过期证书被拒绝"""
          pass
  ```

### 1.2 增强哈希校验

**目标**: 确保包完整性验证不可绕过

**任务清单**:

- [ ] **Task 1.2.1**: 强制哈希验证
  ```python
  # manager.py - install() 方法
  def install(self, name: str, version: Optional[str] = None) -> bool:
      # ... 下载包 ...

      # 强制哈希验证 (不可跳过)
      if not self._verify_package_integrity(package_path, expected_hash):
          self._cleanup_failed_install(name)
          raise SecurityError(
              f"Package integrity check failed for {name}. "
              "The package may have been tampered with."
          )
  ```

- [ ] **Task 1.2.2**: 多重哈希支持
  ```python
  class HashVerifier:
      """支持多种哈希算法"""

      SUPPORTED_ALGORITHMS = ["sha256", "sha384", "sha512"]

      def verify(
          self,
          content: bytes,
          expected_hashes: dict[str, str],
      ) -> bool:
          """验证多重哈希"""
          for algo, expected in expected_hashes.items():
              if algo not in self.SUPPORTED_ALGORITHMS:
                  continue
              hasher = hashlib.new(algo)
              hasher.update(content)
              if hasher.hexdigest() != expected:
                  return False
          return True
  ```

### 1.3 证书链验证

**目标**: 实现完整的证书验证链

**任务清单**:

- [ ] **Task 1.3.1**: 证书模型扩展
  ```python
  # models.py
  class CertificateChain(BaseModel):
      """证书链信息"""
      root_ca: str                    # 根证书
      intermediate_ca: Optional[str]  # 中间证书
      leaf_certificate: str           # 叶子证书
      chain_valid: bool = False
  ```

- [ ] **Task 1.3.2**: 证书链验证器
  ```python
  class CertificateChainVerifier:
      """验证证书链"""

      TRUSTED_ROOT_CAS = [
          "SocialHub.AI Root CA",
      ]

      def verify_chain(self, chain: CertificateChain) -> bool:
          """验证完整的证书链"""
          pass

      def is_revoked(self, certificate_id: str) -> bool:
          """检查证书是否被撤销"""
          pass
  ```

---

## Phase 2: 权限系统强化

### 2.1 敏感权限用户确认

**目标**: 敏感操作必须经过用户明确确认

**文件**: `socialhub/cli/skills/security.py`, `socialhub/cli/skills/loader.py`

**任务清单**:

- [ ] **Task 2.1.1**: 创建权限确认对话框
  ```python
  # security.py
  from rich.prompt import Confirm
  from rich.panel import Panel

  class PermissionPrompter:
      """处理权限确认对话"""

      def request_permissions(
          self,
          skill_name: str,
          permissions: list[str],
          console: Console,
      ) -> bool:
          """请求用户确认敏感权限"""
          sensitive = [p for p in permissions if self.is_sensitive(p)]

          if not sensitive:
              return True

          # 显示权限请求面板
          panel = self._build_permission_panel(skill_name, sensitive)
          console.print(panel)

          # 逐个确认敏感权限
          for perm in sensitive:
              desc = self._get_permission_description(perm)
              if not Confirm.ask(f"允许 [bold]{perm}[/bold] ({desc})?"):
                  return False

          return True

      def _build_permission_panel(
          self,
          skill_name: str,
          permissions: list[str],
      ) -> Panel:
          """构建权限请求面板"""
          content = [
              f"[bold yellow]⚠️ 技能 '{skill_name}' 请求以下敏感权限:[/bold yellow]\n"
          ]
          for perm in permissions:
              risk = self._get_risk_level(perm)
              icon = "🔴" if risk == "high" else "🟡"
              content.append(f"  {icon} {perm}: {self._get_permission_description(perm)}")

          return Panel("\n".join(content), title="权限请求", border_style="yellow")
  ```

- [ ] **Task 2.1.2**: 集成到安装流程
  ```python
  # manager.py - install()
  def install(self, name: str, version: Optional[str] = None) -> bool:
      # ... 下载和验证 ...

      # 检查并请求敏感权限
      manifest = self._load_manifest(skill_dir)
      permissions = [p.value for p in manifest.permissions]

      prompter = PermissionPrompter()
      if not prompter.request_permissions(name, permissions, self.console):
          self._cleanup_failed_install(name)
          raise InstallError(f"Installation cancelled: permissions denied")

      # 记录已授权的权限
      for perm in permissions:
          self.permission_checker.grant_permission(name, perm)
  ```

- [ ] **Task 2.1.3**: 权限持久化存储
  ```python
  # security.py
  class PermissionStore:
      """持久化存储权限授权"""

      PERMISSIONS_FILE = "~/.socialhub/permissions.json"

      def save_grants(self, skill_name: str, permissions: set[str]) -> None:
          """保存权限授权"""
          pass

      def load_grants(self, skill_name: str) -> set[str]:
          """加载权限授权"""
          pass

      def revoke_all(self, skill_name: str) -> None:
          """撤销所有权限"""
          pass
  ```

### 2.2 运行时权限检查

**目标**: 在技能执行时实时检查权限

**任务清单**:

- [ ] **Task 2.2.1**: 创建权限上下文管理器
  ```python
  # security.py
  from contextlib import contextmanager

  class PermissionContext:
      """权限执行上下文"""

      def __init__(self, skill_name: str, permissions: set[str]):
          self.skill_name = skill_name
          self.permissions = permissions
          self._original_funcs = {}

      @contextmanager
      def enforce(self):
          """在上下文中强制执行权限"""
          self._install_guards()
          try:
              yield
          finally:
              self._remove_guards()

      def _install_guards(self):
          """安装权限守卫"""
          # 拦截文件操作
          if "file:write" not in self.permissions:
              self._guard_file_write()

          # 拦截网络操作
          if "network:internet" not in self.permissions:
              self._guard_network()

          # 拦截命令执行
          if "execute" not in self.permissions:
              self._guard_execute()
  ```

- [ ] **Task 2.2.2**: 集成到加载器
  ```python
  # loader.py - execute_command()
  def execute_command(
      self,
      skill_name: str,
      command_name: str,
      **kwargs,
  ) -> Any:
      skill_info = self._loaded_skills.get(skill_name)

      # 创建权限上下文
      permissions = self.permission_checker.get_granted_permissions(skill_name)
      context = PermissionContext(skill_name, permissions)

      # 在权限上下文中执行命令
      with context.enforce():
          func = self.get_command(skill_name, command_name)
          return func(**kwargs)
  ```

### 2.3 权限审计日志

**目标**: 记录所有权限相关操作

**任务清单**:

- [ ] **Task 2.3.1**: 创建审计日志器
  ```python
  # security.py
  import logging
  from datetime import datetime

  class SecurityAuditLogger:
      """安全审计日志"""

      LOG_FILE = "~/.socialhub/logs/security_audit.log"

      def __init__(self):
          self.logger = self._setup_logger()

      def log_permission_grant(
          self,
          skill_name: str,
          permission: str,
          granted_by: str = "user",
      ) -> None:
          """记录权限授予"""
          self.logger.info(
              f"PERMISSION_GRANTED | skill={skill_name} | "
              f"permission={permission} | granted_by={granted_by}"
          )

      def log_permission_denied(
          self,
          skill_name: str,
          permission: str,
          reason: str,
      ) -> None:
          """记录权限拒绝"""
          self.logger.warning(
              f"PERMISSION_DENIED | skill={skill_name} | "
              f"permission={permission} | reason={reason}"
          )

      def log_security_violation(
          self,
          skill_name: str,
          violation_type: str,
          details: str,
      ) -> None:
          """记录安全违规"""
          self.logger.error(
              f"SECURITY_VIOLATION | skill={skill_name} | "
              f"type={violation_type} | details={details}"
          )
  ```

---

## Phase 3: 沙箱隔离实现

### 3.1 文件系统隔离

**目标**: 限制技能只能访问授权目录

**任务清单**:

- [ ] **Task 3.1.1**: 创建文件系统沙箱
  ```python
  # sandbox/filesystem.py
  from pathlib import Path
  from typing import Set

  class FileSystemSandbox:
      """文件系统沙箱"""

      def __init__(self, skill_name: str, allowed_paths: Set[Path]):
          self.skill_name = skill_name
          self.allowed_paths = allowed_paths
          self.work_dir = Path(f"~/.socialhub/skills/sandbox/{skill_name}").expanduser()

      def is_path_allowed(self, path: Path) -> bool:
          """检查路径是否允许访问"""
          resolved = path.resolve()

          # 始终允许工作目录
          if resolved.is_relative_to(self.work_dir):
              return True

          # 检查白名单
          for allowed in self.allowed_paths:
              if resolved.is_relative_to(allowed):
                  return True

          return False

      def guard_open(self, original_open):
          """守卫 open 函数"""
          def guarded_open(file, mode='r', *args, **kwargs):
              path = Path(file)

              # 读取权限检查
              if 'r' in mode and not self.is_path_allowed(path):
                  raise PermissionError(
                      f"Skill '{self.skill_name}' is not allowed to read: {path}"
                  )

              # 写入权限检查
              if any(m in mode for m in ['w', 'a', 'x']):
                  if not self.is_path_allowed(path):
                      raise PermissionError(
                          f"Skill '{self.skill_name}' is not allowed to write: {path}"
                      )

              return original_open(file, mode, *args, **kwargs)

          return guarded_open
  ```

- [ ] **Task 3.1.2**: 集成 pathlib 保护
  ```python
  # sandbox/filesystem.py
  class PathlibGuard:
      """保护 pathlib 操作"""

      GUARDED_METHODS = [
          'write_text', 'write_bytes',
          'unlink', 'rmdir',
          'rename', 'replace',
          'mkdir', 'touch',
      ]

      def install(self, sandbox: FileSystemSandbox):
          """安装 pathlib 守卫"""
          for method_name in self.GUARDED_METHODS:
              self._guard_method(method_name, sandbox)
  ```

### 3.2 网络访问控制

**目标**: 限制技能的网络访问能力

**任务清单**:

- [ ] **Task 3.2.1**: 创建网络沙箱
  ```python
  # sandbox/network.py
  import socket
  from typing import Set

  class NetworkSandbox:
      """网络沙箱"""

      def __init__(
          self,
          skill_name: str,
          allow_local: bool = False,
          allow_internet: bool = False,
          allowed_hosts: Set[str] = None,
      ):
          self.skill_name = skill_name
          self.allow_local = allow_local
          self.allow_internet = allow_internet
          self.allowed_hosts = allowed_hosts or set()

      def is_connection_allowed(self, host: str, port: int) -> bool:
          """检查连接是否允许"""
          # 本地连接检查
          if self._is_local(host):
              return self.allow_local

          # 白名单检查
          if host in self.allowed_hosts:
              return True

          # 互联网访问检查
          return self.allow_internet

      def _is_local(self, host: str) -> bool:
          """检查是否是本地地址"""
          local_hosts = {'localhost', '127.0.0.1', '::1'}
          return host in local_hosts or host.startswith('192.168.')

      def guard_socket(self, original_socket):
          """守卫 socket 连接"""
          sandbox = self

          class GuardedSocket(original_socket):
              def connect(self, address):
                  host, port = address[0], address[1]
                  if not sandbox.is_connection_allowed(host, port):
                      raise PermissionError(
                          f"Skill '{sandbox.skill_name}' is not allowed to connect to: {host}:{port}"
                      )
                  return super().connect(address)

          return GuardedSocket
  ```

- [ ] **Task 3.2.2**: HTTP 客户端拦截
  ```python
  # sandbox/network.py
  class HttpClientGuard:
      """HTTP 客户端守卫"""

      def guard_httpx(self, sandbox: NetworkSandbox):
          """守卫 httpx 库"""
          pass

      def guard_requests(self, sandbox: NetworkSandbox):
          """守卫 requests 库"""
          pass

      def guard_urllib(self, sandbox: NetworkSandbox):
          """守卫 urllib 库"""
          pass
  ```

### 3.3 命令执行限制

**目标**: 防止技能执行任意系统命令

**任务清单**:

- [ ] **Task 3.3.1**: 创建命令执行沙箱
  ```python
  # sandbox/execute.py
  import subprocess
  from typing import List, Set

  class ExecuteSandbox:
      """命令执行沙箱"""

      # 危险命令黑名单
      DANGEROUS_COMMANDS = {
          'rm', 'rmdir', 'del',
          'format', 'fdisk',
          'shutdown', 'reboot',
          'chmod', 'chown',
          'kill', 'killall',
          'sudo', 'su',
      }

      def __init__(
          self,
          skill_name: str,
          allow_execute: bool = False,
          allowed_commands: Set[str] = None,
      ):
          self.skill_name = skill_name
          self.allow_execute = allow_execute
          self.allowed_commands = allowed_commands or set()

      def is_command_allowed(self, command: List[str]) -> bool:
          """检查命令是否允许执行"""
          if not self.allow_execute:
              return False

          if not command:
              return False

          cmd_name = Path(command[0]).name.lower()

          # 检查危险命令
          if cmd_name in self.DANGEROUS_COMMANDS:
              return False

          # 检查白名单
          if self.allowed_commands and cmd_name not in self.allowed_commands:
              return False

          return True

      def guard_subprocess(self, original_run):
          """守卫 subprocess.run"""
          sandbox = self

          def guarded_run(args, *a, **kw):
              cmd = args if isinstance(args, list) else [args]
              if not sandbox.is_command_allowed(cmd):
                  raise PermissionError(
                      f"Skill '{sandbox.skill_name}' is not allowed to execute: {cmd[0]}"
                  )
              return original_run(args, *a, **kw)

          return guarded_run
  ```

### 3.4 统一沙箱管理器

**目标**: 整合所有沙箱组件

**任务清单**:

- [ ] **Task 3.4.1**: 创建沙箱管理器
  ```python
  # sandbox/manager.py
  from contextlib import contextmanager

  class SandboxManager:
      """统一沙箱管理"""

      def __init__(self, skill_name: str, permissions: Set[str]):
          self.skill_name = skill_name
          self.permissions = permissions

          # 初始化各个沙箱
          self.fs_sandbox = FileSystemSandbox(
              skill_name,
              self._get_allowed_paths()
          )
          self.net_sandbox = NetworkSandbox(
              skill_name,
              allow_local="network:local" in permissions,
              allow_internet="network:internet" in permissions,
          )
          self.exec_sandbox = ExecuteSandbox(
              skill_name,
              allow_execute="execute" in permissions,
          )

      @contextmanager
      def activate(self):
          """激活所有沙箱"""
          # 保存原始函数
          original_open = builtins.open
          original_socket = socket.socket
          original_subprocess_run = subprocess.run

          try:
              # 安装守卫
              builtins.open = self.fs_sandbox.guard_open(original_open)
              socket.socket = self.net_sandbox.guard_socket(original_socket)
              subprocess.run = self.exec_sandbox.guard_subprocess(original_subprocess_run)

              yield

          finally:
              # 恢复原始函数
              builtins.open = original_open
              socket.socket = original_socket
              subprocess.run = original_subprocess_run
  ```

---

## Phase 4: 审核与监控

### 4.1 证书撤销列表 (CRL)

**目标**: 支持紧急撤销恶意技能

**任务清单**:

- [ ] **Task 4.1.1**: 创建撤销列表管理器
  ```python
  # security.py
  class RevocationListManager:
      """证书撤销列表管理"""

      CRL_URL = "https://skills.socialhub.ai/api/v1/crl"
      LOCAL_CRL_PATH = "~/.socialhub/security/crl.json"
      UPDATE_INTERVAL = 3600  # 1小时更新一次

      def __init__(self):
          self._revoked_skills: Set[str] = set()
          self._revoked_certificates: Set[str] = set()
          self._last_update: Optional[datetime] = None

      def is_revoked(self, skill_name: str, certificate_id: str) -> bool:
          """检查技能或证书是否被撤销"""
          self._maybe_update()
          return (
              skill_name in self._revoked_skills or
              certificate_id in self._revoked_certificates
          )

      def update(self) -> bool:
          """从服务器更新撤销列表"""
          try:
              response = httpx.get(self.CRL_URL, timeout=10)
              data = response.json()

              self._revoked_skills = set(data.get("revoked_skills", []))
              self._revoked_certificates = set(data.get("revoked_certificates", []))
              self._last_update = datetime.now()

              self._save_local_cache()
              return True
          except Exception:
              return False

      def _maybe_update(self):
          """按需更新撤销列表"""
          if self._last_update is None:
              self._load_local_cache()

          if self._should_update():
              self.update()
  ```

- [ ] **Task 4.1.2**: 集成撤销检查
  ```python
  # manager.py - install()
  def install(self, name: str, version: Optional[str] = None) -> bool:
      # ... 验证签名后 ...

      # 检查撤销状态
      cert_id = manifest.certification.certificate_id
      if self.revocation_manager.is_revoked(name, cert_id):
          raise SecurityError(
              f"Skill '{name}' has been revoked for security reasons. "
              "Installation is blocked."
          )
  ```

### 4.2 安全事件上报

**目标**: 收集安全事件用于分析

**任务清单**:

- [ ] **Task 4.2.1**: 创建事件上报器
  ```python
  # security.py
  class SecurityEventReporter:
      """安全事件上报"""

      REPORT_URL = "https://skills.socialhub.ai/api/v1/security/events"

      def report_violation(
          self,
          skill_name: str,
          violation_type: str,
          details: dict,
      ) -> None:
          """上报安全违规事件"""
          event = {
              "skill_name": skill_name,
              "violation_type": violation_type,
              "details": details,
              "timestamp": datetime.now().isoformat(),
              "cli_version": self._get_cli_version(),
          }

          # 异步上报，不阻塞主流程
          self._async_report(event)

      def report_install_failure(
          self,
          skill_name: str,
          reason: str,
      ) -> None:
          """上报安装失败事件"""
          pass
  ```

### 4.3 技能健康检查

**目标**: 定期检查已安装技能的安全状态

**任务清单**:

- [ ] **Task 4.3.1**: 创建健康检查器
  ```python
  # security.py
  class SkillHealthChecker:
      """技能健康检查"""

      def check_all(self) -> List[HealthCheckResult]:
          """检查所有已安装技能"""
          results = []
          for skill in self.registry.list_installed():
              result = self.check_skill(skill.name)
              results.append(result)
          return results

      def check_skill(self, skill_name: str) -> HealthCheckResult:
          """检查单个技能健康状态"""
          checks = [
              self._check_certificate_expiry(skill_name),
              self._check_revocation_status(skill_name),
              self._check_file_integrity(skill_name),
              self._check_update_available(skill_name),
          ]
          return HealthCheckResult(skill_name, checks)
  ```

- [ ] **Task 4.3.2**: 添加 CLI 命令
  ```python
  # commands/skills.py
  @app.command("health")
  def health_check(
      name: Optional[str] = typer.Argument(None),
      fix: bool = typer.Option(False, "--fix", help="自动修复问题"),
  ):
      """检查技能安全状态"""
      checker = SkillHealthChecker()

      if name:
          result = checker.check_skill(name)
          _display_health_result(result)
      else:
          results = checker.check_all()
          _display_health_summary(results)

      if fix:
          _auto_fix_issues(results)
  ```

---

## Phase 5: 测试与文档

### 5.1 单元测试

**目标**: 确保安全代码的正确性

**任务清单**:

- [ ] **Task 5.1.1**: 签名验证测试
  ```python
  # tests/test_security.py
  import pytest
  from socialhub.cli.skills.security import SignatureVerifier, SecurityError

  class TestSignatureVerifier:
      @pytest.fixture
      def verifier(self):
          return SignatureVerifier()

      @pytest.fixture
      def valid_manifest(self):
          """创建有效签名的测试清单"""
          pass

      def test_valid_signature_passes(self, verifier, valid_manifest):
          """有效签名应该通过验证"""
          assert verifier.verify_manifest_signature(valid_manifest) is True

      def test_invalid_signature_raises(self, verifier):
          """无效签名应该抛出 SecurityError"""
          manifest = self._create_invalid_signature_manifest()
          with pytest.raises(SecurityError):
              verifier.verify_manifest_signature(manifest)

      def test_expired_certificate_raises(self, verifier):
          """过期证书应该抛出 SecurityError"""
          manifest = self._create_expired_manifest()
          with pytest.raises(SecurityError, match="expired"):
              verifier.verify_manifest_signature(manifest)

      def test_untrusted_ca_raises(self, verifier):
          """不可信CA应该抛出 SecurityError"""
          manifest = self._create_untrusted_ca_manifest()
          with pytest.raises(SecurityError, match="not certified by trusted authority"):
              verifier.verify_manifest_signature(manifest)
  ```

- [ ] **Task 5.1.2**: 权限系统测试
  ```python
  # tests/test_permissions.py
  class TestPermissionChecker:
      def test_safe_permissions_auto_granted(self):
          """安全权限应该自动授予"""
          pass

      def test_sensitive_permissions_require_grant(self):
          """敏感权限需要明确授予"""
          pass

      def test_revoked_permissions_not_granted(self):
          """撤销的权限不应该被授予"""
          pass
  ```

- [ ] **Task 5.1.3**: 沙箱测试
  ```python
  # tests/test_sandbox.py
  class TestFileSystemSandbox:
      def test_allowed_path_accessible(self):
          """允许的路径应该可以访问"""
          pass

      def test_disallowed_path_blocked(self):
          """不允许的路径应该被阻止"""
          pass

      def test_work_dir_always_allowed(self):
          """工作目录应该始终允许"""
          pass

  class TestNetworkSandbox:
      def test_local_blocked_by_default(self):
          """本地网络默认应该被阻止"""
          pass

      def test_internet_blocked_by_default(self):
          """互联网默认应该被阻止"""
          pass

      def test_allowed_with_permission(self):
          """有权限时应该允许访问"""
          pass
  ```

### 5.2 集成测试

**目标**: 测试完整的安全流程

**任务清单**:

- [ ] **Task 5.2.1**: 安装流程测试
  ```python
  # tests/integration/test_install_flow.py
  class TestSecureInstallFlow:
      def test_complete_install_flow(self):
          """测试完整的安全安装流程"""
          # 1. 下载
          # 2. 哈希验证
          # 3. 签名验证
          # 4. 权限确认
          # 5. 安装
          pass

      def test_tampered_package_rejected(self):
          """篡改的包应该被拒绝"""
          pass

      def test_revoked_skill_blocked(self):
          """被撤销的技能应该被阻止安装"""
          pass
  ```

- [ ] **Task 5.2.2**: 运行时安全测试
  ```python
  # tests/integration/test_runtime_security.py
  class TestRuntimeSecurity:
      def test_sandbox_enforced_during_execution(self):
          """执行期间应该强制执行沙箱"""
          pass

      def test_permission_violation_blocked(self):
          """权限违规应该被阻止"""
          pass
  ```

### 5.3 安全文档

**目标**: 为开发者和用户提供安全指南

**任务清单**:

- [ ] **Task 5.3.1**: 开发者安全指南
  ```markdown
  # docs/SECURITY-GUIDE-DEVELOPERS.md

  ## 技能开发安全最佳实践

  ### 权限最小化原则
  - 只申请必要的权限
  - 避免使用 execute 权限
  - 网络权限说明使用目的

  ### 安全编码规范
  - 输入验证
  - 路径遍历防护
  - 敏感数据处理
  ```

- [ ] **Task 5.3.2**: 用户安全指南
  ```markdown
  # docs/SECURITY-GUIDE-USERS.md

  ## 技能使用安全指南

  ### 权限理解
  - 各权限含义说明
  - 风险等级说明

  ### 安全检查
  - 如何验证技能来源
  - 如何检查技能健康状态
  ```

---

## 开发里程碑

| 里程碑 | 内容 | 目标完成时间 |
|-------|------|-------------|
| **M1** | Phase 1 完成 - 签名验证修复 | Week 2 |
| **M2** | Phase 2 完成 - 权限系统强化 | Week 4 |
| **M3** | Phase 3 完成 - 沙箱隔离 | Week 7 |
| **M4** | Phase 4 完成 - 审核监控 | Week 9 |
| **M5** | Phase 5 完成 - 测试文档 | Week 11 |
| **Release** | 安全版本发布 | Week 12 |

---

## 技术依赖

```toml
# pyproject.toml 新增依赖

[project.dependencies]
cryptography = ">=41.0.0"      # Ed25519 签名验证

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "pytest-asyncio>=0.21.0",
    "pytest-cov>=4.0.0",
]
```

---

## 风险与缓解

| 风险 | 影响 | 缓解措施 |
|-----|------|---------|
| 签名验证绕过被利用 | 严重 | 优先修复，紧急发布补丁 |
| 沙箱逃逸 | 严重 | 多层防护，定期安全审计 |
| 性能影响 | 中等 | 优化沙箱实现，缓存机制 |
| 兼容性问题 | 低 | 充分测试，渐进式发布 |

---

## 附录

### A. 签名数据格式

```json
{
  "name": "skill-name",
  "version": "1.0.0",
  "timestamp": "2024-03-15T10:00:00Z",
  "permissions": ["file:read", "data:read"],
  "hash": "sha256:xxxx"
}
```

### B. 权限完整列表

| 权限 | 风险等级 | 说明 |
|-----|---------|------|
| `file:read` | 低 | 读取文件 |
| `file:write` | 中 | 写入文件 |
| `network:local` | 中 | 本地网络 |
| `network:internet` | 高 | 互联网访问 |
| `data:read` | 低 | 读取客户数据 |
| `data:write` | 高 | 修改客户数据 |
| `config:read` | 低 | 读取配置 |
| `config:write` | 中 | 修改配置 |
| `execute` | 高 | 执行命令 |

---

*文档版本: 1.0.0*
*创建日期: 2024-03-20*
*作者: SocialHub.AI Security Team*
