import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import PageShell from "../components/PageShell";
import { api } from "../lib/api";
import { useAsync } from "../lib/useAsync";

type Conversation = {
  id: string;
  title: string | null;
  source_platform: string;
  message_count?: number;
  started_at?: string | null;
};

type Message = {
  id: string;
  role: string;
  content_text: string | null;
  event_time: string | null;
  sort_order: number;
  source_model: string | null;
};

type MemoryLite = { id: string; title: string | null; body: string };

/** 选段结果：起止按 sort_order 排序，与点击顺序无关。 */
function normalizeRange(picked: string[], messages: Message[]) {
  const chosen = messages.filter((m) => picked.includes(m.id));
  if (chosen.length === 0) return null;
  const sorted = [...chosen].sort((a, b) => a.sort_order - b.sort_order);
  return { start: sorted[0], end: sorted[sorted.length - 1] };
}

/** 选段范围内的全部消息（不止端点两条）——正文预填、计数都用它。 */
function messagesInRange(
  messages: Message[],
  startSort: number,
  endSort: number,
): Message[] {
  return messages
    .filter((m) => m.sort_order >= startSort && m.sort_order <= endSort)
    .sort((a, b) => a.sort_order - b.sort_order);
}

export default function ConversationViewer() {
  const [convId, setConvId] = useState<string | null>(null);
  const [convQuery, setConvQuery] = useState("");
  const [msgModel, setMsgModel] = useState("");
  const [msgRole, setMsgRole] = useState("");
  const [msgDateFrom, setMsgDateFrom] = useState("");
  const [msgDateTo, setMsgDateTo] = useState("");
  const [picked, setPicked] = useState<string[]>([]);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [eventDate, setEventDate] = useState("");
  const [targetMemory, setTargetMemory] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const conversations = useAsync<Conversation[]>(() => api.get("/conversations"), []);
  const messages = useAsync<Message[]>(
    () => (convId ? api.get(`/conversations/${convId}/messages`) : Promise.resolve([])),
    [convId],
  );
  const memories = useAsync<MemoryLite[]>(() => api.get("/memories?limit=200"), []);

  const range = useMemo(
    () => normalizeRange(picked, messages.data ?? []),
    [picked, messages.data],
  );

  // 原文页的消息筛选（模型 / 角色 / 日期区间）：单会话内前端过滤即可
  const filteredMessages = useMemo(() => {
    return (messages.data ?? []).filter((m) => {
      if (msgModel && !(m.source_model ?? "").toLowerCase().includes(msgModel.toLowerCase()))
        return false;
      if (msgRole && m.role !== msgRole) return false;
      const day = m.event_time ? m.event_time.slice(0, 10) : "";
      if (msgDateFrom && day && day < msgDateFrom) return false;
      if (msgDateTo && day && day > msgDateTo) return false;
      return true;
    });
  }, [messages.data, msgModel, msgRole, msgDateFrom, msgDateTo]);

  // 选段范围内的全部消息（不止端点两条）——正文预填、计数都用它。
  const inRange = useMemo(() => {
    if (!range) return [];
    return messagesInRange(messages.data ?? [], range.start.sort_order, range.end.sort_order);
  }, [range, messages.data]);

  // 正文自动带出选中原文（带「原文引用」前缀），用户在其上改写即可，不用复制粘贴
  useEffect(() => {
    if (!range) return;
    const quoted = inRange
      .map((m) => `【原文｜${m.role}】${m.content_text ?? ""}`)
      .join("\n\n");
    setBody(quoted);
    if (range.start.event_time) setEventDate(range.start.event_time.slice(0, 10));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [picked]);

  const toggle = (id: string) => {
    setPicked((prev) => {
      if (prev.includes(id)) return prev.filter((x) => x !== id);
      // 只保留最近两次点击作为选段端点
      return prev.length < 2 ? [...prev, id] : [prev[1], id];
    });
    setNotice(null);
    setError(null);
  };

  const guessEventDate = () => {
    if (range?.start.event_time) setEventDate(range.start.event_time.slice(0, 10));
  };

  async function createMemoryWithSpan(spanType: "evidence" | "context") {
    if (!range || !convId) return;
    setError(null);
    try {
      const memory = await api.post<{ id: string }>("/memories", {
        title: title.trim() || null,
        body: body.trim(),
        memory_type: "note",
        event_time_start: eventDate || null,
      });
      await api.post(`/memories/${memory.id}/spans`, {
        conversation_id: convId,
        start_message_id: range.start.id,
        end_message_id: range.end.id,
        span_type: spanType,
      });
      setNotice(`已创建记忆并绑定为 ${spanType}`);
      setTitle("");
      setBody("");
      setPicked([]);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function attachToMemory() {
    if (!range || !convId || !targetMemory) return;
    setError(null);
    try {
      await api.post(`/memories/${targetMemory}/spans`, {
        conversation_id: convId,
        start_message_id: range.start.id,
        end_message_id: range.end.id,
        span_type: "evidence",
      });
      setNotice("已加入已有记忆（新版本已记录）");
      setPicked([]);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <PageShell
      title="原文"
      note="点一条消息（变橙 = 选中）作起点，再点另一条作终点：两条之间的整段会被选中，屏幕下方会浮出操作栏，正文已自动带上选中原文，改一改就能存成记忆。"
    >
      <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 260px) minmax(0, 1fr)", gap: "var(--rv-space-3)" }}>
        <aside className="rv-card" style={{ maxHeight: "70vh", overflow: "auto" }}>
          <div style={{ color: "var(--rv-ink-soft)", fontSize: "var(--rv-text-sm)" }}>
            会话（{conversations.data?.length ?? 0}）
          </div>
          <input
            aria-label="搜索会话"
            placeholder="搜索会话名 / 标题…"
            value={convQuery}
            onChange={(e) => setConvQuery(e.target.value)}
            style={{
              width: "100%",
              marginTop: "var(--rv-space-2)",
              padding: "var(--rv-space-2)",
              border: "1px solid var(--rv-line-strong)",
              borderRadius: "var(--rv-radius-sm)",
              fontSize: "var(--rv-text-sm)",
            }}
          />
          {conversations.error ? <div style={{ color: "var(--rv-danger)" }}>{conversations.error}</div> : null}
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {(conversations.data ?? [])
              .filter((c) => {
                const q = convQuery.trim().toLowerCase();
                if (!q) return true;
                const title = (c.title ?? "").toLowerCase();
                return title.includes(q) || c.source_platform.toLowerCase().includes(q);
              })
              .map((c) => (
              <li key={c.id} style={{ marginTop: "var(--rv-space-2)" }}>
                <button
                  type="button"
                  onClick={() => {
                    setConvId(c.id);
                    setPicked([]);
                  }}
                  style={{
                    width: "100%",
                    textAlign: "left",
                    background: c.id === convId ? "var(--rv-accent-soft)" : "transparent",
                    border: "1px solid var(--rv-line)",
                    borderRadius: "var(--rv-radius-sm)",
                    padding: "var(--rv-space-2)",
                    cursor: "pointer",
                    color: "var(--rv-ink)",
                    fontSize: "var(--rv-text-sm)",
                  }}
                >
                  {c.title ?? "（无标题）"}
                  <div style={{ color: "var(--rv-ink-faint)", fontSize: "var(--rv-text-xs)" }}>
                    {c.source_platform} · {c.message_count ?? "?"} 条
                  </div>
                </button>
              </li>
            ))}
          </ul>
        </aside>

        <section>
          {convId ? (
            <div
              className="rv-card"
              style={{
                marginBottom: "var(--rv-space-3)",
                display: "flex",
                gap: "var(--rv-space-2)",
                flexWrap: "wrap",
                alignItems: "center",
              }}
            >
              <input
                aria-label="按模型筛选"
                placeholder="模型（如 gpt-4o，可空）"
                value={msgModel}
                onChange={(e) => setMsgModel(e.target.value)}
                style={{ padding: "var(--rv-space-2)", border: "1px solid var(--rv-line-strong)", borderRadius: "var(--rv-radius-sm)", fontSize: "var(--rv-text-sm)" }}
              />
              <select
                aria-label="按角色筛选"
                value={msgRole}
                onChange={(e) => setMsgRole(e.target.value)}
                style={{ padding: "var(--rv-space-2)", border: "1px solid var(--rv-line-strong)", borderRadius: "var(--rv-radius-sm)", fontSize: "var(--rv-text-sm)" }}
              >
                <option value="">全部角色</option>
                <option value="user">user</option>
                <option value="assistant">assistant</option>
                <option value="system">system</option>
              </select>
              <input
                aria-label="起始日期"
                type="date"
                value={msgDateFrom}
                onChange={(e) => setMsgDateFrom(e.target.value)}
                style={{ padding: "var(--rv-space-2)", border: "1px solid var(--rv-line-strong)", borderRadius: "var(--rv-radius-sm)", fontSize: "var(--rv-text-sm)" }}
              />
              <span style={{ color: "var(--rv-ink-faint)" }}>→</span>
              <input
                aria-label="结束日期"
                type="date"
                value={msgDateTo}
                onChange={(e) => setMsgDateTo(e.target.value)}
                style={{ padding: "var(--rv-space-2)", border: "1px solid var(--rv-line-strong)", borderRadius: "var(--rv-radius-sm)", fontSize: "var(--rv-text-sm)" }}
              />
              <span style={{ color: "var(--rv-ink-soft)", fontSize: "var(--rv-text-sm)" }}>
                筛选出 {filteredMessages.length} / {messages.data?.length ?? 0} 条
              </span>
            </div>
          ) : null}
          {!convId ? (
            <div className="rv-card">左边选一个会话开始阅读。</div>
          ) : messages.loading ? (
            <div className="rv-card">加载中…</div>
          ) : messages.error ? (
            <div className="rv-card" role="alert" style={{ borderColor: "var(--rv-danger)" }}>
              {messages.error}
            </div>
          ) : (
            <div>
              {filteredMessages.map((m) => {
                const selected = picked.includes(m.id);
                return (
                  <article
                    key={m.id}
                    onClick={() => toggle(m.id)}
                    role="button"
                    aria-pressed={selected}
                    className="rv-card"
                    style={{
                      marginBottom: "var(--rv-space-2)",
                      cursor: "pointer",
                      borderColor: selected ? "var(--rv-accent)" : "var(--rv-line)",
                      background: selected ? "var(--rv-accent-soft)" : "var(--rv-surface)",
                    }}
                  >
                    <div style={{ fontSize: "var(--rv-text-xs)", color: "var(--rv-ink-faint)" }}>
                      {m.role}
                      {m.source_model ? ` · ${m.source_model}` : ""} ·{" "}
                      {m.event_time ? new Date(m.event_time).toLocaleString() : "（无时间）"}
                    </div>
                    <div style={{ marginTop: "var(--rv-space-1)", whiteSpace: "pre-wrap" }}>
                      {m.content_text ?? "（空）"}
                    </div>
                  </article>
                );
              })}
            </div>
          )}
        </section>
      </div>

      {range ? (
        <div
          className="rv-card"
          style={{
            position: "sticky",
            bottom: "var(--rv-space-2)",
            zIndex: 10,
            marginTop: "var(--rv-space-3)",
            boxShadow: "var(--rv-shadow-raised)",
            border: "1px solid var(--rv-accent)",
            maxHeight: "55vh",
            overflow: "auto",
          }}
        >
          <div style={{ fontSize: "var(--rv-text-sm)", color: "var(--rv-ink-soft)" }}>
            已选 {inRange.length} 条（第 {range.start.sort_order} → {range.end.sort_order} 条）·
            正文已自动带出原文，你可以直接在上面改写
          </div>
          <div style={{ display: "grid", gap: "var(--rv-space-2)", marginTop: "var(--rv-space-2)" }}>
            <input
              aria-label="记忆标题"
              placeholder="标题（可留空）"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              style={{ padding: "var(--rv-space-2)", border: "1px solid var(--rv-line-strong)", borderRadius: "var(--rv-radius-sm)" }}
            />
            <textarea
              aria-label="记忆正文"
              placeholder="这条记忆写了什么（选中原文会自动填进来，改写它即可）"
              value={body}
              onChange={(e) => setBody(e.target.value)}
              rows={6}
              style={{ padding: "var(--rv-space-2)", border: "1px solid var(--rv-line-strong)", borderRadius: "var(--rv-radius-sm)" }}
            />
            <div style={{ display: "flex", gap: "var(--rv-space-2)", alignItems: "center", flexWrap: "wrap" }}>
              <input
                aria-label="发生日期"
                type="date"
                value={eventDate}
                onChange={(e) => setEventDate(e.target.value)}
                onFocus={guessEventDate}
                style={{ padding: "var(--rv-space-2)", border: "1px solid var(--rv-line-strong)", borderRadius: "var(--rv-radius-sm)" }}
              />
              <button
                type="button"
                onClick={() => createMemoryWithSpan("evidence")}
                disabled={!body.trim()}
                style={{
                  padding: "var(--rv-space-2) var(--rv-space-3)",
                  border: "1px solid var(--rv-accent)",
                  borderRadius: "var(--rv-radius-sm)",
                  background: "var(--rv-accent)",
                  color: "var(--rv-surface)",
                  cursor: "pointer",
                }}
              >
                新建记忆 · 作为证据
              </button>
              <button
                type="button"
                onClick={() => createMemoryWithSpan("context")}
                disabled={!body.trim()}
                style={{
                  padding: "var(--rv-space-2) var(--rv-space-3)",
                  border: "1px solid var(--rv-line-strong)",
                  borderRadius: "var(--rv-radius-sm)",
                  background: "transparent",
                  color: "var(--rv-ink)",
                  cursor: "pointer",
                }}
              >
                新建记忆 · 作为上下文
              </button>
            </div>
            <div style={{ display: "flex", gap: "var(--rv-space-2)", alignItems: "center", flexWrap: "wrap" }}>
              <select
                aria-label="已有记忆"
                value={targetMemory}
                onChange={(e) => setTargetMemory(e.target.value)}
                style={{ padding: "var(--rv-space-2)", border: "1px solid var(--rv-line-strong)", borderRadius: "var(--rv-radius-sm)" }}
              >
                <option value="">加到已有记忆…</option>
                {(memories.data ?? []).map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.title ?? m.body.slice(0, 20)}
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={attachToMemory}
                disabled={!targetMemory}
                style={{
                  padding: "var(--rv-space-2) var(--rv-space-3)",
                  border: "1px solid var(--rv-line-strong)",
                  borderRadius: "var(--rv-radius-sm)",
                  background: "transparent",
                  cursor: "pointer",
                }}
              >
                作为证据加入
              </button>
              <button
                type="button"
                onClick={() => setPicked([])}
                style={{ border: "none", background: "none", color: "var(--rv-ink-soft)", cursor: "pointer" }}
              >
                清除选择
              </button>
              <Link to="/memories" style={{ fontSize: "var(--rv-text-sm)" }}>
                去看记忆
              </Link>
            </div>
          </div>
        </div>
      ) : null}

      {notice ? (
        <p className="rv-page-note" style={{ color: "var(--rv-success)" }}>
          {notice}
        </p>
      ) : null}
      {error ? (
        <p className="rv-page-note" role="alert" style={{ color: "var(--rv-danger)" }}>
          {error}
        </p>
      ) : null}
    </PageShell>
  );
}
