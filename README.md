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

## 红线

- `.env`、真实聊天导出、数据库文件、`exports/` 永不进 Git（见 .gitignore）。
- 日志不记正文、查询全文、token。
- PostgreSQL / Qdrant 在生产环境无公网端口（`tests/test_compose_security.py` 强制）。

## 里程碑

- M1 地基：导入 ChatGPT export / JSONL v1 → 找回原文 ✅
- M2 记忆核心：memory + 版本史 + spans + 权限 + 遗失记忆打捞 ✅
- M3 检索与出口：本地 bge-m3 embedding + Qdrant + Portable Export（进行中）
- M4 可用：前端页面、加固、文档
