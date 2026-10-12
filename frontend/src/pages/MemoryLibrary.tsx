import { useState } from "react";
import { Link } from "react-router-dom";
import PageShell from "../components/PageShell";
import { api } from "../lib/api";
import { useAsync } from "../lib/useAsync";

type Memory = {
  id: string;
  title: string | null;
  body: string;
  memory_type: string;
  status: string;
  event_time_start: string | null;
  event_time_end: string | null;
  created_at: string;
  created_by_actor: string;
  created_by_model: string | null;
  current_version: number;
  tags: string[];
};

const TYPES = ["", "fact", "preference", "event", "relationship", "goal", "note"];

export default function MemoryLibrary() {
  const [q, setQ] = useState("");
  const [type, setType] = useState("");
  const [status, setStatus] = useState("");
  const [newTitle, setNewTitle] = useState("");
  const [newBody, setNewBody] = useState("");
  const [error, setError] = useState<string | null>(null);

  const memories = useAsync<Memory[]>(
    () => {
      const params = new URLSearchParams({ limit: "200" });
      if (q.trim()) params.set("q", q.trim());
      if (type) params.set("memory_type", type);
      if (status) params.set("status", status);
      return api.get(`/memories?${params.toString()}`);
    },
    [q, type, status],
  );

  async function create() {
    if (!newBody.trim()) return;
    setError(null);
    try {
      await api.post("/memories", {
        title: newTitle.trim() || null,
        body: newBody.trim(),
        memory_type: type || "note",
      });
      setNewTitle("");
      setNewBody("");
      memories.reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <PageShell title="记忆" note="每条记忆都能追溯到原文片段；编辑会留下新版本，历史不会被改写。">
      <div className="rv-card" style={{ marginBottom: "var(--rv-space-3)" }}>
        <div style={{ display: "flex", gap: "var(--rv-space-2)", flexWrap: "wrap" }}>
          <input
            aria-label="搜索记忆"
            placeholder="标题 / 正文包含…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            style={{ flex: "1 1 200px", padding: "var(--rv-space-2)", border: "1px solid var(--rv-line-strong)", borderRadius: "var(--rv-radius-sm)" }}
          />
          <select
            aria-label="类型"
            value={type}
            onChange={(e) => setType(e.target.value)}
            style={{ padding: "var(--rv-space-2)", border: "1px solid var(--rv-line-strong)", borderRadius: "var(--rv-radius-sm)" }}
          >
            {TYPES.map((t) => (
              <option key={t} value={t}>
                {t || "全部类型"}
              </option>
            ))}
          </select>
          <select
            aria-label="状态"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            style={{ padding: "var(--rv-space-2)", border: "1px solid var(--rv-line-strong)", borderRadius: "var(--rv-radius-sm)" }}
          >
            <option value="">活跃</option>
            <option value="draft">草稿</option>
            <option value="archived">归档</option>
            <option value="deleted">已删除</option>
          </select>
        </div>

        <div style={{ display: "flex", gap: "var(--rv-space-2)", marginTop: "var(--rv-space-2)", flexWrap: "wrap" }}>
          <input
            aria-label="新记忆标题"
            placeholder="新记忆标题"
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            style={{ flex: "1 1 160px", padding: "var(--rv-space-2)", border: "1px solid var(--rv-line-strong)", borderRadius: "var(--rv-radius-sm)" }}
          />
          <input
            aria-label="新记忆正文"
            placeholder="新记忆正文"
            value={newBody}
            onChange={(e) => setNewBody(e.target.value)}
            style={{ flex: "2 1 240px", padding: "var(--rv-space-2)", border: "1px solid var(--rv-line-strong)", borderRadius: "var(--rv-radius-sm)" }}
          />
          <button
            type="button"
            onClick={create}
            disabled={!newBody.trim()}
            style={{
              padding: "var(--rv-space-2) var(--rv-space-3)",
              border: "1px solid var(--rv-accent)",
              borderRadius: "var(--rv-radius-sm)",
              background: "var(--rv-accent)",
              color: "var(--rv-surface)",
              cursor: "pointer",
            }}
          >
            新建
          </button>
        </div>
        {error ? (
          <p role="alert" style={{ color: "var(--rv-danger)", fontSize: "var(--rv-text-sm)" }}>
            {error}
          </p>
        ) : null}
      </div>

      {memories.error ? (
        <div className="rv-card" role="alert" style={{ borderColor: "var(--rv-danger)" }}>
          {memories.error}
        </div>
      ) : null}

      <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
        {(memories.data ?? []).map((m) => (
          <li key={m.id} className="rv-card" style={{ marginBottom: "var(--rv-space-2)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: "var(--rv-space-2)" }}>
              <Link to={`/memories/${m.id}`} style={{ fontWeight: 600 }}>
                {m.title ?? m.body.slice(0, 24)}
              </Link>
              <span style={{ color: "var(--rv-ink-faint)", fontSize: "var(--rv-text-xs)" }}>
                v{m.current_version} · {m.memory_type} · {m.status}
              </span>
            </div>
            <p style={{ margin: "var(--rv-space-1) 0 0", whiteSpace: "pre-wrap" }}>{m.body}</p>
            <div style={{ color: "var(--rv-ink-faint)", fontSize: "var(--rv-text-xs)" }}>
              发生：{m.event_time_start ?? "未标注"} → {m.event_time_end ?? "—"} · 创建：
              {new Date(m.created_at).toLocaleDateString()} · 由 {m.created_by_actor}
              {m.created_by_model ? ` / ${m.created_by_model}` : ""}
            </div>
          </li>
        ))}
      </ul>
      {memories.data && memories.data.length === 0 ? (
        <p className="rv-page-note">还没有记忆。去「原文」选一段建第一条吧。</p>
      ) : null}
    </PageShell>
  );
}
