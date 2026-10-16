# rianvault-jsonl-v1 导入格式规范

RianVault 的规范化 JSONL 导入格式。Omate、ArenaAI、Cakumi、API 酒馆等来源，
最简单的接入方式是导出/转换成这个格式；也可以为它们单独写 adapter
（见 `backend/app/services/importers/`），但 JSONL v1 是最低门槛。

## 基本规则

- 每行一个 JSON 对象，UTF-8 编码。
- `type` 字段区分行类型：`conversation` | `message`。
- 第一条 `conversation` 行必须携带 `"format": "rianvault-jsonl-v1"`（adapter 据此识别文件）。
- `message` 行引用的 `conversation_id` 必须已在之前的 `conversation` 行声明。
- 无法解析的行让整个导入失败；字段缺失的消息进入隔离区（import_quarantine），
  原始行完整保留，绝不静默丢弃。

## conversation 行

```json
{"type":"conversation","format":"rianvault-jsonl-v1","platform":"omate","conversation_id":"om-100","title":"可选标题","extra":{"any":"thing"}}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `format` | 首行必填 | `rianvault-jsonl-v1` |
| `platform` | 必填 | 来源平台标识（`omate` / `arenaai` / …），进入 `source_platform` |
| `conversation_id` | 必填 | 源平台会话 id；幂等去重键之一 |
| `title` | 可选 | 会话标题 |
| `extra` | 可选 | 任意对象，原样进入 `raw_metadata` |

## message 行

```json
{"type":"message","conversation_id":"om-100","message_id":"m2","parent_id":"m1","role":"assistant","text":"……","timestamp":"2025-03-14T21:02:30+08:00","model":"gpt-4o","model_note":"manual_by_Owner","extra":{}}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `conversation_id` | 必填 | 必须已声明 |
| `message_id` | 可选 | 缺失时用确定性内容哈希兜底去重 |
| `parent_id` | 可选 | 树状对话的父消息 |
| `role` | 必填* | `user` / `assistant` / `system` / `tool` |
| `text` | 必填* | 纯文本正文；*role 与 text 至少要有意义地存在，否则进隔离区 |
| `timestamp` | 可选 | ISO 8601，建议带时区；缺时区按 UTC 存并记 warning，原始字符串保留 |
| `model` | 可选 | 源模型名，如 `gpt-4o`；进入 `source_model` |
| `model_note` | 可选 | 模型标注说明，如 `manual_by_Owner`；带 note 视为手工标注 |
| `content_kind` | 可选 | `text`（默认）/ `multimodal` / `code` / `other` |
| `content_raw` | 可选 | 原始内容结构（多模态等），原样保留 |
| `extra` | 可选 | 原样进入 `raw_metadata` |

## 时间语义

- `timestamp` = 事情真正发生的时间（`event_time`）。
- 导入时间由系统记录为 `ingested_at`，两者永不混用。

## 幂等

- 同一文件（sha256 相同）重复导入：返回已有台账，不产生新数据。
- 不同文件包含相同会话/消息：按 `(platform, conversation_id)` 与
  `(conversation_id, message_id)`（或内容哈希）去重，新消息照常入库。
