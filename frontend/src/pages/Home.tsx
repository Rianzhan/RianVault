import { Link } from "react-router-dom";
import PageShell from "../components/PageShell";
import { api } from "../lib/api";
import { useAsync } from "../lib/useAsync";

type Stats = {
  conversations: number;
  messages: number;
  memories: number;
  spans: number;
  indexed_messages: number;
  unreviewed_candidates: number;
  actor: string;
};

function Metric({
  label,
  value,
  hint,
}: {
  label: string;
  value: number;
  hint?: React.ReactNode;
}) {
  return (
    <div className="rv-card">
      <div style={{ color: "var(--rv-ink-soft)", fontSize: "var(--rv-text-sm)" }}>{label}</div>
      <div
        style={{
          fontFamily: "var(--rv-font-serif)",
          fontSize: "var(--rv-text-xl)",
          marginTop: "var(--rv-space-1)",
        }}
      >
        {value}
      </div>
      {hint ? (
        <div style={{ color: "var(--rv-ink-faint)", fontSize: "var(--rv-text-xs)" }}>{hint}</div>
      ) : null}
    </div>
  );
}

export default function Home() {
  const stats = useAsync<Stats>(() => api.get("/stats"), []);

  return (
    <PageShell title="首页" note="档案馆概览。所有数字都是本机统计，不含任何正文。">
      {stats.error ? (
        <div className="rv-card" role="alert" style={{ borderColor: "var(--rv-danger)" }}>
          {stats.error}
        </div>
      ) : null}

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
          gap: "var(--rv-space-3)",
        }}
      >
        <Metric label="会话" value={stats.data?.conversations ?? 0} />
        <Metric label="原始消息" value={stats.data?.messages ?? 0} hint="第一手材料" />
        <Metric
          label="已索引消息"
          value={stats.data?.indexed_messages ?? 0}
          hint="向量索引可再生"
        />
        <Metric label="记忆" value={stats.data?.memories ?? 0} />
        <Metric label="来源片段" value={stats.data?.spans ?? 0} hint="evidence / context" />
        <Metric
          label="待审阅线索"
          value={stats.data?.unreviewed_candidates ?? 0}
          hint={<Link to="/migration-audit">去打捞</Link>}
        />
      </div>

      <p className="rv-page-note" style={{ marginTop: "var(--rv-space-4)" }}>
        当前身份：<code>{stats.data?.actor ?? "…"}</code>
        {stats.loading ? "（加载中）" : null}
      </p>
    </PageShell>
  );
}
