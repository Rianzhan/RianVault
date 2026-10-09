# RianVault 架构说明（开发版）

完整设计与审计见根目录 `RIANVAULT_DESIGN_AUDIT.md`。本文记录落地时的实际决策。

## 当前状态（M1 完成）

- FastAPI + SQLAlchemy 2 + Alembic；SQLite 开发零依赖，PostgreSQL 为生产目标。
- JSON 列使用 `JSON().with_variant(postgresql.JSONB)`：测试跑 SQLite，生产用 JSONB。
- 已实现：imports / conversations / messages / import_quarantine；
  ChatGPT export 与 rianvault-jsonl-v1 两个 adapter；幂等三层去重；
  对账不变式；隔离区；消息读取 API（含 around 窗口）。

## 开发环境

```bash
cd backend
alembic upgrade head                       # 建库（默认 sqlite 文件）
uvicorn app.main:app --reload              # 启动 API
python -m pytest                           # 测试（44 项）
```

- 有 Docker 时：`docker compose -f deploy/compose.dev.yml up -d`
  并把 `DATABASE_URL` 指向 `postgresql+psycopg://rianvault:<pwd>@127.0.0.1:5432/rianvault`
  （需 `pip install -e "backend[pg]"`）。
- 前端：`cd frontend && npm install && npm run dev`（vite 代理 /api → 8000）。

## 目录职责

- `app/models/` 表结构（messages 正文不可变）
- `app/services/importers/` adapter 架构；新增来源 = 新文件 + 注册一行
- `app/api/routes/` 薄路由层，业务都在 services
- `deploy/` dev/prod compose；`tests/test_compose_security.py` 强制 prod 数据库无公网端口

## 已记录的环境注意

- 本机无 Docker：compose 只能静态断言，运行验证在有 Docker 的机器上做。
- Git Bash PATH 需手动修复（见 .workbuddy/memory/2026-10-09.md）。
- 本机有 HTTP 代理：访问本机服务 curl 需要 `--noproxy '*'`。
