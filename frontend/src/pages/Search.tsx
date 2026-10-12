import { useState } from "react";
import { Link } from "react-router-dom";
import PageShell from "../components/PageShell";
import { api } from "../lib/api";

type Hit = {
  message_id: string;
  conversation_id: string;
  conversation_title: string | null;
  source_platform: string | null;
  source_model: string | null;
  role: string;
  content_text: string;
  event_time: string | null;
  score: number;
  match_types: string[];
};

type SearchResponse = { mode: string; count: number; hits: Hit[] };

export default function Search() {
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<"keyword" | "semantic" | "hybrid">("hybrid");
  const [platform, setPlatform] = useState("");
  const [results, setResults] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const body: Record<string, unknown> = { query: query.trim(), mode, limit: 30 };
      if (platform) body.filters = { source_platform: platform };
      setResults(await api.post<SearchResponse>("/search", body));
    } catch (e) {
      setResults(null);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <PageShell
      title="检索"
      note="查询走 POST：私人查询词不会出现在 URL、浏览器历史或服务端日志里。"
    >
      <div className="rv-card">
        <textarea
          aria-label="查询"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          rows={2}
          placeholder="想找什么？可以直接描述，也可以给关键词"
          style={{ width: "100%", padding: "var(--rv-space-2)", border: "1px solid var(--rv-line-strong)", borderRadius: "var(--rv-radius-sm)" }}
        />
        <div style={{ display: "flex", gap: "var(--rv-space-2)", marginTop: "var(--rv-space-2)", flexWrap: "wrap", alignItems: "center" }}>
          <select
            aria-label="检索模式"
            value={mode}
            onChange={(e) => setMode(e.target.value as typeof mode)}
            style={{ padding: "var(--rv-space-2)", border: "1px solid var(--rv-line-strong)", borderRadius: "var(--rv-radius-sm)" }}
          >
            <option value="hybrid">混合</option>
            <option value="semantic">语义</option>
            <option value="keyword">关键词</option>
          </select>
          <input
            aria-label="平台过滤"
            placeholder="平台（可空）"
            value={platform}
            onChange={(e) => setPlatform(e.target.value)}
            style={{ padding: "var(--rv-space-2)", border: "1px solid var(--rv-line-strong)", borderRadius: "var(--rv-radius-sm)" }}
          />
          <button
            type="button"
            onClick={run}
            disabled={!query.trim() || loading}
            style={{
              padding: "var(--rv-space-2) var(--rv-space-3)",
              border: "1px solid var(--rv-accent)",
              borderRadius: "var(--rv-radius-sm)",
              background: "var(--rv-accent)",
              color: "var(--rv-surface)",
              cursor: "pointer",
            }}
          >
            {loading ? "检索中…" : "检索"}
          </button>
        </div>
      </div>

      {error ? (
        <div className="rv-card" role="alert" style={{ marginTop: "var(--rv-space-3)", borderColor: "var(--rv-danger)" }}>
          {error}
        </div>
      ) : null}

      {results ? (
        <div style={{ marginTop: "var(--rv-space-3)" }}>
          <p className="rv-page-note">
            命中 {results.count} 条（{results.mode}）
          </p>
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {results.hits.map((h) => (
              <li key={h.message_id} className="rv-card" style={{ marginBottom: "var(--rv-space-2)" }}>
                <div style={{ fontSize: "var(--rv-text-xs)", color: "var(--rv-ink-faint)" }}>
                  {h.role}
                  {h.source_model ? ` · ${h.source_model}` : ""} ·{" "}
                  {h.event_time ? new Date(h.event_time).toLocaleString() : "（无时间）"} · 得分{" "}
                  {h.score} · {h.match_types.join("+")}
                </div>
                <p style={{ whiteSpace: "pre-wrap", margin: "var(--rv-space-1) 0" }}>{h.content_text}</p>
                <Link to={`/conversations/${h.conversation_id}`} style={{ fontSize: "var(--rv-text-sm)" }}>
                  跳回原文{h.conversation_title ? `：${h.conversation_title}` : ""}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </PageShell>
  );
}
