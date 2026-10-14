# RianVault（湛Owner私人记忆库）

长期保存、检索、追溯、迁移私人聊天与衍生记忆的私人档案馆。

- **数据主权**：原文、embedding 全在本机/自有 VPS；禁止任何第三方 embedding / AI API。
- **真源**：PostgreSQL 是唯一权威；Qdrant 只是可重建的语义索引。
- **可追溯**：每条 Memory 有多来源、跨会话的 evidence/context span，全量快照版本史，append-only 审计。

设计与审计文档：[RIANVAULT_DESIGN_AUDIT.md](./RIANVAULT_DESIGN_AUDIT.md)

**完整工程交付书（新接手者 / 想从零理解本项目的人，先看这份）：
[docs/RIANVAULT_HANDOVER.md](./docs/RIANVAULT_HANDOVER.md)**
—— 面向完全没有项目背景的读者，含 24 章：起源与需求演变、架构全景、数据模型全解、
端到端流程、检索实现现状、隐私设计、权限模型、逐页与逐 API 说明、导出恢复、
安全边界、验收脚本逐项解释、状态矩阵、已知限制、Roadmap 与接手指南。
首次出现的术语都给「英文全称 + 中文 + 在本项目负责什么」。

## 仓库布局

```
backend/    FastAPI + SQLAlchemy 2 + Alembic（唯一写入路径 service 层）
frontend/   React + Vite + TypeScript（私人档案馆风格 UI）
deploy/     docker compose（dev 绑 127.0.0.1；prod 数据库无公网端口）
docs/       架构、导入格式规范、运维手册
scripts/    重建索引、从导出恢复等运维脚本
```

## 验收（一条命令）

```bash
cd C:/Users/Owner/Projects/RianVault
python scripts/acceptance_check.py                 # 全量，约 1 分钟（含真机语义检索）
python scripts/acceptance_check.py --skip-semantic # 不加载 2GB 权重，约 20 秒
```

它会自建一个全新的库（带时间戳，不动你现有数据）、起服务、造 token，
然后逐项跑 G.0 完成标准（导入幂等 / 选段建记忆 / 版本史 / 检索 / 遗失记忆审计 /
导出恢复对账 / 权限矩阵 / 安全头），最后打印 `通过 30 / 30`。
任何一项 FAIL 都会把原因打印出来，把输出原样发给我就行。

日常启动与手工验收步骤见 [docs/ops-runbook.md](./docs/ops-runbook.md)。

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

## 本地 embedding 与语义索引（T6）

embedding **只在本机推理**（默认 `BAAI/bge-m3`），不经过任何第三方 API。

```bash
# 依赖较重，单独安装（CPU 版 torch，约 130MB）
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install sentence-transformers

# 权重下载一次后即可离线使用；国内建议用镜像，并把缓存放在项目内
HF_ENDPOINT=https://hf-mirror.com HF_HOME=./.hf-cache python -c "
from sentence_transformers import SentenceTransformer
SentenceTransformer('BAAI/bge-m3')"
```

Qdrant 有两种模式（`QDRANT_MODE`）：

- `local`（默认）：进程内/本地文件存储，没装 Docker 也能跑索引与检索。
- `server`：compose 起的容器，`QDRANT_URL` 指向它。

```bash
python ../scripts/rebuild_qdrant.py --check            # 看当前索引状态
python ../scripts/rebuild_qdrant.py                    # 增量补索引
python ../scripts/rebuild_qdrant.py --rebuild          # 换模型后必须全量重建
```

语义索引是**可丢弃**的：`chunk_index` 表记录每个 chunk 的所属消息与模型，
正文永远只在 PostgreSQL；Qdrant payload 只允许 `chunk_id / conversation_id /
source_platform / source_model / event_time` 五个中性字段，
任何"正文类"字段都会在写入前被 `build_payload` 拦下（有测试守着）。

## 一键导出与恢复（T7）

```bash
# 导出（仅 Owner；POST /api/export → GET /api/export/{id}/download）
curl -X POST -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/export
curl -OJ -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8000/api/export/<export_id>/download

# 恢复到全新库（先校验 manifest 与 checksums，不符就中止）
python scripts/restore_from_export.py exports/<export_id>.zip \
  --database-url sqlite:///./restored.db
```

包内 `data/*.jsonl` 是权威数据（按主键原样写回，可重复恢复），
`markdown/` 是不装程序也能读的全文；**向量不导出**（用 rebuild_qdrant.py 重算）。
`scripts/e2e_t7_check.py` 会跑完整的导出→下载→CLI 恢复→计数对账。

## 红线

- `.env`、真实聊天导出、数据库文件、`exports/` 永不进 Git（见 .gitignore）。
- 日志不记正文、查询全文、token。
- PostgreSQL / Qdrant 在生产环境无公网端口（`tests/test_compose_security.py` 强制）。
- **只增不删**：临时产物一律用带时间戳的新名字，不清空/覆盖已存在的文件（详见 `docs/dev-log.md`）。

## 开发日志

进度、决策与踩过的坑都在 `docs/dev-log.md`（仓库内，不写到仓库外的任何地方）。

## 文档

- [docs/RIANVAULT_HANDOVER.md](./docs/RIANVAULT_HANDOVER.md)：**完整工程交付书**（从零理解本项目，推荐入口）
- [RIANVAULT_DESIGN_AUDIT.md](./RIANVAULT_DESIGN_AUDIT.md)：设计与审计（A–H 节 + 附录，含验收标准 G.0）
- [docs/architecture.md](./docs/architecture.md)：落地后的实际结构与不变式
- [docs/import-format-v1.md](./docs/import-format-v1.md)：JSONL v1 导入格式
- [docs/ops-runbook.md](./docs/ops-runbook.md)：启动、备份恢复、重建索引、故障排查
- [docs/dev-log.md](./docs/dev-log.md)：开发日志（进度、决策、踩过的坑）

## 加固（T10）

- 日志脱敏过滤器：token / Bearer / 连接串密码 / 正文字段一律抹掉（兜底网，真正保证是"不写"）。
- 统一异常处理：未处理异常 → 500 + `error_id`，**不回吐异常细节**（可能夹带 SQL 参数＝正文），
  响应体绝不含"成功"字样；默认不打完整堆栈（`DEBUG=true` 才打）。
- 安全响应头：`nosniff` / `X-Frame-Options: DENY` / `no-referrer`；`/api` 一律 `Cache-Control: no-store`。
- 限流：写操作与检索按客户端 IP 滑动窗口限流（`RATE_LIMIT_PER_MINUTE`，默认 120/分钟）。
- 测试：`tests/test_hardening.py`（日志不泄漏、5xx 不装成功、安全头、真实 429、零第三方 embedding）。

## 里程碑

- M1 地基：导入 ChatGPT export / JSONL v1 → 找回原文 ✅
- M2 记忆核心：memory + 版本史 + spans + 权限 + 遗失记忆打捞 ✅
- M3 检索与出口：本地 bge-m3 embedding + Qdrant + Portable Export ✅
- M4 可用：前端页面、加固、文档 ✅
