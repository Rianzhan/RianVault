import { useLocation, NavLink } from "react-router-dom";
import { useEffect, useState } from "react";
import type { ReactNode } from "react";

export const NAV_ITEMS = [
  { to: "/", label: "首页", end: true },
  { to: "/search", label: "检索", end: false },
  { to: "/conversations", label: "原文", end: false },
  { to: "/memories", label: "记忆", end: false },
  { to: "/migration-audit", label: "遗失记忆审计", end: false },
  { to: "/import", label: "导入", end: false },
  { to: "/export", label: "导出 / 备份", end: false },
  { to: "/settings", label: "设置", end: false },
];

export default function Layout({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const location = useLocation();

  // 路由变化后收起窄屏导航，避免遮挡正文
  useEffect(() => {
    setOpen(false);
  }, [location.pathname]);

  return (
    <div className="rv-app">
      <a className="rv-skip-link" href="#rv-content">
        跳到正文
      </a>
      <nav className="rv-nav" aria-label="主导航">
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "var(--rv-space-2)",
          }}
        >
          <NavLink to="/" className="rv-nav__brand">
            RianVault
          </NavLink>
          <button
            type="button"
            className="rv-nav__toggle"
            aria-expanded={open}
            aria-controls="rv-nav-links"
            onClick={() => setOpen((v) => !v)}
          >
            {open ? "收起" : "菜单"}
          </button>
        </div>
        <div className="rv-nav__links" id="rv-nav-links" data-open={open}>
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className="rv-nav__link"
              // react-router v6 会给当前项加 aria-current="page"
            >
              {item.label}
            </NavLink>
          ))}
        </div>
      </nav>
      <main className="rv-main" id="rv-content">
        <div className="rv-main__inner">{children}</div>
      </main>
    </div>
  );
}
