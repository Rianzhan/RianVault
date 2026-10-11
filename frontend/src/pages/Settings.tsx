import { useEffect, useState } from "react";
import PageShell from "../components/PageShell";
import { getToken, setToken } from "../lib/api";

export default function Settings() {
  const [token, setTokenValue] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setTokenValue(getToken() ?? "");
  }, []);

  return (
    <PageShell title="设置" note="访问令牌只存放在浏览器会话里（sessionStorage），不会写进 URL 或上传。">
      <div className="rv-card">
        <label htmlFor="rv-token" style={{ display: "block", marginBottom: "var(--rv-space-2)" }}>
          访问令牌（<code>rv_...</code>，用 scripts/create_token.py 生成）
        </label>
        <input
          id="rv-token"
          type="password"
          value={token}
          onChange={(e) => {
            setTokenValue(e.target.value);
            setSaved(false);
          }}
          style={{
            width: "100%",
            padding: "var(--rv-space-2)",
            border: "1px solid var(--rv-line-strong)",
            borderRadius: "var(--rv-radius-sm)",
            background: "var(--rv-bg)",
            color: "var(--rv-ink)",
            fontFamily: "var(--rv-font-mono)",
            fontSize: "var(--rv-text-sm)",
          }}
        />
        <div style={{ display: "flex", gap: "var(--rv-space-2)", marginTop: "var(--rv-space-3)" }}>
          <button
            type="button"
            onClick={() => {
              setToken(token.trim() || null);
              setSaved(true);
            }}
            style={{
              padding: "var(--rv-space-2) var(--rv-space-3)",
              border: "1px solid var(--rv-accent)",
              borderRadius: "var(--rv-radius-sm)",
              background: "var(--rv-accent)",
              color: "var(--rv-surface)",
              cursor: "pointer",
            }}
          >
            保存
          </button>
          <button
            type="button"
            onClick={() => {
              setToken(null);
              setTokenValue("");
              setSaved(false);
            }}
            style={{
              padding: "var(--rv-space-2) var(--rv-space-3)",
              border: "1px solid var(--rv-line-strong)",
              borderRadius: "var(--rv-radius-sm)",
              background: "transparent",
              color: "var(--rv-ink)",
              cursor: "pointer",
            }}
          >
            清除
          </button>
        </div>
        {saved ? (
          <p style={{ color: "var(--rv-success)", fontSize: "var(--rv-text-sm)", marginBottom: 0 }}>
            已保存到当前会话
          </p>
        ) : null}
      </div>
    </PageShell>
  );
}
