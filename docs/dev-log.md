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

## 2026-10-11 — T8 前端骨架 + 设计令牌

- `tokens.css` 补齐层次/动效/布局令牌；新增 `layout.css`（桌面侧栏 + 窄屏可折叠导航 + 跳转链接）。
- `lib/api.ts` 是唯一通信入口：非 2xx 抛 `ApiError`（带 status/detail），网络异常原样抛出；
  token 只在 sessionStorage；查询走 body 不进 URL（私人查询词不进地址栏/日志）。
- Layout + PageShell + 9 个页面空壳 + `BrowserRouter` 路由；Settings 页可保存/清除令牌。
- 验证：`npm run build` 过；`npm run test` 21 项全过（api client 6 + 令牌 15）。
- commit：`bbc3c70`。

## 2026-10-12 — T9 前端核心页面

- 后端补 `GET /api/stats`（首页概览：会话/消息/已索引/记忆/片段/待审阅线索 + 当前身份；
  只给计数、排除软删除；3 项测试）。
- 前端：`useAsync`（统一加载/报错/重试，错误必显示）、Conversation Viewer（点两条消息框出选段
  → 建记忆并绑 evidence/context，或加入已有记忆）、Memory Library、Memory Detail/Genesis
  （双时间 + 来源片段跳回原文 + 版本史可回滚 + 审计史 + 编辑 + 软删除）、Search（POST 查询）、
  Import（上传与对账、警告）、Export（生成与下载）、Migration Audit（扫描 + 七种人工判定 + 整理成记忆）。
- 验证：后端 pytest 135 绿 + ruff 净；前端 vitest 30 绿、`npm run build` 过；
  vite dev 代理真实后端冒烟（无 token 401、带 token 200）。
- commit：`71f34f6`、`ec2c576`。

### 前端坑位

- Python 生成 .tsx 时，f-string 会把 JSX 的 `{{ }}` 吃成单括号 → 直接 tsc 报错；生成代码要转义 `{{{{ }}}}`。
- vitest 默认 `css: false`，`?raw` 导入 CSS 拿到空字符串；想读 CSS 原文就 `node:fs` + `@types/node`。
- 没装 `@types/node` 时 `import "node:fs"` 会让 `tsc -b` 失败（不只是 vitest 报错）。
- vitest 不开 `globals` 时 RTL **不会自动 cleanup**，多个组件测试会互相污染 DOM（findByText 报
  "found multiple elements"）→ 每个测试文件都要 `afterEach(cleanup)`。
- `toBeDisabled()` 等是 jest-dom 匹配器，没装就别用；用 `(el as HTMLButtonElement).disabled`。
- `getByText(/正则/)` 会同时命中父元素与子元素 → 用 `getAllByText(...).length > 0`。
- vite dev 会生成 `vite.config.ts.timestamp-*.mjs`，`git add -A` 容易把它带进提交，已在 .gitignore 排除。
- vite dev 默认只监听 localhost，curl `127.0.0.1` 可能连不上，用 `localhost`。

## 2026-10-12 — T10 加固与文档

- `core/logging_setup.py`：日志脱敏过滤器（token / Bearer / 连接串密码 / 正文字段）——
  兜底网，真正的保证是"根本不写这些东西进日志"。
- `core/errors.py`：未处理异常 → 500 + `error_id`，不回吐异常细节（SQLAlchemy 异常可能夹带
  SQL 参数＝正文）；默认不打印完整堆栈，`DEBUG=true` 才打。
- `core/middleware.py`：安全响应头 + `/api` 一律 `no-store` + 写操作/检索按 IP 滑动窗口限流。
- `tests/test_hardening.py`（11 项）；文档：`architecture.md` 重写、`ops-runbook.md` 新增、
  README 补文档索引与加固说明。
- 验证：后端 pytest 146 绿 + ruff 净；前端 vitest 30 绿 + build 过；真实服务冒烟确认安全头。
- commit：`2cca33e`。

## 2026-10-12 — 一键验收脚本（acceptance_check.py）

- Owner反馈"不知道文件在哪、不知道怎么验收"，于是加了 `scripts/acceptance_check.py`：
  自建全新库（带时间戳）→ 起服务 → 造 token → 逐项跑 G.0 → 打印 PASS/FAIL → 关服务。
- 30/30 通过（约 46 秒，含真机 bge-m3 语义检索）；`--skip-semantic` 可跳过权重加载。
- 新增 `backend/tests/fixtures/acceptance_chat.json`：2026-08 的「已经记住了」样本，
  让审计窗口 2026-07-01~10-31 真能扫出候选（原 fixture 是 2023 年，扫不到）。
- 另外写了 `backend/.env`（不进 Git）：本地 SQLite + Qdrant 本地模式 + bge-m3 本地权重路径，
  这样手工起服务不用再敲一串环境变量。
- commit：`b511ea6`。

## 2026-10-12（晚）— Owner实测反馈三处修复

- 导出下载 401 → 前端带 token 的 blob 下载（`api.downloadFile`）；401 明确提示去设置页。
- 语义检索 0 条 → 根因：导入后**不会自动建索引**（设计如此，但 UI 没提示，等于灵异事件）。
  检索页加「已索引 X / 共 Y」横幅 + 一键补齐 + 0 结果原因提示。Owner的库 4136 条消息、
  chunk_index 0 行、"爱"出现 2260 次——关键词模式本来就能搜到，语义必须先补索引。
- 选段交互：操作栏沉底看不到 → 改 sticky 悬浮；正文自动带出选中原文（【原文｜role】前缀）。
- 教训：**"设计上没做"和"用户眼里坏了"是同一件事**。导入完成 → 没建索引 → 检索 0 条，
  这条链路必须当场提示，否则必被当成 bug。
- commit：`45f01a6`。

## 2026-10-13 — Owner第二批反馈

- 导航卡片化 + 大字号 + 侧栏/正文独立滚动（height:100vh + overflow）；原文页加搜会话名。
- 检索加筛选：模型、角色、起止日期区间（后端补 source_model，前端接齐 date_from/date_to/role/model）。
- Qdrant 本地模式锁残留：`get_qdrant` 讲清「目录被占用」并提示别手删 .lock；
  `rebuild_qdrant.py` atexit 主动 close；embedding batch 可配置 + 进度日志。
- **待Owner拍板的设计决策**（本轮先不动，见回复）：
  ① 记忆要不要加「摘要」字段（evidence/context 之上再加一层 summary）；
  ② span 是否允许增删/编辑（现在只读，靠版本史溯源）；
  ③ 筛选放检索还是原文还是都放。
- commit：`0d77fbc`、`538f06a`。

## 2026-10-13 — Owner拍板的四项（含产品设计定案）

**Owner的产品决定（重要，后续按此走）：**
- 记忆的 **正文 = 摘要**（主体），**来源片段 = 引用**（evidence/context）。两者分开，不合并。
- 正文/标题必须能随便改（本来就能改，改了留新版本）。
- **来源片段的起止范围允许编辑**——场景：AI（通过 MCP）或Owner自己当初凭印象圈的范围不准，
  等原文真正导进来才发现圈错了。
- 筛选：检索页和原文页**都做**（模型/角色/日期区间/平台）。

**实现：**
- `span_service.update_span` + `PATCH /api/memories/{id}/spans/{span_id}`（SpanUpdate）：
  改完 bump 新版本（快照含旧范围 → 可回滚）+ 审计 `span_updated` 记 before/after（只记 id）。
  换会话的跨度拒绝（换出处＝换证据链，应先删再建）。
- 前端：MemoryDetail 加标题编辑 + 每条来源「调整范围」下拉；ConversationViewer 加消息筛选。
- 新增 `tests/test_span_update.py`（9 项）、`scripts/smoke_span_update.py`（真机 6/6）。
- 索引真相：4136 条消息里 426 条空正文（纯图片）本就不进索引；stats 加 `indexable_messages`
  做分母，避免"永远差 426 条"的假警报。
- commit：`ab8caf6`。

## 2026-10-14 — 启动自检 + 检索「证据可见」（高亮 / 命中来源标注）

**Owner的问题（逐条答，见对话；结论记此）：**

| 问题 | 结论（事实，不美化） |
| --- | --- |
| 还要手动建索引吗？ | 导入后后台线程自动建（`auto_index_after_import`），也可手动「补齐语义索引」；建索引是增量的，已索引的不会重做。 |
| 关键词检索是 BM25 吗？ | **不是**。现在是 PostgreSQL `ILIKE` 子串匹配（多词 AND），按时间倒序；关键词命中固定记 0.3 分，没有相关性打分。要 BM25 得上 FTS5/tsvector，待办。 |
| 结果重排序了吗？ | 语义结果按余弦相似度降序（bge-m3 的分数就是排序依据）；混合＝语义为主 + 关键词补充。**没有 cross-encoder reranker**（bge-reranker 未装，CPU 上再跑一遍很贵，等评测显示精度不够再说）。 |
| 混合能标出来源吗？ | 已做：后端 `match_types`（`["semantic"]` / `["keyword"]` / 两者都有），前端渲染成彩色胶囊标签。 |
| 关键词能标亮吗？ | 已做：前端 `highlight()` 把查询词包 `<mark>`（黄底）。 |
| 语义为什么命中？ | 已做：后端返回 `chunk_index` + `matched_chunk_text`——用建索引时**同一套切分规则**重新切原文取回那一段，前端单独框出来。正文不进向量库，所以是"重切还原"而不是"从向量库读回"。 |
| 谁切的 chunk？切多大？在哪断？ | `services/chunking.py::chunk_message`，由 `index_service.index_messages` 在建索引时调用。按句末标点（`。！？!?；;`）+ 换行断句，累积到 ≤600 token（`chunk_max_tokens` 可配）成一块；整条消息不超预算就**不切**（单块 index 0）。 |
| 怎么知道检索全不全？ | 两层：`qdrant-client` 本地模式是 **exact 暴力全扫**（不采样不近似，实测源码里有 `Local mode performs exact (brute-force) search`），所以 top-k 排序是完整精确的；但"语义相关不相关"是模型的判断，**没有真值就量不出召回率**。关键词模式是数据库全表扫描，这一路的召回是完备的，可做交叉验证。 |

**实现：**
- `services/search_service.py`：`SearchHit` 加 `chunk_index` / `matched_chunk_text`；新增
  `_matched_chunk_text()`（用 `get_settings().chunk_max_tokens` 重切，保证与建索引时一致）。
- `frontend/src/lib/highlight.tsx`（新）：`termsOf()`（与后端切词规则一致，含全角空格归一）、
  `highlight()`（正则转义 + 长度降序 + 大小写不敏感，返回 `ReactNode[]`）。
- `frontend/src/pages/Search.tsx`：命中头部加「语义 / 关键词」胶囊标签；语义命中额外展示
  「语义命中片段」框（仅当该条消息真被切成多块时展示，避免与整条原文重复）。
- 测试：后端 `tests/test_search.py` 加 `test_semantic_hit_carries_matched_chunk`（含"片段必须是原
  文子串"断言）；前端 `src/lib/highlight.test.tsx`（6 项）。

**坑位：**
- pytest 默认 basetemp 在系统临时目录，清理时会被沙箱判为"批量删除"而拒绝（表现为莫名 1 个 ERROR）。
  跑测试统一加 `--basetemp=./.pytest-tmp`（落在仓库内）。
- Qdrant 本地模式在解释器退出时 `__del__` 抛 `ImportError: sys.meta_path is None`——是关机噪音，
  不影响测试结果，别当成失败去修。
- 测试辅助函数递归 `ReactNode` 时**必须先处理数组**：`highlight()` 返回 `ReactNode[]`，
  只按 `ReactElement` 处理会得到空串（第一次就是这么翻车的）。

**当前运行状态：** 端口 8000 上只有 1 个 python 进程（PID 35104，约 3.7GB＝bge-m3 已驻留），
热态语义检索约 0.2 秒／次。冷启动首次仍需约 60 秒加载模型（建模在启动线程预热）。
索引吞吐约 17 条消息/秒（CPU，bge-m3）——2000 万字级别全量重建预计要跑几小时，靠增量避免重做。
**本轮改动需重启后端才生效。**

## 2026-10-14（下午）— 三个被崩出来的并发 bug（都不是段错误的表象那么简单）

跑全量后端测试时直接**段错误**把整个 pytest 进程带走了（`access violation`，没有任何 Python
异常可抓）。顺着崩溃栈往下挖，挖出三个真 bug——它们全都会在Owner的日常使用中炸，不只是测试问题：

### ① 导入后自动建索引：并发 torch 推理会崩进程

`schedule_auto_index()` 原来是"每个导入各起一个线程"。Owner一次性导入十几个文件时，
就会有十几个线程同时用 bge-m3 跑 torch 推理 → 段错误。
改为**串行**：同一时刻只允许一个 worker，后来的导入标记 `pending`，当前批次跑完再补一轮，
既覆盖全部新消息，又绝不并发推理。新增 `tests/test_auto_index.py`（3 项）把这条约束钉死。

### ② 上面的 worker 里 `global` 漏写了变量名（会让自动建索引永久失效）

```python
global _auto_index_pending      # ← 漏了 _auto_index_running
...
finally:
    _auto_index_running = False # ← 实际创建的是**局部变量**，全局标志永远复位不了
```
后果：第一次导入后 `_auto_index_running` 永远是 True，**此后所有导入都不会再自动建索引**
（搜不到新内容，且完全静默）。是刚写的测试把它抓出来的（测 Triton 之外的东西也值了）。

### ③ 启动自检把 Qdrant 单例钉死在开发库上（维度冲突）

`_check_qdrant_exclusive()` 用 `index_service.get_qdrant()` 探测，等于创建了单例并永久缓存。
测试随后要在临时目录用 256 维替身模型建索引，却拿钉在**开发库 1024 维集合**上的单例 →
`Vector dimension error: expected dim: 1024, got 256`。
之前一直没暴露，是因为Owner的后端占着开发库目录，自检必然失败、单例压根没建起来——
她这边一停，坑就露出来了。**自检改为一次性探针**（`QdrantClient(path=...)` 用完即关），不碰正式单例。

### 顺带：测试环境不再偷偷加载真模型

`conftest.py` 里 `os.environ.setdefault` 关掉 `AUTO_INDEX_AFTER_IMPORT` 与
`WARMUP_EMBEDDING_ON_STARTUP`：原本每次 TestClient 起 lifespan 都会开线程加载真的 bge-m3
（4.3GB），整套用例起十几个 client 就是十几份大模型 → 内存炸、段错误。关掉后全量测试从
「崩/9 分钟」变成 **161 通过 / 4 分 55 秒**。生产里也给预热加了"只起一次"的开关（`start_warmup_once`）。

**验证：** 后端 161 passed（exit=0）；前端 43 passed。
新增 `frontend/src/pages/Search.test.tsx`（3 项，覆盖「关键词标亮 / 来源标签可见 / 语义片段框」），
补齐了这轮改动最后一块没有守门人的地方。

**坑位续（工程）：**
- 前端测试用 gut role 定位按钮更安全：页面 `<h1>` 标题也叫「检索」，`getByText("检索")` 会撞两个。
  同理多条结果都有同名标签时要用 `findAllByText`。
- 测试里 `render()` 只能调一次：helper 里再 render 一次就出现两套 DOM，`getByLabelText` 报
  "Found multiple elements"。

**当前运行状态（17:47 起）：** 后端已重新拉起（PID 21244，端口 8000），启动自检通过，
并在 17:47:54 完成 embedding 预热——**之后检索都是热态**。前端 Vite 会自动热更新，
刷新浏览器搜「爱」即可看到黄底高亮、「语义/关键词」标签与语义命中片段框。

## 2026-10-14（晚）— 回收站（软删除 → 还原 / 彻底删除）

**Owner的要求：** 软删除要二次确认；删了先进回收站；**只有她能彻底删除（AI 身份不行）**。

**实现：**
- `memory_service.undelete_memory`：回收站还原。关键是**还原到删除前那一刻的状态**——
  先看上一版快照里的 status 再恢复（否则原本「归档」的记忆会被悄悄变成「活跃」）。
  还原同样是**追加新版本**（不改写历史），审计记 `memory_restored`。
- `POST /api/memories/{id}/undelete`（Owner only）。彻底删除复用已有的
  `DELETE /memories/{id}/purge`（Owner only，物理删 memory + 版本 + span，留一条 `memory_purged` 审计）。
- `GET /api/auth/me`（新增）：返回 `{role, can_admin}`，让前端据此隐藏 Owner 专属按钮，
  别摆出点了必然 403 的按钮。**真正的权限判断永远在后端**（`require_owner`），这里只是 UI 收敛。
- 前端：MemoryLibrary 加「回收站（N）」入口；MemoryDetail 的删除键改为「移进回收站」并二次确认，
  已删除的记忆显示「从回收站还原」。

**权限矩阵补充（实测）：** zhan_mcp 对 删除 / 还原 / 彻底删除 全部 403（测试 `TestRecycleBin` 覆盖）。

**UX 取舍：** 只有**毁灭性**操作（彻底删除）要点两次确认；还原是无损的，点一次就走，
不给人添堵。

**验证：** 后端 169 passed（+8），前端 47 passed（+4）。

**未解（等Owner定）：** GPT 通过 MCP 写入时，若那段聊天还没导出成 json，就没有 message id 可绑
→ 只能先写摘要、等导入后再补绑来源（改范围已支持这条路径）。要不要支持"待补来源"标记，待定。

### 加固相关坑位

- 测试里用默认 `hybrid` 调 `/api/search` 会去加载 bge-m3 权重（本机默认模型名解析不到就**联网**，
  直接卡几分钟）→ 与检索无关的测试一律用 `mode: "keyword"`。
- 全局限流会让整套测试累积 429（TestClient 共用一个 client IP）→
  `tests/conftest.py` 顶部 `os.environ.setdefault("RATE_LIMIT_PER_MINUTE", "0")`；
  限流器本身用独立 app 单独测（真实配额、真实 429）。
- 全量跑测试前先确认没有"会触发真实模型加载"的用例混入，否则会出现长时间无输出。
- **Windows 双 Python**：系统全局 Python（3.14）没装项目依赖，裸 `python` 会报
  `No module named uvicorn` / `'alembic' is a package`。所有命令必须走
  `.venv\Scripts\python.exe`；acceptance_check.py 已加自动切换（检测到非 venv 解释器
  就重新执行），手册命令全部改写为 venv 路径。

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
