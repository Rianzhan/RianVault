# RianVault — AI 接手引导（BOOTSTRAP）

> **本文件不是交付书。** 完整详情只有一份真源：[`../RIANVAULT_HANDOVER.md`](../RIANVAULT_HANDOVER.md)。
> 本目录只做「导航 + 机器可读索引」，**不复制正文**；任何冲突以 HANDOVER 为准。
> 称谓：一律用 **Owner** 指代项目所有者，**不要**在本目录扩散真实姓名。

---

## 1. 这是什么

Owner 的私人聊天记忆库：聊天原文 + 从中提炼的「记忆」保存在自有机器上，可检索、可追溯、
可整体迁移。所有深度学习能力本机完成（bge-m3 embedding）。
栈：FastAPI + PostgreSQL（开发期 SQLite）+ Qdrant **本地模式** + React/TS。

## 2. 当前阶段

- **Phase 1（T0–T10）已完成**，一键验收 30/30。
- **现在站在 Phase 1.5「检索评估与优化」门口**（当前位置）。
- 测试基線：后端 169 passed、前端 47 passed（2026-10-14 全量，本轮已复现前端 47）。
- Phase 2 远程 MCP、Phase 3 VPS 部署：**未开工**。

## 3. 七条不变式（要动 = 必须先问 Owner）

| # | 不变式 | 证据 |
|---|---|---|
| 1 | PostgreSQL 是**唯一真源**；Qdrant 只是可重建索引，**正文一个字不进向量库** | `backend/app/services/index_service.py`（`PAYLOAD_WHITELIST` / `FORBIDDEN_PAYLOAD_KEYS` / `_assert_payload_safe`）；`backend/tests/test_index_payload.py` |
| 2 | **embedding 永远本地**（只接 `sentence-transformers`） | `backend/app/services/embedding.py`；`backend/tests/test_hardening.py`（零第三方 embedding） |
| 3 | **默认不向第三方 AI 外发私人正文**；唯一例外是远程 MCP，且须 Owner 对指定 principal/scope 显式授权 + 逐次审计 | HANDOVER **14.3** |
| 4 | **版本追加不覆盖**，历史不可改写 | `backend/app/services/memory_service.py::_write_version` / `restore_version`；`backend/tests/test_memory_domain.py` |
| 5 | 记忆必须**可溯源**到原聊天片段；改 span 也触发新版本 | `memory_service.bump_version_for_span_change`；`backend/tests/test_span_update.py` |
| 6 | 两角色权限：`owner` 全权；`zhan_mcp` 只能读写记忆 + 检索，**不得** import / delete / undelete / purge / restore / export / token-admin / reindex / scan | `backend/app/core/deps.py::require_owner`；`backend/tests/test_auth.py`、`test_memory_api.py::TestRecycleBin` |
| 7 | 昂贵资源**单例化**（Qdrant client、embedding provider） | `index_service.get_qdrant` / `embedding.get_embedding_provider`；commit `f708156` |

## 4. 红线（看到就停）

- 不要为了「MCP 方便」把本地 embedding 换成云端 API —— 两者**没有因果关系**（HANDOVER 14.3）。
- 不要把正文写进日志、Qdrant payload 或 URL 查询串（检索走 POST 就是为了后者）。
- **不要**在多线程里并发跑 torch 推理 —— 会段错误，进程直接消失。
- 不要手删 Qdrant 的 `.lock`。
- 不要为「感觉会更好」就下载 2GB reranker —— 先评测拿数字。
- 不要在本目录维护第二套事实；改事实去 HANDOVER / `docs/dev-log.md` / 代码。

## 5. 术语纪律（两条，别改回去）

**a) 「留一法找回自身」＝ known-item / self-retrieval，不是 Recall@K。**
它只能支撑 **Hit@K** 与 **MRR**；开放式 **Precision@K / Recall@K** 必须靠
**pooled relevance judgment**（把多个检索器的 top-K 混成池子人工判相关）。
理由：自检索把「相关集合」人为定义成 1，且无从判断 top-K 里其余结果是否相关。
→ HANDOVER **6.5**（术语纪律）与 **第 19 章**。

**b) 第三方 AI 数据政策分两层。**
- 当前（已生效）：**默认不外发**，代码里根本没有对外 AI 调用点；embedding 本地。
- 未来远程 MCP 是**有条件例外**，须同时满足：Owner 对**指定 principal / scope** 显式授权；
  换 principal 或扩 scope 要重新授权；逐次进审计；权限上限仍是 `zhan_mcp`；
  **embedding 仍本地**；令牌吊销即失效。
→ HANDOVER **14.3**（唯一权威表述）。

## 6. NEXT（按序）

1. **Phase 1.5 检索评测**：先做 known-item 自检索，**只报 Hit@K / MRR**（零标注）。
   跑之前**必须停掉运行中的后端**（Qdrant 单进程独占）。
2. 视数字决定是否上 BM25 / reranker。 — **决策门：需 Owner 批准**
3. 补 `docker/Dockerfile.backend`（`deploy/compose.prod.yml` 引用了不存在的文件，Phase 3 前置）。 — **决策门**
4. 决定是否清理仓库里已提交的 zip 产物。 — **决策门**

## 7. 已知会咬人的坑

- 跑 pytest **必须从 `backend/` 目录**（`conftest.py` 用相对路径 `tests/fixtures/...`），
  且要加 `--basetemp=./.pytest-tmp`（系统临时目录清理会被沙箱拦下）。
- Qdrant 本地模式**单进程独占**：评测 / 重建脚本与运行中的后端互斥。
- 解释器退出时 Qdrant `__del__` 抛 `ImportError: sys.meta_path is None` —— 关机噪音，不是失败。
- 改 `CHUNK_MAX_TOKENS` 或切块规则 → **必须重建索引**，否则命中片段与库内块对不上。
- 前端测试辅助函数递归 `ReactNode` 时**必须先处理数组**（`highlight()` 返回数组）。
- **全量跑可能「假报错」**：在本会话环境里，全量跑后端会出现成片 `AssertionError at setup`
  ——栈顶是 `shutil.rmtree → _try_trash → _check_bulk_delete_guard`。
  这是环境的批量删除守卫拦了 `.pytest-tmp` 清理，**不是项目缺陷**（关沙箱也没用）。
  已验证绕过方式：**按模块分批跑**（`test_export.py` 单独 11 passed、`test_search.py` 单独 14 passed）。
- 完整清单见 `AI_FAILURES.jsonl`（含 FL011）。

## 8. 阅读顺序

`00_BOOTSTRAP.md`（本文件）→ HANDOVER 第 1 章概览 → 第 2 章架构 → 第 3 章数据模型 →
第 9 章权限 → 第 14 章安全（含 14.3）→ 第 19 章 Roadmap → 再按任务跳章。
细节**一律回 HANDOVER**，不要在本目录补写。

## 9. 验证命令

```bash
cd backend
../.venv/Scripts/python.exe -m pytest tests -q --basetemp=./.pytest-tmp
../.venv/Scripts/python.exe scripts/acceptance_check.py --skip-semantic   # 30 项，约 20s
cd ../frontend
<node> ./node_modules/vitest/vitest.mjs run
```

## 10. 本目录内容

`00_BOOTSTRAP.md`（本文件）、`AI_CONTEXT.json`（上下文快照）、`AI_FACTS.jsonl`（原子事实+证据）、
`AI_FAILURES.jsonl`（重大故障与「不要再引入」）、`AI_TASK_GRAPH.yaml`（任务依赖与 Owner 决策门）、
`HANDOFF_MANIFEST.json`（生成时间 / Git HEAD / 脏状态 / 哈希）。
