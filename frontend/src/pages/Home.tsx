import PageShell from "../components/PageShell";

export default function Home() {
  return (
    <PageShell title="首页" note="档案馆概览：会话数、消息数、记忆数、最近导入。T9 接入真实统计。">
      <div className="rv-card">
        <p style={{ margin: 0, color: "var(--rv-ink-soft)" }}>页面骨架已就位，T9 接入数据与交互。</p>
      </div>
    </PageShell>
  );
}
