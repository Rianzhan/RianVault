# RianVault 完整工程交付书 / Handover Document

> **关于本文档**
>
> 这是 RianVault 的工程说明文档：系统为什么这样设计、目前做到哪一步、如何验证。
> 写给需要理解或接手这个项目的人，也写给未来的自己。
> 设计文档与代码不一致的地方，单列在第 25 章。

> 这份文档假设读者**从零开始**：没参与过任何讨论、没看过聊天记录、不懂后端、数据库、
> 向量检索、RAG。所有专业术语第一次出现时都给出「英文全称 + 中文 + 在 RianVault 里具体
> 负责什么」。
>
> 本文件基于**对当前仓库的实际审查**撰写（2026-10-14），不是设计文档摘要。凡结论都尽量
> 标注源码位置。若设计文档与代码不一致，本文以**代码为现状**，并在
> 「第 25 章 交付审计发现」中逐条列出差异。
>
> 本轮工作只新增/修改文档，未改动任何业务代码。

---

## 术语速查（先看这个，后面不再重复解释）

| 缩写 / 术语 | 英文全称 | 中文 | 在 RianVault 中具体负责什么 |
|---|---|---|---|
| API | Application Programming Interface | 应用程序编程接口 | 前端与后端之间约定的一组 HTTP 调用（如 `POST /api/memories`）。前端只能通过它读写，不能直接碰数据库 |
| HTTP | HyperText Transfer Protocol | 超文本传输协议 | 浏览器与服务器通信的基础协议 |
| REST | Representational State Transfer | 表述性状态转移 | 一种 API 风格：用 `GET/POST/PATCH/DELETE` 对应查/增/改/删 |
| JSON | JavaScript Object Notation | JS 对象表示法 | 接口之间传递数据的文本格式 |
| PostgreSQL | — | 关系型数据库 | **权威真源**：所有原文、记忆、版本、审计的最终存放处 |
| SQLite | — | 单文件关系型数据库 | 开发环境的默认数据库（一个 `.db` 文件），零配置；生产目标是 PostgreSQL |
| Qdrant | — | 向量数据库 | 只存「语义索引」（向量 + 少量中性元数据），可整体删除并重建 |
| 向量 / Embedding | Embedding / Vector | 嵌入向量 | 把一段文字变成一串数字（bge-m3 是 1024 维），使「意思相近」可以变成「数字相近」 |
| bge-m3 | BAAI General Embedding Model m3 | 一个开源多语言嵌入模型 | 在本机把中文/英文文本转成向量；权重下载一次后离线运行，不联网 |
| FastAPI | — | Python Web 框架 | 后端服务的骨架：接收 HTTP 请求、校验权限、调用 service、返回 JSON |
| SQLAlchemy | — | Python 的 ORM 库 | ORM = Object-Relational Mapping（对象关系映射）：把数据库表映射成 Python 类 |
| Alembic | — | 数据库迁移工具 | Migration = 数据库结构变更脚本（加表、加列），可升级/回滚 |
| React | — | 前端界面库 | 构建浏览器页面的组件库 |
| Vite | — | 前端构建工具 | 开发服务器与打包器；把 `/api` 请求转发到后端 8000 端口 |
| TypeScript | — | 带类型的 JavaScript | 前端使用的语言 |
| RAG | Retrieval-Augmented Generation | 检索增强生成 | 「先检索原文，再让大模型据此回答」。**RianVault 目前只做前半段的检索，不做答题** |
| MCP | Model Context Protocol | 模型上下文协议 | 让外部 AI（如 GPT）通过标准协议读写本系统。**目前未实现，属第二阶段** |
| Chunk | — | 文本切片 | 一条很长的消息被切成若干 ≤600 token 的小段，逐段转向量 |
| Token | — | 词元 | 模型处理文本的最小单位；中文近似 1 字 ≈ 1 token（本项目是估算值） |
| Cosine similarity | — | 余弦相似度 | 两个向量方向的接近程度，取值 −1~1；越大越「意思相近」 |
| BM25 | Best Matching 25 | 一种经典关键词相关性打分算法 | **本项目目前未使用**；关键词检索用的是数据库的子串匹配 |
| ILIKE | — | 不区分大小写的模糊匹配 | SQL 里的 `LIKE` 匹配；当前关键词检索的实际实现方式 |
| reranker | — | 重排序模型 | 对已召回的候选再精排一遍。**本项目目前没有** |
| Bearer token | — | 持有者令牌 | 请求头里 `Authorization: Bearer rv_xxx` 的一段密钥，用来证明「我是谁」 |
| SHA-256 | Secure Hash Algorithm 256-bit | 安全散列算法 | 单向哈希：数据库只存 token 的哈希，不存明文 |
| append-only | — | 只追加 | 数据只新增、不修改不删除（审计与版本史的性质） |
| JSONL | JSON Lines | 每行一个 JSON | 导出包里 `data/*.jsonl` 的格式：一行一条记录，便于逐行恢复 |
| Idempotent | — | 幂等 | 同一操作重复执行多次，结果完全一致（如重复导入同一文件不产生重复数据） |
| Quarantine | — | 隔离区 | 解析失败的原始数据单独存放，绝不静默丢弃 |
| UUID | Universally Unique Identifier | 通用唯一标识符 | 128 位随机 id，作为各表主键 |
| ORM | Object-Relational Mapping | 对象关系映射 | 见 SQLAlchemy |
| CORS / CSP | Cross-Origin Resource Sharing / Content Security Policy | 跨域资源共享 / 内容安全策略 | 浏览器安全机制；本项目为单机自用，未启用 CORS |
| Docker / Compose | — | 容器与容器编排 | 把数据库、Qdrant 打包成可一键启动的服务 |

---

## 0. 一页执行摘要（给完全不懂技术的人）

### RianVault 是什么

RianVault 是**我的私人档案馆**：把我多年来在各类 AI 聊天平台上的对话原文、以及从这些对话里
提炼出的「记忆」，长期保存在**我自己拥有的机器**上，可以随时检索、追溯、迁移。

### 为什么要做

因为那些聊天记录散落在各个平台，而**平台上的记忆不属于她**：

- 平台可能改规则、清数据、停止服务；
- 平台自己的「记忆」功能写进去的东西，导出聊天记录时**根本不会带出来**（这就是本项目
  第 8 章要打捞的「遗失记忆」）；
- 把私人聊天交给第三方服务做索引，等于把隐私交出去。**当前策略是：默认不外发**
  （embedding 本地跑，不调任何第三方 AI/embedding API）；唯一的例外通道是未来的远程 MCP，
  而它必须先经我显式授权指定对象与范围，并留审计（见 14.3）。

所以目标是：**原文永远在自己手里，任何「智能」能力都在本机完成，随时能整体迁走。**

### 现在已经能做什么

- 导入 ChatGPT 导出文件 / 自研 JSONL v1 格式 → 原文完整入库，重复导入不会产生重复数据，
  解析失败的条目进隔离区而不是被丢掉。
- 浏览会话原文、按平台/角色/模型/日期筛选（原文页与检索页都能筛）。
- 三种检索：**关键词**（数据库子串匹配）、**语义**（本机 bge-m3 向量检索）、**混合**；
  语义命中会告诉你「是哪一段被匹配上了」，关键词命中会把那个词标亮。
- 从原文选一段 → 建一条「记忆（Memory）」，标注它是**证据（evidence）**还是
  **上下文（context）**；每次改动都留一个完整版本快照，可回滚到任意旧版本。
- 「遗失记忆打捞」：扫描历史聊天里「记住 / 加入记忆库 / Model set context updated.」之类的
  信号，把候选列出来给人工判定，并可从候选直接建记忆。
- 一键导出成一个 zip（人能直接读，程序能整库恢复），并可从 zip 恢复到全新数据库。
- 回收站：删除先进回收站，可还原；只有作者本人能彻底删除，AI 身份不行。

### 现在还不能做什么（重要，别误会）

- **还没有**把系统接给外部 AI 使用的 MCP 接口（第二阶段）。
- **还没有**部署到 VPS（自有服务器）上，目前只在本机（Windows）运行。
- 关键词检索**还不是** BM25（只是简单的子串匹配）；**没有**重排序模型。
- **还没有**任何检索质量的量化评测（没建过人工标注集），所以「语义检索到底好不好」
  目前只有主观感受，没有数字。
- **不是**生产级安全系统：没有登录密码、没有 HTTPS、没有加密备份、没有自动备份调度。

### 核心原则（所有设计都从这四条长出来）

1. **数据主权**：原文与向量永远在本机/自有服务器。**当前默认不向任何第三方 AI 外发私人正文**，
   embedding 一律本地运行（详见 14.3「第三方 AI 数据政策」）。
   未来一旦要接远程 MCP，只在 **我对指定 principal / scope 显式授权后**才可披露，且必须审计。
2. **PostgreSQL 是唯一真源**：Qdrant 只是可随时删掉重建的索引；正文一个字都不进向量库。
3. **一切可追溯**：每条记忆都能指回原始聊天片段；每次改动都有版本与审计留痕。
4. **历史不可改写**：版本是「追加新版本」，不是「覆盖旧版本」。

### 现在处于什么阶段

第一阶段（T0–T10）已完成并通过一键验收脚本；正处于 **Phase 1.5：检索评估与优化**的门口
（准备做检索评测、再决定是否上 BM25 / 重排序）。第二阶段的远程 MCP、第三阶段的 VPS 部署
都还只是计划。

---

## 1. 项目起源与需求演变

### Phase 0：空仓库审计（2026-10-09）

**当时的需求**：「做一个能长期保存、检索、追溯、迁移私人聊天与衍生记忆的系统」，
但仓库是完全空的（绿地项目 / Greenfield）。在写第一行代码之前，先做了一次完整审计，
产出 [`RIANVAULT_DESIGN_AUDIT.md`](../RIANVAULT_DESIGN_AUDIT.md)。

**为什么先审计而不是直接写**：这个项目的工作方式是「先审计后开工，明确批准后才动代码」。
审计结论是：**不要急着写功能，先把真源、索引、权限、隐私边界定死**，否则后面每一次改动
都要推倒重来。

**四个奠基决策**：

1. **PostgreSQL 作为真源**
   - 理由：原文是不可再生的第一手材料，必须放在一个成熟、可备份、可迁移、支持事务的
     关系型数据库里；任何问题的最终答案以它为准。
   - 代码体现：`backend/app/models/` 全部表；`backend/app/db/session.py` 提供会话。

2. **Qdrant 只做可重建索引**
   - 理由：向量库是「为了搜得快」而存在的派生数据。它可以是错的、过期的、被删掉的——
     只要能从 PostgreSQL 重新算出来就行。
   - 代码体现：`backend/app/services/index_service.py` 顶部的红线注释；
     `PAYLOAD_WHITELIST` / `FORBIDDEN_PAYLOAD_KEYS` 断言。

3. **embedding 必须本地运行**
   - 理由：把私人聊天正文发给第三方 API 就等于交出隐私。
   - 代码体现：`backend/app/services/embedding.py` 只接 `sentence-transformers` 本地模型；
     有测试专门守「零第三方 embedding 调用」。

4. **Memory 必须可追溯到原聊天**
   - 理由：一条「记忆」如果没有出处，就无法验证、无法修正、无法信任。
   - 代码体现：`memory_source_spans` 表（第 3 章）、span 增删也触发新版本（第 5 章）。

### T0 — 仓库骨架与工程纪律

- **要解决的问题**：开工前把「怎么算做完了」定下来，避免后面靠自觉。
- **新增**：`.gitignore`（私人数据与 `.env` 永不入库）、`ruff` 配置、测试目录、
  一条「只增不删」的工程约定、以及一条专门的仓库卫生测试。
- **踩过的坑**：`.gitignore` 里写了未锚定的 `models/`，把 `backend/app/models/` 整个 ORM 包
  忽略掉了——本地测试全绿，clone 之后才发现包没了。已改成 `/models/`，并新增
  `backend/tests/test_repo_hygiene.py` 守门。
- **证据**：`git show 873999c`。

### T1 — 数据库基座 + imports / conversations / messages

- **要解决的问题**：原文得先有地方放，而且要能区分「这次导入」和「那次导入」。
- **新增**：迁移 `0001`（`imports` / `conversations` / `messages` 三表）、Alembic 配置。
- **关键决策**：
  - **双时间**：`event_time`（事情真正发生的时间）与 `ingested_at`（导入时间）**严格分开**。
    理由：2023 年的聊天在 2026 年被导入，这两个时间不能混。
  - **导入台账**：每次导入记为一条 `imports` 记录，带文件 checksum（校验和），
    同一文件重复导入直接返回已有记录。
- **踩过的坑**：`alembic/env.py` 曾自己解析数据库连接串，与运行时配置是两套逻辑，
  结果环境变量写错就会静默迁移到别的库（已实际误清过一次开发库）。已改为复用同一份配置，
  并在启动时打印连的是哪个库（密码脱敏）。
- **证据**：`backend/alembic/versions/9fa6f1d16975_0001_*.py`；`git show 053821f`。

### T2 — 导入管线（ChatGPT + JSONL v1）

- **要解决的问题**：不同平台导出格式不同，且**绝不能静默丢数据**。
- **新增**：`backend/app/services/importers/`（`base.py` 定义规范格式，
  `chatgpt.py` / `jsonl_v1.py` 两个适配器，`pipeline.py` 编排）、`import_quarantine` 表。
- **关键决策**：
  - **三层幂等**：① 文件 checksum；② 平台 + 源会话 id；③ 消息内容哈希。
    任一层命中就跳过，保证重复导入零重复数据。
  - **对账不变式**：`解析条数 = 导入 + 重复 + 隔离`，不满足就把这次导入标记为 `failed`，
    不允许「看起来成功了其实少了一半」。
  - **隔离区**：解析不了的原始条目原样存进 `import_quarantine`，绝不丢。
- **证据**：`backend/tests/test_import_pipeline.py`；验收脚本第 3 项。

### T3 — Memory 域 + 版本史 + spans + 审计

- **要解决的问题**：从原文里提炼出的「记忆」必须能被信任——要能追溯、能回滚、能知道谁改的。
- **新增**：`memories` / `memory_versions` / `memory_source_spans` / `audit_events` 四表，
  `memory_service.py` / `span_service.py` / `audit_service.py`。
- **三个核心决策（这是整个项目最容易被误解的地方）**：
  1. **版本用「全量快照」而不是「差异补丁」**
     - 为什么：差异链（diff）里任何一环损坏，之后所有版本都恢复不出来；而一条记忆正文
       只有 KB 级，存整份快照的成本可以忽略。
     - 代码：`memory_service.build_snapshot()` 把当时的全部字段 + 当时生效的 spans 列表
       一起冻结成 JSON。
  2. **span 增删也触发新版本**
     - 为什么：来源变了，这条记忆的「证据链」就变了，属于实质变更，必须留痕。
     - 代码：`span_service.add_span()` / `remove_span()` 都调用 `bump_version_for_span_change()`。
  3. **restore（回滚）绝不覆写旧历史**
     - 为什么：如果回滚是「把 v2、v3 删掉」，那你就再也回不去了，审计也断了。
     - 实际做法：把 v1 的内容**复制成一个新版本 v4** 追加在后面，v2/v3 原样保留。
     - 代码：`memory_service.restore_version()`；测试
       `tests/test_memory_domain.py::TestDeleteAndRestore::test_restore_appends_new_version`。
- **踩过的坑**：`audit_events.target_id` 是 NOT NULL，而「导出」这类事件没有实体 id——
  解决办法是用 UUID 推导一个稳定句柄（uuid5），而不是塞个假 id。

### T4 — 认证与权限矩阵

- **要解决的问题**：系统将来会被 AI（通过 MCP）访问，必须**事先**把「AI 能做什么」
  限制住，而不是等出了事再补。
- **新增**：`api_tokens` 表、`core/security.py`（token 生成与哈希）、
  `core/deps.py`（`require_any_role` / `require_owner` 两个权限依赖）。
- **关键决策**：**角色只有两个**：`owner`（作者本人，全权限）与 `zhan_mcp`（受限写入）。
  AI 身份可以读写记忆、检索、加来源片段，但**不能导入、删除、回滚、导出、管令牌**。
- **证据**：设计文档「附 1 权限矩阵」；`tests/test_auth.py`；验收脚本第 22–28 项。

### T5 — 遗失记忆打捞（Migration Audit）

- **要解决的问题**：别的平台曾经「记住」过一些事，而这些记忆**不在**导出的聊天记录里。
- **新增**：`migration_reviews` 表、`migration_audit_service.py`、
  `backend/config/migration_signals.yaml`（31 条信号词）、前端打捞页面。
- **关键决策**：**命中信号 ≠ 真实记忆写入**。系统只负责把候选连上下文列出来，
  判定（verdict）一律由人工完成，系统永不自动认定、永不自动建记忆。
- **证据**：`tests/test_migration_audit.py`；验收脚本第 13–15 项。

### T6 — 本地 embedding + Qdrant + 检索

- **要解决的问题**：20M 字的聊天，靠关键词「记得有这回事但忘了用词」是搜不到的。
- **新增**：`chunking.py`（切块）、`embedding.py`（模型封装）、`index_service.py`（写向量）、
  `search_service.py`（检索）、`chunk_index` 表。
- **关键决策**：**正文不进向量库**。Qdrant 的每个点只带 `chunk_id` 与少量中性过滤字段，
  拿到 `chunk_id` 后**回 PostgreSQL 取原文**。
- **踩过的坑（真实崩过）**：
  - 本机没有 Docker → 用 `qdrant-client` 的**本地文件模式**（`QDRANT_MODE=local`）。
  - 本地模式**独占存储目录**：同一进程内开第二个客户端也会冲突，表现为并发检索 503。
    已改为进程内单例（`index_service.get_qdrant()`）。
  - embedding 提供者也必须单例——原先每次调用都重新加载 2GB 模型，语义检索 5.6 秒/次；
    改单例后热态 0.21 秒/次（实测提速约 26 倍）。
- **证据**：`tests/test_search.py`、`tests/test_index_payload.py`、真机 e2e
  `scripts/e2e_t6_check.py`。

### T7 — Portable Export 与恢复

- **要解决的问题**：如果这台机器/这个程序没了，数据要还能拿出来，而且**不用装程序也能读**。
- **新增**：`export_service.py`（打 zip）、`restore_service.py`（从 zip 恢复）、
  `scripts/restore_from_export.py`、前端导出页。
- **关键决策**：包里 `data/*.jsonl` 是权威数据（按主键原样写回），`markdown/` 是给人读的副本；
  **向量不导出**（可以重算）；恢复前先验 `manifest.json` 与 `checksums.sha256`，不符就中止。
- **证据**：`tests/test_export.py`、`scripts/e2e_t7_check.py`、验收脚本第 16–21 项。

### T8 / T9 — 前端骨架与核心页面

- **要解决的问题**：不能只靠 curl 用这个系统。
- **新增**：React + Vite + TS 前端，设计令牌（颜色/间距/字号变量）、`api.ts` 单一通信入口、
  十个页面（第 10 章逐页说明）。
- **踩过的坑**：生成代码时 JSX 括号不匹配；vitest 需要关掉 CSS 解析；
  测试组件后必须 `cleanup()`，否则后续用例拿到脏 DOM。

### T10 — 加固与文档

- **要解决的问题**：这是个私人库，最怕的不是被黑客，而是「自己手滑把正文写进日志/响应」。
- **新增**：日志脱敏过滤器、统一异常处理（500 + `error_id`，不回吐细节）、安全响应头、
  全站 `no-store`、写操作与检索限流、`tests/test_hardening.py`、运维手册。
- **踩过的坑**：自建 logger 默认没有 handler，INFO 不显示；限流默认额度会把整套测试一起
  限成 429（已在测试环境关闭并单独测试限流本身）。

### 一键验收脚本（G.0）

- **要解决的问题**：「做完了」不能靠嘴说，也不能靠几十条命令手工跑。
- **新增**：`scripts/acceptance_check.py`（第 15 章逐项解释）。
- **关键设计**：自建**带时间戳的新数据库**，不碰现有数据；起服务、造 token、逐项跑，
  最后打印 `通过 30 / 30`。

> 后续（T10 之后）的产品决策与 bug 修复记录在 `docs/dev-log.md`，包括：来源片段范围可编辑、
> 检索页与原文页都要筛选、多文件导入、检索证据可见（高亮 / 语义命中片段 / 来源标签）、
> 回收站，以及三个并发相关的崩溃级 bug。详见该文件 2026-10-13 / 2026-10-14 条目。

---

## 2. 当前系统全景架构

### 2.1 用文字先讲一遍

系统一共四层，职责边界非常清楚：

1. **浏览器里的 React 前端**：只负责显示与收集操作。它**不认识数据库**，也不会自己去算向量，
   一切通过 `http://…/api/...` 请求后端。
2. **FastAPI 后端**：收到请求后做三件事——**验身份**（令牌是谁、什么角色）、
   **调 service**（业务逻辑的唯一入口）、**返回 JSON**。路由本身很薄，不含业务规则。
3. **Service 层（唯一写入路径）**：所有会改动数据的操作，都必须经过这里，并且按固定顺序：
   `权限校验 → 业务校验 → 写版本快照 → 写审计 → 提交`。UI、导入脚本、未来的 MCP，
   走的都是同一批函数，**不允许任何旁路直写数据库**。
4. **存储**：
   - **PostgreSQL（生产）/ SQLite（开发默认）**：唯一权威真源。
   - **Qdrant**：语义索引，可删可重建。
   - **bge-m3（本机进程内）**：把文本变向量的模型，不联网。

另外五条旁路能力也挂在 service 层上：**Import（导入）**、**Search（检索）**、
**Memory（记忆）**、**Migration Audit（遗失记忆打捞）**、**Export/Restore（导出恢复）**，
以及贯穿一切的 **Audit Log（审计）**。

### 2.2 ASCII 架构图

```
┌──────────────────────────────────────────────────────────────────────┐
│  浏览器 Browser（我的电脑）                                            │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │  React 前端（frontend/）                                        │  │
│  │  Home / 原文 / 记忆库 / 记忆详情 / 检索 / 导入 / 导出 / 打捞 / 设置  │  │
│  │  只通过 fetch('/api/...') 说话；令牌只存在 sessionStorage        │  │
│  └───────────────────────────┬────────────────────────────────────┘  │
└──────────────────────────────┼───────────────────────────────────────┘
                               │ HTTP + Bearer token（POST 查，正文不进 URL）
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│  FastAPI 后端（backend/app/）                                         │
│                                                                      │
│   ① 中间件：安全响应头 / no-store / 写操作限流                        │
│   ② 认证：Authorization: Bearer → 查 api_tokens（只存哈希）           │
│   ③ 路由（薄）：解析参数 → 依赖注入权限 → 调 service                  │
│                                                                      │
│   ┌──────────────────────── Service 层（唯一写入路径）─────────────┐  │
│   │  memory_service   记忆 + 版本史 + 回滚 + 软删除 + 彻底删除      │  │
│   │  span_service     来源片段增删与范围调整（触发新版本）           │  │
│   │  importers/*      导入适配 + 三层幂等 + 隔离区 + 对账            │  │
│   │  chunking         按句末标点把长消息切成 ≤600 token 的块         │  │
│   │  index_service    块 → 向量 → Qdrant；PG 侧登记 chunk_index     │  │
│   │  search_service   关键词 / 语义 / 混合；命中片段回传             │  │
│   │  migration_audit  遗失记忆候选扫描与人工判定                     │  │
│   │  export/restore   打 zip / 从 zip 重建                          │  │
│   │  audit_service    审计事件（append-only）                        │  │
│   └────────────────────────────────────────────────────────────────┘  │
└───────┬───────────────────────┬──────────────────────┬───────────────┘
        │ 读写（唯一入口）        │ 块文本 → 向量          │ 向量 + 白名单
        ▼                       ▼                      ▼
┌────────────────────┐  ┌──────────────────┐  ┌────────────────────────┐
│ PostgreSQL / SQLite │  │ 本地 bge-m3      │  │ Qdrant                 │
│ ★ 唯一权威真源 ★    │  │ （进程内推理）    │  │ 可丢弃、可重建的索引    │
│ imports             │  │ 权重约 4.3GB     │  │ 只存向量 + chunk_id    │
│ conversations       │  │ 首次加载约 60 秒  │  │  + 中性过滤字段        │
│ messages（正文）     │  │ 启动后台预热      │  │ ✗ 绝不含正文           │
│ memories            │  └──────────────────┘  └────────────────────────┘
│ memory_versions     │
│ memory_source_spans │
│ audit_events        │
│ api_tokens          │
│ chunk_index         │
│ migration_reviews   │
│ import_quarantine   │
└────────────────────┘
```

**一句话记住**：**箭头可以往下走（写），但「答案」只能从 PostgreSQL 来。** Qdrant 只回答
「哪几个 id 可能相关」，正文必须回 PostgreSQL 取。

### 2.3 每一层能访问什么 / 不能访问什么

| 层 | 能访问 | 不能访问 |
|---|---|---|
| React 前端 | 通过 `/api` 拿到的 JSON；存在浏览器会话里的令牌 | 不能直接连数据库、不能连 Qdrant、不能加载 bge-m3 |
| FastAPI 路由 | 请求参数、service 返回值 | 不写业务逻辑、不直接改表 |
| Service 层 | 全部表、Qdrant、embedding | 不得绕过权限检查；不得把正文写进日志 |
| Qdrant | 向量 + `chunk_id` + 中性过滤字段 | **绝不含正文**（写入前有白名单断言，测试守着） |
| 外部世界 | 无 | **当前**不允许把正文/向量发给任何第三方服务；唯一例外是未来经我显式授权的远程 MCP（14.3） |

---

## 3. 数据模型 / Schema 全解

全部 ORM 定义在 `backend/app/models/`，共 **11 张表**。下面按「它在现实里代表什么」来讲，
不只列字段。

### 3.1 表清单与通俗解释

| 表 | 现实里代表什么 | 谁创建它 | 能改吗 | 删除策略 |
|---|---|---|---|---|
| `imports` | **一次导入的台账**：导入了哪个文件、多大、什么格式、导入结果统计 | 导入管线 | 状态与统计会更新 | 不删（留痕） |
| `conversations` | **一个会话/聊天窗口**（来自某个平台） | 导入管线 | 标题等可改 | 不删 |
| `messages` | **一条原始消息**（一问或一答） | 导入管线 | **正文不可变** | 不删 |
| `import_quarantine` | **解析失败的原始数据**（这条没解析成功，但不能扔） | 导入管线 | 不改 | 不删 |
| `memories` | **一条衍生记忆**（从原文提炼的结论） | 记忆服务 | 可改（每次改留新版本） | 软删除 → 可彻底删 |
| `memory_versions` | **某条记忆在某个时刻的完整快照** | 记忆服务 | **append-only** | 随记忆彻底删除 |
| `memory_source_spans` | **记忆的出处**：指向原文的一段连续消息 | span 服务 | 可改范围、可软移除 | 软移除（`removed_at`） |
| `audit_events` | **谁在什么时候做了什么** | 各处写入 | **append-only** | 不删 |
| `api_tokens` | **一把钥匙**（只存哈希） | 令牌管理（作者） | 可吊销 | 不删（吊销） |
| `chunk_index` | **哪些原文块已经进了向量库**（索引状态登记） | 索引服务 | 随重建更新 | 级联删 |
| `migration_reviews` | **一条遗失记忆候选 + 人工判定** | 打捞扫描 / 人工 | 判定可改 | 不删 |

### 3.2 关键字段与约束（挑真正重要的说）

**`imports`**（`backend/app/models/import_.py`）
- 主键 `id`（UUID）。
- `checksum_sha256`：**唯一**。同一个文件再传一次，直接命中这一列 → 幂等。
- `status`：`running` / `completed` / `failed`（「已导入过」只是响应里的状态，不落库）。

**`conversations`**
- 唯一约束：`(source_platform, source_conversation_id)`——同一平台同一个会话不会存两份。
- `dedup_hash`：源会话 id 缺失时的确定性哈希兜底（也唯一）。
- `raw_metadata`：导出文件里没被映射的字段**原样保留**，不丢信息。

**`messages`**（最关键的一张表）
- 唯一约束两条：`(conversation_id, source_message_id)` 与 `(conversation_id, dedup_hash)`。
- **双时间**：`event_time`（事情发生）+ `event_time_raw`（原始字符串）+ `ingested_at`（导入时间）。
- `content_text` / `content_raw`：**导入后永不出现在 UPDATE 语句里**（写在类的文档字符串里当红线）。
- `source_model` / `source_model_note` / `model_label_source`：模型标签。**第一阶段系统不做任何
  猜测**，来源只能是 `export`（导出文件里带的）或 `manual`（人工标注）。
- `dedup_hash`：内容哈希，幂等的第三层。

**`memories`**
- `status`：`active` / `draft` / `archived` / `deleted`。
- 双时间：`event_time_start` / `event_time_end` 是 **date（日期）**，表示「事情发生在哪天」；
  与 `created_at`（什么时候建的这条记忆）严格分开。
- `current_version`：当前版本号，每次改动 +1。

**`memory_versions`**
- 唯一约束 `(memory_id, version_number)`。
- `snapshot`：该版本的**完整**记忆字段 + 当时生效的 spans 列表。
- append-only：只有新增，没有修改。

**`memory_source_spans`**
- `span_type`：`evidence`（证据，直接支撑这条记忆）或 `context`（上下文，帮助理解）。
- `start_message_id` / `end_message_id`：一段**连续**消息的起止。
- `removed_at` / `removed_by_actor`：软移除（不是物理删），历史留在版本快照与审计里。

**`audit_events`**
- `target_type` / `target_id`：对谁做的。`target_id` 是 NOT NULL（没有实体时用 uuid5 推导）。
- `detail`：只放轻量元信息（版本号、id、计数），**不放正文**。

**`chunk_index`**
- `vector_id`：由 `message_id + chunk_index` 用 uuid5 **确定性推导** → 重复写入天然幂等。
- `embedding_model`：**换模型必须整库重建**（换模型 = 换向量空间），脚本靠这一列判断。

**`migration_reviews`**
- `signal_message_id`：**唯一**（一条消息最多一条候选）。
- `verdict` 取值（见 `backend/app/models/migration_review.py`）：
  `unreviewed` / `successful_write` / `failed_write` / `retry_success` / `edit` / `delete` /
  `uncertain` / `ignore`。
- `context_start_message_id` / `context_end_message_id`：人工选定的上下文范围。
- `linked_memory_id`：从候选建出的正式记忆。

### 3.3 ER 图（实体关系，ASCII）

```
imports ──┬─1:N─▶ conversations ──1:N─▶ messages ──┬─1:N─▶ chunk_index
          │                                │        │
          └─1:N─▶ import_quarantine        │        └──1:N─▶ migration_reviews
                                           │                    （signal_message_id 唯一）
                                           │                    │
                                           │                    └──N:1──▶ memories（可选）
                                           │
                                           └──◀── memory_source_spans
                                                  （start/end 都指向 messages）

memories ──1:N──▶ memory_versions          （每改一次追加一份全量快照）
memories ──1:N──▶ memory_source_spans      （一条记忆可有多个 span，可跨会话）

audit_events     独立表，用 (target_type, target_id) 软指向任意对象
api_tokens       独立表（只存 token 哈希）
```

### 3.4 那条最重要的链：conversation → message → source span → memory → version

用一句人话串起来：

> **一个会话（conversation）**里有很多**消息（message）**；
> 你从中挑出连续的一段（比如第 12～15 条），这就是一个**来源片段（source span）**；
> 你基于它写下一条结论，这就是**记忆（memory）**；
> 这条记忆此后每一次被改动，都会再冻结一份**版本（version）**。

所以：

- **conversation → message**：一条消息只属于一个会话。
- **message → source span**：span 不是复制原文，而是**指向**原文的起止消息 id
  （原文仍然只有一份，不可变）。
- **source span → memory**：一条记忆可以有多个 span，可以是 evidence 也可以是 context，
  甚至可以跨会话。
- **memory → memory version**：版本是「时间的切片」，记录**那时**记忆长什么样、
  挂着哪些 span。

**为什么 span 要单独一张表、而不是把原文复制进来？** 因为原文必须只有一份（可追溯、不可篡改），
span 只是「引用」。复制一份就会有两份真相。

---

## 4. 「一条聊天进入 RianVault」全过程

下面用一个虚构例子完整追踪。假设你导出了一份 `my-chats.json`，点开系统的「导入」页上传。

### 4.1 流程图

```
 ① 选择文件（前端，可多选）
        │
        ▼
 ② POST /api/imports  （multipart 上传；仅作者本人）
        │
        ▼
 ③ 计算文件 SHA-256 checksum
        │
        ├── 已存在同 checksum 的 imports 行？ ──是──▶ 直接返回 already_imported=True（结束）
        │
        ▼ 否
 ④ 识别格式：_detect_adapter(data, filename, source_type)
        │   依次问每个适配器「你认识这个文件吗」
        ├── chatgpt 适配器  ──▶ 认识
        ├── jsonl_v1 适配器 ──▶ 认识
        └── 都不认识 ──▶ 400 拒绝（绝不半懂不懂地硬塞）
        │
        ▼
 ⑤ 适配器把文件解析成「规范结构」CanonicalConversation / CanonicalMessage
        │
        ▼
 ⑥ 逐会话：_get_or_create_conversation
        │   先按 (平台, 源会话 id) 找；找不到再按 dedup_hash 找；都没有才新建
        ▼
 ⑦ 逐消息：_import_messages
        │   ├─ 解析失败 → 写 import_quarantine（原样保留 payload + 原因）
        │   ├─ 本次已见过相同 dedup_hash → 计为重复，跳过
        │   ├─ 库里已存在相同 dedup_hash → 计为重复，跳过
        │   └─ 新建 message（正文 + 双时间 + 模型标签 + dedup_hash）
        ▼
 ⑧ 对账：parsed == imported + duplicates + quarantined
        │   不满足 → 这次导入标记 failed（绝不「看起来成功」）
        ▼
 ⑨ 更新 imports 台账（stats / warnings / finished_at），提交事务
        │
        ▼
 ⑩ 后台（守护线程、串行）自动补齐语义索引：切块 → bge-m3 → Qdrant
```

### 4.2 逐个概念解释

- **source ID（源 id）**：这条消息在**原来那个平台**里的编号（如 ChatGPT 的 message id）。
  存在 `messages.source_message_id`。有了它，同一条消息被重复导入时才能认出来。

- **deterministic hash（确定性哈希）**：把「平台 + 会话 + 角色 + 正文 + 时间」等字段拼起来
  算出的 SHA-256。只要内容一样，算出来的值永远一样——所以即使源 id 缺失，也能认出重复。
  存在 `messages.dedup_hash` 与 `conversations.dedup_hash`。

- **幂等（idempotent）**：同一操作做 N 次，结果跟做 1 次一样。本项目用了三层：
  文件 checksum（整份文件级）、源 id（平台级）、内容哈希（消息级）。
  → 所以你手抖传了两次，不会得到两份聊天记录。

- **event_time（事件时间）**：这条消息**在当时**是什么时候发的。来自导出文件的时间戳；
  原始字符串也存一份 `event_time_raw`（防止解析规则变了还能重算）。

- **ingested_at（摄入时间）**：这条消息**什么时候被导入进 RianVault**。是系统时间。
  → 为什么两个都要？2023 年的聊天在 2026 年导入，`event_time` 是 2023，`ingested_at` 是 2026。
  混在一起就没法回答「我哪天导入的」。

- **raw_metadata（原始元数据）**：导出文件里那些**没有专门做字段**的内容，原样存进
  JSON 列。理由：现在不需要，不代表以后不需要；丢了就再也找不回来。

- **model label（模型标签）**：这条消息是哪个模型生成的（`source_model`）。
  **第一阶段系统绝不猜测**——只接受导出文件里写明的（`export`）或人工标注的（`manual`）。
  理由：猜错等于编造，而这是个以「可追溯」为生命线的系统。

- **quarantine（隔离区）**：解析失败的条目连原始 payload 一起存进 `import_quarantine`，
  并写明失败原因。**绝不静默丢数据**是本项目的硬纪律。

- **reconciliation（对账）**：`解析条数 = 成功导入 + 重复 + 隔离`。这个等式不成立就把这次
  导入判为 `failed`。写在 `backend/app/services/importers/pipeline.py` 顶部当不变式。

### 4.3 导入之后系统做了什么（容易忽略的一步）

导入成功返回后，后端会**在后台串行地**给新消息建语义索引（切块 → 向量 → Qdrant）。
页面上「已索引 X / Y 条」会增长；如果因为另一个进程占着索引目录而失败，索引页会提示你
手动「补齐语义索引」。**这一步失败不会导致导入失败**——原文已经在库里了，索引随时可以补。

---

## 5. 「从原聊天创建一条 Memory」全过程

### 5.1 具体例子

你在「原文」页打开一个会话，选中第 12～15 条消息，选择**类型 = 证据（evidence）**，
写下结论：「喜欢安静、有空间感的环境。」然后保存。

```
 ① 在 Conversation Viewer 选中消息 A～D（起止顺序反了也没关系，前端会纠正）
        │
        ▼
 ② POST /api/memories   { title, body, memory_type, ... }
        │   权限：owner 与 zhan_mcp 都可以
        ▼
 ③ memory_service.create_memory()
        │   - 校验（正文非空、类型合法等）
        │   - 写入 memories 行，current_version = 1
        │   - 冻结 v1 快照（此时还没有 span）
        │   - 写审计事件 memory_created
        ▼
 ④ 前端再 POST /api/memories/{id}/spans  { start_message_id=A, end_message_id=D,
        │                                   span_type="evidence" }
        ▼
 ⑤ span_service.add_span()
        │   - 校验 A、D 属于同一会话、顺序正确、消息存在
        │   - 写入 memory_source_spans 行
        │   - bump_version_for_span_change()：current_version = 2，冻结 v2 快照
        │     （v2 快照里已经带上这条 span）
        │   - 写审计 span_added
        ▼
 ⑥ 你后来觉得结论写得不好，改了正文
        │
        ▼
 ⑦ PATCH /api/memories/{id} → current_version = 3，冻结 v3，审计 memory_updated
        │
        ▼
 ⑧ 你后悔了，点「回滚到 v2」
        │
        ▼
 ⑨ restore_version(2)：把 v2 的内容**复制**成 v4 追加在后面（v2、v3 原封不动），
        审计 version_restored（记 restored_from=2）
```

### 5.2 四个容易混淆的概念

| 概念 | 是什么 | 不是什么 |
|---|---|---|
| **Evidence Source（证据来源）** | 直接支撑这条结论的原文片段。「我从这段推出这个结论」 | 不是背景介绍 |
| **Context Source（上下文来源）** | 帮助理解、但本身不构成证据的片段（比如前因后果） | 不是证据 |
| **Memory Version（记忆版本）** | 这条记忆在**某个时刻**被冻结的完整状态（含当时的 spans） | 不是「差异补丁」，也不是可修改的记录 |
| **Audit Event（审计事件）** | 「谁、在什么时候、对什么、做了什么」的一条留痕 | 不含正文；不是版本本身 |

一句话区分：**版本回答「那时它长什么样」，审计回答「谁动过它」。**

### 5.3 为什么回滚（restore）必须是「追加」而不是「覆盖」

假设 v1 → v2 → v3，你觉得 v2 之后改坏了，想回到 v2：

- **错误做法**：把 v3 删掉，把当前状态改成 v2 的内容。
  → 后果：你再也回不到 v3 了；审计史出现断口；「谁在什么时候改坏了」这件事被抹掉了。
- **本项目做法**：新建 v4，内容与 v2 相同，追加在后面。
  → 好处：v1..v3 全部完好；v4 也是一次正常的、有审计的改动；你随时能再回滚到 v3。

代价是版本会变多，但一条记忆只有 KB 级，完全可以接受。
代码：`backend/app/services/memory_service.py::restore_version()`。

### 5.4 删除与回收站（2026-10-14 新增）

- **软删除**：`DELETE /api/memories/{id}` → `status="deleted"` + `deleted_at`，
  正文、版本、spans **都还在**。前端按钮需要点两次确认。
- **还原**：`POST /api/memories/{id}/undelete` → 恢复到**删除前那一刻的状态**
  （读上一版快照里的 status，不会把「归档」悄悄变成「活跃」），并且也追加一个新版本。
- **彻底删除**：`DELETE /api/memories/{id}/purge` → 物理删除 memory + 版本 + spans，
  只留一条 `memory_purged` 审计留痕（说明「它曾经存在、被谁删的」）。
- **权限**：以上三个**仅 owner 角色**。AI 身份（`zhan_mcp`）对三者全部得到 403，
  且前端不会给它显示这些按钮。

---

## 6. 检索系统详解（忠实于当前实现，不写理想状态）

代码：`backend/app/services/search_service.py`、`chunking.py`、`index_service.py`。
入口：`POST /api/search`（用 POST 而非 GET，是为了让查询词不出现在 URL、浏览器历史、
代理日志里——查询词是私人内容）。

### 6.1 关键词检索（Keyword Search）

- **是不是 BM25？不是。** 这一点必须说清楚，避免后人误以为有了相关性排序。
- **实际算法**：数据库里的**子串包含匹配**（PostgreSQL/SQLite 的 `ILIKE '%词%'`）。
  查询按空格切成多个词，**所有词都出现才算命中（AND）**，大小写不敏感。
  - 代码：`search_service.keyword_search()`，逐词 `Message.content_text.ilike(pattern)`。
- **怎么排序**：按 `event_time` **倒序**（新的在前）。关键词命中一律记 **固定分 0.3**
  （`KEYWORD_ONLY_SCORE`），**没有相关性打分**。
- **局限（真实存在）**：
  1. 没有相关性排序：搜「爱」，出现过 100 次的和只出现 1 次的排在一起。
  2. 只是子串匹配：搜「记忆库」搜不到「记忆 库」（中间有空格）。
  3. 没有中文分词：不像专业全文引擎那样处理同义词、词形。
  4. 大表上 `LIKE '%...%'` 无法利用普通索引，数据量很大时会变慢（当前规模无感）。

### 6.2 语义检索（Semantic Search）

**它到底是怎么工作的**（一步一步）：

1. **切块（chunking）**：一条消息如果超过预算，就切成若干块。
   - 谁切：`backend/app/services/chunking.py::chunk_message()`，由 `index_service` 在
     **建索引时**调用（不是导入时直接切，也不是你手动切）。
   - 切多大：每块 **≤600 token**（配置项 `CHUNK_MAX_TOKENS`，默认 600；中文约等于 600 字）。
   - 在哪里断：按**自然边界**——中文句末标点 `。！？!?；;`、**换行**、以及西文的 `. `。
     单句本身超预算时才按字硬切。
   - 整条消息不超预算 → **根本不切**（只有一个块，index 0）。
   - 切块**不改写、不摘要、不翻译**原文（这是红线）。
2. **转向量**：本机 bge-m3 模型把每个块变成 **1024 维向量**。权重约 4.3GB，
   启动后在后台线程预热（冷启动约 60 秒，之后每次查询约 0.2 秒）。
3. **存 Qdrant**：向量写进 Qdrant；同时在 PostgreSQL 的 `chunk_index` 表登记
   「这个块属于哪条消息、第几块、用的哪个模型」。
   - `vector_id` 由 `message_id + chunk_index` 用 uuid5 **确定性推导** → 重复建索引天然幂等。
4. **查询**：把你的查询也转成向量 → 在 Qdrant 里找**余弦相似度**最高的若干块 →
   拿到 `chunk_id` 后**回 PostgreSQL 取原文**。
5. **排序**：按余弦相似度**降序**（分越高越相关）。
6. **解释「为什么命中」**：后端会回传 `chunk_index` 与 `matched_chunk_text`——
   用**与建索引时完全相同**的切分规则把原文重新切一遍，取回真正被比对的那一小段。
   前端把它单独框成「语义命中片段」。
   - 注意：这一步是「重切还原」，**不是**从向量库里读回正文（正文根本没进向量库）。

**关于「检索全不全」的诚实回答**：
- `qdrant-client` 本地模式执行的是**精确暴力搜索**（源码里明确写了
  `Local mode performs exact (brute-force) search`），**不采样、不近似**，
  所以给定的 top-K 排序是完整精确的。
- 但「语义上相不相关」是**模型的判断**。没有人工标注的标准答案，就**量不出**召回率。
  这是第 19 章「检索评测」要解决的问题。

### 6.3 混合检索（Hybrid Search）

- **当前融合方式**：先跑语义检索（主），再跑关键词检索（补充）；
  按 message 去重后按分数排序；如果一条既是语义命中又是关键词命中，两条标签都给它。
- **标签**：每条结果带 `match_types`（`["semantic"]` / `["keyword"]` / 两者都有），
  前端渲染成彩色「语义」「关键词」胶囊标签。
- **有没有重排序（reranker）？明确回答：没有。**
  - 没有下载、也没有使用任何 cross-encoder / reranker 模型。
  - 排序依据就是：语义 = 余弦相似度；关键词 = 固定分 0.3。
- **为什么关键词命中分数是固定的、排在后面**：因为当前关键词检索本身不产出相关性分数。
  这是「语义为主、关键词兜底」的取舍，不是 bug。

### 6.4 检索流程图

```
POST /api/search  { query, mode: keyword|semantic|hybrid, filters }
        │
        ├─ mode=keyword ─▶ 数据库 ILIKE 扫描 messages（多词 AND）
        │                   → 按 event_time 倒序，score 固定 0.3
        │
        ├─ mode=semantic ─▶ 查询文本 → bge-m3 向量
        │                   → Qdrant 精确 top-K（余弦）
        │                   → chunk_index 回查 PostgreSQL 拿原文
        │                   → 重切原文取回「命中片段」
        │
        └─ mode=hybrid ──▶ 上面两条都跑 → 按 message 去重 → 按分数排序
                            → 每条标注 match_types（语义 / 关键词 / 两者）
        │
        ▼
   返回 hits[]：正文 + 得分 + match_types + 命中片段（语义时）
   日志只记「命中几条」，绝不记查询词本身
```

### 6.5 下一阶段检索改进建议（**全部是未来优化，均未实现**）

| 方向 | 术语解释 | 现状 |
|---|---|---|
| BM25 | 经典关键词相关性打分算法，比子串匹配更合理 | **未实现**，当前是 ILIKE |
| Retrieval evaluation | 检索评测：用标注集量化「搜得准不准、全不全」 | **未做**，没有任何 gold set |
| Known-item queries | 「我知道有这么一条，看你能不能搜出来」型的测试查询 | 未做 |
| **Known-item / self-retrieval**（本项目称「留一法找回自身」） | 抽 N 条已入库消息，用其中一句有代表性的话当查询，看它能否在 top-K 里**找回它自己** | **✅ 已完成第一版**（2026-10-16，30 题，结果见下）⚠️ 这是 known-item 自检索，不是真正的 Recall@K |
| Pooled relevance judgment | 把多个检索器的 top 结果混在一起人工判定，减少标注量 | 未做；**开放式 recall/precision 的前置条件** |
| Hit@K | 前 K 条里有没有至少一条相关 | **已测**：semantic / hybrid = 1.00，keyword = 0.87（30 题，K=10） |
| MRR | Mean Reciprocal Rank：第一条相关结果平均排在「第几位的倒数」，1.0 表示总在第一位 | **已测**：semantic / hybrid = 1.00，keyword = 0.87 |
| Precision@K | 前 K 条里有多少是真的相关 | 未测；**自检索给不出，必须人工判定** |
| Recall@K | 所有相关的里面，被找回来多少 | 未测；**自检索给不出，必须人工判定** |
| nDCG | 折损累计增益：考虑排序位置的相关性打分 | 未测；需要分级相关性标注 |
| reranker | 对 top-K 再精排一遍（如 bge-reranker-v2-m3） | **未实现、未下载** |

#### ✅ 第一版结果（2026-10-16，30 题，K=10）

| mode | Hit@1 | Hit@10 | MRR | 命中 |
|---|---|---|---|---|
| keyword | 0.867 | 0.867 | 0.867 | 26/30 |
| **semantic** | **1.000** | **1.000** | **1.000** | **30/30** |
| **hybrid** | **1.000** | **1.000** | **1.000** | **30/30** |

**怎么读这个结果（重要，别过度解读）：**

- 这是在 6,785 条已索引消息上跑的（另有约 3,000 条尚未进索引，出题时已排除）。
- **semantic 100% 是 known-item 方法的应有表现，不是「语义检索很强」的证明**——用原句搜原文，
  同一句子 embedding 后的相似度天然最高。它的真正价值是**回归测试**：证明切块、索引、embedding
  整条管线零退化（12 条造题时连自己都搜不回的句子已被过滤，其余全部找回）。
- **keyword 0.867 说明有 4 条关键词搜不到**——值得看一眼是分词问题还是跨块问题。
- hybrid 与 semantic 完全一致，符合实现（语义为主、关键词补位）。
- 简历/PS 上可写："Evaluated retrieval with known-item/self-retrieval (30 queries, Hit@10 & MRR);
  semantic and hybrid both reached 1.00, keyword 0.87 — confirming the indexing pipeline is
  free of degradation."**不要**把它写成检索质量的整体证明。

脚本：`scripts/eval_build_known_item_set.py`（造题 + 答案唯一性验证）、`scripts/eval_known_item.py`（三档对比）。
查询集与报告在 `backend/exports/eval/`（gitignore 覆盖，**文件里只有 message_id，无任何正文**）。

#### ⚠️ 术语纪律：不要把「留一法找回自身」说成 Recall@K

这是本项目**刻意采用**的措辞约束，接手时请不要改回去：

- **留一法找回自身是 known-item / self-retrieval**，不是 Recall@K。
  它的查询来自一条**已知存在**的文档自身，正确答案**恰好只有一个**（就是它自己），
  而且「相关集合」是人为构造出来的，不是真实的相关集合。
- 因此它只能支撑两个指标：**Hit@K**（top-K 里找没找到它自己）与
  **MRR**（它自己平均排在第几位）。这两个指标是客观、可复现、不需要人工标注的。
- 它**不能**支撑 Precision@K 与 Recall@K：
  - Precision@K 需要判断「top-K 里**其余** K−1 条算不算相关」——自检索无从判断；
  - Recall@K 需要知道「**一共**有多少条相关」——自检索把相关集合定义成了 1，
    算出来的数字没有真实语义，报出来会误导人。
- **开放式 recall / precision 仍然需要 pooled relevance judgment**：
  把若干检索器（关键词 / 语义 / 混合）的 top-K 结果混成一个池子，人工逐条判相关/不相关，
  才能算出有意义的 Precision@K 与 Recall@K。这一步省不掉。

> 所以 Phase 1.5 的正确产出是：**先报 Hit@K / MRR**（零标注，立刻能跑），
> 再决定是否为「真正的 recall/precision」投入人工标注（pooled judgment）。

> 本项目的态度是：**先用评测拿到数字，再决定要不要为 BM25 / reranker 付出复杂度与体积**。
> 不要为了「感觉会更好」就下载 2GB 模型。

---

## 7. Qdrant 与隐私设计

### 7.1 为什么正文绝不进 Qdrant payload

- Qdrant 在这里被定义为**可丢弃的派生索引**。一旦正文进了索引，就会出现两份真相，
  而且向量库的保护等级通常低于主数据库。
- 更实际的理由：**出问题时的爆炸半径**。如果向量库被误删、被污染、被别的进程覆盖，
  只要正文不在里面，损失就只是「重建索引的时间」。
- 代码里有**三重保险**：
  1. `index_service.PAYLOAD_WHITELIST`：白名单外的键直接拒绝写入。
  2. `FORBIDDEN_PAYLOAD_KEYS`：`text` / `content` / `body` / `snippet` 等正文类字段名一旦出现
     → 抛异常阻止写入。
  3. `tests/test_index_payload.py` 专门守这条红线。

### 7.2 当前允许进入 payload 的字段（就这 5 个）

| 字段 | 用途 |
|---|---|
| `chunk_id` | 命中后回 PostgreSQL 取原文的钥匙 |
| `conversation_id` | 过滤 |
| `source_platform` | 过滤（哪个平台） |
| `source_model` | 过滤（哪个模型） |
| `event_time` | 过滤（时间） |

开启 `QDRANT_MINIMAL_PAYLOAD=true` 时，**只保留 `chunk_id` 与 `conversation_id`**，
其余过滤条件一律回 PostgreSQL 查。→ 默认 `false`。

### 7.3 如果 Qdrant 被整个删掉

- **会丢什么**：语义检索能力（在重建完成前，语义/混合检索返回空）。
- **不会丢什么**：**原文、记忆、版本、来源片段、审计、导入台账**——一个字都不会少。
  因为它们在 PostgreSQL，`chunk_index` 表也在 PostgreSQL。
- **怎么重建**：
  ```bash
  python scripts/rebuild_qdrant.py --check      # 看当前索引状态
  python scripts/rebuild_qdrant.py              # 增量补齐
  python scripts/rebuild_qdrant.py --rebuild    # 换模型后必须全量重建
  ```
  也可以直接用 `POST /api/index/build`（仅作者本人）。
- **为什么这证明了 PostgreSQL 才是唯一真源**：因为**任何**答案最终都能从 PostgreSQL 得到；
  Qdrant 只是让「意思相近」这件事变快。

### 7.4 一个必须知道的运行限制

Qdrant **本地文件模式独占存储目录**：**同一时刻只能有一个后端进程**持有它。
所以：
- 不要同时开两个后端（第二个会在启动自检时警告，检索时报 503）。
- 跑评测脚本 / 重建索引脚本时，也要先把正在运行的服务停掉。

---

## 8. Migration Audit / 遗失记忆打捞（本项目的独特功能）

代码：`backend/app/services/migration_audit_service.py`、
`backend/app/api/routes/migration_audit.py`、信号配置 `backend/config/migration_signals.yaml`、
前端 `frontend/src/pages/MigrationAudit.tsx`。

### 8.1 为什么存在

你在别的 AI 平台上聊天时，平台可能**偷偷帮你存了记忆**（比如「已加入记忆库」）。
当你导出聊天记录时，**这些记忆不会被导出来**——它们留在了那个平台里，随着平台改版、
清数据、停止服务而永久消失。

这个功能就是**从聊天记录里把这些「记忆曾经被写入/被改动」的瞬间打捞出来**，让你人工复核、
并把它重新写进你自己的 RianVault。

### 8.2 关键概念

- **signal（信号词）**：一句「疑似记忆写入动作」的话，共 **31 条**，例如
  `记住`、`加入记忆库`、`存好了`、`保存失败`、`没存进去`、`记忆库满了`、
  以及英文的 `Model set context updated.`。
  配置文件可以**随时增补**（`backend/config/migration_signals.yaml`，经人工确认过的清单）。
- **candidate（候选）**：一条消息命中了某个信号词 → 生成一条候选记录。
  同一条消息最多一条候选（`signal_message_id` 唯一，重复扫描幂等）。
- **context（上下文）**：候选消息**前后各若干条**（默认窗口 6 条，可配），
  因为只看那一句话根本判断不了「到底存没存进去」。
- **verdict（判定）**：由**作者本人**人工给出的结论。取值见 3.2 节。
  **默认 `unreviewed`（未审阅）**。

### 8.3 为什么「命中信号 ≠ 真实记忆写入」

这是这个功能最重要的纪律，必须原样传达：

- 「记住」可能只是你随口说「记住明天要交电费」，平台根本没存；
- 「保存失败」说明**没存进去**；
- 「Model set context updated.」是平台内部提示，可能是成功也可能是别的；
- 一句「已经记住了」后面可能跟着「才怪」。

所以系统**只负责把候选 + 上下文摆出来**，**绝不自动认定**，**绝不自动建记忆**。
判定权永远在人手里。

### 8.4 完整虚构例子

1. 你在打捞页选择扫描区间 `2026-07-01 ~ 2026-10-31`（也可以限定某个平台）→ 点「扫描」。
   接口：`POST /api/audit/migration-candidates/scan`（**仅作者本人**）。
2. 系统在区间内的消息里搜 31 个信号词。找到一条你 2026-08-12 说的：
   「**记住**我 caffeine 不耐受」。
3. 生成候选：`signal_message_id = 那条消息`，`matched_signal = "记住"`，
   `verdict = unreviewed`。
4. 页面上列出这条候选，并把**前后各 6 条原文**一起显示给你。
5. 你看到后面平台回了一句「已保存到记忆」→ 判定为 **`successful_write`**（真的存进去了），
   并可写备注。接口：`POST /api/audit/migration-candidates/{id}/verdict`。
6. 你觉得上下文范围要扩大一点（把平台那句确认也圈进来），选定起止消息后，
   点「从候选创建记忆」→ 系统**用你填的正文**建一条正式 Memory，并自动绑一条 span 指向
   你选定的那段原文。候选记录里的 `linked_memory_id` 指向它。
   接口：`POST /api/audit/migration-candidates/{id}/create-memory`。
7. 如果那条其实是失败的，你可以判 `failed_write` 或 `ignore`，不建记忆。

> 注意：扫描是 仅作者本人（会写入数据）；查看候选、打判定、从候选建记忆，
> owner 与 zhan_mcp 都可以。

---

## 9. 权限模型

代码：`backend/app/core/deps.py`（`require_any_role` / `require_owner`）、
`backend/app/core/security.py`（token 生成与哈希）、`backend/app/models/api_token.py`。

### 9.1 两个角色

- **owner**：作者本人。**全部权限**。
- **zhan_mcp**：给外部 AI（未来通过 MCP）用的身份。**可以读写记忆、检索、加来源片段**，
  但**不能做破坏性操作**。

### 9.2 权限矩阵（这是真实实现，不是设计稿）

| 能力 | owner | zhan_mcp | 代码依据 |
|---|---|---|---|
| 浏览 / 读 / 检索 | ✅ | ✅ | `require_any_role` |
| 创建记忆 | ✅ | ✅ | `POST /api/memories` |
| 编辑记忆（正文/标题/时间） | ✅ | ✅ | `PATCH /api/memories/{id}` |
| 新增来源片段 | ✅ | ✅ | `POST /api/memories/{id}/spans` |
| 调整来源片段范围 | ✅ | ✅ | `PATCH /api/memories/{id}/spans/{span_id}` |
| 移除来源片段 | ✅ | ✅ | `DELETE /api/memories/{id}/spans/{span_id}` |
| 导入 | ✅ | ❌ 403 | `imports.py` 路由级 `require_owner` |
| 回滚历史版本 | ✅ | ❌ 403 | `restore_memory` |
| 软删除 | ✅ | ❌ 403 | `delete_memory` |
| 还原（回收站） | ✅ | ❌ 403 | `undelete_memory` |
| 彻底删除 | ✅ | ❌ 403 | `purge_memory` |
| 建/重建索引 | ✅ | ❌ 403 | `POST /api/index/build` |
| 导出 / 下载导出包 | ✅ | ❌ 403 | `export.py` 全部 `require_owner` |
| 令牌管理（铸造/列表/吊销） | ✅ | ❌ 403 | `admin_tokens.py` 路由级 |
| 查看全站审计 | ✅ | ❌ 403 | `GET /api/audit` |
| 遗失记忆扫描 | ✅ | ❌ 403 | `POST .../scan` |
| 看自己的身份 | ✅ | ✅ | `GET /api/auth/me` |

### 9.3 401 与 403 的区别（常被混淆）

- **401 Unauthorized（未认证）**：「我不知道你是谁」。
  → 没带令牌、令牌格式不对、令牌不存在或已被吊销。
  代码：`deps.get_current_actor()`。
- **403 Forbidden（已认证但没权限）**：「我知道你是谁，但你不配做这件事」。
  → 令牌有效，但角色不是 owner。代码：`deps.require_owner()`。

### 9.4 为什么 zhan_mcp 能维护记忆却不能做破坏性操作

设计意图很直接：**让 AI 帮你整理记忆是安全的，让 AI 毁掉记忆是不可接受的。**

- AI 可以写错一条记忆——没关系，有版本史，你能回滚。
- AI 如果**能删除**，那就可能一条命令把多年积累抹掉；如果**能导出**，就能把整个档案馆
  批量带走；如果**能管令牌**，它就能给自己提权。
- 所以：破坏性（delete / purge / restore）与外泄性（export）操作**一律只对 owner 开放**。

### 9.5 令牌（token）机制

- **怎么生成**：`python scripts/create_token.py --role owner --name "…"`。
  明文（`rv_` 开头）**只在创建时显示这一次**。
- **怎么存**：数据库**只存 SHA-256 哈希**（`api_tokens.token_hash`）。
  为什么可以只存哈希而不用慢哈希（如 Argon2）？因为这是 256 位高熵随机串，不是用户密码，
  不存在被字典爆破的问题。（未来如果加「人类登录密码」，那必须用 Argon2id——
  这一点在 `core/security.py` 的文档字符串里写明了。）
- **怎么存（客户端）**：浏览器 `sessionStorage`（关掉标签页就没了），
  **不写进 URL、不写进 localStorage、不上传**。
- **服务端怎么验**：请求头 `Authorization: Bearer rv_xxx` → 取 SHA-256 → 查表
  （且 `revoked_at IS NULL`）→ 命中就认，并更新 `last_used_at`。
- **怎么吊销**：`POST /api/admin/tokens/{id}/revoke` → 写 `revoked_at`。
  吊销后该令牌立即 401。**吊销不删除行**，留着审计上「它存在过」。

---

## 10. 前端页面逐页说明

前端是 React + Vite + TypeScript（`frontend/src/`）。路由定义在 `frontend/src/App.tsx`，
共 **9 个页面**。所有页面共享 `Layout`（侧栏导航）与 `PageShell`（标题 + 说明的统一外壳）。
所有请求只走 `frontend/src/lib/api.ts` 这一个出口（统一带令牌、统一抛错）。

| 路由 | 页面 | 你为什么会来这里 |
|---|---|---|
| `/` | Home | 看档案馆概览（会话数、消息数、记忆数、未审阅候选数） |
| `/search` | Search | 找「记得有这回事但忘了用词」的原文 |
| `/conversations`、`/conversations/:id` | Conversation Viewer | 读原文、筛选消息、选段建记忆 |
| `/memories` | Memory Library | 记忆列表 + **回收站** |
| `/memories/:id` | Memory Detail（Genesis） | 看/改一条记忆、看版本史与审计史、回滚、删除 |
| `/migration-audit` | Migration Audit | 打捞遗失记忆 |
| `/import` | Import | 上传聊天导出文件（可多选） |
| `/export` | Export | 一键导出 zip |
| `/settings` | Settings | 粘贴/清除访问令牌（只存浏览器会话） |

### 10.1 逐页细节

**Home（首页）**
- 做什么：显示统计数字，并提供去各处的入口（含「去打捞」）。
- 调用：`GET /api/stats` → `stats.py`。只读。
- 常见错误：401（没设令牌）→ 去 `/settings` 粘贴。

**Conversation Viewer（原文）**
- 做什么：列出会话、打开某会话读原文；支持**筛选**（模型 / 角色 / 日期区间 / 平台）；
  选中一段消息后可建记忆。
- 调用：`GET /api/conversations`、`GET /api/conversations/{id}/messages`、
  `GET /api/messages/{id}`。
- 常见错误：筛选后「0 条」通常是条件太窄，不是数据丢了。

**Memory Library（记忆库 + 回收站）**
- 做什么：列记忆（可按类型/状态/关键词筛选）、新建记忆；右上角「回收站（N）」进入回收站，
  可**还原**或**彻底删除**。
- 调用：`GET /api/memories`、`POST /api/memories`、`GET /api/auth/me`（判断是否显示危险按钮）、
  回收站：`POST /api/memories/{id}/undelete`、`DELETE /api/memories/{id}/purge`。
- 交互纪律：**彻底删除要点两次**（第一次只是变文案为「确认彻底删除？」）；
  还原是无损操作，点一次即执行。
- 常见错误：403 = 你用的不是 owner 令牌。

**Memory Detail / Genesis（记忆详情）**
- 做什么：看正文、改标题/正文、看来源片段（可**调整起止范围**）、
  看**版本史**（可回滚到任意版本）、看**审计史**、移进回收站 / 从回收站还原。
- 调用：`GET/PATCH/DELETE /api/memories/{id}`、`PATCH /api/memories/{id}/spans/{span_id}`、
  `POST /api/memories/{id}/restore`、`POST /api/memories/{id}/undelete`、
  `GET /api/memories/{id}/versions`、`GET /api/memories/{id}/audit`。
- 常见错误：改已删除的记忆会被拒（400「已删除的 memory 不能编辑」）——先还原。

**Search（检索）**
- 做什么：输入查询，选「关键词 / 语义 / 混合」，可加平台/模型/角色/日期筛选。
  结果里：**关键词命中会标亮查询词**；**语义命中会额外框出「命中片段」**；
  每条结果带「语义」「关键词」标签。
- 调用：`POST /api/search`、`GET /api/stats`（判断是否索引已覆盖）、
  `POST /api/index/build`（补齐索引，owner）。
- 常见错误：语义检索 0 条 → 多半是还没建索引，页面顶部会提示并可一键补齐；
  503 → 另一个后端进程占着索引目录。

**Import（导入）**
- 做什么：一次选**多个**文件逐个上传；结果**累加显示**（不会顶掉之前的）；下方始终显示
  历史导入列表。
- 调用：`POST /api/imports`（multipart）、`GET /api/imports`。
- 常见错误：403（不是 owner）、400（格式识别不了 / 文件过大）。

**Export（导出）**
- 做什么：一键打包，并列出/下载历史导出包。
- 调用：`POST /api/export`、`GET /api/export`、`GET /api/export/{id}/download`。
- 常见错误：403（不是 owner）。

**Migration Audit（遗失记忆打捞）**
- 做什么：选日期区间 → 扫描 → 逐条看候选 + 上下文 → 打判定 → 可从候选直接建记忆。
- 调用：`POST /api/audit/migration-candidates/scan`（作者）、
  `GET /api/audit/migration-candidates`、`POST .../{id}/verdict`、`POST .../{id}/create-memory`。
- 常见错误：扫描返回 0 条 = 区间内没有消息命中信号词（不是坏了）。

**Settings（设置）**
- 做什么：把令牌粘进去并保存；令牌存在 `sessionStorage`，关标签页即失效。
- 调用：不调后端（纯本地）；页面上的统计类接口会带上它。

### 10.2 「用户动作 → API → Service → 数据」映射表

| 用户动作 | API | Service | 读到/写到 |
|---|---|---|---|
| 上传聊天文件 | `POST /api/imports` | `importers/pipeline.run_import` | 写 imports / conversations / messages / import_quarantine |
| 浏览会话 | `GET /api/conversations` | 直接查询（只读） | 读 conversations |
| 读原文 | `GET /api/conversations/{id}/messages` | 只读 | 读 messages |
| 建记忆 | `POST /api/memories` | `memory_service.create_memory` | 写 memories + memory_versions(v1) + audit_events |
| 绑定来源片段 | `POST /api/memories/{id}/spans` | `span_service.add_span` | 写 memory_source_spans + memory_versions(v+1) + audit_events |
| 调整片段范围 | `PATCH /api/memories/{id}/spans/{sid}` | `span_service.update_span` | 改 span + 新版本（快照含 before/after） + audit_events |
| 回滚版本 | `POST /api/memories/{id}/restore` | `memory_service.restore_version` | 追加新版本 + audit_events |
| 检索 | `POST /api/search` | `search_service.*` | 读 messages / chunk_index / Qdrant |
| 建索引 | `POST /api/index/build` | `index_service.index_messages` | 写 chunk_index + Qdrant |
| 打捞扫描 | `POST /api/audit/migration-candidates/scan` | `migration_audit_service.scan` | 写 migration_reviews |
| 打判定 | `POST .../{id}/verdict` | `set_verdict` | 改 migration_reviews.verdict |
| 从候选建记忆 | `POST .../{id}/create-memory` | `create_memory_from_candidate` | 写 memories + span + 版本 + 回写 linked_memory_id |
| 导出 | `POST /api/export` | `export_service.build_export` | 读全表 + 写 zip + 记 audit |
| 软删除 | `DELETE /api/memories/{id}` | `soft_delete_memory` | 改 status + 新版本 + audit |
| 还原 | `POST /api/memories/{id}/undelete` | `undelete_memory` | 改 status + 新版本 + audit |
| 彻底删除 | `DELETE /api/memories/{id}/purge` | `purge_memory` | 物理删记忆/版本/spans + 留一条 audit |

---

## 11. API 全量说明

以下**直接读取当前路由文件**整理（`backend/app/api/routes/`），不是照抄旧设计。
权限列：`公开`（无需令牌）/ `任意`（owner 与 zhan_mcp 皆可）/ `owner`。

### 11.1 健康与身份

| 方法 | 路径 | 权限 | 说明 | 错误码 |
|---|---|---|---|---|
| GET | `/health` | 公开 | 返回 `{"status":"ok"}` | — |
| GET | `/auth/me` | 任意 | 返回当前令牌的 `{id, name, role, can_admin}`；供前端决定是否显示 作者专属按钮 | 401 |

### 11.2 导入

| 方法 | 路径 | 权限 | 请求 | 返回 | 写到 |
|---|---|---|---|---|---|
| POST | `/api/imports` | owner | multipart 文件 + 可选 `source_type` | `{already_imported, import_, quarantine[]}` | imports / conversations / messages / import_quarantine |
| GET | `/api/imports` | owner | — | 导入台账列表 | 读 imports |
| GET | `/api/imports/{id}` | owner | — | 单次导入详情（含隔离区） | 读 |

审计：导入本身不写 `audit_events`；**导出**才写（见下）。

### 11.3 会话与消息（只读）

| 方法 | 路径 | 权限 | 参数 | 说明 |
|---|---|---|---|---|
| GET | `/api/conversations` | 任意 | `platform` `limit` `offset` | 会话列表（含消息数） |
| GET | `/api/conversations/{id}` | 任意 | — | 单个会话 |
| GET | `/api/conversations/{id}/messages` | 任意 | `around`（以某条为中心）`window` `offset` `limit` | 消息列表 |
| GET | `/api/messages/{id}` | 任意 | — | 单条消息 |

### 11.4 记忆与来源片段

| 方法 | 路径 | 权限 | 说明 | 写审计 | 错误码 |
|---|---|---|---|---|---|
| POST | `/api/memories` | 任意 | 建记忆 → v1 | ✅ memory_created | 400 校验失败 |
| GET | `/api/memories` | 任意 | 列表；`status` 显式传 `deleted` 可看回收站（默认排除） | — | — |
| GET | `/api/memories/{id}` | 任意 | 详情（记忆 + spans + versions + audit） | — | 404 |
| PATCH | `/api/memories/{id}` | 任意 | 改标题/正文/类型/状态/重要性/双时间/标签 → 新版本 | ✅ | 400（已删除不能改）/404 |
| DELETE | `/api/memories/{id}` | **owner** | 软删除 → 新版本 | ✅ memory_deleted | 403/404 |
| POST | `/api/memories/{id}/undelete` | **owner** | 从回收站还原 → 新版本 | ✅ memory_restored | 403/404 |
| POST | `/api/memories/{id}/restore` | **owner** | 回滚到指定版本（**追加**新版本） | ✅ version_restored | 403/404/400 |
| DELETE | `/api/memories/{id}/purge` | **owner** | 彻底删除（记忆+版本+spans） | ✅ memory_purged | 403/404 |
| POST | `/api/memories/{id}/spans` | 任意 | 新增来源片段 → 新版本 | ✅ span_added | 400/404 |
| PATCH | `/api/memories/{id}/spans/{sid}` | 任意 | 调整片段起止/类型/备注 → 新版本（审计记 before/after） | ✅ span_updated | 400/404 |
| DELETE | `/api/memories/{id}/spans/{sid}` | 任意 | 移除片段（软移除）→ 新版本 | ✅ span_removed | 404 |
| GET | `/api/memories/{id}/versions` | 任意 | 版本史 | — | 404 |
| GET | `/api/memories/{id}/audit` | 任意 | 该记忆的审计史 | — | 404 |

### 11.5 检索与索引

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| POST | `/api/search` | 任意 | `{query, mode, limit, filters{platform, conversation_id, role, source_model, date_from, date_to}}`；返回 `{mode, count, hits[]}` |
| GET | `/api/index/status` | 任意 | 各模型的 chunk 数、总 chunk 数、collection 名 |
| POST | `/api/index/build` | **owner** | `{rebuild, limit_messages}` 建/重建索引 |
| GET | `/api/index/chunks` | 任意 | 列出 chunk 登记记录（调试用） |

### 11.6 遗失记忆打捞

| 方法 | 路径 | 权限 | 说明 | 写审计 |
|---|---|---|---|---|
| POST | `/api/audit/migration-candidates/scan` | **owner** | `{scan_from, scan_to, source_platform?}` 扫描候选（幂等） | ❌ |
| GET | `/api/audit/migration-candidates` | 任意 | 候选列表（可按 verdict 过滤） | — |
| POST | `/api/audit/migration-candidates/{id}/verdict` | 任意 | 人工判定 + 备注 | ❌ |
| POST | `/api/audit/migration-candidates/{id}/create-memory` | 任意 | 从候选建正式记忆（可指定上下文范围与 span 类型） | ✅（走 memory_service） |

### 11.7 导出、审计、令牌、统计

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| POST | `/api/export` | **owner** | 打一个 zip，返回 export_id |
| GET | `/api/export` | **owner** | 历史导出列表 |
| GET | `/api/export/{id}/download` | **owner** | 下载 zip |
| GET | `/api/export/status` | **owner** | 导出状态 |
| GET | `/api/audit` | **owner** | 全站最近审计事件 |
| POST | `/api/admin/tokens` | **owner** | 铸造令牌（**明文只出现这一次**） |
| GET | `/api/admin/tokens` | **owner** | 令牌列表（只有哈希与元数据） |
| POST | `/api/admin/tokens/{id}/revoke` | **owner** | 吊销 |
| GET | `/api/stats` | 任意 | 会话/消息/记忆/片段/已索引/可索引/未审阅候选计数 |

> 全局错误码：`401` 无令牌或令牌无效、`403` 角色不够、`404` 对象不存在、
> `400` 业务校验失败、`422` 参数格式错误、`429` 触发限流、
> `500` 未预期错误（响应体只给 `error_id`，不吐细节）。

---

## 12. 数据流图

### A. Import（导入）

```
文件 → POST /api/imports → SHA-256 → 识别 adapter → 规范结构
     → 找/建 conversation → 逐条找/建 message（三层幂等）
     → 失败条目进 quarantine → 对账 → 更新 imports 台账
     → 后台串行线程：切块 → bge-m3 → Qdrant + chunk_index
```
**解释**：导入只写 PostgreSQL；向量是随后**另外**补的，导入失败不代表索引失败，反之亦然。

### B. Search（检索）

```
POST /api/search
  ├─ keyword  → messages 表 ILIKE 扫描 → 按时间倒序
  └─ semantic → 查询转向量 → Qdrant 精确 top-K → chunk_index 回查 → PostgreSQL 取原文
                → 重切原文得到「命中片段」
  hybrid = 两者合并去重 + match_types 标注
```
**解释**：Qdrant 只给 id，正文永远从 PostgreSQL 回来。

### C. Memory Write（记忆写入）

```
前端 → POST/PATCH/DELETE（记忆或 span）
     → 权限校验 → 业务校验
     → 改对象 → 冻结新版本快照（含当时的 spans）
     → 写审计事件 → 提交
```
**解释**：**任何**改动（包括增删来源片段、软删除、还原、回滚）都走同一条链路，
都会产生新版本与审计。没有「悄悄改」的入口。

### D. Export（导出）

```
POST /api/export
 → 逐表导出 data/*.jsonl（conversations/messages/memories/memory_versions/
   memory_source_spans/audit_events/imports/chunks）
 → 生成 markdown/ 人类可读副本
 → 算每个文件 sha256 → 写 checksums.sha256 + manifest.json
 → 打 zip → 写一条 export 审计事件
```
**解释**：向量**不导出**（可重算）；`import_quarantine`、`migration_reviews`、`api_tokens`
**也不在包里**（见第 13 章的限制）。

### E. Restore（恢复）

```
zip → 解到临时目录 → 读 manifest（格式版本必须支持）
    → 逐文件校验 sha256（不符即中止，不静默继续）
    → 按 jsonl 逐表写回（保留原 UUID）
    → 计数对账（manifest vs 实际），不一致要报出来
```
**解释**：因为保留了原 UUID，记忆的版本史与来源片段才能对得上。

### F. Migration Audit（遗失记忆打捞）

```
选日期区间 → POST /scan → 在 messages 里搜 31 个信号词
          → 命中即生成候选（含前后上下文窗口）
          → 人看上下文 → 打 verdict
          → 需要的话 create-memory → 走正常的 memory_service（同样留版本与审计）
```

### G. Authentication（认证）

```
请求头 Authorization: Bearer rv_xxx
 → SHA-256(xxx) → 查 api_tokens（revoked_at IS NULL）
 → 没带/查不到 → 401
 → 查到但角色不是 owner 而接口要求 owner → 403
 → 通过 → 更新 last_used_at → 进入路由
```

---

## 13. Export / Backup / Restore

代码：`backend/app/services/export_service.py`、`restore_service.py`、
`scripts/restore_from_export.py`。

### 13.1 包里到底有什么（这是实际实现）

```
rianvault-export-YYYYMMDD-HHMMSS.zip
├── manifest.json            # 格式版本、导出时间、每张表的条数、markdown 文件数
├── checksums.sha256         # 每个文件的 sha256
├── data/                    # ★ 权威数据（可程序恢复）
│   ├── conversations.jsonl
│   ├── messages.jsonl
│   ├── memories.jsonl
│   ├── memory_versions.jsonl
│   ├── memory_source_spans.jsonl
│   ├── audit_events.jsonl
│   ├── imports.jsonl
│   └── chunks.jsonl         # 只记「索引状态」，不含任何向量
└── markdown/                # ★ 给人读的副本
    ├── memories/<id>-<标题>.md
    └── conversations/<id>-<标题>.md
```

- **真源数据**：`data/*.jsonl`。恢复程序只吃这些。
- **人类可读副本**：`markdown/`。不装 RianVault 也能双击打开读完所有记忆与会话。
- **不导出的三张表**：`import_quarantine`（隔离区）、`migration_reviews`（打捞候选）、
  `api_tokens`（令牌哈希）。→ **这是真实限制，见 13.4。**
- **为什么向量不需要导出**：向量是能重算的派生数据，导出它只会让包变大、还要操心版本兼容。

### 13.2 checksum 与 manifest 各自干什么

- **checksums.sha256**：每个文件的指纹。恢复前逐一比对——**有人改过压缩包里的东西，
  或者包传坏了，能被发现**。
- **manifest.json**：元信息 + **每张表应该有多少条**。恢复后做**计数对账**：
  manifest 说 1000 条消息，恢复完发现 998 条 → 要报出来，不允许悄悄过去。

### 13.3 「原电脑彻底坏了，我只有一个 export.zip」怎么恢复

1. 找一台能跑 Python 的机器（Windows / macOS / Linux 都行），装好 RianVault 依赖
   （见 `docs/ops-runbook.md`）。
2. 准备一个**新的空数据库**。最简单是 SQLite：
   `sqlite:///./restored.db`（就是个文件）。想上 PostgreSQL 就先起 compose 的 db。
3. 跑恢复：
   ```bash
   python scripts/restore_from_export.py exports/rianvault-export-….zip \
     --database-url sqlite:///./restored.db
   ```
4. 脚本会：解压 → 验 manifest 的版本 → 逐文件验 sha256 → 按表写回（保留原 UUID）→
   打印计数对账结果。**任何一步不通过就中止**。
5. 把配置指向这个新库（`DATABASE_URL`），启动后端。
6. **重建语义索引**（因为向量没导出）：`python scripts/rebuild_qdrant.py`
   或前端检索页的「补齐语义索引」。
7. 核对：看统计数字是否与导出时一致；抽查几条记忆的来源片段是否还能跳回原文。

### 13.4 它不是什么（重要）

| 它不是 | 为什么 |
|---|---|
| **≠ PostgreSQL `pg_dump`** | 不导 `import_quarantine` / `migration_reviews` / `api_tokens`；也不含数据库层面的索引、约束定义 |
| **≠ Qdrant snapshot** | 不含任何向量 |
| **≠ 完整灾难恢复方案** | 没有加密、没有异地副本、没有自动调度；恢复出来的库还要重建索引才算完整可用 |
| **≠ 加密备份** | zip 本身不加密，谁拿到文件谁就能读 |

---

## 14. 安全模型

### 14.1 当前**真实做到**的（逐条说明防的是什么风险）

| 措施 | 代码位置 | 防什么风险 |
|---|---|---|
| **本地 embedding** | `services/embedding.py` | 防「把私人聊天正文发给第三方 API」。只接本地 `sentence-transformers`，有测试守「零第三方调用」。**MCP 放开后此条不变**（14.3） |
| **默认不外发第三方 AI** | 全项目（当前无任何对外 AI 调用点） | 防私人正文经由任何 AI 通道离开本机；本项目也不做 LLM 答题 |
| **`.env` 与私人数据永不进 Git** | `.gitignore`（`.env`、`exports/`、`data/`、`*-dev.db`） | 防密钥与私人数据被推到远端仓库 |
| **Bearer token** | `core/deps.py` | 防「任何人都能读写」；无令牌一律 401 |
| **只存 token 哈希（SHA-256）** | `core/security.py`、`models/api_token.py` | 防数据库泄露后令牌被直接拿去用 |
| **可分角色 + 可吊销** | `api_tokens.role` / `revoked_at` | 防 AI 身份做破坏性操作；令牌丢失可即时作废 |
| **DB / Qdrant 无公网端口（生产 compose）** | `deploy/compose.prod.yml` + `tests/test_compose_security.py` | 防数据库被直接从公网访问。**注意：这只保证配置文件写法正确，不等于已部署** |
| **检索走 POST** | `POST /api/search` | 防查询词出现在 URL → 浏览器历史 / 代理日志 / 引荐来源 |
| **日志脱敏（兜底网）** | `core/logging_setup.py` 的过滤器 | 防「有人手滑把 token / 连接串密码 / 正文写进日志」。真正的保证是「不写」，这是第二道网 |
| **日志不记正文与查询词** | 各 service（只记计数） | 防隐私从日志外泄 |
| **`/api` 一律 `Cache-Control: no-store`** | `core/middleware.py` | 防私人内容被浏览器/中间层缓存下来 |
| **安全响应头** | `middleware.SECURITY_HEADERS` | 防被 iframe 嵌套点击劫持、MIME 嗅探、referrer 泄漏 |
| **未处理异常只回 `error_id`** | `core/errors.py` | 防 500 响应把异常细节（可能夹带 SQL 参数＝正文）回吐给客户端 |
| **限流（写操作与检索）** | `RateLimitMiddleware` | 防脚本失控 / 意外循环把机器压垮；也提高暴力尝试成本 |
| **软删除 + 回收站** | `memory_service.soft_delete/undelete/purge` | 防误删；彻底删除仅 owner 角色且需二次确认 |

### 14.2 目前**仍然没有解决**的安全问题（不要装作已达生产级）

1. **没有人类登录密码 / 没有会话管理**：谁拿到 owner 令牌谁就是 owner。
   未来若要加登录密码，必须用 Argon2id（已在 `core/security.py` 注释里写明）。
2. **没有 HTTPS**：开发环境是 `http://127.0.0.1`。生产要靠 Caddy 终止 TLS，
   **但那属于第三阶段，尚未部署**。
3. **没有应用层加密**：数据库文件/导出 zip 都是明文。机器被物理接触即可读。
4. **没有自动备份、没有异地副本、没有备份加密**（明确列为第一阶段非目标）。
5. **没有多用户与细粒度授权**：只有两个角色，做不到「这条记忆只给某人看」。
6. **没有 CORS 策略与 CSP**：当前只假设本机自用；一旦对外暴露需要重新评估。
7. **限流是单进程内存态**：多实例部署时会失效（注释里已声明「多实例再换 Redis」）。
8. **令牌在浏览器 `sessionStorage`**：同源 JS 可读取；XSS 会波及。**没有** XSS 防护专项审查。
9. **导出 zip 未加密**：见 13.4。
10. **依赖与镜像未做漏洞扫描**；`gitleaks` 只是设计里提到（P1），未验证是否接入 CI。

### 14.3 第三方 AI 数据政策（**本小节是该项目政策的唯一权威表述**）

这一节的存在理由：文档早期把边界写成一句「禁止任何第三方 embedding 或 AI API」，
容易被读成「本项目永远不可能有任何对外 AI 通道」。但 Roadmap 里第二阶段就是要做远程 MCP——
两句会打架。所以这里把政策拆成「**当前默认**」与「**未来例外条件**」两层讲清楚。

#### 第一层：当前默认（**已生效，代码层面真实如此**）

| 项目 | 政策 | 现状 |
|---|---|---|
| embedding / 向量化 | **永远本地**（`sentence-transformers` + 本机 bge-m3） | 已实现，有测试守 |
| 私人正文外发 | **默认不外发**：系统不主动把任何聊天正文、记忆正文发给第三方 AI | 已实现——当前代码里**根本没有任何对外 AI 调用点** |
| LLM 答题 / 生成 | 不做 | 已实现（本项目不代答） |
| 第三方 embedding API | **不用**，包括「临时顶一下」 | 红线，见第 20 章排障 |

一句话：**现在这台机器上，没有任何一条私人正文会因为 RianVault 而离开本机。**

#### 第二层：未来例外——远程 MCP（**未开工，且必须先满足全部条件**）

Phase 2 的远程 MCP 会让外部 AI（如 GPT）**读**本系统的记忆。那意味着正文会离开本机，
进入第三方模型上下文。这条通道**不是**默认开启，必须同时满足：

1. **经我显式授权**，且授权是针对**指定 principal**（＝「谁」，哪一个具体的 AI / agent /
   账号）与**指定 scope**（＝「能看什么、能写什么、多长时间」），而不是笼统开关。
2. **授权是一次决定，不是一次配置**：换 principal 或扩 scope 都要重新授权。
3. **逐次审计**：谁、在什么时间、读了/写了哪条记忆，必须进 `audit_events`，
   我事后可查。
4. **权限沿用 `zhan_mcp` 上限**：可读写记忆与检索，**不得**删除 / 导出 / 管令牌 /
   重建索引（第 9 章权限矩阵）。即使经我授权，也不自动获得 owner 级破坏性能力。
5. **embedding 仍然本地**：授权外部 AI「读取检索结果」≠ 把正文交给第三方做向量化。
   无论 MCP 是否开放，`services/embedding.py` 的本地约束与「零第三方调用」测试**都不放宽**。
6. **撤销即生效**：令牌可吊销（`api_tokens.revoked_at`），吊销后该 principal 立即失效。

> **给接手者的红线**：如果在代码里看到「为了 MCP 方便，把 embedding 换成某某云 API」
> 这类改动——**拒绝**。这两件事没有因果关系，MCP 不需要也不允许改 embedding 通道。

#### 常见误读（明确排除）

| 误读 | 正解 |
|---|---|
| 「禁止第三方 AI」＝ 永远不能有 MCP | 错。是有条件的例外，条件见上；MCP 未开工，当前仍是无外发 |
| 有了 MCP 之后，第三方就能拿到全部原文 | 错。受 principal/scope 限制，且只给授权的读取路径 |
| MCP 上线后可以顺势换云端 embedding | 错。embedding 本地是独立不变式 |
| 我的授权 = 永久授权 | 错。可吊销；换 principal/scope 需重新授权 |

---

## 15. `scripts/acceptance_check.py` 完整解释

**它是什么**：一条命令跑完「第一阶段完成标准（G.0）」的自动化验收。
```bash
python scripts/acceptance_check.py                 # 全量（含真机语义检索，约 1 分钟起）
python scripts/acceptance_check.py --skip-semantic # 不加载 bge-m3，约 20 秒
```

**它会不会碰现有数据**：**不会**。它新建一个**带时间戳的新数据库文件**，自带服务与令牌，
跑完关掉服务。旧文件一个都不删（符合仓库「只增不删」约定）。

### 15.1 30 项逐条在测什么

| # | 检查项 | 发出了什么操作 | 期待什么行为 | 为什么重要 |
|---|---|---|---|---|
| 1 | 服务可访问 | `GET /health` | 200 | 服务真的起来了 |
| 2 | 导入成功 | 上传样例文件 | 状态 `completed` | 导入管线通 |
| 3 | 重复导入不产生重复数据 | 同一个文件再传一次 | `already_imported=true` 且消息数不变 | **幂等**，手抖传两次不会变两份 |
| 4 | 能列出会话 | `GET /api/conversations` | ≥1 条 | 读通路 |
| 5 | 能读到原文消息 | `GET .../messages` | ≥4 条 | 正文真的落库了 |
| 6 | 能创建记忆 | `POST /api/memories` | 200 | 记忆域通 |
| 7 | 能绑定来源片段 | `POST /spans` | 200 | 可追溯这条链通 |
| 8 | span 增删进版本史（v2） | 查详情 | `current_version == 2` | **span 变更必须留版本**，这是核心不变式 |
| 9 | 版本史可查 | 查详情 | ≥2 个版本 | 版本没丢 |
| 10 | 来源片段可查 | 查详情 | ≥1 条 | 出处没丢 |
| 11 | 审计史可查 | 查详情 | 有 `span_added` 事件 | **谁动过**有留痕 |
| 12 | 关键词检索能找回原文 | `POST /api/search` keyword | 命中含目标原文 | 关键词链路可用 |
| 13 | 建立语义索引（本地 bge-m3） | `POST /api/index/build` | ≥4 个 chunk | 本机 embedding 真能跑 |
| 14 | 语义检索命中相关原文 | `POST /api/search` semantic | ≥1 条命中 | 向量检索真能搜到 |
| 15 | 扫描候选（不自动认定） | `POST .../scan` | 200 | 打捞可用（**只出候选**） |
| 16 | 人工标记可保存 | `POST .../verdict` | 200 | 判定权在人手里 |
| 17 | 能从候选创建记忆 | `POST .../create-memory` | 200 | 打捞能闭环成正式记忆 |
| 18 | 能导出 | `POST /api/export` | 200 | 出口通 |
| 19 | 能下载导出包 | `GET .../download` | 内容是 zip（PK 头） | 包真的能拿到手 |
| 20 | 能从导出包恢复到全新库 | 调 `restore_from_export.py` | 退出码 0 | **能迁走**是核心价值 |
| 21 | 恢复后关键计数一致 | 对比 manifest 与新库 | 一致 | 迁移没少数据 |
| 22 | 恢复后正文一致 | 抽查正文 | 能取到 | 正文没在迁移中损坏 |
| 23 | zhan 不能导入（403） | zhan 令牌导入 | 403 | 权限矩阵 |
| 24 | zhan 不能删除（403） | zhan 令牌删除 | 403 | AI 不能毁数据 |
| 25 | zhan 不能恢复（403） | zhan 令牌 restore | 403 | 同上 |
| 26 | zhan 不能管令牌（403） | zhan 令牌建令牌 | 403 | **防 AI 给自己提权** |
| 27 | zhan 不能导出（403） | zhan 令牌导出 | 403 | 防批量外泄 |
| 28 | zhan 可以读记忆（200） | zhan 令牌读 | 200 | 证明不是「一律拒绝」，而是**精确**授权 |
| 29 | 无 token 401 | 不带令牌 | 401 | 匿名一律挡在门外 |
| 30 | 安全响应头与不缓存 | 看响应头 | `X-Frame-Options=DENY` 且 `Cache-Control=no-store` | 私内容不被嵌套、不被缓存 |

> 第 13、14 项在 `--skip-semantic` 时会跳过；第 15–17 项若样例区间内没有候选，
> 会以「未通过」报出来（脚本设计如此：不打马虎眼）。

### 15.2 30/30 **能证明**什么

- 在本机（Windows + 项目自带 venv + SQLite 或已配置的数据库）上，
  从导入 → 建记忆 → 版本史 → 检索 → 打捞 → 导出 → 恢复到全新库 → 权限矩阵 → 安全头，
  这条主链路**端到端可用**。
- 关键不变式（幂等、span 变更留版本、审计留痕、权限边界）**有自动化证据**。

### 15.3 30/30 **不能证明**什么（务必写清楚）

- **≠** 生产 VPS 部署已经完成（从未部署过）。
- **≠** Docker / PostgreSQL 生产环境已验证（生产 compose 引用的 Dockerfile **在仓库里不存在**，
  见第 25 章）。
- **≠** 远程 MCP 已实现（第二阶段，未开工）。
- **≠** 检索质量好（脚本只验证「能搜到」，**没有任何质量指标**）。
- **≠** 大规模数据可用（只跑样例小数据）。
- **≠** 安全已达生产级（见 14.2）。

---

## 16. 测试体系

| 类型 | 位置 | 负责什么 | 特点 |
|---|---|---|---|
| 单元测试 / 领域测试 | `backend/tests/test_memory_domain.py`、`test_chunking.py`、`test_models.py` 等 | 单个函数的逻辑正确性（如「版本必须追加」「切块必须能还原原文」） | 快；用内存 SQLite；embedding 用**测试替身** |
| 集成测试 | `backend/tests/test_search.py`、`test_index_payload.py`、`test_memory_api.py` | 跨组件链路（真实 Qdrant 本地模式 + 真实 SQL + 替身 embedding） | 验证链路，不验证语义质量 |
| 权限测试 | `test_auth.py`、`test_memory_api.py::TestRecycleBin` | 权限矩阵（401/403/200） | 用不同角色的令牌逐个试 |
| 加固测试 | `test_hardening.py` | 日志不泄漏、5xx 不装成功、安全头、真实 429、零第三方 embedding | 守红线 |
| 仓库卫生 | `test_repo_hygiene.py` | `.gitignore` 不会误伤源码目录等 | 防「本地绿、clone 后炸」 |
| 前端组件测试 | `frontend/src/**/*.test.tsx`（vitest + Testing Library） | 页面行为（如高亮、二次确认、多文件上传） | 用假的 `fetch`，不连真后端 |
| E2E | `scripts/e2e_t3_check.py`、`e2e_t5_check.py`、`e2e_t6_check.py`、`e2e_t7_check.py` | 真机跑某一阶段的完整链路（含真 bge-m3） | 慢；需要模型权重 |
| 冒烟 | `scripts/smoke_span_update.py`、`smoke_index_concurrency.py` | 真机快速验证某条具体链路 | 需要 `RV_OWNER_TOKEN` |
| 验收 | `scripts/acceptance_check.py` | 第 15 章的 30 项 | 用**新建的**数据库 |

**四种测试的区别（一次讲清）**：
- **mock test（替身测试）**：把外部依赖（如 embedding 模型）换成假的，
  只验证「这段逻辑对不对」。快、稳定，但**不能证明真实模型下也对**。
- **integration test（集成测试）**：真数据库 + 真 Qdrant + 假模型，验证「零件装起来转不转」。
- **E2E（端到端）**：真模型、真数据库、真服务，从用户动作跑到结果。慢，但最接近真实。
- **acceptance test（验收测试）**：把「什么叫做完」逐条自动化。它回答的是
  **「能不能交付」**，而不是「每个函数对不对」。

> 当前数量（2026-10-14 实测）：**后端 169 项通过，前端 47 项通过**。
> 注意 `docs/architecture.md` 里写的「146 / 30」**已过时**。

---

## 17. 当前真实状态矩阵

> 读这张表时请连「限制」一列一起读。状态只描述**代码里能验证到什么程度**。

| 功能 | 状态 | 证据 | 限制 |
|---|---|---|---|
| 仓库骨架 / 工程纪律 | 已实现 | `test_repo_hygiene.py` | — |
| 数据库迁移（Alembic） | 已实现 | 5 个迁移文件 | 只在本机 SQLite 与样例上跑过 |
| ChatGPT 导出导入 | 已实现 | `test_import_pipeline.py` + e2e + 验收第 2/3 项 | 平台导出格式会漂移，需持续适配 |
| JSONL v1 导入 | 已实现 | `test_jsonl_v1_adapter.py` | 同上 |
| 三层幂等 / 隔离区 / 对账 | 已实现 | `test_import_pipeline.py` | — |
| 会话与原文浏览 + 筛选 | 已实现 | 前端组件测试 + 手工 | — |
| 建记忆 + 版本史 + 回滚 | 已实现 | `test_memory_domain.py` + 验收第 6–11 项 | 回滚是「追加」，版本会增长 |
| 来源片段（evidence/context）增删与范围调整 | 已实现 | `test_span_update.py` + 冒烟脚本 | 跨会话的范围需先删再建 |
| 审计（append-only） | 已实现 | 各写入测试 | 只记轻量元信息，不含正文 |
| 认证与权限矩阵 | 已实现 | `test_auth.py` + 验收第 23–29 项 | 只有两个角色，无细粒度授权 |
| 回收站（软删/还原/彻底删） | 已实现（2026-10-14） | `TestRecycleBin` 5 项 + 前端 4 项 | 彻底删除不可恢复 |
| 本地 bge-m3 embedding | 已实现 | e2e + 验收第 13 项 | CPU 上慢；冷启动约 60 秒；权重约 4.3GB |
| 语义检索（Qdrant 本地模式） | 已实现 | 真机 e2e + 验收第 14 项 | **单进程独占**；CPU 吞吐约 17 条消息/秒 |
| 关键词检索 | 已实现 | 验收第 12 项 | **不是 BM25**，是 ILIKE 子串匹配；无相关性排序 |
| 混合检索 + 来源标签 | 已实现 | `test_search.py` + 前端组件测试 | 无重排序 |
| 检索证据可见（高亮 / 命中片段） | 已实现（2026-10-14） | 后端 1 项 + 前端 3 项 | 语义「为什么命中」只给到片段级，不给打分依据 |
| 遗失记忆打捞 | 已实现 | `test_migration_audit.py` + 验收第 15–17 项 | 信号词命中 ≠ 真实记忆；必须人工判 |
| Portable Export / Restore | 已实现 | `test_export.py` + e2e + 验收第 18–22 项 | 不导 3 张表；不含向量；未加密 |
| 加固（脱敏/安全头/限流/error_id） | 已实现 | `test_hardening.py` + 验收第 30 项 | 单进程限流；非生产级 |
| 前端 9 个页面 | 已实现 | 47 项前端测试 | 手工 UI 验证有限 |
| **BM25 关键词排序** | **未实现** | — | 待评测后再决定 |
| **reranker（重排序）** | **未实现、未下载** | — | 待评测证明有需要 |
| **检索评测：known-item 自检索（Hit@K / MRR）** | **已实现（第一版）** | `scripts/eval_known_item.py` + `exports/eval/` | 2026-10-16 跑出结果，见 §6.5 |
| **检索评测：开放式 P@K / Recall（pooled judgment）** | **未实现** | — | 需人工标注，自检索替代不了 |
| **远程 MCP 接口** | **未实现** | — | 第二阶段 |
| **外部 AI 读写记忆** | **未实现** | — | 依赖 MCP |
| **生产 VPS 部署** | **未部署** | — | 第三阶段；且 Dockerfile 缺失 |
| **Docker 实际运行验证** | **未做** | — | 一直用 Qdrant 本地模式 |
| **大规模真实数据验证** | **未做** | — | 现有规模仅样例级 |
| **HTTPS / 登录密码 / 加密备份** | **未实现** | — | 明确列为非目标 |
| **自动备份调度 / 灾难恢复方案** | **未实现** | — | 见 14.2 |

---

## 18. 已知问题 / 技术债 / 限制

### 18.1 运行环境与部署

1. **SQLite 开发模式 vs PostgreSQL 正式环境有差异**：
   代码里 JSON 列用了「PostgreSQL 用 JSONB、其他用 JSON」的变体，行为大体一致，
   但 **SQLite 上从未验证过大规模数据与并发写**。生产前必须在真 PostgreSQL 上跑一遍。
2. **Docker 从未真正运行验证**：`deploy/compose.dev.yml` 与 `compose.prod.yml` 写好了，
   但开发全程用的是 Qdrant **本地文件模式** + SQLite。compose 是否真能起来，未验证。
3. **生产 compose 引用的 Dockerfile 不存在**：`compose.prod.yml` 里
   `build.context=../backend`、`dockerfile: ../docker/Dockerfile.backend`，
   但仓库里**没有任何 Dockerfile**（已确认）。→ 生产部署目前**根本无法构建**。
4. **从未部署到 VPS**：第三阶段目标，未开工。

### 18.2 检索能力

5. **关键词检索不是 BM25**：只有 `ILIKE` 子串匹配 + 时间倒序 + 固定分 0.3，
   **没有相关性排序**。设计文档「附 3」提到 pg_trgm，但代码里**没有** pg_trgm
   （已 grep 确认）。
6. **没有 reranker**，也没有下载任何重排序模型。
7. **没有检索质量评测**：没有人工标注集（gold set），因此「语义检索准不准、全不全」
   **目前没有任何数字支撑**，只有主观感受。
8. **切块策略的限制**：
   - 固定 ≤600 token、按句末标点断句，**块与块之间没有重叠** → 跨越断句边界的内容
     可能被稀释；
   - 单句超长时按字硬切，可能切断语义；
   - 切块规则一旦改变（或 `CHUNK_MAX_TOKENS` 改了），**必须重建索引**，
     否则检索时「重切还原」的片段会对不上。
9. **CPU 上的 bge-m3 性能有限**：实测建索引约 **17 条消息/秒**。
   目标是 2000 万字级别，全量重建预计要跑**数小时**；靠增量索引缓解，但没有加速手段
   （未上 GPU、未做批量优化之外的手段）。
10. **记忆（Memory）本身没有被向量化**：语义检索只覆盖**消息原文**；
    记忆库只能用筛选 + 关键词找（设计文档「附 4」明确列为第一阶段非目标）。

### 18.3 数据与规模

11. **尚未导入真实大规模数据验证**：现有验证都是样例级（数千条消息）。
12. **导出不是完整备份**：`import_quarantine`、`migration_reviews`、`api_tokens`
    三张表**不在导出包里**（见 13.4）。
13. **没有自动备份调度、没有异地副本、没有加密冷备**。
14. **仓库里存在被提交的压缩包产物**：`backend.zip`、`frontend.zip`、
    `backend/exports-e2e-t7/rianvault-export-20261011-024553.zip` 都在 Git 里。
    经抽查，导出包内是**合成测试数据**（会话名含「合成测试会话」），**不含真实私人聊天**，
    但把构建产物/导出产物提交进仓库是坏习惯——尤其将来若真实导出落在类似目录，
    **`.gitignore` 只忽略了名为 `exports/` 的目录**，`exports-e2e-t7/` 这种名字匹配不到。

### 18.4 权限与安全

15. **权限体系很粗**：只有 owner / zhan_mcp 两个角色，做不到按记忆/按平台授权。
16. **没有人类登录密码与会话管理**（见 14.2）。
17. **限流是单进程内存态**，多实例失效。

### 18.5 运行期约束（不是 bug，但必须知道）

18. **Qdrant 本地模式单进程独占**：同一时刻只能有一个后端/脚本持有索引目录。
    表现：第二个实例启动自检告警、检索 503「Qdrant 存储目录被占用」。
19. **后台建索引与预热都已串行化**（2026-10-14 修复），但历史上曾因并发 torch 推理
    **直接段错误崩溃**；任何新增的「后台跑模型」代码都必须遵守同样的串行约束
    （见 `tests/test_auto_index.py`）。
20. **Windows 双 Python 陷阱**：系统 Python 没装项目依赖，所有命令必须走
    `C:\Users\Owner\Projects\RianVault\.venv\Scripts\python.exe`。
21. **测试环境的临时目录**：pytest 默认把临时目录放在系统 temp，某些环境下清理会被
    安全策略拦截而报错。本项目统一用 `--basetemp=./.pytest-tmp`（已加入 `.gitignore`）。

---

## 19. 下一阶段 Roadmap

### Phase 1（已完成）

T0–T10 全部完成并通过一键验收（30/30）：导入管线、记忆域与版本史、权限、
遗失记忆打捞、本地 embedding + 语义检索、Portable Export/Restore、前端 9 页、加固与文档。
2026-10-13/14 追加：来源范围可编辑、检索与原文双边筛选、多文件导入、检索证据可见、回收站。

### Phase 1.5 — 检索评估与优化（**当前位置**）

目标：**先用数字说话，再决定要不要加复杂度**。

1. **Retrieval Evaluation（检索评测）**：建立评测集与脚本。
   - **第一步（零标注）✅ 已完成（2026-10-16）**：**known-item / self-retrieval**
     30 题（答案唯一性已逐条验证），结果 semantic/hybrid = Hit@10 1.00、MRR 1.00，keyword 0.87。
     ⚠️ 这不是 Recall@K（理由见 6.5「术语纪律」）。
   - **第二步（需要人工标注）**：开放式 **Precision@K / Recall@K / nDCG**
     必须走 **pooled relevance judgment**（把关键词/语义/混合的 top-K 混成池子人工判相关）。
     自检索**替代不了**这一步，也**推算不出**这两个指标。
   - **运行约束**：评测脚本要用真实 bge-m3，**必须先把正在运行的后端停掉**
     （Qdrant 本地模式单进程独占文件锁）。
2. **BM25**：视评测结果决定是否替换/补充关键词检索。
3. **可选 reranker**：只有评测显示 top-K 排序确实有问题时，才考虑下载 bge-reranker
   （约 2GB，且 CPU 上推理更贵）。**目前未下载、未实现**。

### Phase 2 — 远程 MCP（**未开工，仅需求目标**）

- 让外部 AI（如 GPT）通过 **MCP（Model Context Protocol，模型上下文协议）** 读写本系统。
- 已确定的方向：MCP **必须调用与 Web API 相同的 service 层**（不允许旁路写库），
  令牌由服务端配置持有，权限沿用 `zhan_mcp`（可读写记忆、检索，**不能删除/导出/管令牌**）。
- 一个**未解的设计问题**（记录在 `docs/dev-log.md`）：AI 通过 MCP 写入记忆时，
  若那段聊天还没导出成 json，就没有 message id 可绑定来源片段——需要「待补来源」机制。
- 以下条目来自**我的长期规划**，仓库内**尚无设计细节文档**，此处只记录需求目标，
  **不代为设计架构**：
  - `get_bootstrap_context`（AI 接入时先给一段背景上下文）
  - recent changes / memory health（最近变更与记忆健康度）
  - Timeline / Turning Points（时间线与转折点）
  - Anchor Lexicon（锚点词表）
  - Model Era / Continuity（模型世代与连续性）
  - External References（外部引用体系）
  - 多平台 adapter（除 ChatGPT / JSONL v1 之外）
  - Memory merge / split（记忆合并与拆分）
  - Entity / Alias Registry（实体与别名登记表）

### Phase 3 — 生产部署（**未开工，仅需求目标**）

- VPS 部署（Docker 私有网络、Caddy 终止 HTTPS、DB/Qdrant 无公网端口）
- OAuth / mTLS（更强的身份认证）
- 加密本地冷备（encrypted local cold mirror）
- 备份自动化与灾难恢复方案
- **前提**：先补上缺失的 Dockerfile，并在真实 PostgreSQL 上完整验证一遍。

---

## 20. 新开发者 / 新 Agent 接手指南

### 20.1 第一天按顺序读什么

1. 本文件（交付书）——先建立整体心智模型。
2. `RIANVAULT_DESIGN_AUDIT.md` —— 原始设计决策与理由（注意：部分内容已被实现超越，
   差异见本文件第 25 章）。
3. `docs/architecture.md` —— 落地后的实际分层与不变式（**注意测试数量已过时**）。
4. `docs/dev-log.md` —— 按时间线的决策、踩坑、产品拍板记录。**必读**，
   里面有「为什么这么做」的一手记录。
5. `backend/app/models/` —— 11 张表，先把数据形状装进脑子。
6. `backend/app/services/` —— 唯一写入路径，业务全在这里。
7. `backend/app/api/routes/` —— 薄路由，看权限怎么挂。

### 20.2 怎么把环境跑起来

```bash
# 一律用仓库自带 venv（系统 Python 没有依赖）
cd C:/Users/Owner/Projects/RianVault
.venv/Scripts/python.exe -m pip install -e "backend[dev]"

cd backend
../.venv/Scripts/python.exe -m alembic upgrade head     # 建表
../.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 令牌（明文只显示一次）
../.venv/Scripts/python.exe scripts/create_token.py --role owner --name laptop

# 前端（另一个终端）
cd frontend && npm install && npm run dev                # http://localhost:5173
```

**怎么验证环境对了**：
```bash
cd C:/Users/Owner/Projects/RianVault
python scripts/acceptance_check.py --skip-semantic       # 约 20 秒，应打印 通过 N / N
```

### 20.3 怎么跑测试

```bash
# 后端（169 项）
cd backend
../.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --basetemp=./.pytest-tmp

# 前端（47 项）
cd frontend && npm run test

# 真机 E2E（需要 bge-m3 权重，慢）
cd backend && ../.venv/Scripts/python.exe ../scripts/e2e_t6_check.py
```

> 跑后端测试时**不要**同时开着后端服务（Qdrant 单进程独占）。

### 20.4 修改代码前必须理解的**不变式（invariants）**

1. PostgreSQL 是唯一真源；Qdrant 可删可重建。
2. **正文绝不进 Qdrant payload**（白名单 + 禁用字段断言 + 测试）。
3. `messages` 导入后正文**不可变**。
4. 记忆的每次改动（含 span 增删、软删、还原、回滚）都**追加新版本**，历史不改写。
5. 审计 append-only；日志**不记**正文、查询词、token。
6. 所有写入走 service 层，先权限后业务。
7. 双时间严格区分（`event_time*` vs `created_at`/`ingested_at`）。
8. 导入必须满足对账等式；失败条目进隔离区，**绝不静默丢**。
9. 「命中信号 ≠ 真实记忆」，打捞**永不自动认定**。
10. 只增不删：临时产物用带时间戳的新名字，不覆盖/清空已存在的文件。

### 20.5 明确禁止（写进代码评审清单）

- ❌ 绕过 service 层直接写库（包括「临时脚本」）。
- ❌ 改写已有的 `memory_versions` 历史（只能追加）。
- ❌ 把正文塞进 Qdrant payload 或日志。
- ❌ 把私人正文写进日志、错误消息、响应体。
- ❌ 自动猜测模型身份（`model_label_source` 只能是 `export` 或 `manual`）。
- ❌ 把失败吞掉装成功（catch 了不记不抛、返回空结果）。
- ❌ 用真实私人数据做 CI fixture / 提交到仓库。
- ❌ 删除已有私人数据（含「顺手清理」旧库文件）。
- ❌ 未经批准执行**破坏性迁移**（drop table / 覆盖数据 / 全量重建）。
- ❌ 在仓库之外的位置写项目日志（工程约定：日志只写在仓库内 `docs/dev-log.md`）。

---

## 21. 故障排查手册

### 服务起不来

- **现象**：uvicorn 报错 / 立刻退出。
- **可能原因**：① 用了系统 Python（没依赖）；② 端口被占；③ 数据库文件被锁。
- **怎么确认**：看启动日志第一行 `database=` 与 `embedding_model=`；
  `netstat -ano | grep :8000` 看谁占着端口。
- **怎么修**：用 `.venv` 的 Python；换端口或停掉旧进程。
- **不能做什么**：不要删数据库文件「重来一次」。

### 数据库连错（写到别的库了）

- **现象**：数据看起来不见了 / 统计数字不对。
- **怎么确认**：启动日志会打印 `database=`（密码已脱敏）。**先看这行**。
- **怎么修**：确认 `.env` 里的 `DATABASE_URL`，重启。
- **不能做什么**：不要靠「再导一次」掩盖问题——先确认连的是哪个库。

### Migration（数据库结构变更）失败

- **现象**：`alembic upgrade head` 报错。
- **怎么确认**：看报错里的迁移版本号；`alembic current` 看停在哪。
- **怎么修**：读对应迁移文件；**不要**手改数据库结构绕过 Alembic。
- **不能做什么**：不要执行 drop/重建来「解决」迁移冲突（属破坏性操作，需 我 批准）。

### 401 Unauthorized

- **现象**：所有接口 401。
- **可能原因**：没设令牌 / 令牌粘错 / 令牌被吊销 / 请求头格式不对。
- **怎么确认**：`/settings` 重新粘一次；`GET /api/auth/me` 看返回。
- **怎么修**：重新生成并粘贴令牌。

### 403 Forbidden

- **现象**：某些操作 403。
- **可能原因**：你用的是 `zhan_mcp` 令牌，而该操作只给 owner（导入/删除/还原/导出/建索引/管令牌）。
- **怎么确认**：`GET /api/auth/me` 看 `role`。
- **怎么修**：换 owner 令牌。**不要**为了让 AI 能用就把权限放开。

### semantic search 503「Qdrant 存储目录被占用」

- **现象**：语义检索 503，或启动日志「启动自检失败：另一个 RianVault 进程正在运行」。
- **可能原因**：**另一个后端进程/脚本正持有索引目录**（本地模式单进程独占）。
- **怎么确认**：`tasklist | grep python`；`netstat -ano | grep :8000`。
- **怎么修**：停掉另一个进程，等它跑完（尤其后台建索引）。
- **不能做什么**：**不要手删 `.lock`**——那可能损坏正在写入的实例。

### bge-m3 权重找不到

- **现象**：`embedding 预热失败` / 语义检索报错说模型加载不了。
- **可能原因**：权重没下载，或 `EMBEDDING_MODEL` 指向的路径不对；
  HuggingFace 直连超时（国内需用镜像并把缓存放在项目内）。
- **怎么修**：按 README 的下载命令重下（用 `hf-mirror.com` + 项目内 `HF_HOME`），
  或把 `EMBEDDING_MODEL` 指向本机目录。
- **不能做什么**：不要用第三方 embedding API「临时顶一下」——这是红线，且与未来是否开放
  MCP 无关（见 14.3：embedding 本地是独立不变式）。

### Qdrant 索引 stale（新导入的内容搜不到）

- **现象**：原文能看到，语义检索搜不到；页面提示「有 N 条还没进索引」。
- **怎么修**：检索页点「补齐语义索引」（作者），或
  `python scripts/rebuild_qdrant.py`。
- **注意**：导入后后台**会自动串行**补索引，给它一点时间。

### Export 失败 / Restore checksum 不通过

- **现象**：导出报错；或恢复时提示校验不符并中止。
- **可能原因**：导出——没有 owner 权限 / 磁盘空间不足；恢复——**包被改过或传坏了**。
- **怎么修**：导出换 owner 令牌重试；恢复**重新拿一份完好的 zip**，
  不要试图「跳过校验」。
- **不能做什么**：**绝不为了恢复成功而绕过 checksum 校验**——校验不符说明数据已经不可信。

### 前端打不开

- **现象**：5173 页面空白 / 接口全红。
- **怎么确认**：后端 `/health` 是否 200；浏览器控制台看是 401 还是网络错误。
- **怎么修**：先确认后端起来了，再去 `/settings` 粘令牌。

### API 500 + `error_id`

- **现象**：响应 `{"detail":"服务器内部错误（已记录 error_id…）","error_id":"…"}`。
- **怎么修**：拿 `error_id` 去**服务端日志**里搜对应那一行。
  需要完整堆栈时把 `DEBUG=true` 打开——**注意这可能让日志夹带 SQL 参数（即正文），
  排查完记得关掉，并谨慎处理该日志文件**。
- **不能做什么**：不要把 500 的响应体贴到任何外部服务去「问 AI」。

---

## 22. 文件地图

### 核心后端（最重要）

| 文件 | 负责什么 |
|---|---|
| `backend/app/main.py` | 应用装配：启动日志（打印连的哪个库）、Qdrant 独占自检、embedding 预热（只起一次）、注册路由与中间件 |
| `backend/app/core/config.py` | 全部配置项（数据库 / Qdrant / embedding / 限流…），环境变量无前缀 |
| `backend/app/core/deps.py` | 认证与权限依赖（`require_any_role` / `require_owner`） |
| `backend/app/core/security.py` | 令牌生成与 SHA-256 哈希 |
| `backend/app/core/middleware.py` | 安全响应头、`no-store`、写操作限流 |
| `backend/app/core/errors.py` | 统一异常处理（500 + `error_id`，不回吐细节） |
| `backend/app/core/logging_setup.py` | 日志与脱敏过滤器（兜底网） |

### 数据模型

| 文件 | 负责什么 |
|---|---|
| `backend/app/models/message.py` | 原始消息（正文不可变、双时间、三重唯一约束） |
| `backend/app/models/conversation.py` | 会话 |
| `backend/app/models/memory.py` | 记忆本体（正文 = 摘要） |
| `backend/app/models/memory_version.py` | 全量快照版本史 |
| `backend/app/models/memory_source_span.py` | 来源片段（evidence / context） |
| `backend/app/models/audit_event.py` | 审计事件（append-only） |
| `backend/app/models/chunk_index.py` | 索引状态登记（哪块已入库、用的哪个模型） |
| `backend/app/models/migration_review.py` | 遗失记忆候选与判定（含 verdict 取值集合） |
| `backend/app/models/api_token.py` | 令牌（只存哈希） |
| `backend/app/models/import_.py`、`import_quarantine.py` | 导入台账与隔离区 |

### 服务层（唯一写入路径）

| 文件 | 负责什么 |
|---|---|
| `backend/app/services/memory_service.py` | 建/改/软删/还原/彻底删/回滚 + 版本快照 |
| `backend/app/services/span_service.py` | 来源片段增删与范围调整（触发新版本） |
| `backend/app/services/audit_service.py` | 写审计、按对象查审计 |
| `backend/app/services/importers/pipeline.py` | 导入编排：识别格式、三层幂等、隔离区、对账 |
| `backend/app/services/importers/chatgpt.py`、`jsonl_v1.py`、`base.py` | 两个适配器与规范结构定义 |
| `backend/app/services/chunking.py` | 按句末标点切块（≤600 token） |
| `backend/app/services/embedding.py` | 本地 embedding 封装（**进程内单例**） |
| `backend/app/services/index_service.py` | 写 Qdrant（**进程内单例**）+ payload 白名单断言 |
| `backend/app/services/search_service.py` | 关键词 / 语义 / 混合检索 + 命中片段回传 |
| `backend/app/services/migration_audit_service.py` | 遗失记忆扫描、判定、从候选建记忆 |
| `backend/app/services/export_service.py` | 打 zip（data + markdown + manifest + checksums） |
| `backend/app/services/restore_service.py` | 从 zip 恢复（先验校验 + 计数对账） |

### API

`backend/app/api/routes/` 下 11 个模块：`health.py`（健康/身份）、`imports.py`、
`conversations.py`、`messages.py`、`memories.py`、`search.py`、`migration_audit.py`、
`export.py`、`audit.py`、`admin_tokens.py`、`stats.py`。全部端点见第 11 章。

### 迁移

`backend/alembic/versions/`：
`0001`（imports/conversations/messages/import_quarantine）、
`0002`（memory domain：memories + versions + spans）、
`0003`（api_tokens）、`0004`（migration_reviews）、`0005`（chunk_index）。
> 注意：编号与设计文档的对应关系不一致，见第 25 章。

### 前端

| 文件 | 负责什么 |
|---|---|
| `frontend/src/App.tsx` | 路由表（9 个页面） |
| `frontend/src/lib/api.ts` | **唯一**通信出口（带令牌、统一抛错） |
| `frontend/src/lib/useAsync.ts` | 异步数据加载 + reload |
| `frontend/src/lib/highlight.tsx` | 检索结果高亮（把查询词包成 `<mark>`） |
| `frontend/src/pages/Search.tsx` | 检索页（三模式 + 筛选 + 标签 + 命中片段） |
| `frontend/src/pages/MemoryLibrary.tsx` | 记忆列表 + **回收站** |
| `frontend/src/pages/MemoryDetail.tsx` | 记忆详情（版本史 / 回滚 / 片段调整 / 删除） |
| `frontend/src/pages/ConversationViewer.tsx` | 原文浏览 + 筛选 + 选段建记忆 |
| `frontend/src/pages/MigrationAudit.tsx` | 遗失记忆打捞 |
| `frontend/src/pages/ImportPage.tsx` / `ExportPage.tsx` | 导入（多文件）/ 导出 |
| `frontend/src/pages/Settings.tsx` | 令牌存放（sessionStorage） |
| `frontend/src/components/Layout.tsx` / `PageShell.tsx` | 导航外壳与页面外壳 |

### 测试

`backend/tests/`（23 个文件，重点：`test_memory_domain.py`、`test_memory_api.py`、
`test_search.py`、`test_index_payload.py`、`test_auth.py`、`test_migration_audit.py`、
`test_export.py`、`test_hardening.py`、`test_auto_index.py`、`test_repo_hygiene.py`、
`embedding_double.py` 是 embedding 测试替身）；
`frontend/src/**/*.test.tsx`（10 个文件）。

### 脚本与运维

| 文件 | 负责什么 |
|---|---|
| `scripts/acceptance_check.py` | 一键验收（30 项，用新建的库） |
| `scripts/create_token.py` | 铸造 / 列出 / 吊销令牌 |
| `scripts/rebuild_qdrant.py` | 检查 / 增量 / 全量重建向量索引 |
| `scripts/restore_from_export.py` | 从导出 zip 恢复到新库 |
| `scripts/e2e_t3/t5/t6/t7_check.py` | 各阶段真机端到端检查 |
| `scripts/smoke_span_update.py`、`smoke_index_concurrency.py` | 真机冒烟 |
| `deploy/compose.dev.yml` / `compose.prod.yml` | 容器编排（**prod 引用的 Dockerfile 缺失**） |
| `docs/ops-runbook.md` | 日常启动、备份恢复、重建索引、故障排查 |

---

## 23. Git / 开发历史

共 **33 个提交**，单分支 `main`，工作区干净。按里程碑列主要提交：

| SHA | 日期 | 功能 | 为什么重要 |
|---|---|---|---|
| `a4cc3a5` | 2026-10-09 | 骨架 + 导入管线 + 记忆域（M1+M2/T3） | 一次把「导入 → 记忆 → 版本 → 审计」主干立起来 |
| `65618aa` | 2026-10-09 | T4 认证与权限矩阵 | 从机制上限制 AI 身份 |
| `873999c` | 2026-10-10 | 修复 `.gitignore` 误伤 `backend/app/models/` | 教训：本地测试全绿 ≠ clone 后能跑 |
| `053821f` | 2026-10-10 | 数据库 URL 单一来源 + 启动打印目标库 | 防「静默迁移到别的库」 |
| `85de24b` | 2026-10-10 | T5 遗失记忆打捞（31 条信号） | 本项目独特能力 |
| `7a02c0a` | 2026-10-10 | T6 本地 embedding + Qdrant + 检索 | 语义检索落地 |
| `0bdc315` | 2026-10-11 | T7 Portable Export 与恢复 | 「随时能迁走」的兑现 |
| `bbc3c70` / `71f34f6` | 2026-10-11/12 | T8 前端骨架 / T9 前端核心页面 | 从命令行走向可用 |
| `2cca33e` | 2026-10-12 | T10 加固与文档 | 日志脱敏、error_id、安全头、限流 |
| `b511ea6` | 2026-10-12 | 一键验收脚本（G.0，30/30） | 「做完了」有客观证据 |
| `d4aace8` / `107ac45` / `9fe50e9` | 2026-10-12 | 全部命令改用 venv；Windows 提示置顶 | 双 Python 坑的系统性解决 |
| `45f01a6` / `0d77fbc` / `538f06a` | 2026-10-12/13 | 我实测反馈的三批体验修复 | 真实使用反馈闭环 |
| `b7f9d29` | 2026-10-13 | 索引统计口径（空正文不算漏索引） | 消除「永远差 426 条」的假警报 |
| `ab8caf6` | 2026-10-13 | 我拍板四项：来源范围可编辑 / 标题可改 / 双边筛选 | 产品设计定案 |
| `f708156` | 2026-10-13 | 修掉两个让语义检索慢/报错的真 bug（**实测提速 26 倍**） | 单例化 embedding 与 Qdrant 客户端 |
| `0a7d29d` | 2026-10-14 | 检索证据可见（高亮 / 命中片段 / 来源标签）+ 修三个并发 bug | 让「为什么命中」可解释；同时修掉会崩进程的并发缺陷 |
| `5a6e24e` | 2026-10-14 | 检索页组件测试 | 给新功能补守门人 |
| `373ecdf` | 2026-10-14 | 回收站（软删 → 还原 / 彻底删，AI 身份无权） | 删除可反悔，且只有 我 能彻底删 |

---

## 24. 最后一节：把 RianVault 讲给一个完全不懂计算机的人

把它想成**一座实体的私人档案馆**：

- **PostgreSQL（数据库）＝ 档案库房本体**。所有原件（聊天原文、你写的记忆卡片、
  每次修改的留档、谁动过什么的登记簿）都锁在这里。这里是**唯一的真相**。
- **Qdrant（向量库）＝ 库房门口的索引卡片柜**。它只写「第几排第几柜可能有你要的东西」。
  卡片柜被烧了，原件还在，重做一批卡片就行；但**原件绝不复印一份放进卡片柜**——
  那样就有了两份真相，而且柜子的防护远不如库房。
- **bge-m3（嵌入模型）＝ 一个不懂人话但很会「比相似度」的图书员**。
  你把一句话给他，他把这句话变成一串数字；意思相近的话，数字也相近。
  他**只在馆内工作**，绝不把你的原件带出馆外（所以是本地运行、绝不调第三方 API）。
  将来若真要给外部 AI 开一个「查阅席位」（远程 MCP），那也是 我 点名指定、限定范围、
  逐次登记，而且**图书员本人依旧不出馆**（见 14.3）。
- **FastAPI（后端）＝ 前台与规章**。所有调阅、归档、修改都要经过前台，
  前台先查你的证件（令牌），再按规章办事（service 层），绝不让你自己进库房翻。
- **React（前端）＝ 你手上的查阅终端**。它只显示、只收集你的操作，自己不存任何东西。
- **Memory（记忆）＝ 你写在卡片上的一条结论**，比如「我偏好安静的环境」。
- **Source Span（来源片段）＝ 卡片背面贴的「出处便签」**，写着「见 XX 会话第 12–15 条」。
  它**不是**把原件抄一遍，而是指回原件——所以永远只有一份真相。
- **Version（版本）＝ 每次改卡片，旧的那张不扔，而是新写一张压在上面**。
  所以你随时能翻回任何一版；后悔了也只是「照着旧版再写一张新的」，历史从不被撕掉。
- **Audit（审计）＝ 登记簿**：谁、什么时候、动了哪张卡片。只记动作，不抄内容。
- **Export（导出）＝ 把整个档案馆复印打包成一个箱子**，里面既有机器能读的清单，
  也有不装软件就能读的册子。哪天房子没了，凭这个箱子能在别处重建一座。
  （但箱子**没有锁**，也**没有复印隔离间和待判定抽屉**——它是迁移包，不是保险柜。）
- **MCP（未来）＝ 给外面的研究员开一个受控的窗口**：他可以帮你整理卡片、查资料，
  但**不能撕卡片、不能搬走整馆、不能自己配钥匙**。这个窗口还没开。

如果有人问「为什么这么麻烦？」，一句话回答：

> 因为这些东西**不可再生**，而且**只属于一个人**。所以宁可慢一点、笨一点，
> 也不能有第二份真相、不能有无法追溯的改动、不能让它们离开自己的房子。

---

## 25. 交付审计发现 / Handover Findings（文档 vs 实现的差异）

> 本节是撰写本交付书时**实际审查发现的差异**。以**代码为现状**。
> 本轮**只记录，不修改**（不碰业务代码，也不擅自改设计文档）。

### 25.1 设计文档与实现不一致

| # | 设计文档说法 | 实际实现 | 影响 |
|---|---|---|---|
| 1 | ADR 6：「删除只有 soft delete；**硬删除不在第一阶段提供任何入口**」 | 已实现 `DELETE /api/memories/{id}/purge`（仅作者本人，物理删记忆+版本+span，留 `memory_purged` 审计） | 这是**后来经 我 要求新增**的功能（回收站需求）。设计文档未同步 |
| 2 | ADR 7：「Qdrant collection 名含模型 slug（如 `rianvault_chunks_bge-m3`），换模型 = 新 collection + 别名切换」 | `config.qdrant_collection = "rianvault_chunks"`，**不含模型 slug**；换模型靠 `chunk_index.embedding_model` 判断并 **rebuild 同一 collection** | 换模型策略不同（重建而非切别名），功能上等价但实现不同 |
| 3 | T1–T6 的迁移编号：memory 域 = 0003、api_tokens = 0004、migration_reviews = 0005、chunks = 0006 | 实际：memory 域 = **0002**、api_tokens = **0003**、migration_reviews = **0004**、chunk_index = **0005**；`import_quarantine` 在 0001 内 | 只是编号不同，**最终表结构一致**；但照文档找迁移会找错文件 |
| 4 | 「附 3 技术栈」提到 PostgreSQL 启用 **pg_trgm** | 代码中**没有任何** pg_trgm（全库 grep 为空）；关键词检索是 `ILIKE` | 关键词检索**没有**相关性排序能力 |
| 5 | 附 2 导出布局列出 `imports.jsonl`、`chunks.jsonl`（「可选」） | 两者**都在**，但**缺少** `import_quarantine`、`migration_reviews`、`api_tokens` | 导出**不是**全库备份（见 13.4） |

### 25.2 文档内容已过时

| # | 位置 | 问题 |
|---|---|---|
| 6 | `docs/architecture.md`「开发环境」 | 写的是「pytest **146** 项」「vitest **30** 项」，实测是 **169 / 47** |
| 7 | `README.md`「语义索引」 | 写「不加载 2GB 权重」，实际 bge-m3 权重约 **4.3GB** |

### 25.3 新增发现的技术债 / 风险

| # | 发现 | 严重性 | 说明 |
|---|---|---|---|
| 8 | **`deploy/compose.prod.yml` 引用的 Dockerfile 不存在**：`dockerfile: ../docker/Dockerfile.backend`，仓库内无任何 Dockerfile | **高** | 生产部署**当前无法构建**；Phase 3 前必须先补 |
| 9 | **Git 里提交了压缩包产物**：`backend.zip`、`frontend.zip`、`backend/exports-e2e-t7/rianvault-export-20261011-024553.zip` | 中（潜在风险高） | 抽查确认导出包内是**合成测试数据**，无真实私人聊天；但 `.gitignore` 只忽略名为 `exports/` 的目录，`exports-e2e-t7/` 匹配不到 → 将来真实导出若落在同类目录会被提交 |
| 10 | **Docker 从未实际运行验证**：全程用 Qdrant 本地模式 + SQLite | 中 | compose 能否真正起来未经验证 |
| 11 | ~~检索质量无任何量化证据~~ **已部分解决**：2026-10-16 完成 known-item 自检索第一版（semantic/hybrid Hit@10 = 1.00，keyword 0.87，见 §6.5）。仍缺：开放式 P@K / Recall（pooled judgment）与更大查询集 | ~~中~~ 低 | known-item 只证明管线零退化；真实检索体验仍需开放评测 |
| 12 | Qdrant 本地模式**单进程独占**：跑评测/重建脚本必须停服务 | 中（运行约束） | 已知但必须在文档中明确，否则新 Agent 会踩 |
| 13 | 切块规则与 `CHUNK_MAX_TOKENS` 改变后**必须重建索引** | 中 | 否则「重切还原」的命中片段与库内块对不上 |
| 14 | 大规模真实数据（2000 万字级）**从未验证**；CPU 建索引约 17 条消息/秒 | 中 | 全量重建预计数小时 |

### 25.4 本轮工作边界声明

- **新建**：`docs/RIANVAULT_HANDOVER.md`（本文件）。
- **修改**：`README.md`（仅在顶部增加交付书链接）。
- **未修改**：任何业务代码、测试、配置、迁移、设计文档。
- 上述所有差异与风险**只记录，未修复**；如需处理，请 我 明确批准后单独开工。

