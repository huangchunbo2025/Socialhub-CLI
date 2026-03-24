# Skills Store Render 部署说明

## 1. 目标

本文档说明如何把 [skills-store](C:\Users\86185\Socialhub-CLI\skills-store) 部署到 Render，并与 Render Postgres 连接。

当前目标是先部署后端 API：

- FastAPI Web Service
- Render Postgres

静态原型仍继续使用 GitHub Pages。

## 2. 已准备好的文件

仓库中已经补好 Render 相关文件：

- [render.yaml](C:\Users\86185\Socialhub-CLI\skills-store\render.yaml)
- [start.sh](C:\Users\86185\Socialhub-CLI\skills-store\start.sh)

启动逻辑是：

1. `alembic upgrade head`
2. `uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT`

## 3. Render 上要创建的资源

需要两项：

1. `Web Service`
2. `PostgreSQL`

推荐命名：

- Web Service: `skills-store-backend`
- Postgres: `skills-store-postgres`

## 4. 使用 Blueprint 部署

如果你打算直接让 Render 读取仓库里的 blueprint：

1. 打开 Render Dashboard
2. 点击 `New +`
3. 选择 `Blueprint`
4. 选择 GitHub 上这个仓库
5. Render 会识别 [render.yaml](C:\Users\86185\Socialhub-CLI\skills-store\render.yaml)
6. 确认资源配置后部署

## 5. 手动部署方式

如果你想手动点 Web Service：

### 5.1 创建 Postgres

1. `New +` -> `PostgreSQL`
2. 名称填 `skills-store-postgres`
3. 数据库名填 `skills_store`
4. 用户名填 `skills_store`
5. 先用 Free 或 Starter

### 5.2 创建 Web Service

1. `New +` -> `Web Service`
2. 选择当前 GitHub 仓库
3. `Root Directory` 设为 `skills-store`
4. Runtime 选 `Python 3`
5. Build Command:

```bash
pip install -e .
```

6. Start Command:

```bash
bash ./start.sh
```

7. Health Check Path:

```text
/health
```

## 6. 环境变量

至少配置这些变量：

### 必填

- `DATABASE_URL`
- `JWT_SECRET`

### 建议显式配置

- `APP_ENV=production`
- `JWT_EXPIRE_HOURS=24`
- `PACKAGE_STORAGE_MODE=local`
- `PACKAGE_STORAGE_ROOT=./data/packages`
- `ED25519_PRIVATE_KEY_PATH=./secrets/ed25519-private.pem`
- `ED25519_PUBLIC_KEY_ID=ed25519-main`

说明：

- `DATABASE_URL` 直接使用 Render Postgres 提供的连接串
- `ALEMBIC_DATABASE_URL` 可以不单独配，代码会从 `DATABASE_URL` 自动推导
- `JWT_SECRET` 建议用 Render 自动生成随机值

## 7. 部署后检查

部署成功后，至少检查这几个地址：

1. `/health`
2. `/openapi.json`
3. `/api/v1/categories`

预期：

- `/health` 返回 `{"status":"ok"}`
- `/openapi.json` 返回 `200`
- `/api/v1/categories` 返回分类列表

## 8. 当前已知限制

当前后端已经具备这些能力：

- 注册 / 登录 / 当前用户 / 修改资料
- 技能列表 / 技能详情 / 版本列表 / 精选 / 分类
- 开发者创建技能
- 开发者上传技能版本
- 基础 zip 校验与基础扫描
- 管理员审核
- 审核通过后签发证书
- 下载、下载元信息
- 吊销证书
- CRL 返回

当前还没有完整验证的部分：

- Render 上真实数据库迁移是否一次通过
- 全链路联调是否完全无兼容偏差
- pytest 自动化测试

## 9. 推荐部署顺序

1. 先推送当前代码到 GitHub
2. 在 Render 上建 Postgres
3. 在 Render 上建 Web Service
4. 打开 `/health`
5. 打开 `/openapi.json`
6. 再开始做注册、建技能、上传、审核的手工联调

## 10. 建议

开发和演示阶段可以直接用 Render。

如果后面要稳定长期使用，建议：

- Web Service 不要长期停留在 Free
- Postgres 不要长期停留在 Free
- 私钥不要依赖自动生成，而是显式上传受控密钥
