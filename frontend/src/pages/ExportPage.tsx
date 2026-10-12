import { useState } from "react";
import PageShell from "../components/PageShell";
import { api } from "../lib/api";
import { useAsync } from "../lib/useAsync";

type ExportItem = { export_id: string; size_bytes: number; created_at: string };
type ExportResult = { export_id: string; sha256: string; size_bytes: number; counts: Record<string, number> };

export default function ExportPage() {
  const exports = useAsync<ExportItem[]>(() => api.get("/export"), []);
  const [created, setCreated] = useState<ExportResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function create() {
    setError(null);
    try {
      setCreated(await api.post<ExportResult>("/export"));
      exports.reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <PageShell
      title="导出 / 备份"
      note="导出的 zip 里有可人工阅读的 markdown，也有能重建数据库的 jsonl。向量不导出（可再生）。仅 Owner 可用。"
    >
      <div className="rv-card">
        <button
          type="button"
          onClick={create}
          style={{
            padding: "var(--rv-space-2) var(--rv-space-3)",
            border: "1px solid var(--rv-accent)",
            borderRadius: "var(--rv-radius-sm)",
            background: "var(--rv-accent)",
            color: "var(--rv-surface)",
            cursor: "pointer",
          }}
        >
          生成新的导出包
        </button>
        {created ? (
          <div style={{ marginTop: "var(--rv-space-2)", fontSize: "var(--rv-text-sm)" }}>
            已生成：<code>{created.export_id}</code>
            <div style={{ color: "var(--rv-ink-faint)" }}>sha256: {created.sha256.slice(0, 32)}…</div>
          </div>
        ) : null}
        {error ? (
          <div role="alert" style={{ color: "var(--rv-danger)" }}>
            {error}
          </div>
        ) : null}
      </div>

      {exports.error ? (
        <div className="rv-card" role="alert" style={{ marginTop: "var(--rv-space-3)", borderColor: "var(--rv-danger)" }}>
          {exports.error}
        </div>
      ) : null}

      <div className="rv-card" style={{ marginTop: "var(--rv-space-3)" }}>
        <div style={{ color: "var(--rv-ink-soft)", fontSize: "var(--rv-text-sm)" }}>
          已有导出（{exports.data?.length ?? 0}）
        </div>
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {(exports.data ?? []).map((item) => (
            <li key={item.export_id} style={{ marginTop: "var(--rv-space-2)" }}>
              <a
                href={`/api/export/${item.export_id}/download`}
                style={{ color: "var(--rv-accent)" }}
              >
                {item.export_id}
              </a>
              <div style={{ color: "var(--rv-ink-faint)", fontSize: "var(--rv-text-xs)" }}>
                {Math.round(item.size_bytes / 1024)} KB ·{" "}
                {new Date(item.created_at).toLocaleString()}
              </div>
            </li>
          ))}
        </ul>
        <p className="rv-page-note" style={{ marginTop: "var(--rv-space-2)" }}>
          下载链接需要带 Authorization 头，浏览器直接点可能 401 —— 用 curl 或在设置里保存 token 后再试。
        </p>
      </div>
    </PageShell>
  );
}
