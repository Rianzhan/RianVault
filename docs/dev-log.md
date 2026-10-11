# Dev Log（RianVault 开发日志）

日志写在仓库内：仓库之外（WorkBuddy / Agent 目录、全局记忆等）一律不写、不改。

## 工程约定（Owner定，必须遵守）

1. **只增不删**。需要"干净环境"时用带时间戳的新名字（如 `e2e-t7-104457.db`、`exports-e2e-t7/`），
   旧文件留着不动。要清空或覆盖任何已存在的文件，必须先列出路径 + 理由，等Owner点头。
2. **代码里只允许删自己在系统临时目录里创建的东西**，并写清注释。
3. 不用 mock 成功冒充完成；测试失败就报失败，不许跳过、不许吞异常。
4. 私人数据主权：正文/embedding 不出本机；日志不记正文、查询全文、token。
5. 单一写入路径：所有写操作（UI / MCP / 导入）都走同一套 service 层（权限 → 校验 → 版本快照 → 审计）。

---

## 2026-10-09 — Phase 0：审计（未写任何代码）

- Owner交付长期项目 RianVault（湛Owner私人记忆库）：先完整审计再设计，等「批准开工」才动代码。
- 审计结论（实测）：工作区为空 → 绿地项目；产出 `RIANVAULT_DESIGN_AUDIT.md`（A–H 节 + 附录）。
- 关键决策：PG 是唯一权威真源、Qdrant 可重建（payload 白名单无正文）；memory 用全量快照版本史，
  span 增删也触发新版本；messages 导入后正文不可变；zhan_mcp 无 delete/restore/权限管理/export；
  搜索走 POST 防日志泄漏；第一阶段系统不猜模型标签。

## 2026-10-09 — 迁址 + T0–T4

- Owner确认：仓库根 `C:\Users\Owner\Projects\RianVault`；embedding 默认 `BAAI/bge-m3`；
  遗失记忆信号 +18 条；未经要求不得改仓库外的 WorkBuddy/Agent 文件。
- 完成 T0（骨架/compose 安全断言/CI）、T1（0001+0002 迁移）、T2（ChatGPT+JSONL v1 adapter、
  三层幂等 + 对账 + 隔离区）、T3（memory 全量快照版本史 / span / restore=追加 / soft delete / 审计）、
  T4（api_tokens + Bearer + 权限矩阵）。
- commit：`a4cc3a5`、`65618aa`。

## 2026-10-10 — T5 遗失记忆审计

- migration_reviews + 0004 迁移；31 条信号（13 原始 + 18 补充）；只出 candidate，verdict 由 Owner 人工判。
- 从候选建记忆会产生 v1（创建）+ v2（绑 span）——符合"span 增删进版本史"，不是 bug。
- commit：`85de24b`。同批修了两个隐患（见下"坑位"）：gitignore 吞掉 ORM 包、alembic 与运行时 DB URL 两套解析。

## 2026-10-10 — T6 本地 embedding + Qdrant + 检索

- chunking / embedding provider / chunk_index（0005）/ Qdrant 本地模式 / payload 白名单 /
  keyword+semantic+hybrid 检索 / `scripts/rebuild_qdrant.py`。
- 真机验证：bge-m3 CPU 推理 + 本地 Qdrant，e2e 13 项全过（语义命中正确 + 抽查向量库无正文）。
- commit：`7a02c0a`。

## 2026-10-11 — T7 Portable Export 与恢复

- `data/*.jsonl`（8 张表，含 chunks 索引状态）+ `markdown/`（记忆 frontmatter + 来源摘录 + 版本史；会话全文）
  + manifest.json + checksums.sha256；向量不导出。
- `restore_service` 先验 manifest/校验和再写回，按主键幂等，计数对不上直接失败；
  `scripts/restore_from_export.py` 为 CLI 外壳；`/api/export` 仅 Owner、拒绝路径穿越。
- 验证：pytest 132 绿；`scripts/e2e_t7_check.py` 17 项全过（真实 HTTP 导出/下载 + 真实 CLI 恢复 + 对账）。
- commit：`0bdc315`。

---

## 坑位（不要再踩）

### 工程 / 工具链

- `.gitignore` 里未锚定的 `models/` 会把 `backend/app/models/` 整个 ORM 包忽略掉
  （本地测试全绿，clone 后才炸）。已改 `/models/` + `tests/test_repo_hygiene.py` 守门。
- `alembic/env.py` 曾自己解析 `DATABASE_URL`，与运行时 `Settings` 是两套逻辑 → 环境变量名写错就会
  静默迁移到别的库（已实际误清一次开发库）。已改为复用 `get_settings()`，启动时打印 `database=`（脱敏）。
- 环境变量：**没有 `RV_` 前缀**，是 `DATABASE_URL` / `QDRANT_*` / `EMBEDDING_*`（见 `.env.example`）。
- 验证命令走管道必须 `set -o pipefail`，否则失败会被吞掉。
- 后台服务用工具的 `run_in_background`，别用 shell `&`（回合结束会被杀）。
- uvicorn 之外自建 logger 默认没有 handler，INFO 不显示：需显式加 `StreamHandler` + `propagate=False`。
- 本机有死代理：curl 用 `--noproxy '*'`、httpx 用 `trust_env=False`。
- Git Bash 的 PATH 初始损坏，命令前需
  `export PATH="/c/Users/Owner/.workbuddy/binaries/PortableGit/versions/1.2.0/usr/bin:$PATH"`。
- `ruff format` 后记得 `ruff check`：格式化可能把行拉长触发 E501。

### 依赖 / 模型

- 本机无 docker → Qdrant 用 `qdrant-client` 本地模式（`QDRANT_MODE=local`），同代码路径、进程内存储。
- torch 从 `https://download.pytorch.org/whl/cpu` 装（默认源又大又断流），加 `--retries 15 --timeout 300`。
- HF 下载：`huggingface.co` 直连超时；`hf-mirror.com` 可用，但 `HF_HOME` 必须放项目内
  （用户缓存目录里的临时文件清理会被沙箱拦截 → 下载失败）。
- hf-mirror 的 bge-m3 存在两个不一致的 revision：新版 `model.safetensors` 走 CAS（xethub）401 拉不全配置；
  可用旧 revision 快照（`pytorch_model.bin` 完整）以**本地目录**作为 `EMBEDDING_MODEL`。
- sentence-transformers 6.x：`get_sentence_embedding_dimension` 已改名 `get_embedding_dimension`（要兼容新旧）。
- qdrant-client 1.19 移除了 `client.search()`，用 `query_points()`。
- 单元测试里 embedding 用 `tests/embedding_double.py`（字符袋向量）：只验链路，不验语义质量；
  语义质量由真机 e2e 证明。

### 数据模型细节

- `audit_events.target_id` 是 NOT NULL：导出这类没有实体 id 的事件，用 uuid5 推导一个稳定句柄。
- `memory_type` 只允许 `fact / preference / event / relationship / goal / note`。
- e2e 脚本要求"全新库"（候选表/索引按唯一键幂等，脏库重跑会被误判成失败）——但做法是**新建新名字**，
  不是删旧库。
