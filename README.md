# RianVault（湛Owner私人记忆库）

长期保存、检索、追溯、迁移私人聊天与衍生记忆的私人档案馆。

- **数据主权**：原文、embedding 全在本机/自有 VPS；禁止任何第三方 embedding / AI API。
- **真源**：PostgreSQL 是唯一权威；Qdrant 只是可重建的语义索引。
- **可追溯**：每条 Memory 有多来源、跨会话的 evidence/context span，全量快照版本史，append-only 审计。

设计与审计文档：[RIANVAULT_DESIGN_AUDIT.md](./RIANVAULT_DESIGN_AUDIT.md)

## 仓库布局

```
backend/    FastAPI + SQLAlchemy 2 + Alembic（唯一写入路径 service 层）
frontend/   React + Vite + TypeScript（私人档案馆风格 UI）
deploy/     docker compose（dev 绑 127.0.0.1；prod 数据库无公网端口）
docs/       架构、导入格式规范、运维手册
scripts/    重建索引、从导出恢复等运维脚本
```

## 快速开始（开发）

```bash
# 后端（Python >= 3.12）
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e "backend[dev]"
cd backend && alembic upgrade head && uvicorn app.main:app --reload

# 数据库（有 Docker 时；无 Docker 默认 sqlite 文件，开箱即用）
docker compose -f deploy/compose.dev.yml up -d

# 测试
cd backend && python -m pytest -q
```

## 红线

- `.env`、真实聊天导出、数据库文件、`exports/` 永不进 Git（见 .gitignore）。
- 日志不记正文、查询全文、token。
- PostgreSQL / Qdrant 在生产环境无公网端口（`tests/test_compose_security.py` 强制）。

## 里程碑

- M1 地基：导入 ChatGPT export / JSONL v1 → 找回原文 ✅（当前）
- M2 记忆核心：memory + 版本史 + spans + 权限 + 遗失记忆打捞（进行中）
- M3 检索与出口：本地 bge-m3 embedding + Qdrant + Portable Export
- M4 可用：前端页面、加固、文档
