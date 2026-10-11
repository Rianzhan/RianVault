import PageShell from "../components/PageShell";

export default function MemoryLibrary() {
  return (
    <PageShell title="记忆" note="按类型、时间、标签浏览衍生记忆；每条都能追溯到原文片段。">
      <div className="rv-card">
        <p style={{ margin: 0, color: "var(--rv-ink-soft)" }}>页面骨架已就位，T9 接入数据与交互。</p>
      </div>
    </PageShell>
  );
}
