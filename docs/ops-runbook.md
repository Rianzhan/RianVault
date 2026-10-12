# 运维手册（RianVault）

面向"我自己这台机器 / 自有 VPS"。所有操作都在本机或可信网络内完成，
**不使用任何第三方 AI / embedding 服务**。

## 1. 日常启动

```bash
cd backend
export DATABASE_URL="sqlite:///./rianvault-dev.db"        # 或 PostgreSQL
export QDRANT_MODE=local QDRANT_PATH=./data/qdrant        # 无 docker 时用本地模式
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

前端（另一个终端）：

```bash
cd frontend && npm run dev      # http://localhost:5173，/api 代理到 8000
```

启动日志里会打印 `database=`（凭据脱敏）与 `embedding_model=`——**先看这两行**，
确认连的是你想连的库，再继续操作。

## 2. 令牌

```bash
python ../scripts/create_token.py --role owner  --name laptop     # 明文只显示一次
python ../scripts/create_token.py --role zhan_mcp --name mcp
python ../scripts/create_token.py --list
python ../scripts/create_token.py --revoke <id>
```

- `owner`：全通（导入、删除、恢复、令牌管理、导出）。
- `zhan_mcp`：可读写记忆、检索、加 span；**不能**导入/删除/恢复/管令牌/导出。
- 前端把令牌存在浏览器 sessionStorage（设置页），请求头 `Authorization: Bearer ...`。

## 3. 备份与恢复

```bash
# 导出（Owner）
curl -X POST -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/export
curl -OJ -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8000/api/export/rianvault-export-YYYYMMDD-HHMMSS.zip/download

# 恢复到全新库（会先验 manifest 与 checksums，不符就中止）
python scripts/restore_from_export.py exports/<zip> --database-url sqlite:///./restored.db
```

- 包内 `data/*.jsonl` 可按主键原样写回，重复恢复不会产生重复行。
- `markdown/` 不装程序也能读完所有重要文本。
- **向量不导出**：恢复后跑一次重建即可。

建议节奏：每周一次 Portable Export，另外定期对 PostgreSQL 做 `pg_dump` 与 Qdrant snapshot
（Portable Export 是"能读能恢复"的保底，不等于数据库级备份）。

## 4. 语义索引

```bash
python ../scripts/rebuild_qdrant.py --check     # 看状态（集合/模型/已索引消息数）
python ../scripts/rebuild_qdrant.py             # 增量补索引
python ../scripts/rebuild_qdrant.py --rebuild   # 换模型后必须全量重建
```

- `chunk_index` 表记录每个 chunk 属于哪条消息、用的哪个模型；**换模型会被识别为 stale**。
- 索引坏了/想省空间：直接删掉 Qdrant 集合后 `--rebuild`，PG 里的原文毫发无损。

## 5. 换机器 / 换模型

1. 新机器装依赖 + `alembic upgrade head`。
2. 拷入最新导出包，`restore_from_export.py` 恢复到新库。
3. `rebuild_qdrant.py`（首次会下载 bge-m3 权重；之后离线可用，
   `HF_HOME` 放项目内 `.hf-cache/` 更稳）。
4. 用 `scripts/e2e_*_check.py` 做一次端到端自检。

## 6. 常见故障

| 现象 | 原因与处理 |
| --- | --- |
| 迁移跑到了别的库 | `alembic` 与运行时共用 `get_settings()`；启动日志确认 `database=`。没有 `RV_` 前缀。 |
| 语义检索 503 | 本地 embedding 依赖/权重没装好。看 `README` 的安装步骤与 `HF_HOME`。 |
| 语义检索很慢/卡住 | 首次使用要加载 2GB 权重（CPU 上约 1 分钟）。可先用 `keyword` 模式。 |
| 429 | 写操作/检索超 `RATE_LIMIT_PER_MINUTE`（默认 120/分钟）。 |
| 500 + error_id | 服务端日志里搜 error_id；响应体不会回吐细节（防正文泄漏）。 |
| 导出包校验失败 | 包被改动或损坏：恢复会中止，换一份备份。 |

## 7. 自检脚本

```bash
python scripts/e2e_t3_check.py   # 导入/记忆/版本/权限
python scripts/e2e_t5_check.py   # 遗失记忆审计（需全新库）
python scripts/e2e_t6_check.py   # 真机 embedding + Qdrant 检索
python scripts/e2e_t7_check.py   # 导出 → CLI 恢复 → 计数对账
```

每个脚本都需要先起服务 + 生成 token，且（`e2e_t5/t6`）要求**全新库**
（候选表与索引按唯一键幂等，脏库重跑会被误判成失败）。
