import PageShell from "../components/PageShell";

export default function MigrationAudit() {
  return (
    <PageShell title="遗失记忆审计" note="扫描历史会话里的「记忆写入」线索，只给候选与上下文，判定权在你手里。">
      <div className="rv-card">
        <p style={{ margin: 0, color: "var(--rv-ink-soft)" }}>页面骨架已就位，T9 接入数据与交互。</p>
      </div>
    </PageShell>
  );
}
