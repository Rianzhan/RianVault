const PAGES = [
  { path: "/", name: "Home / Dashboard" },
  { path: "/search", name: "Search" },
  { path: "/conversations", name: "Conversation Viewer" },
  { path: "/memories", name: "Memory Library" },
  { path: "/memories/:id", name: "Memory Detail / Genesis" },
  { path: "/migration-audit", name: "Memory Migration Audit" },
  { path: "/import", name: "Import" },
  { path: "/export", name: "Export / Backup" },
  { path: "/settings", name: "Settings" },
];

export default function App() {
  return (
    <main
      style={{
        maxWidth: "var(--rv-reading-width)",
        margin: "0 auto",
        padding: "var(--rv-space-5) var(--rv-space-3)",
      }}
    >
      <h1
        style={{
          fontFamily: "var(--rv-font-serif)",
          fontSize: "var(--rv-text-xl)",
          fontWeight: 500,
        }}
      >
        RianVault · 湛Owner私人记忆库
      </h1>
      <p style={{ color: "var(--rv-ink-soft)" }}>
        第一阶段骨架已就位。页面将在 T8/T9 逐个落地：
      </p>
      <ul style={{ lineHeight: 2 }}>
        {PAGES.map((p) => (
          <li key={p.path}>
            <code style={{ color: "var(--rv-ink-faint)" }}>{p.path}</code> — {p.name}
          </li>
        ))}
      </ul>
    </main>
  );
}
