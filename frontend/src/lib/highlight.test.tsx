import { describe, expect, it } from "vitest";
import type { ReactElement, ReactNode } from "react";

import { highlight, termsOf } from "./highlight";

/** 把 ReactNode 树拍平成纯文本，方便断言。 */
function toText(node: ReactNode): string {
  if (node == null || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  // highlight() 返回的是 ReactNode[]，必须先展开数组再递归
  if (Array.isArray(node)) return node.map(toText).join("");
  const el = node as ReactElement<{ children?: ReactNode }>;
  return toText(el.props?.children ?? "");
}

function markedTerms(node: ReactNode): string[] {
  const out: string[] = [];
  const walk = (n: ReactNode) => {
    if (n == null || typeof n === "boolean") return;
    if (typeof n === "string" || typeof n === "number") return;
    if (Array.isArray(n)) {
      n.forEach(walk);
      return;
    }
    const el = n as ReactElement<{ children?: ReactNode }>;
    if (el.type === "mark") out.push(toText(el.props?.children ?? ""));
    else walk(el.props?.children ?? null);
  };
  walk(node);
  return out;
}

describe("highlight", () => {
  it("termsOf 按空白切词，并归一全角空格", () => {
    expect(termsOf("爱 你")).toEqual(["爱", "你"]);
    expect(termsOf("爱\u3000你")).toEqual(["爱", "你"]);
    expect(termsOf("  love  you  ")).toEqual(["love", "you"]);
  });

  it("把查询词标成 mark，其余文字原样保留", () => {
    const nodes = highlight("我很爱她，爱得深沉", ["爱"]);
    expect(toText(nodes)).toBe("我很爱她，爱得深沉");
    expect(markedTerms(nodes)).toEqual(["爱", "爱"]);
  });

  it("英文不区分大小写", () => {
    const nodes = highlight("Love is love", ["love"]);
    expect(markedTerms(nodes)).toEqual(["Love", "love"]);
  });

  it("查询词含正则特殊字符时不炸", () => {
    const nodes = highlight("价格 (100) 元", ["(100)"]);
    expect(markedTerms(nodes)).toEqual(["(100)"]);
  });

  it("没有查询词时原样返回纯文本", () => {
    const nodes = highlight("没有高亮", []);
    expect(nodes).toEqual(["没有高亮"]);
  });

  it("语义场景：查询词没字面出现时不高亮任何片段", () => {
    const nodes = highlight("这段是语义相近但不是字面匹配的内容", ["怀念"]);
    expect(markedTerms(nodes)).toEqual([]);
  });
});
