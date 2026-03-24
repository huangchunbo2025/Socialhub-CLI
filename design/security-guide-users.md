# SocialHub.AI Skills 用户安全指南

本文档帮助用户安全地使用 SocialHub.AI CLI 技能系统。

## 1. 安全概述

SocialHub.AI Skills 采用多层安全保护：

```
┌─────────────────────────────────────────────────────┐
│                  安全保护层次                        │
├─────────────────────────────────────────────────────┤
│  1. 官方认证     只能安装官方商店的技能               │
│  2. 签名验证     Ed25519 数字签名防篡改              │
│  3. 权限控制     敏感操作需要用户授权                 │
│  4. 沙箱隔离     限制文件/网络/命令访问               │
│  5. 撤销机制     可紧急撤销恶意技能                   │
└─────────────────────────────────────────────────────┘
```

## 2. 权限说明

### 2.1 权限类型

当安装技能时，您可能会看到以下权限请求：

| 权限 | 风险 | 说明 |
|------|------|------|
| `file:read` | 🟢 低 | 允许读取文件 |
| `file:write` | 🟡 中 | 允许写入文件 |
| `data:read` | 🟢 低 | 允许读取客户数据 |
| `data:write` | 🔴 高 | 允许修改客户数据 |
| `network:local` | 🟡 中 | 允许访问本地网络 |
| `network:internet` | 🔴 高 | 允许访问互联网 |
| `config:read` | 🟢 低 | 允许读取 CLI 配置 |
| `config:write` | 🟡 中 | 允许修改 CLI 配置 |
| `execute` | 🔴 高 | 允许执行系统命令 |

### 2.2 权限请求示例

```
┌─────────────────────────────────────────────────────┐
│  Permission Request: data-export-plus v1.0.0        │
├─────────────────────────────────────────────────────┤
│  Risk    Permission          Description            │
│  ● LOW   file:read           Read files from disk   │
│  ◆ HIGH  network:internet    Access the internet    │
└─────────────────────────────────────────────────────┘

◆ Allow network:internet (Access the internet)? [y/N]:
```

### 2.3 权限决策指南

**何时授予权限：**
- 您信任技能的来源和开发者
- 权限与技能功能相符（导出技能需要 file:write）
- 您了解授予该权限的影响

**何时拒绝权限：**
- 权限与技能功能不符（文本分析技能不应需要 network:internet）
- 您不确定为什么需要该权限
- 技能要求的权限过多

## 3. 安装技能

### 3.1 浏览官方商店

```bash
# 浏览所有可用技能
socialhub skills browse

# 按分类浏览
socialhub skills browse --category=data

# 搜索技能
socialhub skills search "export"
```

### 3.2 查看技能详情

在安装前，查看技能详情：

```bash
socialhub skills info data-export-plus
```

检查以下信息：
- 作者和许可证
- 所需权限
- 用户评分
- 更新历史

### 3.3 安装技能

```bash
# 安装最新版本
socialhub skills install data-export-plus

# 安装指定版本
socialhub skills install data-export-plus@1.2.0
```

安装过程中会：
1. 下载技能包
2. 验证数字签名
3. 检查撤销状态
4. 请求权限授权

## 4. 管理已安装技能

### 4.1 查看已安装技能

```bash
socialhub skills list
```

### 4.2 检查技能健康状态

```bash
# 检查所有技能
socialhub skills health

# 检查特定技能
socialhub skills health data-export-plus

# 详细输出
socialhub skills health --verbose
```

健康检查包括：
- 证书是否过期
- 是否被撤销
- 文件完整性
- 更新可用性

### 4.3 更新技能

```bash
# 更新特定技能
socialhub skills update data-export-plus

# 更新所有技能
socialhub skills update --all
```

### 4.4 禁用/启用技能

如果您暂时不想使用某个技能但不想卸载：

```bash
# 禁用技能
socialhub skills disable data-export-plus

# 启用技能
socialhub skills enable data-export-plus
```

### 4.5 卸载技能

```bash
socialhub skills uninstall data-export-plus
```

卸载会：
- 删除技能文件
- 撤销所有权限
- 清除相关缓存

## 5. 安全最佳实践

### 5.1 定期检查

```bash
# 每周运行健康检查
socialhub skills health

# 检查并更新所有技能
socialhub skills update --all
```

### 5.2 最小权限原则

- 只安装您需要的技能
- 只授予必要的权限
- 定期审查已授权的权限

### 5.3 注意异常行为

如果技能出现以下行为，请警惕：
- 请求与功能不符的权限
- 运行时尝试访问未授权的资源
- 消耗异常的系统资源
- 产生大量网络流量

### 5.4 报告可疑技能

如果发现可疑技能，请报告：

```bash
# 技能详情页有报告链接
socialhub skills info suspicious-skill
```

或联系：security@socialhub.ai

## 6. 故障排除

### 6.1 安装失败

**签名验证失败**
```
Error: Security verification failed: Invalid signature
```

原因：技能包可能被篡改或损坏
解决：
1. 清除缓存后重试：`socialhub skills cache --clear`
2. 确保网络连接正常
3. 如问题持续，联系技能开发者

**技能被撤销**
```
Error: Skill 'xxx' has been revoked for security reasons
```

原因：技能因安全问题被官方撤销
解决：
1. 卸载该技能
2. 寻找替代技能
3. 等待开发者发布修复版本

### 6.2 权限问题

**缺少权限**
```
Error: Skill 'xxx' requires permissions that have not been granted
```

解决：重新安装技能并授予所需权限
```bash
socialhub skills uninstall xxx
socialhub skills install xxx
```

### 6.3 健康检查问题

**证书即将过期**
```
Warning: Certificate expires in 15 days
```

解决：更新技能
```bash
socialhub skills update skill-name
```

**文件完整性问题**
```
Error: Manifest file missing
```

解决：重新安装技能
```bash
socialhub skills uninstall skill-name
socialhub skills install skill-name
```

## 7. 权限存储位置

权限配置存储在：
```
~/.socialhub/security/permissions.json
```

您可以查看已授予的权限：
```json
{
  "skills": {
    "data-export-plus": {
      "permissions": ["file:read", "file:write"],
      "granted_at": "2024-03-20T10:30:00",
      "version": "1.0.0"
    }
  }
}
```

## 8. 沙箱保护

技能在沙箱环境中运行，限制如下：

### 8.1 文件系统限制

技能只能访问：
- `~/.socialhub/skills/sandbox/{skill-name}/` - 技能沙箱目录
- `~/.socialhub/skills/installed/{skill-name}/` - 安装目录（只读）
- `~/Documents`、`~/Downloads` - 默认允许目录
- 用户明确授权的其他目录

### 8.2 网络限制

- 无 `network:local` 权限：无法访问本地网络
- 无 `network:internet` 权限：无法访问互联网
- 只能连接白名单中的主机

### 8.3 命令执行限制

- 无 `execute` 权限：无法执行任何命令
- 有权限时，以下命令始终被阻止：
  - `rm`、`sudo`、`shutdown`、`format` 等危险命令

## 9. 常见问题

**Q: 技能可以访问我的所有文件吗？**
A: 不能。技能只能访问授权的目录，且受沙箱限制。

**Q: 技能可以在后台运行吗？**
A: 不能。技能只在您执行命令时运行。

**Q: 如何确保技能是安全的？**
A: 所有技能必须通过官方审核和签名验证。

**Q: 我可以撤销已授予的权限吗？**
A: 可以，卸载技能会撤销所有权限，或删除权限配置文件。

**Q: 技能会收集我的数据吗？**
A: 官方审核会检查数据收集行为。有 `network:internet` 权限的技能理论上可以传输数据，请谨慎授权。

## 10. 联系方式

- 安全问题: security@socialhub.ai
- 技术支持: support@socialhub.ai
- 文档反馈: docs@socialhub.ai

---

*文档版本: 1.0.0*
*最后更新: 2024-03-20*
