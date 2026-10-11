import PageShell from "../components/PageShell";

export default function ExportPage() {
  return (
    <PageShell title="导出 / 备份" note="一键导出 zip（含人类可读 markdown 与可恢复的 jsonl）。仅 Owner 可用。">
      <div className="rv-card">
        <p style={{ margin: 0, color: "var(--rv-ink-soft)" }}>页面骨架已就位，T9 接入数据与交互。</p>
      </div>
    </PageShell>
  );
}
