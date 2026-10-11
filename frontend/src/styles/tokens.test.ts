/* 设计令牌是唯一视觉来源：组件里不许写死颜色/字号。这里守住令牌的存在与分层。 */

import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

// vitest 默认不处理 CSS（css: false），?raw 拿不到内容，所以直接读源文件
const TOKENS = readFileSync(new URL("./tokens.css", import.meta.url), "utf8");
const LAYOUT = readFileSync(new URL("./layout.css", import.meta.url), "utf8");

const REQUIRED = [
  "--rv-bg",
  "--rv-surface",
  "--rv-ink",
  "--rv-ink-soft",
  "--rv-line",
  "--rv-accent",
  "--rv-evidence",
  "--rv-context",
  "--rv-font-serif",
  "--rv-text-md",
  "--rv-space-3",
  "--rv-radius",
  "--rv-reading-width",
];

describe("design tokens", () => {
  it.each(REQUIRED)("定义了 %s", (token) => {
    expect(TOKENS).toContain(`${token}:`);
  });

  it("evidence 与 context 用不同颜色（来源片段必须能一眼区分）", () => {
    const evidence = /--rv-evidence:\s*([^;]+);/.exec(TOKENS)?.[1]?.trim();
    const context = /--rv-context:\s*([^;]+);/.exec(TOKENS)?.[1]?.trim();
    expect(evidence).toBeTruthy();
    expect(context).toBeTruthy();
    expect(evidence).not.toBe(context);
  });

  it("窄屏有专门的导航规则（移动端也要能读、能点）", () => {
    expect(LAYOUT).toContain("@media (max-width: 720px)");
    expect(LAYOUT).toContain(".rv-nav__links[data-open=\"true\"]");
  });
});
