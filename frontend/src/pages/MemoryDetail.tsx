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
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const detail = useAsync<Detail>(() => api.get(`/memories/${id}`), [id]);

  const startEdit = () => {
    setBody(detail.data?.memory.body ?? "");
    setEditing(true);
  };

  async function save() {
    if (!id || !body.trim()) return;
    setError(null);
    try {
      await api.patch(`/memories/${id}`, { body: body.trim(), reason: "前端编辑" });
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
      setNotice("已软删除（仍可在状态筛选里找回）");
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
                  <li key={s.id} style={{ marginBottom: "var(--rv-space-2)" }}>
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

          <div>
            <button type="button" onClick={remove} style={{ color: "var(--rv-danger)" }}>
              软删除
            </button>
          </div>
        </div>
      ) : null}
    </PageShell>
  );
}
