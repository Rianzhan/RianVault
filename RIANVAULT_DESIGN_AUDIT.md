# RianVault 设计审计与第一阶段方案

> Phase 0 交付物 · 2026-10-09 · 状态：**待批准**
> 本轮只做审计与设计，未编写、未修改任何项目代码。

---

## 0. 本轮范围

- 完成当前仓库审计（A）、架构方案（B）、Schema 方案（C）、导入策略（D）、检索策略（E）、安全威胁审查（F）、第一阶段实施计划（G）。
- 本文档不含代码实现。开工以「批准开工」的确认为准。

---

## A. 当前仓库审计

### A.1 审计方法与覆盖范围

实际执行过的检查（非推测）：

1. `ls -la` 当前工作区 `C:\Users\Owner\WorkBuddy\2026-10-09-18-27-25\`（含隐藏文件）
2. `ls -la` 父目录 `C:\Users\Owner\WorkBuddy\`（排查兄弟项目）
3. `find` 在 `Desktop` / `Documents` / `WorkBuddy` 三个位置（深度 3）搜索 `*rianvault*` / `*rian-vault*` / `*rian_vault*`
4. 抽查兄弟会话目录 `2026-10-09-15-23-47`（内容为另一项目 snowhome「雪山小家」Expo 应用，与 RianVault 无关）与 `Claw`（空目录）

### A.2 结论：绿地项目（Greenfield）

| 审计项 | 结果 |
|---|---|
| 当前目录结构 | **完全为空**：无 `.git`、无代码、无配置、无隐藏文件 |
| 当前技术栈 | 不存在。无既有栈需要沿用，可自由采用推荐栈 |
| 已存在功能 | 无 |
| 可复用代码 | 无（兄弟目录的 snowhome 是 Expo/React Native 项目，技术栈与目标均不同，不复用） |
| 与本需求冲突的既有实现 | 无 |
| 既有数据 / 数据库 | 无 |

含义：没有历史包袱，但**第一阶段计划中的每一项都是新建**，工作量评估不应对标「改造」，应对标「从零奠基」。绿地的好处是可以从第一天就把真源/版本/审计/权限边界做正确，不需要迁移烂摊子。

### A.3 当前安全问题

无仓库即无现存泄漏面。需要预防性纪律（开工第一天就建立，而不是事后补）：

- `.gitignore` 首批提交就就位：`.env*`（除 `.env.example`）、`exports/`、`backups/`、`*.sqlite`、模型缓存、`node_modules`
- `.env.example` 只放键名和占位符，永不放真实值
- pre-commit 挂 `gitleaks` 防 secret 入库；GitHub 仓库**私有**
- 测试 fixtures 一律用合成数据，禁止把真实聊天导出文件提交进仓库

### A.4 当前数据迁移风险

- 无历史数据库，无旧 schema 迁移风险。
- 真实风险在两个外部源头：
  1. **ChatGPT export schema 漂移**：conversations.json 结构随时间变化，不同年份的导出字段不同 → 靠 D 节的「未知字段不静默丢弃 + 对账不变式 + raw_metadata 保底」解决。
  2. **2026-07 ~ 2026-10 遗失记忆窗口**：旧平台记忆写入可能大量失败 → 靠 MVP-E 的 Migration Audit 工具人工打捞，不允许关键词自动认定为记忆。

### A.5 需要注意的一点

当前工作区目录名形如会话临时目录（`2026-10-09-18-27-25`）。**请确认这里就是 RianVault 的永久仓库根**；若另有打算（例如独立磁盘目录），批准开工时一并告知，T0 会在确认的位置 `git init`。

---

## B. 架构方案

### B.1 数据流图

```
                        ┌──────────────────┐   ┌──────────────────┐
                        │  Browser UI       │   │  MCP 客户端       │
                        │  React+Vite+TS    │   │  （第二阶段）      │
                        └────────┬─────────┘   └────────┬─────────┘
                                 │ HTTPS                │ MCP 协议
┌──────────────────┐             │                      │
│ 导入源            │             ▼                      ▼
│ ChatGPT export   │     ┌─────────────────────────────────────┐
│ JSONL v1 / 未来   │────▶│  API 服务层（FastAPI）                │
│ Omate/ArenaAI 等  │     │  唯一写入路径：                        │
└──────────────────┘     │  权限校验 → 业务校验 → 版本史 → 审计     │
                         └───────┬──────────────┬──────────────┘
                                 │ 读写（唯一入口） │ 查询 chunk_id
                                 ▼              │ 后回这里取原文
              ┌──────────────────────────────┐  │
              │  PostgreSQL（权威真源）         │◀─┘
              │  conversations / messages /   │
              │  memories / versions / spans  │
              │  / audit / chunks / imports   │
              └──────┬───────────────┬───────┘
                     │ 读取消息        │ 读取全量表
                     ▼               ▼
        ┌──────────────────┐  ┌──────────────────┐
        │ Chunk 切分        │  │ Portable Export  │
        │ （消息边界对齐）    │  │ ZIP（可迁移备份）  │
        └────────┬─────────┘  └──────────────────┘
                 ▼
        ┌──────────────────┐
        │ 本地 Embedding    │   sentence-transformers
        │ （可替换 Provider）│   模型权重一次性下载后离线运行
        └────────┬─────────┘
                 ▼  向量 + 白名单 metadata（绝不含正文）
        ┌──────────────────┐
        │ Qdrant            │   可重建派生索引
        │ （语义检索索引）    │   全删后可从 PostgreSQL 重建
        └──────────────────┘
```

生产形态（第三阶段）：以上全部跑在同一 VPS 的 Docker 私有网络内，Caddy 终止 HTTPS，PostgreSQL / Qdrant 不发布任何公网端口。

### B.2 组件职责与数据真源

| 组件 | 职责 | 不是什么 |
|---|---|---|
| Browser UI | 浏览、选段、创建/编辑记忆、审计、导入导出；只通过 HTTP API 操作 | 不直连数据库 |
| API 服务层（FastAPI） | **唯一写入路径**。所有写入（UI、MCP、Importer）都经过同一组 service 函数：权限 → 校验 → 版本快照 → 审计 → 提交 | 不允许任何旁路直写数据库的脚本/接口 |
| PostgreSQL | **唯一权威真源**：原文、衍生记忆、版本、来源、审计、chunk 记录、导入台账 | 不依赖 Qdrant 才能回答的问题，都不放 Qdrant |
| 本地 Embedding Provider | 把 chunk 文本变成向量；可替换实现；模型名只出现在配置 | 禁止第三方 embedding API |
| Qdrant | 语义检索**索引**：向量 + 白名单 metadata | **不是数据源**。整体删除后可由 `rebuild` 从 PG 全量重建 |
| Portable Export | 人类可读 + 机器可读的迁移备份（zip） | 不是唯一恢复手段（第三阶段加 PG dump / Qdrant snapshot / 加密全量备份） |

**数据真源原则**：任何问题的最终答案以 PostgreSQL 为准。Qdrant 的每个 point 只有 `chunk_id` 和非敏感过滤字段；检索到 `chunk_id` 后回 PG 取原文和上下文。

### B.3 关键架构决策（ADR 摘要）

1. **版本史用全量快照而非 diff**：`memory_versions.snapshot` 保存该版本的完整 memory 字段 + 当时生效的 spans 列表。恢复快照 = 追加一个新版本（历史永不被改写）。理由：diff 链任何一环损坏即全链不可恢复；memory 正文是 KB 级，快照成本可忽略；消息原文不进快照（messages 不可变，无重复存储）。
2. **span 增删也触发新版本**：需求示例「v3：湛补充 source span」直接成为系统行为——任何 memory 本体或来源变化都产生版本。
3. **messages 不可变**：导入后消息正文永不 UPDATE；模型标签手工更正走单独字段 + 审计事件，不改原文。
4. **单一写入路径**：MCP（第二阶段）调用与 Web API 相同的 service 层函数，从机制上杜绝「绕开版本史和审计的另一套写入」。
5. **搜索走 POST**：查询词放请求体而非 URL query，避免 access log / 代理日志记录查询全文。
6. **删除只有 soft delete**：`deleted_at` 标记；硬删除不在第一阶段提供任何入口。
7. **embedding collection 与模型绑定**：Qdrant collection 名含模型 slug（如 `rianvault_chunks_bge-m3`），换模型 = 新建 collection + 后台重建 + 别名切换，不污染旧索引。

---

## C. Schema 方案（第一阶段）

### C.1 表清单与关系

```
imports 1───n conversations 1───n messages
                                  messages n───1 conversations
memories 1───n memory_versions
memories 1───n memory_source_spans n───1 conversations
memory_source_spans：start_message_id / end_message_id ──▶ messages
audit_events（独立，指向任意 target）
chunks n───1 conversations（canonical chunk 记录，Qdrant 重建依据）
migration_reviews 1───1 messages（信号消息）+ n───1 memories（打捞产物，可空）
api_tokens（认证主体：owner / zhan_mcp）
```

### C.2 核心表字段

**imports** — 导入台账（幂等第一层）
`id` uuid pk · `source_type` text（`chatgpt_export` / `jsonl_v1` / …）· `original_filename` text · `checksum_sha256` text **unique** · `file_size_bytes` bigint · `adapter_version` text · `status` text（`running` / `completed` / `failed`）· `stats` jsonb（conversations/messages/imported/duplicates/quarantined 计数）· `warnings` jsonb（未识别字段清单等）· `error` text null · `created_at` / `finished_at` timestamptz

**import_quarantine** — 解析失败条目隔离区（不静默丢）
`id` uuid pk · `import_id` fk · `raw_payload` jsonb · `reason` text · `created_at`

**conversations**
`id` uuid pk · `source_platform` text · `source_conversation_id` text null · `title` text null · `started_at` timestamptz null（首条消息源时间）· `import_id` fk · `raw_metadata` jsonb（导出中未被映射的字段原样保留）· `created_at`
唯一约束：`(source_platform, source_conversation_id)`（源 id 缺失时退化用 `dedup_hash` text unique）

**messages** — 原文，**导入后不可变**
`id` uuid pk · `conversation_id` fk · `source_message_id` text null · `parent_source_message_id` text null（ChatGPT 树结构）· `sort_order` int（主时间线序）· `role` text（`user`/`assistant`/`system`/`tool`/`unknown`）· `content_text` text null（规范化纯文本）· `content_kind` text（`text`/`multimodal`/`code`/`other`）· `content_raw` jsonb（原始 content 结构）· `event_time` timestamptz null（**事情发生时间**，来自源）· `event_time_raw` text null（源时间字符串原样）· `ingested_at` timestamptz（**导入时间**）· `source_model` text null（如 `gpt-4o`）· `source_model_note` text null（如 `manual_by_Owner`）· `model_label_source` text null（`export`/`manual`；第一阶段**不做系统猜测**）· `import_id` fk · `raw_metadata` jsonb · `dedup_hash` text（无源 id 时的确定性内容哈希）
唯一约束：`(conversation_id, source_message_id)`（源 id 非空时）；`(conversation_id, dedup_hash)` 兜底

**memories**
`id` uuid pk · `title` text null · `body` text not null · `memory_type` text（`fact`/`preference`/`event`/`relationship`/`goal`/`note`，可扩展）· `status` text（`draft`/`active`/`archived`/`deleted`）· `importance` smallint null · `event_time_start` date null · `event_time_end` date null（**事情发生日期**，用 `date` 而非 timestamptz：粒度到天，避免时区假精确，天然区分「2025 发生的事 / 2026 导入」）· `tags` text[] · `metadata` jsonb · `current_version` int · `created_by_actor` text（`owner`/`zhan_mcp`/`importer`/`system`）· `created_by_model` text null · `created_at` / `updated_at` timestamptz · `deleted_at` timestamptz null（soft delete）

**memory_versions** — append-only
`id` uuid pk · `memory_id` fk · `version_number` int · `snapshot` jsonb（**全量**：title/body/type/status/importance/event_time_start/end/tags/metadata + 当时生效 spans 列表）· `edited_by_actor` text · `edited_by_model` text null · `edit_reason` text null · `created_at` timestamptz
唯一约束：`(memory_id, version_number)`；无 UPDATE/DELETE 入口

**memory_source_spans** — 当前态 + 软移除（历史在 versions 快照与 audit 中）
`id` uuid pk · `memory_id` fk · `conversation_id` fk · `start_message_id` fk · `end_message_id` fk · `span_type` text（`evidence`/`context`）· `note` text null · `sort_order` int · `created_at` timestamptz · `created_by_actor` text · `created_by_model` text null · `removed_at` timestamptz null · `removed_by_actor` text null
校验：start/end 必须属于 `conversation_id` 且 `sort_order(start) <= sort_order(end)`；一条 memory 可有多条、可不连续、可跨 conversation

**audit_events** — append-only
`id` uuid pk · `event_type` text（`import_completed`/`memory_created`/`memory_updated`/`memory_deleted`/`span_added`/`span_removed`/`version_restored`/`model_label_corrected`/`export_created`/`token_created`…）· `actor` text · `actor_model` text null · `target_type` text · `target_id` uuid · `detail` jsonb（轻量元信息：版本号、span id、计数等；**不记正文**）· `created_at` timestamptz
应用层无 UPDATE/DELETE；DB 角色层撤销写权限（第三阶段加固）

**chunks** — canonical chunk 记录（Qdrant 的重建依据）
`id` uuid pk（= Qdrant point id）· `conversation_id` fk · `start_message_id` fk · `end_message_id` fk · `text_hash` text（内容指纹，源消息不可变故稳定）· `token_count` int · `embedding_model` text · `embedding_status` text（`pending`/`indexed`/`stale`）· `embedded_at` timestamptz null · `created_at`

**migration_reviews** — 遗失记忆打捞（MVP-E）
`id` uuid pk · `signal_message_id` fk · `scan_from` date · `scan_to` date · `matched_signal` text · `verdict` text（`unreviewed`/`successful_write`/`failed_write`/`retry_success`/`edit`/`delete`/`uncertain`/`ignore`）· `reviewed_by` text null · `reviewed_at` timestamptz null · `context_start_message_id` fk null · `context_end_message_id` fk null · `linked_memory_id` fk null · `note` text null

**api_tokens**
`id` uuid pk · `name` text · `role` text（`owner`/`zhan_mcp`）· `token_hash` text unique（SHA-256，高熵 token 足够）· `created_at` / `revoked_at` · `last_used_at` null

### C.3 索引与约束（要点）

- `messages(conversation_id, sort_order)`；`messages(event_time)`；`messages(source_model)`；`messages(content_text)` 的 trigram（`pg_trgm` GIN，供关键词 ILIKE 兜底）
- `memory_source_spans(memory_id)`、`(conversation_id)`、`(start_message_id)`、`(end_message_id)`
- `memory_versions(memory_id, version_number desc)`
- `audit_events(created_at)`、`(target_type, target_id)`
- `chunks(embedding_status)`；`migration_reviews(verdict)`
- 所有唯一约束见 C.2；迁移必须可 `downgrade` 回滚

### C.4 不变式（写进测试，不靠自觉）

1. `imports.stats` 满足 `parsed == imported + duplicates + quarantined`，否则 import 置 `failed`
2. 任何 memory 变更后，`memory_versions` 行数 == `memories.current_version`
3. `memory_source_spans` 的 start/end 消息与 `conversation_id` 一致且有序（service 层校验 + 测试）
4. `audit_events` 与 `memory_versions` 表对应用层只插不改
5. messages 正文列不出现在任何 UPDATE 语句中（代码审查 + 测试双保险）

---

## D. 导入策略

### D.1 Adapter 架构

```
ImporterAdapter（协议）
  ├─ detect(file_meta, sample) -> bool
  ├─ parse(file) -> Iterator[CanonicalConversation]
  │     CanonicalConversation = { source_conversation_id, title, raw_metadata,
  │       messages: [ { source_message_id, parent_id, role, content_text,
  │                     content_kind, content_raw, event_time, event_time_raw,
  │                     source_model, raw_metadata } ] }
  └─ name / version
实现：ChatGPTExportAdapter（第一阶段）、JsonlV1Adapter（第一阶段）、
     OmateAdapter / ArenaAIAdapter / CakumiAdapter（以后各自独立文件）
```

核心数据模型只认 Canonical 结构，ChatGPT 格式细节**不泄漏进核心模型**。新增来源 = 新增 adapter 文件，不改 schema。

### D.2 ChatGPT export 解析细则

- `conversations.json` 的 `mapping` 是**树**（parent/children）：以 `current_node` 回溯的当前分支为主时间线生成 `sort_order`；`parent_source_message_id` 保留树关系；整棵 mapping 的关键字段进 `raw_metadata`
- `source_conversation_id` ← conversation `id`；`source_message_id` ← node `message.id`
- 模型标签：assistant 消息取 `message.metadata.model_slug` → `source_model`，`model_label_source = export`；取不到则留空（不猜）
- 内容：`content.parts` 按 `content_type` 提取纯文本进 `content_text`（text / multimodal_text 等）；原始结构完整进 `content_raw`；无法提取文本的类型 `content_text = null` + warning（不丢）
- 时间：`create_time`（epoch 秒）→ `event_time`，原始值进 `event_time_raw`
- 源 id 缺失（旧导出）：合成确定性 id `sha256(conversation_id + parent_id + role + content_text)`，保证重复导入得到同一哈希 → 幂等

### D.3 幂等与去重（三层）

1. **文件层**：`imports.checksum_sha256` unique。同一文件重复导入 → 返回已有 import（`status=already_imported`），不产生新数据
2. **实体层**：conversations / messages 的唯一约束（C.2），数据库级别防重
3. **内容层**：源 id 缺失时用 `dedup_hash` 兜底

同一文件改过一个字节再导 = 新 import 行，但实体层去重保证不产生重复会话/消息，stats 如实记 duplicates。

### D.4 容错与对账（绝不静默丢数据）

- 每个 conversation 一个事务；单条消息解析失败 → 原始 payload 进 `import_quarantine` + 计数 + 继续
- 文件级失败 → import `status=failed` + `error`，**禁止吞异常后显示成功**
- 完成时校验对账不变式 `parsed == imported + duplicates + quarantined`，不满足即 `failed`
- import 报告（`GET /api/imports/{id}`）必须展示：计数、未识别字段 warnings、quarantine 列表与原因
- 未知/变化的导出 schema：未映射字段一律进 `raw_metadata`，adapter 按版本号记录，升级 adapter 后可重跑补齐

### D.5 规范化 JSONL v1（`rianvault-jsonl-v1`）

每行一个 JSON 对象，`type` 区分：

```json
{"type":"conversation","format":"rianvault-jsonl-v1","platform":"omate","conversation_id":"...","title":"...","extra":{}}
{"type":"message","conversation_id":"...","message_id":"...","parent_id":null,"role":"assistant","text":"...","timestamp":"2025-03-14T21:02:11+08:00","model":"gpt-4o","model_note":"manual_by_Owner","extra":{}}
```

规则：`extra` 原样进 `raw_metadata`；缺 `message_id` 走内容哈希；时间必须 ISO8601 带时区（缺时区进 warning 并按 UTC 存，原始字符串保留）。完整规范开工后落在 `docs/import-format-v1.md`。

---

## E. 检索策略

### E.1 Chunk 策略

- **边界**：绝不把一条消息切成两半（除非单条消息超 `chunk_max_tokens`，此时按段落 → 句子边界切，允许 10–15% 重叠）
- **合并**：相邻短消息按对话轮次合并，目标 300–600 tokens（可配置），同一 chunk 不跨 conversation
- **排除**：`system` / 空文本消息默认不进 chunk（可配置）
- **canonical**：每个 chunk 在 PG `chunks` 表有记录（消息范围 + text_hash + token_count + embedding_model + status）；chunk 文本不重复存储，由消息范围现取（messages 不可变，导出文本稳定）

### E.2 Embedding 抽象与模型

```python
class EmbeddingProvider(Protocol):
    name: str
    dimension: int
    def embed(self, texts: list[str]) -> list[list[float]]: ...
```

- 默认实现 `SentenceTransformersProvider`：默认模型 `BAAI/bge-m3`（中英双语效果好、长文本友好）；低配机器可配置切换 `paraphrase-multilingual-MiniLM-L12-v2`；**模型名只出现在配置**（`EMBEDDING_MODEL`），业务代码零硬编码
- 权重一次性下载后完全离线运行，语料不出本机/VPS；Docker 镜像构建期预下载
- 测试用 `DeterministicStubProvider`（哈希伪向量），CI 不下载真模型、不联网；真模型集成测试打 `slow` 标记
- **禁止** OpenAI / Cohere / Voyage 等第三方 embedding API——以依赖白名单 + 代码审查 +（第三阶段）VPS 出站规则三层保证
- 换模型 = 新 collection + 后台重建 + 读切换（B.3-7）

### E.3 Qdrant 索引与 metadata 白名单

point id = `chunks.id`；payload 白名单：

| 字段 | 用途 | 敏感性 |
|---|---|---|
| `chunk_id` | 回 PG 取原文 | 无 |
| `conversation_id` | 过滤 | 低（内部 uuid） |
| `source_platform` / `source_model` | 过滤 | 低（枚举值） |
| `event_time_start` / `event_time_end` | 日期过滤 | 低（日期） |

**正文、标题、tag 一律不进 payload。** 提供 `QDRANT_MINIMAL_PAYLOAD=true` 时只留 `chunk_id`，过滤全部回 PG（更慢但更保守，威胁模型变化时可切换）。

### E.4 查询、过滤与回原文

`POST /api/search/semantic`（请求体：query + filters{date_from,date_to,platform,model,conversation_id} + limit）：

1. 本地 embed query → Qdrant 带过滤检索 → chunk_id 列表
2. 回 PG join chunks/messages/conversations 取原文、定位 sort_order
3. 返回：命中片段 + `conversation_id` + `message_id` + 前后窗口指针，前端可一键跳到 Conversation Viewer 对应位置
`POST /api/search/keyword`：PG `ILIKE` + `pg_trgm` 索引（中文子串可用），同样的回原文结构

### E.5 Hybrid 升级路径（预留，不在第一阶段）

中文全文检索若要升级：评估 `pg_jieba`/`zhparser` 扩展、ParadeDB `pg_search`，或 Qdrant sparse（BM25）与 dense 双路 RRF 融合。检索接口从第一天就返回统一结构，未来加一路召回不改 API 形状。第一阶段若中文分词引入明显复杂度，则按批准范围只做 semantic + 关键词兜底，并在验收文档注明。

---

## F. 安全威胁审查

| # | 威胁 | 对策（阶段） |
|---|---|---|
| 1 | VPS 被扫描/爆破 | 仅开 22/80/443；UFW 默认拒绝；SSH 仅密钥、禁 root 直登、禁密码登录；fail2ban；PG/Qdrant 无公网端口（P3） |
| 2 | API token 泄漏 | token 只存 SHA-256 哈希；分角色（owner/zhan_mcp）；可吊销（`revoked_at`）；`.env` 不进 Git；gitleaks 门禁（P1）；后续 OAuth + 短期令牌（P2/P3） |
| 3 | 数据库误暴露公网 | prod compose 中 db/qdrant **不写 `ports:`**；CI 有「compose 安全断言」测试解析 compose 文件强制此规则；上线后外部 nmap 验证写进运维手册（P1 建测试，P3 执行验证） |
| 4 | Git 泄漏 secret | `.gitignore` 首批提交；`.env.example` 仅占位符；gitleaks pre-commit + CI；仓库私有（P1） |
| 5 | 日志泄漏正文/查询 | 结构化日志字段白名单：只记 id、计数、状态码；**不记**消息正文、查询全文、token、Authorization 头；搜索走 POST 避免 URL 入 access log；审计 detail 不含正文（P1） |
| 6 | 恶意/损坏 import | 文件大小上限；解压防 zip-slip；解析器纯函数无执行；单条失败进 quarantine 不中断；对账不变式失败即 failed；事务隔离（P1） |
| 7 | 误删 | 全系统只有 soft delete；zhan_mcp 无删除权限；删除必有 audit event + 可 restore 的版本快照；破坏性操作前提示先导出（P1）；定期备份与恢复演练（P3） |
| 8 | 错误模型标签 | 第一阶段**系统不做任何模型猜测**；`model_label_source` 区分 `export`/`manual`；手工更正走专用端点 + `model_label_corrected` 审计（含前后值）（P1） |
| 9 | 备份不可恢复 | 第一阶段就把「导出 → 全新库恢复 → 计数一致」做成自动化 round-trip 测试，而不是「应该能恢复」；manifest + checksums 防静默损坏（P1）；3-2-1 策略与恢复演练文档（P3） |

**加密立场**：第一阶段不做 application-level 加密。任何字段级/全库加密方案必须先提交威胁模型、对检索的影响分析、密钥管理设计，经批准再实施。不自造加密协议。

---

## G. 第一阶段实施计划（TDD）

### G.0 阶段总完成标准（Definition of Done）

1. 真实（或脱敏）ChatGPT 导出文件导入成功，重复导入零重复数据
2. 能从搜索/浏览找回任意原文并定位到会话位置
3. 能创建带 evidence/context 来源的 memory，编辑有完整版本史，span 增删有版本和审计
4. Migration Audit 能对 2026-07-01 ~ 2026-10-31 扫描、人工标记、从候选创建 memory
5. 一键导出 zip，且在干净环境 `restore_from_export` 重建后关键计数一致（自动化测试）
6. zhan_mcp token 权限矩阵测试全绿；全测试套件绿；零第三方 embedding 调用

### T0 — 仓库骨架与工程纪律（migration：无）

- 新建：`README.md`、`.gitignore`、`.env.example`、`.pre-commit-config.yaml`（gitleaks + ruff）、`backend/pyproject.toml`、`deploy/compose.dev.yml`（PG+Qdrant 绑 127.0.0.1）、`.github/workflows/ci.yml`、`frontend/`（Vite+React+TS 脚手架）、`docs/`
- 对外接口：无（`GET /health` 占位）
- 先写失败测试：`test_smoke`（app 可导入）；`test_compose_security`（解析 compose 断言 db/qdrant 无公网 `ports`）
- 完成标准：`docker compose -f deploy/compose.dev.yml up -d` 成功；`pytest -q` 绿；`npm run dev` 可开；pre-commit 生效
- 验证：`pytest -q`；`docker compose config`

### T1 — DB 基座 + imports/conversations/messages（migration：0001）

- 新建：`backend/app/core/config.py`、`db/session.py`、`models/{import_,conversation,message}.py`、`alembic/versions/0001_*`
- 对外接口：无（内部模型）
- 先写失败测试：会话/消息唯一约束去重；`event_time` 与 `ingested_at` 分别落库；`raw_metadata` 原样保留；`alembic downgrade base` 可回滚
- 完成标准：迁移 up/down/up 通过，测试绿
- 验证：`alembic upgrade head && alembic downgrade base && alembic upgrade head && pytest -q`

### T2 — ChatGPT + JSONL v1 adapter 与导入管线（migration：0002，import_quarantine）

- 新建：`services/importers/{base,chatgpt,jsonl_v1,pipeline}.py`、`api/imports.py`、`tests/fixtures/`（合成数据）
- 对外接口：`POST /api/imports`（multipart，adapter 自动识别）、`GET /api/imports`、`GET /api/imports/{id}`（报告）
- 先写失败测试：同文件重复导入幂等；缺源 id 时确定性哈希去重；树结构按 current_node 线性化且 parent 保留；未识别字段进 raw_metadata + warnings；坏条目进 quarantine 且对账平衡；坏文件 failed 不装成功
- 完成标准：合成 fixture 全绿；手工导入脱敏样例可见会话与消息
- 验证：`pytest -k import -q`；`curl -F file=@sample.json :8000/api/imports`

### T3 — Memory 域 + 版本史 + spans + 审计（migration：0003）

- 新建：`models/{memory,memory_version,memory_source_span,audit_event}.py`、`services/{memory_service,span_service,audit_service}.py`、`api/memories.py`
- 对外接口：`POST/GET/PATCH/DELETE(soft) /api/memories[/{id}]`、`GET /api/memories/{id}/versions`、`POST /api/memories/{id}/restore`、`POST/DELETE /api/memories/{id}/spans`、`GET /api/memories/{id}/audit`
- 先写失败测试：创建即 v1；编辑产生全量快照 v2；**span 增删也产生新版本**；restore 生成新版本而非改写历史；跨会话多 span；span 同会话+有序校验；soft delete；audit append-only
- 完成标准：测试绿；API 手测通过
- 验证：`pytest -k memory -q`

### T4 — 认证与权限矩阵（migration：0004，api_tokens）

- 新建：`core/security.py`、`core/deps.py`、`models/api_token.py`、全端点接入角色校验
- 对外接口：`Authorization: Bearer <token>`；`POST /api/admin/tokens`（owner）
- 先写失败测试：无 token 401；zhan_mcp delete/restore/token 管理 403；zhan_mcp create/edit/add_span 200 且 actor/model 落库；owner 全通
- 完成标准：权限矩阵测试全绿
- 验证：`pytest -k auth -q`

### T5 — 遗失记忆审计（migration：0005，migration_reviews）

- 新建：`services/migration_audit_service.py`、`config/migration_signals.yaml`（默认信号=需求清单，可增补）、`api/migration_audit.py`
- 对外接口：`GET /api/audit/migration-candidates?from&to&verdict`、`POST /api/audit/migration-candidates/{id}/verdict`、`POST /api/audit/migration-candidates/{id}/create-memory`
- 先写失败测试：信号命中且不自动认定（默认 unreviewed）；上下文窗口返回正确；标记持久化；从候选创建 memory 时 span 绑定人工选定范围
- 完成标准：对 2026-07-01~10-31 扫描可出候选、可标记、可转 memory
- 验证：`pytest -k migration_audit -q`

### T6 — chunks + embedding + Qdrant + 搜索（migration：0006，chunks + pg_trgm）

- 新建：`services/embedding/{base,sentence_transformers_provider,stub_provider}.py`、`services/{chunk_service,index_service,search_service}.py`、`api/search.py`、`scripts/rebuild_qdrant.py`
- 对外接口：`POST /api/search/semantic`、`POST /api/search/keyword`、`POST /api/admin/reindex`（owner）
- 先写失败测试：chunk 不切半句；长消息按段落切；payload 白名单断言（无正文）；删除 collection 后 rebuild 计数一致；日期/平台/模型/会话过滤正确；结果含回原文定位字段
- 完成标准：本地 Qdrant 端到端检索通，结果可跳回会话原文
- 验证：`pytest -k search -q`；`python scripts/rebuild_qdrant.py`

### T7 — Portable Export 与恢复（migration：无，audit event 记录）

- 新建：`services/export_service.py`、`api/export.py`、`scripts/restore_from_export.py`
- 对外接口：`POST /api/export` → `GET /api/export/{id}/download`
- 先写失败测试：zip 结构/校验和/manifest 完整；markdown 含正文与来源；**round-trip：导出 → 全新库恢复 → 计数一致**
- 完成标准：round-trip 测试绿
- 验证：`pytest -k export -q`

### T8 — 前端骨架 + design tokens（migration：无）

- 新建：`frontend/src/styles/tokens.css`（色彩/字距/圆角/字体变量，档案馆暖纸基调）、路由、响应式布局、`lib/api.ts`（错误不吞）、9 个页面空壳
- 先写失败测试（vitest）：tokens 加载；api client 对 5xx 抛错不伪装成功
- 完成标准：`npm run build` 过；移动端视口可正常阅读导航
- 验证：`npm run build && npm run test`

### T9 — 前端核心页面（migration：无）

- 新建：Conversation Viewer（连续阅读 + 选段「Add as Evidence / Context」）、Memory Library、Memory Detail/Genesis（正文/元数据/双时间/来源模型/spans/版本史/审计史/跳回原文）、Search、Import、Export/Backup、Migration Audit、Home/Dashboard、Settings
- 先写失败测试：选段提交 payload 正确；Memory Detail 渲染版本列表；Audit 标记交互
- 完成标准：全流程手工走通「导入→浏览→选段→建记忆→编辑留版本→审计打捞→导出」
- 验证：`npm run test`；人工 e2e checklist

### T10 — 加固与文档（migration：无）

- 新建：日志白名单过滤器、统一异常处理（不吞异常）、速率限制、安全响应头、`docs/{architecture.md,import-format-v1.md,ops-runbook.md}`、README 完善
- 先写失败测试：captured logs 断言不含正文/查询词；5xx 不返回成功字样
- 完成标准：全套测试绿 + 文档齐 + G.0 验收逐项通过
- 验证：`pytest -q && npm run build`

### G.12 里程碑建议

- **M1（地基）**：T0–T2 → 能导入真实导出文件并找回原文
- **M2（记忆核心）**：T3–T5 → 有来源、有版本、可打捞
- **M3（检索与出口）**：T6–T7 → 语义检索 + 一键导出可恢复
- **M4（可用）**：T8–T10 → 界面完整、权限收紧、验收

每个里程碑结束都可独立验收，允许中途暂停而不留半成品状态。

---

## H. 声明

**本轮没有修改任何代码。**

本文档为唯一产出。等你回复「批准开工」（以及附录 6 的确认项）后，从 T0 开始。

---

## 附录

### 附 1 权限矩阵（第一阶段）

| 能力 | owner（作者本人） | Zhan MCP |
|---|---|---|
| search / read | ✅ | ✅ |
| create memory | ✅ | ✅（带 actor/model + 版本 + 审计） |
| edit memory（含 event date、模型标签） | ✅ | ✅（强制版本史） |
| add/remove source span | ✅ | ✅（触发新版本） |
| delete | ✅（soft） | ❌（403） |
| restore 历史版本 | ✅ | ❌ |
| token / 权限管理 | ✅ | ❌ |
| export / backup | ✅ | ❌（防批量外泄，可配置放开） |
| import | ✅ | ❌ |
| reindex | ✅ | ❌ |

### 附 2 Portable Export ZIP 布局

```
rianvault-export-YYYYMMDD-HHMMSS.zip
├── manifest.json            # 格式版本、应用版本、导出时间、各文件计数与 sha256
├── checksums.sha256
├── data/
│   ├── conversations.jsonl  ├── messages.jsonl
│   ├── memories.jsonl       ├── memory_versions.jsonl
│   ├── memory_source_spans.jsonl
│   ├── audit_events.jsonl   ├── imports.jsonl
│   └── chunks.jsonl         # 可选；向量本身不导出（可再生）
└── markdown/
    ├── memories/<id>-<title>.md        # frontmatter（类型/双时间/模型/标签）+ 正文 + 来源引用
    └── conversations/<id>-<title>.md   # 完整会话可读版
```

设计目标：无 RianVault 程序也能人工阅读全部重要文本；`scripts/restore_from_export.py` 可据 data/ 重建数据库。

### 附 3 技术栈与版本基线

- Python ≥ 3.12 · FastAPI · SQLAlchemy 2.x · Alembic · Pydantic v2 · pytest
- PostgreSQL 16+（启用 pg_trgm）· Qdrant 最新稳定版 · qdrant-client
- sentence-transformers 3.x（默认 BAAI/bge-m3，可配置）
- React 18 · Vite · TypeScript · vitest · React Router
- Docker Compose（dev 绑 127.0.0.1；prod 数据库无公网端口）· 第三阶段 Caddy
- argon2-cffi（未来密码哈希）· gitleaks · ruff · mypy

### 附 4 第一阶段非目标（YAGNI，明确不做）

- MCP server 实现（仅设计接口形状，第二阶段做）
- External References 体系（第二阶段）
- LLM 答案生成（第一阶段只有检索，没有「RAG 答题」）
- application-level 加密、多用户、Vercel、自动化备份调度、中文分词全文引擎
- memory 本身的向量化（第一阶段语义检索覆盖消息原文；memory 库用筛选+关键词）

### 附 5 待确认事项（已全部确认，2026-10-09）

1. **永久仓库位置**：✅ 确认为 `C:\Users\Owner\Projects\RianVault`（不使用 WorkBuddy 会话目录；不迁移/复用 snowhome 等无关项目）。
2. **embedding 默认模型**：✅ `BAAI/bge-m3`。EmbeddingProvider 保持可替换，模型名只在配置中，不硬编码进业务逻辑。
3. **信号清单**：✅ 在原 13 条基础上补充 18 条（"更新记忆"、"写入记忆"、"已经记住"、"已保存到记忆"、"记忆更新成功"、"记忆写入失败"、"没有写进去"、"记忆满了"、"memory full" 等），已落入 `backend/config/migration_signals.yaml`。所有信号永远只是候选，人工审阅才算数。
4. **工程边界（新增）**：未经我明确要求，不修改 RianVault 仓库之外的 WorkBuddy / Agent 文件（SOUL.md、BOOTSTRAP、身份档案、全局记忆等）。
