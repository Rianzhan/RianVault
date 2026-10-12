import { useState } from "react";
import { Link } from "react-router-dom";
import PageShell from "../components/PageShell";
import { api } from "../lib/api";
import { useAsync } from "../lib/useAsync";

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
type Stats = { messages: number; indexed_messages: number };

export default function Search() {
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<"keyword" | "semantic" | "hybrid">("hybrid");
  const [platform, setPlatform] = useState("");
  const [results, setResults] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [building, setBuilding] = useState(false);
  const [buildNote, setBuildNote] = useState<string | null>(null);

  // 语义检索只看得到"已索引"的消息——新导入还没建索引时，必须提示，否则像灵异事件
  const stats = useAsync<Stats>(() => api.get("/stats"), []);
  const total = stats.data?.messages ?? 0;
  const indexed = stats.data?.indexed_messages ?? 0;
  const indexStale = total > indexed;
  const indexEmpty = total > 0 && indexed === 0;

  async function buildIndex() {
    setBuilding(true);
    setBuildNote(null);
    try {
      const result = await api.post<{ chunks: number }>("/index/build", {});
      setBuildNote(`索引已补齐：本次新增 ${result.chunks} 块。`);
      stats.reload();
    } catch (e) {
      setBuildNote(e instanceof Error ? e.message : String(e));
    } finally {
      setBuilding(false);
    }
  }

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
      {indexStale ? (
        <div
          className="rv-card"
          role="status"
          style={{ marginBottom: "var(--rv-space-3)", borderColor: "var(--rv-accent)" }}
        >
          <div style={{ fontSize: "var(--rv-text-sm)" }}>
            {indexEmpty
              ? "语义索引还没有建立：现在用「语义/混合」检索只会得到 0 条（关键词检索不受影响）。"
              : `有 ${total - indexed} 条消息还没进语义索引（导入后不会自动建索引），语义检索会漏掉它们。`}
          </div>
          <div style={{ display: "flex", gap: "var(--rv-space-2)", marginTop: "var(--rv-space-2)", alignItems: "center" }}>
            <button
              type="button"
              onClick={buildIndex}
              disabled={building}
              style={{
                padding: "var(--rv-space-1) var(--rv-space-3)",
                border: "1px solid var(--rv-accent)",
                borderRadius: "var(--rv-radius-sm)",
                background: "var(--rv-accent-soft)",
                color: "var(--rv-accent)",
                cursor: "pointer",
                fontSize: "var(--rv-text-sm)",
              }}
            >
              {building ? "建索引中（消息多时要等一会）…" : "补齐语义索引"}
            </button>
            <span style={{ color: "var(--rv-ink-faint)", fontSize: "var(--rv-text-xs)" }}>
              已索引 {indexed} / {total} 条 · 仅 Owner 可执行
            </span>
          </div>
          {buildNote ? (
            <div style={{ color: "var(--rv-ink-soft)", fontSize: "var(--rv-text-sm)", marginTop: "var(--rv-space-2)" }}>
              {buildNote}
            </div>
          ) : null}
        </div>
      ) : null}

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
            命中 {results.count} 条（{results.mode}）· 关键词=包含匹配，语义=意思相近，混合=两者合并
          </p>
          {results.count === 0 && mode !== "keyword" && indexStale ? (
            <p className="rv-page-note" style={{ color: "var(--rv-accent)" }}>
              0 条很可能是因为语义索引没覆盖全部消息（上面有补齐按钮）；或者换「关键词」模式试试精确字词。
            </p>
          ) : null}
          {results.count === 0 && mode === "keyword" ? (
            <p className="rv-page-note">
              关键词是「整词包含」匹配：换个更短的字（如单字）或换种说法再试。
            </p>
          ) : null}
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
