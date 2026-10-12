import { useState } from "react";
import PageShell from "../components/PageShell";
import { upload } from "../lib/api";

type ImportResult = {
  import_: {
    id: string;
    status: string;
    source_type: string;
    original_filename: string;
    stats: Record<string, number>;
    warnings: string[] | null;
    error: string | null;
  };
  already_imported: boolean;
};

export default function ImportPage() {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run() {
    if (!file) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(await upload<ImportResult>("/imports", file));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const stats = result?.import_.stats ?? {};

  return (
    <PageShell
      title="导入"
      note="支持 ChatGPT 导出的 conversations.json 与 RianVault JSONL v1。重复导入同一文件会被识别，不会重复入库。"
    >
      <div className="rv-card">
        <input
          aria-label="选择导出文件"
          type="file"
          accept=".json,.jsonl,application/json,text/plain"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
        <button
          type="button"
          onClick={run}
          disabled={!file || busy}
          style={{
            marginLeft: "var(--rv-space-2)",
            padding: "var(--rv-space-2) var(--rv-space-3)",
            border: "1px solid var(--rv-accent)",
            borderRadius: "var(--rv-radius-sm)",
            background: "var(--rv-accent)",
            color: "var(--rv-surface)",
            cursor: "pointer",
          }}
        >
          {busy ? "导入中…" : "开始导入"}
        </button>
      </div>

      {error ? (
        <div className="rv-card" role="alert" style={{ marginTop: "var(--rv-space-3)", borderColor: "var(--rv-danger)" }}>
          {error}
        </div>
      ) : null}

      {result ? (
        <div className="rv-card" style={{ marginTop: "var(--rv-space-3)" }}>
          <div>
            状态：<strong>{result.import_.status}</strong>
            {result.already_imported ? "（此前已导入过同一文件）" : null}
          </div>
          <div style={{ fontSize: "var(--rv-text-sm)", color: "var(--rv-ink-soft)" }}>
            类型：{result.import_.source_type} · 文件：{result.import_.original_filename}
          </div>
          {result.import_.error ? (
            <div role="alert" style={{ color: "var(--rv-danger)" }}>
              {result.import_.error}
            </div>
          ) : null}
          <ul style={{ marginTop: "var(--rv-space-2)" }}>
            {Object.entries(stats).map(([k, v]) => (
              <li key={k}>
                {k}：{String(v)}
              </li>
            ))}
          </ul>
          {result.import_.warnings?.length ? (
            <details>
              <summary>警告 {result.import_.warnings.length} 条</summary>
              <ul>
                {result.import_.warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            </details>
          ) : null}
        </div>
      ) : null}
    </PageShell>
  );
}
