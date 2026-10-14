import type { ReactNode } from "react";

/** 和后端 keyword_search 的切词规则保持一致：全角空格归一 + 空白切分。 */
export function termsOf(query: string): string[] {
  return query
    .replace(/\u3000/g, " ")
    .split(/\s+/)
    .map((t) => t.trim())
    .filter(Boolean);
}

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * 把正文里出现的查询词用 <mark> 包起来。
 * 关键词检索的词会高亮；语义检索里若查询词碰巧也字面出现，同样会被标出。
 * 用 split + 集合判断，避免正则 global 标志的 lastIndex 状态坑。
 */
export function highlight(text: string, terms: string[]): ReactNode[] {
  if (!terms.length || !text) return [text];
  const pattern = terms
    .map(escapeRegExp)
    .sort((a, b) => b.length - a.length)
    .join("|");
  const re = new RegExp(`(${pattern})`, "gi");
  const lowerTerms = new Set(terms.map((t) => t.toLowerCase()));
  const parts = text.split(re);
  return parts.map((part, i) => {
    if (part === "") return null;
    return lowerTerms.has(part.toLowerCase()) ? (
      <mark
        key={i}
        style={{
          background: "var(--rv-highlight, #ffe58f)",
          color: "inherit",
          borderRadius: "2px",
          padding: "0 1px",
          fontWeight: 600,
        }}
      >
        {part}
      </mark>
    ) : (
      part
    );
  });
}
