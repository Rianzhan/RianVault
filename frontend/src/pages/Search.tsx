import PageShell from "../components/PageShell";

export default function Search() {
  return (
    <PageShell title="检索" note="语义 / 关键词 / 混合检索，结果可跳回原文。查询走 POST，不进 URL 与日志。">
      <div className="rv-card">
        <p style={{ margin: 0, color: "var(--rv-ink-soft)" }}>页面骨架已就位，T9 接入数据与交互。</p>
      </div>
    </PageShell>
  );
}
