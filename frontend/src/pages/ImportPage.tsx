import { useState } from "react";
import PageShell from "../components/PageShell";
import { api, upload } from "../lib/api";
import { useAsync } from "../lib/useAsync";

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

type ImportOut = {
  id: string;
  original_filename: string;
  source_type: string;
  status: string;
  created_at: string;
};

/** 单个文件的上传结果（成功或失败都留痕，不互相顶掉）。 */
type FileOutcome = {
  filename: string;
  ok: boolean;
  detail: ImportResult | null;
  error: string | null;
};

export default function ImportPage() {
  const [files, setFiles] = useState<File[]>([]);
  const [outcomes, setOutcomes] = useState<FileOutcome[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [current, setCurrent] = useState<string | null>(null);

  // 历史导入一直都在：列表来自后端，不会被新导入顶掉
  const history = useAsync<ImportOut[]>(() => api.get("/imports"), []);

  async function run() {
    if (files.length === 0) return;
    setBusy(true);
    setError(null);
    const collected: FileOutcome[] = [];
    try {
      // 逐个上传：一个文件失败不影响其余文件，结果全部累加展示
      for (const f of files) {
        setCurrent(f.name);
        try {
          collected.push({ filename: f.name, ok: true, detail: await upload<ImportResult>("/imports", f), error: null });
        } catch (e) {
          collected.push({ filename: f.name, ok: false, detail: null, error: e instanceof Error ? e.message : String(e) });
        }
      }
      setOutcomes((prev) => [...collected, ...prev]);
      history.reload();
    } finally {
      setBusy(false);
      setCurrent(null);
      setFiles([]);
    }
  }

  return (
    <PageShell
      title="导入"
      note="支持 ChatGPT 导出的 conversations.json 与 RianVault JSONL v1，可一次选多个文件。重复导入同一文件会被识别，不会重复入库。"
    >
      <div className="rv-card">
        <input
          aria-label="选择导出文件（可多选）"
          type="file"
          multiple
          accept=".json,.jsonl,application/json,text/plain"
          onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
        />
        <button
          type="button"
          onClick={run}
          disabled={files.length === 0 || busy}
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
          {busy ? `导入中…（${current ?? ""}）` : `开始导入${files.length ? `（${files.length} 个文件）` : ""}`}
        </button>
        {files.length ? (
          <div style={{ color: "var(--rv-ink-faint)", fontSize: "var(--rv-text-xs)", marginTop: "var(--rv-space-2)" }}>
            已选 {files.length} 个：{files.map((f) => f.name).join("、")}
          </div>
        ) : null}
      </div>

      {error ? (
        <div className="rv-card" role="alert" style={{ marginTop: "var(--rv-space-3)", borderColor: "var(--rv-danger)" }}>
          {error}
        </div>
      ) : null}

      {outcomes.map((o, i) => (
        <div
          key={`${o.filename}-${i}`}
          className="rv-card"
          style={{
            marginTop: "var(--rv-space-3)",
            borderColor: o.ok ? undefined : "var(--rv-danger)",
          }}
        >
          {o.ok && o.detail ? (
            <>
              <div>
                <strong>{o.detail.import_.original_filename}</strong> · 状态：
                <strong>{o.detail.import_.status}</strong>
                {o.detail.already_imported ? "（此前已导入过同一文件，未重复入库）" : null}
              </div>
              <div style={{ fontSize: "var(--rv-text-sm)", color: "var(--rv-ink-soft)" }}>
                类型：{o.detail.import_.source_type}
              </div>
              {o.detail.import_.error ? (
                <div role="alert" style={{ color: "var(--rv-danger)" }}>
                  {o.detail.import_.error}
                </div>
              ) : null}
              <ul style={{ marginTop: "var(--rv-space-2)" }}>
                {Object.entries(o.detail.import_.stats ?? {}).map(([k, v]) => (
                  <li key={k}>
                    {k}：{String(v)}
                  </li>
                ))}
              </ul>
              {o.detail.import_.warnings?.length ? (
                <details>
                  <summary>警告 {o.detail.import_.warnings.length} 条</summary>
                  <ul>
                    {o.detail.import_.warnings.map((w) => (
                      <li key={w}>{w}</li>
                    ))}
                  </ul>
                </details>
              ) : null}
            </>
          ) : (
            <div role="alert" style={{ color: "var(--rv-danger)" }}>
              <strong>{o.filename}</strong> 导入失败：{o.error}
            </div>
          )}
        </div>
      ))}

      <div className="rv-card" style={{ marginTop: "var(--rv-space-3)" }}>
        <div style={{ color: "var(--rv-ink-soft)", fontSize: "var(--rv-text-sm)" }}>
          历史导入（{history.data?.length ?? 0}）—— 都留着，不会被新的顶掉
        </div>
        {history.error ? <div style={{ color: "var(--rv-danger)" }}>{history.error}</div> : null}
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {(history.data ?? []).map((imp) => (
            <li key={imp.id} style={{ marginTop: "var(--rv-space-2)", fontSize: "var(--rv-text-sm)" }}>
              {imp.original_filename} · {imp.status} · {imp.source_type} ·{" "}
              {new Date(imp.created_at).toLocaleString()}
            </li>
          ))}
        </ul>
      </div>
    </PageShell>
  );
}
