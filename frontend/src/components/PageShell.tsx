import type { ReactNode } from "react";

/** 页面外壳：标题 + 说明 + 内容。所有页面共用，保证观感一致（DRY）。 */
export default function PageShell({
  title,
  note,
  children,
}: {
  title: string;
  note?: string;
  children?: ReactNode;
}) {
  return (
    <section>
      <h1 className="rv-page-title">{title}</h1>
      {note ? <p className="rv-page-note">{note}</p> : null}
      {children}
    </section>
  );
}
