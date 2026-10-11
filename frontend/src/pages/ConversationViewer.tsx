import PageShell from "../components/PageShell";

export default function ConversationViewer() {
  return (
    <PageShell title="原文" note="连续阅读原始会话，选中一段即可「Add as Evidence / Context」。">
      <div className="rv-card">
        <p style={{ margin: 0, color: "var(--rv-ink-soft)" }}>页面骨架已就位，T9 接入数据与交互。</p>
      </div>
    </PageShell>
  );
}
