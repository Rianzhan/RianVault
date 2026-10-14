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

type Me = { name: string; role: string; can_admin: boolean };

const TYPES = ["", "fact", "preference", "event", "relationship", "goal", "note"];

function listParams(q: string, type: string, status: string, inBin: boolean): string {
  const params = new URLSearchParams({ limit: "200" });
  if (q.trim()) params.set("q", q.trim());
  if (type) params.set("memory_type", type);
  if (inBin) params.set("status", "deleted");
  else if (status) params.set("status", status);
  return params.toString();
}

export default function MemoryLibrary() {
  const [q, setQ] = useState("");
  const [type, setType] = useState("");
  const [status, setStatus] = useState("");
  const [inBin, setInBin] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newBody, setNewBody] = useState("");
  const [error, setError] = useState<string | null>(null);
  // 二次确认：先点一下进入待确认态，再点一次才真的执行
  const [pending, setPending] = useState<{ id: string; action: "purge" | "undelete" } | null>(null);

  // 只有 Owner 能删/还原/彻底删除（后端用 require_owner 强制校验，这里只是别摆出必然 403 的按钮）。
  // 旧后端还没有 /auth/me 时，宁可按 Owner 显示，不要把功能藏起来。
  const me = useAsync<Me>(() => api.get("/auth/me"), []);
  const isOwner = me.data ? me.data.can_admin : true;

  const memories = useAsync<Memory[]>(
    () => api.get(`/memories?${listParams(q, type, status, inBin)}`),
    [q, type, status, inBin],
  );
  const trashed = useAsync<Memory[]>(() => api.get("/memories?status=deleted&limit=200"), []);

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

  async function runAction(m: Memory, action: "purge" | "undelete") {
    setError(null);
    try {
      if (action === "purge") await api.del(`/memories/${m.id}/purge`);
      else await api.post(`/memories/${m.id}/undelete`);
      setPending(null);
      memories.reload();
      trashed.reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setPending(null);
    }
  }

  function actionButton(m: Memory, action: "purge" | "undelete", label: string) {
    // 只有**毁灭性**操作（彻底删除）要点两次确认；还原是无损的，别给人添堵。
    const armed = pending?.id === m.id && pending.action === action;
    const needsConfirm = action === "purge";
    const danger = action === "purge";
    const onClick = () => {
      if (!needsConfirm) {
        void runAction(m, action);
        return;
      }
      if (armed) {
        void runAction(m, action);
        return;
      }
      setPending({ id: m.id, action });
    };
    const text = needsConfirm && armed ? `确认${label}？` : label;
    return (
      <button
        type="button"
        aria-label={text}
        onClick={onClick}
        style={{
          padding: "2px 10px",
          border: `1px solid ${danger ? "var(--rv-danger)" : "var(--rv-accent)"}`,
          borderRadius: "var(--rv-radius-sm)",
          background: armed && needsConfirm ? "var(--rv-danger)" : "transparent",
          color: danger ? "var(--rv-danger)" : "var(--rv-accent)",
          cursor: "pointer",
          fontSize: "var(--rv-text-xs)",
        }}
      >
        {text}
      </button>
    );
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
            disabled={inBin}
            onChange={(e) => setStatus(e.target.value)}
            style={{ padding: "var(--rv-space-2)", border: "1px solid var(--rv-line-strong)", borderRadius: "var(--rv-radius-sm)" }}
          >
            <option value="">活跃</option>
            <option value="draft">草稿</option>
            <option value="archived">归档</option>
            {inBin ? <option value="deleted">已删除</option> : null}
          </select>
          <button
            type="button"
            aria-label="切换回收站"
            onClick={() => setInBin((v) => !v)}
            style={{
              padding: "var(--rv-space-2) var(--rv-space-3)",
              border: `1px solid ${inBin ? "var(--rv-danger)" : "var(--rv-line-strong)"}`,
              borderRadius: "var(--rv-radius-sm)",
              background: inBin ? "var(--rv-danger)" : "transparent",
              color: inBin ? "var(--rv-surface)" : "var(--rv-ink-soft)",
              cursor: "pointer",
            }}
          >
            回收站（{trashed.data?.length ?? 0}）
          </button>
        </div>

        {inBin ? (
          <p className="rv-page-note" style={{ marginTop: "var(--rv-space-2)" }}>
            这里是软删除的记忆：正文、版本史、来源片段都还在，随时能还原。
            「彻底删除」会连版本一起物理抹掉（只留一条审计留痕），且需要点两次确认——
            这一步只有 Owner 能做，AI 身份没有这个权限。
          </p>
        ) : (
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
        )}
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
            {inBin && isOwner ? (
              <div style={{ display: "flex", gap: "var(--rv-space-2)", marginTop: "var(--rv-space-2)" }}>
                {actionButton(m, "undelete", "还原")}
                {actionButton(m, "purge", "彻底删除")}
              </div>
            ) : null}
          </li>
        ))}
      </ul>
      {memories.data && memories.data.length === 0 ? (
        <p className="rv-page-note">
          {inBin
            ? "回收站是空的——没有软删除的记忆。"
            : "还没有记忆。去「原文」选一段建第一条吧。"}
        </p>
      ) : null}
    </PageShell>
  );
}
