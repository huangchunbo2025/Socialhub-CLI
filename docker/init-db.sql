-- PostgreSQL 初始化脚本：创建两个独立数据库
-- 由 postgres 容器启动时自动执行（docker-entrypoint-initdb.d/）
-- 对应 render.yaml 中的两个服务共享同一 PG 实例

-- MCP Server 运营数据库（API Key、凭证、门户 Session）
CREATE DATABASE socialhub_mcp;

-- Skills Store 数据库（用户、开发者、技能目录）
CREATE DATABASE skills_store;
