import { useParams } from "react-router-dom";
import PageShell from "../components/PageShell";

export default function MemoryDetail() {
  const { id } = useParams();
  return (
    <PageShell
      title="记忆详情 · Genesis"
      note="正文、双时间（发生时间 / 创建时间）、来源模型、spans、版本史、审计史，并可跳回原文。"
    >
      <div className="rv-card">
        <p style={{ margin: 0, color: "var(--rv-ink-soft)" }}>
          memory_id: <code>{id ?? "（未选择）"}</code>
        </p>
        <p style={{ margin: "var(--rv-space-2) 0 0", color: "var(--rv-ink-soft)" }}>
          页面骨架已就位，T9 接入版本史与来源片段。
        </p>
      </div>
    </PageShell>
  );
}
