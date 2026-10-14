import { useState } from "react";
import { Link } from "react-router-dom";
import PageShell from "../components/PageShell";
import { api } from "../lib/api";
import { highlight, termsOf } from "../lib/highlight";
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
  chunk_index: number | null;
  matched_chunk_text: string | null;
};

const MATCH_LABEL: Record<string, { label: string; color: string; bg: string }> = {
  semantic: { label: "语义", color: "var(--rv-accent)", bg: "var(--rv-accent-soft)" },
  keyword: { label: "关键词", color: "var(--rv-success, #1a7f37)", bg: "var(--rv-success-soft, #e6f4ea)" },
};

type SearchResponse = { mode: string; count: number; hits: Hit[] };
type Stats = { messages: number; indexed_messages: number; indexable_messages: number };

export default function Search() {
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<"keyword" | "semantic" | "hybrid">("hybrid");
  const [platform, setPlatform] = useState("");
  const [results, setResults] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [building, setBuilding] = useState(false);
  const [buildNote, setBuildNote] = useState<string | null>(null);
  const [model, setModel] = useState("");
  const [role, setRole] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  // 语义检索只看得到"已索引"的消息——新导入还没建索引时，必须提示，否则像灵异事件
  const stats = useAsync<Stats>(() => api.get("/stats"), []);
  // 分母用"有正文的消息数"：纯图片/空消息本来就不进索引，不算漏
  const indexable = stats.data?.indexable_messages ?? stats.data?.messages ?? 0;
  const indexed = stats.data?.indexed_messages ?? 0;
  const indexStale = indexable > indexed;
  const indexEmpty = indexable > 0 && indexed === 0;

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
      const filters: Record<string, unknown> = {};
      if (platform) filters.source_platform = platform;
      if (model) filters.source_model = model;
      if (role) filters.role = role;
      if (dateFrom) filters.date_from = dateFrom;
      if (dateTo) filters.date_to = dateTo;
      if (Object.keys(filters).length) body.filters = filters;
      setResults(await api.post<SearchResponse>("/search", body));
    } catch (e) {
      setResults(null);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  const terms = termsOf(query);

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
              : `有 ${indexable - indexed} 条消息还没进语义索引（导入后不会自动建索引），语义检索会漏掉它们。`}
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
              已索引 {indexed} / {indexable} 条 · 仅 Owner 可执行
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
          <input
            aria-label="模型过滤"
            placeholder="模型（如 gpt-4o，可空）"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            style={{ padding: "var(--rv-space-2)", border: "1px solid var(--rv-line-strong)", borderRadius: "var(--rv-radius-sm)" }}
          />
          <select
            aria-label="角色过滤"
            value={role}
            onChange={(e) => setRole(e.target.value)}
            style={{ padding: "var(--rv-space-2)", border: "1px solid var(--rv-line-strong)", borderRadius: "var(--rv-radius-sm)" }}
          >
            <option value="">全部角色</option>
            <option value="user">user</option>
            <option value="assistant">assistant</option>
            <option value="system">system</option>
          </select>
          <input
            aria-label="起始日期"
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            style={{ padding: "var(--rv-space-2)", border: "1px solid var(--rv-line-strong)", borderRadius: "var(--rv-radius-sm)" }}
          />
          <span style={{ color: "var(--rv-ink-faint)" }}>→</span>
          <input
            aria-label="结束日期"
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
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
            {results.hits.map((h) => {
              const showChunk = !!h.matched_chunk_text && h.matched_chunk_text !== h.content_text;
              return (
                <li key={h.message_id} className="rv-card" style={{ marginBottom: "var(--rv-space-2)" }}>
                  <div style={{ fontSize: "var(--rv-text-xs)", color: "var(--rv-ink-faint)", display: "flex", flexWrap: "wrap", gap: "var(--rv-space-1)", alignItems: "center" }}>
                    <span>
                      {h.role}
                      {h.source_model ? ` · ${h.source_model}` : ""} ·{" "}
                      {h.event_time ? new Date(h.event_time).toLocaleString() : "（无时间）"} · 得分{" "}
                      {h.score}
                    </span>
                    {h.match_types.map((mt) => {
                      const m = MATCH_LABEL[mt];
                      return (
                        <span
                          key={mt}
                          style={{
                            fontSize: "var(--rv-text-xs)",
                            color: m.color,
                            background: m.bg,
                            border: `1px solid ${m.color}`,
                            borderRadius: "999px",
                            padding: "0 8px",
                            lineHeight: "1.4",
                          }}
                        >
                          {m.label}
                        </span>
                      );
                    })}
                  </div>
                  {showChunk ? (
                    <div
                      style={{
                        margin: "var(--rv-space-2) 0",
                        padding: "var(--rv-space-2)",
                        background: "var(--rv-accent-soft)",
                        borderLeft: "3px solid var(--rv-accent)",
                        borderRadius: "var(--rv-radius-sm)",
                      }}
                    >
                      <div style={{ fontSize: "var(--rv-text-xs)", color: "var(--rv-accent)", fontWeight: 600, marginBottom: "var(--rv-space-1)" }}>
                        语义命中片段（向量库里真正比对的就是这段，而不是整条原文）
                      </div>
                      <p style={{ whiteSpace: "pre-wrap", margin: 0, fontSize: "var(--rv-text-sm)" }}>
                        {highlight(h.matched_chunk_text as string, terms)}
                      </p>
                    </div>
                  ) : null}
                  <p style={{ whiteSpace: "pre-wrap", margin: "var(--rv-space-1) 0" }}>
                    {highlight(h.content_text, terms)}
                  </p>
                  <Link to={`/conversations/${h.conversation_id}`} style={{ fontSize: "var(--rv-text-sm)" }}>
                    跳回原文{h.conversation_title ? `：${h.conversation_title}` : ""}
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}
    </PageShell>
  );
}
