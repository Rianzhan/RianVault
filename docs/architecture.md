# RianVault 架构说明

完整设计与审计见根目录 `RIANVAULT_DESIGN_AUDIT.md`。本文记录**落地后的实际结构**（T0–T10）。

## 一句话

PostgreSQL 是唯一权威真源；Qdrant 只是可重建的语义索引；embedding 只在本机推理；
所有写入走同一套 service 层（权限 → 校验 → 版本快照 → 审计）。

## 分层

```
frontend/        React + Vite + TS（只读展示 + 通过 /api 写入）
backend/
  app/api/routes/    薄路由：参数解析、权限依赖、调用 service
  app/services/      唯一写入路径（memory_service / span_service / import pipeline /
                     index_service / search_service / export_service / restore_service /
                     migration_audit_service / audit_service）
  app/models/        表结构；messages 正文导入后不可变
  app/core/          config / deps（权限）/ security（token 哈希）/ logging_setup / errors / middleware
scripts/             create_token.py、rebuild_qdrant.py、restore_from_export.py、e2e_*_check.py
```

## 关键不变式（改动前先读）

1. **正文只在 PG**：Qdrant payload 只有 `chunk_id / conversation_id / source_platform /
   source_model / event_time`；写入前有白名单断言（`tests/test_index_payload.py`）。
2. **messages 导入后不可变**：`content_text` / `content_raw` 永不出现在 UPDATE 里。
3. **memory 版本用全量快照**：编辑、span 增删、restore 都产生**新版本**，历史不被改写。
4. **双时间**：`event_time*`（事情发生）与 `created_at / ingested_at`（系统时间）严格分开。
5. **审计 append-only**：写入类事件必留痕；日志只记计数，不记正文/查询词/token。
6. **权限**：`owner` 全通；`zhan_mcp` 可读写记忆与检索，但**不能** import / delete / restore /
   token 管理 / export（`tests/test_auth*.py` 守矩阵）。
7. **单一写入路径**：UI 与未来的 MCP 走同一 service，不允许旁路写库。

## 数据流

```
导入 → conversations/messages（+ 隔离区/对账）
     → chunking → 本地 embedding(bge-m3) → Qdrant（可重建）
浏览 → 选段 → memory(+span) → memory_version 快照 → audit_event
检索 → POST /api/search（keyword=PG / semantic=Qdrant / hybrid）
导出 → zip（data/*.jsonl + markdown/ + manifest + checksums）→ 可 restor
```

## 加固（T10）

- `core/logging_setup.py`：日志脱敏过滤器（token / Bearer / 连接串密码 / 正文字段）作为兜底网。
- `core/errors.py`：统一异常处理 —— 未处理异常返回 500 + `error_id`，响应体**不回吐异常细节**
  （SQLAlchemy 异常可能夹带 SQL 参数＝正文），默认不打印完整堆栈（`DEBUG=true` 才打）。
- `core/middleware.py`：安全响应头（nosniff / DENY / no-referrer）、`/api` 一律
  `Cache-Control: no-store`、写操作与检索按客户端 IP 滑动窗口限流（`RATE_LIMIT_PER_MINUTE`）。
- `tests/test_hardening.py`：日志不泄漏、5xx 不装成功、安全头、限流真实 429、零第三方 embedding。

## 开发环境

```bash
# 后端
cd backend
alembic upgrade head                  # 默认 sqlite 文件；生产用 PostgreSQL
uvicorn app.main:app --reload         # API（默认 8000）
python -m pytest                      # 146 项

# 前端
cd frontend && npm install && npm run dev   # vite 代理 /api → 8000
npm run test                                # vitest 30 项
```

- PostgreSQL：`pip install -e "backend[pg]"`，`DATABASE_URL` 指向 compose 里的库。
- 本机 embedding：`pip install torch --index-url https://download.pytorch.org/whl/cpu`
  + `pip install sentence-transformers`；权重下载一次后可离线。

## 目录职责补充

- `config/migration_signals.yaml`：遗失记忆审计的信号清单（31 条，可增补）。
- `exports/`：导出包（gitignore 排除）。
- `docs/`：`architecture.md`（本文）、`import-format-v1.md`、`ops-runbook.md`、`dev-log.md`。
