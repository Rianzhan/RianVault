import PageShell from "../components/PageShell";

export default function ImportPage() {
  return (
    <PageShell title="导入" note="ChatGPT 导出 conversations.json 或 RianVault JSONL v1；导入前可先看对账预览。">
      <div className="rv-card">
        <p style={{ margin: 0, color: "var(--rv-ink-soft)" }}>页面骨架已就位，T9 接入数据与交互。</p>
      </div>
    </PageShell>
  );
}
