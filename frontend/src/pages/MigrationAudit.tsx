import { useState } from "react";
import PageShell from "../components/PageShell";
import { api } from "../lib/api";
import { useAsync } from "../lib/useAsync";

type Candidate = {
  id: string;
  matched_signal: string;
  verdict: string;
  signal_message: { id: string; role: string; content_text: string; event_time: string | null };
  context: { id: string; role: string; content_text: string; event_time: string | null }[];
  linked_memory_id: string | null;
  note: string | null;
};

type ScanReport = { created: number; existing: number; total: number };

const VERDICTS = [
  { value: "successful_write", label: "确实写入了" },
  { value: "failed_write", label: "写入失败" },
  { value: "retry_success", label: "重试后成功" },
  { value: "edit", label: "是修改" },
  { value: "delete", label: "是删除" },
  { value: "uncertain", label: "不确定" },
  { value: "ignore", label: "忽略" },
];

function today(daysAgo: number) {
  const d = new Date();
  d.setDate(d.getDate() - daysAgo);
  return d.toISOString().slice(0, 10);
}

export default function MigrationAudit() {
  const [from, setFrom] = useState(today(3650));
  const [to, setTo] = useState(today(0));
  const [report, setReport] = useState<ScanReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const candidates = useAsync<Candidate[]>(
    () => api.get("/audit/migration-candidates?limit=200"),
    [],
  );

  async function scan() {
    setBusy(true);
    setError(null);
    try {
      setReport(await api.post<ScanReport>("/audit/migration-candidates/scan", { scan_from: from, scan_to: to }));
      candidates.reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function setVerdict(id: string, verdict: string) {
    setError(null);
    try {
      await api.post(`/audit/migration-candidates/${id}/verdict`, { verdict });
      candidates.reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function createMemory(c: Candidate) {
    setError(null);
    const body = window.prompt("把这条线索整理成记忆：", c.signal_message.content_text.slice(0, 80));
    if (!body) return;
    try {
      await api.post(`/audit/migration-candidates/${c.id}/create-memory`, {
        body,
        span_type: "evidence",
        context_start_message_id: c.context[0]?.id ?? c.signal_message.id,
        context_end_message_id: c.context[c.context.length - 1]?.id ?? c.signal_message.id,
        memory_type: "note",
      });
      candidates.reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <PageShell
      title="遗失记忆审计"
      note="系统只负责把「看起来像记忆写入」的线索挑出来，并附上上下文；是否真写入过，判定权始终在你手里。"
    >
      <div className="rv-card">
        <div style={{ display: "flex", gap: "var(--rv-space-2)", flexWrap: "wrap", alignItems: "center" }}>
          <input
            aria-label="起始日期"
            type="date"
            value={from}
            onChange={(e) => setFrom(e.target.value)}
            style={{ padding: "var(--rv-space-2)", border: "1px solid var(--rv-line-strong)", borderRadius: "var(--rv-radius-sm)" }}
          />
          <span>→</span>
          <input
            aria-label="结束日期"
            type="date"
            value={to}
            onChange={(e) => setTo(e.target.value)}
            style={{ padding: "var(--rv-space-2)", border: "1px solid var(--rv-line-strong)", borderRadius: "var(--rv-radius-sm)" }}
          />
          <button
            type="button"
            onClick={scan}
            disabled={busy}
            style={{
              padding: "var(--rv-space-2) var(--rv-space-3)",
              border: "1px solid var(--rv-accent)",
              borderRadius: "var(--rv-radius-sm)",
              background: "var(--rv-accent)",
              color: "var(--rv-surface)",
              cursor: "pointer",
            }}
          >
            {busy ? "扫描中…" : "扫描候选"}
          </button>
          {report ? (
            <span style={{ fontSize: "var(--rv-text-sm)", color: "var(--rv-ink-soft)" }}>
              新增 {report.created} · 已存在 {report.existing} · 合计 {report.total}
            </span>
          ) : null}
        </div>
        {error ? (
          <div role="alert" style={{ color: "var(--rv-danger)", marginTop: "var(--rv-space-2)" }}>
            {error}
          </div>
        ) : null}
      </div>

      {candidates.error ? (
        <div className="rv-card" role="alert" style={{ marginTop: "var(--rv-space-3)", borderColor: "var(--rv-danger)" }}>
          {candidates.error}
        </div>
      ) : null}

      <ul style={{ listStyle: "none", padding: 0, margin: "var(--rv-space-3) 0 0" }}>
        {(candidates.data ?? []).map((c) => (
          <li key={c.id} className="rv-card" style={{ marginBottom: "var(--rv-space-3)" }}>
            <div style={{ fontSize: "var(--rv-text-xs)", color: "var(--rv-ink-faint)" }}>
              命中信号「{c.matched_signal}」 · 当前判定：{c.verdict}
              {c.linked_memory_id ? " · 已生成记忆" : ""}
            </div>
            <div style={{ marginTop: "var(--rv-space-1)" }}>
              <strong>{c.signal_message.role}</strong>：{c.signal_message.content_text}
            </div>
            <details>
              <summary>上下文（{c.context.length} 条）</summary>
              <ul style={{ listStyle: "none", padding: 0 }}>
                {c.context.map((m) => (
                  <li key={m.id} style={{ fontSize: "var(--rv-text-sm)", color: "var(--rv-ink-soft)" }}>
                    {m.role}：{m.content_text}
                  </li>
                ))}
              </ul>
            </details>
            <div style={{ display: "flex", gap: "var(--rv-space-2)", flexWrap: "wrap", marginTop: "var(--rv-space-2)" }}>
              {VERDICTS.map((v) => (
                <button
                  key={v.value}
                  type="button"
                  onClick={() => setVerdict(c.id, v.value)}
                  style={{
                    padding: "var(--rv-space-1) var(--rv-space-2)",
                    border: "1px solid var(--rv-line-strong)",
                    borderRadius: "var(--rv-radius-sm)",
                    background: c.verdict === v.value ? "var(--rv-accent-soft)" : "transparent",
                    cursor: "pointer",
                    fontSize: "var(--rv-text-sm)",
                  }}
                >
                  {v.label}
                </button>
              ))}
              <button
                type="button"
                onClick={() => createMemory(c)}
                style={{
                  padding: "var(--rv-space-1) var(--rv-space-2)",
                  border: "1px solid var(--rv-accent)",
                  borderRadius: "var(--rv-radius-sm)",
                  background: "transparent",
                  color: "var(--rv-accent)",
                  cursor: "pointer",
                  fontSize: "var(--rv-text-sm)",
                }}
              >
                整理成记忆
              </button>
            </div>
          </li>
        ))}
      </ul>
    </PageShell>
  );
}
