import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import PageShell from "../components/PageShell";
import { api } from "../lib/api";
import { useAsync } from "../lib/useAsync";

type MemoryOut = {
  id: string;
  title: string | null;
  body: string;
  memory_type: string;
  status: string;
  event_time_start: string | null;
  event_time_end: string | null;
  created_at: string;
  updated_at: string;
  created_by_actor: string;
  created_by_model: string | null;
  current_version: number;
  tags: string[];
};

type Span = {
  id: string;
  conversation_id: string;
  start_message_id: string;
  end_message_id: string;
  span_type: string;
  created_by_actor: string;
};

type Version = {
  id: string;
  version_number: number;
  snapshot: Record<string, unknown>;
  edited_by_actor: string;
  edited_by_model: string | null;
  edit_reason: string | null;
  created_at: string;
};

type AuditEvent = {
  id: string;
  event_type: string;
  actor: string;
  actor_model: string | null;
  created_at: string;
  detail: Record<string, unknown>;
};

type Detail = {
  memory: MemoryOut;
  spans: Span[];
  versions: Version[];
  audit_events: AuditEvent[];
};

export default function MemoryDetail() {
  const { id } = useParams();
  const [editing, setEditing] = useState(false);
  const [body, setBody] = useState("");
  const [title, setTitle] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  // 正在调整范围的 span + 该会话的消息列表
  const [spanEditing, setSpanEditing] = useState<string | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [spanRange, setSpanRange] = useState<{ start: string; end: string }>({
    start: "",
    end: "",
  });

  const detail = useAsync<Detail>(() => api.get(`/memories/${id}`), [id]);
  const editingSpan = detail.data?.spans.find((s) => s.id === spanEditing) ?? null;
  const convMessages = useAsync<{ id: string; role: string; content_text: string | null; sort_order: number }[]>(
    () => (editingSpan ? api.get(`/conversations/${editingSpan.conversation_id}/messages`) : Promise.resolve([])),
    [editingSpan?.conversation_id],
  );

  const startEdit = () => {
    setBody(detail.data?.memory.body ?? "");
    setTitle(detail.data?.memory.title ?? "");
    setEditing(true);
  };

  const startSpanEdit = (span: Span) => {
    setSpanEditing(span.id);
    setSpanRange({ start: span.start_message_id, end: span.end_message_id });
    setError(null);
    setNotice(null);
  };

  async function saveSpanRange() {
    if (!id || !spanEditing) return;
    setError(null);
    try {
      await api.patch(`/memories/${id}/spans/${spanEditing}`, {
        start_message_id: spanRange.start,
        end_message_id: spanRange.end,
        reason: "前端调整来源范围",
      });
      setSpanEditing(null);
      setNotice("来源范围已调整（旧范围留在版本史里，可回滚）");
      detail.reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function save() {
    if (!id || !body.trim()) return;
    setError(null);
    try {
      await api.patch(`/memories/${id}`, {
        body: body.trim(),
        title: title.trim() || null,
        reason: "前端编辑",
      });
      setEditing(false);
      setNotice("已保存（新版本已记录）");
      detail.reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function restore(versionNumber: number) {
    if (!id) return;
    setError(null);
    try {
      await api.post(`/memories/${id}/restore`, {
        version_number: versionNumber,
        reason: "前端回滚",
      });
      setNotice(`已回滚到 v${versionNumber}（历史未被改写，只是追加了新版本）`);
      detail.reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function remove() {
    if (!id) return;
    setError(null);
    try {
      await api.del(`/memories/${id}`);
      setNotice("已移进回收站——去「记忆」页右上角的回收站可以还原，或彻底删除。");
      setConfirmingDelete(false);
      detail.reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setConfirmingDelete(false);
    }
  }

  async function undelete() {
    if (!id) return;
    setError(null);
    try {
      await api.post(`/memories/${id}/undelete`);
      setNotice("已从回收站还原（删除前后各留一个版本，历史没有被改写）。");
      detail.reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  if (!id) return <PageShell title="记忆详情" note="缺少 memory id" />;

  return (
    <PageShell
      title={detail.data?.memory.title ?? "记忆详情 · Genesis"}
      note="正文 + 双时间 + 来源片段 + 版本史 + 审计史；任何改动都会留下新版本。"
    >
      {detail.error ? (
        <div className="rv-card" role="alert" style={{ borderColor: "var(--rv-danger)" }}>
          {detail.error}
        </div>
      ) : null}
      {notice ? <p className="rv-page-note" style={{ color: "var(--rv-success)" }}>{notice}</p> : null}
      {error ? (
        <p className="rv-page-note" role="alert" style={{ color: "var(--rv-danger)" }}>
          {error}
        </p>
      ) : null}

      {detail.data ? (
        <div style={{ display: "grid", gap: "var(--rv-space-3)" }}>
          <div className="rv-card">
            <div style={{ fontSize: "var(--rv-text-xs)", color: "var(--rv-ink-faint)" }}>
              发生时间：{detail.data.memory.event_time_start ?? "未标注"} →{" "}
              {detail.data.memory.event_time_end ?? "—"}
              <br />
              创建时间：{new Date(detail.data.memory.created_at).toLocaleString()}
              <br />
              由 {detail.data.memory.created_by_actor}
              {detail.data.memory.created_by_model
                ? ` / ${detail.data.memory.created_by_model}`
                : ""}{" "}
              · 当前 v{detail.data.memory.current_version} · {detail.data.memory.memory_type} ·{" "}
              {detail.data.memory.status}
            </div>
            {editing ? (
              <div style={{ marginTop: "var(--rv-space-2)" }}>
                <input
                  aria-label="编辑标题"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="标题（可留空）"
                  style={{ width: "100%", padding: "var(--rv-space-2)", border: "1px solid var(--rv-line-strong)", borderRadius: "var(--rv-radius-sm)", marginBottom: "var(--rv-space-2)" }}
                />
                <textarea
                  aria-label="编辑正文"
                  value={body}
                  onChange={(e) => setBody(e.target.value)}
                  rows={5}
                  style={{ width: "100%", padding: "var(--rv-space-2)", border: "1px solid var(--rv-line-strong)", borderRadius: "var(--rv-radius-sm)" }}
                />
                <div style={{ display: "flex", gap: "var(--rv-space-2)", marginTop: "var(--rv-space-2)" }}>
                  <button type="button" onClick={save}>
                    保存
                  </button>
                  <button type="button" onClick={() => setEditing(false)}>
                    取消
                  </button>
                </div>
              </div>
            ) : (
              <p style={{ whiteSpace: "pre-wrap", marginTop: "var(--rv-space-2)" }}>
                {detail.data.memory.body}
              </p>
            )}
            {!editing ? (
              <button type="button" onClick={startEdit} style={{ marginTop: "var(--rv-space-2)" }}>
                编辑（会新增版本）
              </button>
            ) : null}
          </div>

          <div className="rv-card">
            <h2 style={{ fontSize: "var(--rv-text-lg)", marginTop: 0 }}>来源片段</h2>
            {detail.data.spans.length === 0 ? (
              <p className="rv-page-note">还没有来源片段。</p>
            ) : (
              <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
                {detail.data.spans.map((s) => (
                  <li key={s.id} style={{ marginBottom: "var(--rv-space-3)" }}>
                    <span
                      style={{
                        color: s.span_type === "evidence" ? "var(--rv-evidence)" : "var(--rv-context)",
                        fontSize: "var(--rv-text-sm)",
                      }}
                    >
                      {s.span_type}
                    </span>{" "}
                    <Link to={`/conversations/${s.conversation_id}`}>跳回原文</Link>
                    <div style={{ color: "var(--rv-ink-faint)", fontSize: "var(--rv-text-xs)" }}>
                      {s.start_message_id.slice(0, 8)}… → {s.end_message_id.slice(0, 8)}… · 由{" "}
                      {s.created_by_actor}
                    </div>

                    {spanEditing === s.id ? (
                      <div style={{ marginTop: "var(--rv-space-2)", padding: "var(--rv-space-2)", border: "1px solid var(--rv-accent)", borderRadius: "var(--rv-radius-sm)" }}>
                        <div style={{ fontSize: "var(--rv-text-sm)", marginBottom: "var(--rv-space-2)" }}>
                          调整这段来源的起止范围（圈错了可以改，旧范围会留在版本史里）：
                        </div>
                        <label style={{ fontSize: "var(--rv-text-xs)" }}>
                          起始消息
                          <select
                            aria-label="起始消息"
                            value={spanRange.start}
                            onChange={(e) => setSpanRange((p) => ({ ...p, start: e.target.value }))}
                            style={{ display: "block", width: "100%", marginTop: "var(--rv-space-1)", padding: "var(--rv-space-1)", border: "1px solid var(--rv-line-strong)", borderRadius: "var(--rv-radius-sm)" }}
                          >
                            {(convMessages.data ?? []).map((m) => (
                              <option key={m.id} value={m.id}>
                                #{m.sort_order} {m.role}：{(m.content_text ?? "（空）").slice(0, 40)}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label style={{ fontSize: "var(--rv-text-xs)", display: "block", marginTop: "var(--rv-space-2)" }}>
                          结束消息
                          <select
                            aria-label="结束消息"
                            value={spanRange.end}
                            onChange={(e) => setSpanRange((p) => ({ ...p, end: e.target.value }))}
                            style={{ display: "block", width: "100%", marginTop: "var(--rv-space-1)", padding: "var(--rv-space-1)", border: "1px solid var(--rv-line-strong)", borderRadius: "var(--rv-radius-sm)" }}
                          >
                            {(convMessages.data ?? []).map((m) => (
                              <option key={m.id} value={m.id}>
                                #{m.sort_order} {m.role}：{(m.content_text ?? "（空）").slice(0, 40)}
                              </option>
                            ))}
                          </select>
                        </label>
                        <div style={{ display: "flex", gap: "var(--rv-space-2)", marginTop: "var(--rv-space-2)" }}>
                          <button type="button" onClick={saveSpanRange}>
                            保存范围
                          </button>
                          <button type="button" onClick={() => setSpanEditing(null)}>
                            取消
                          </button>
                        </div>
                      </div>
                    ) : (
                      <button
                        type="button"
                        onClick={() => startSpanEdit(s)}
                        style={{ marginTop: "var(--rv-space-1)", fontSize: "var(--rv-text-sm)" }}
                      >
                        调整范围
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="rv-card">
            <h2 style={{ fontSize: "var(--rv-text-lg)", marginTop: 0 }}>
              版本史（{detail.data.versions.length}）
            </h2>
            <ol style={{ paddingLeft: "var(--rv-space-4)" }}>
              {detail.data.versions.map((v) => (
                <li key={v.id} style={{ marginBottom: "var(--rv-space-2)" }}>
                  <div>
                    v{v.version_number} · {new Date(v.created_at).toLocaleString()} ·{" "}
                    {v.edited_by_actor}
                    {v.edited_by_model ? ` / ${v.edited_by_model}` : ""}
                  </div>
                  <div style={{ color: "var(--rv-ink-soft)", fontSize: "var(--rv-text-sm)" }}>
                    {typeof v.snapshot?.body === "string"
                      ? String(v.snapshot.body).slice(0, 120)
                      : "—"}
                  </div>
                  <button type="button" onClick={() => restore(v.version_number)}>
                    回滚到此版本
                  </button>
                </li>
              ))}
            </ol>
          </div>

          <div className="rv-card">
            <h2 style={{ fontSize: "var(--rv-text-lg)", marginTop: 0 }}>审计史</h2>
            <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
              {detail.data.audit_events.map((e) => (
                <li key={e.id} style={{ fontSize: "var(--rv-text-sm)" }}>
                  {new Date(e.created_at).toLocaleString()} · {e.event_type} · {e.actor}
                </li>
              ))}
            </ul>
          </div>

          <div style={{ display: "flex", gap: "var(--rv-space-2)", alignItems: "center" }}>
            {detail.data.memory.status === "deleted" ? (
              <button
                type="button"
                onClick={undelete}
                style={{ border: "1px solid var(--rv-accent)", borderRadius: "var(--rv-radius-sm)", background: "var(--rv-accent-soft)", color: "var(--rv-accent)", padding: "var(--rv-space-1) var(--rv-space-3)", cursor: "pointer" }}
              >
                从回收站还原
              </button>
            ) : (
              <button
                type="button"
                onClick={() => (confirmingDelete ? remove() : setConfirmingDelete(true))}
                onBlur={() => setConfirmingDelete(false)}
                style={{
                  color: confirmingDelete ? "var(--rv-surface)" : "var(--rv-danger)",
                  background: confirmingDelete ? "var(--rv-danger)" : "transparent",
                  border: "1px solid var(--rv-danger)",
                  borderRadius: "var(--rv-radius-sm)",
                  padding: "var(--rv-space-1) var(--rv-space-3)",
                  cursor: "pointer",
                }}
              >
                {confirmingDelete ? "确认移进回收站？" : "移进回收站"}
              </button>
            )}
            <span style={{ color: "var(--rv-ink-faint)", fontSize: "var(--rv-text-xs)" }}>
              软删除后正文/版本/来源片段都还在，随时能还原；彻底删除要到「记忆」页的回收站里做。
            </span>
          </div>
        </div>
      ) : null}
    </PageShell>
  );
}
