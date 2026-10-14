// @vitest-environment jsdom
/* 检索页：关键词必须标亮、混合检索要能看出哪条是语义哪条是关键词、语义要给出命中片段。 */

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Search from "./Search";

const HITS = [
  {
    message_id: "m-1",
    conversation_id: "c-1",
    conversation_title: "深夜闲聊",
    source_platform: "chatgpt",
    source_model: null,
    role: "user",
    content_text: "我很爱她，爱得深沉。",
    event_time: "2026-10-01T21:00:00Z",
    score: 0.3,
    match_types: ["keyword"],
    chunk_index: null,
    matched_chunk_text: null,
  },
  {
    message_id: "m-2",
    conversation_id: "c-1",
    conversation_title: "深夜闲聊",
    source_platform: "chatgpt",
    source_model: null,
    role: "assistant",
    content_text: "前面铺垫很多…中间才是重点…后面又一堆收尾。",
    event_time: "2026-10-01T21:05:00Z",
    score: 0.87,
    match_types: ["semantic", "keyword"],
    chunk_index: 1,
    matched_chunk_text: "中间才是重点",
  },
];

let lastSearchBody: Record<string, unknown> | null = null;

function json(value: unknown) {
  return {
    ok: true,
    status: 200,
    statusText: "OK",
    text: async () => JSON.stringify(value),
  };
}

beforeEach(() => {
  lastSearchBody = null;
  const store = new Map<string, string>();
  store.set("rianvault.token", "rv_test_token");
  vi.stubGlobal("sessionStorage", {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => void store.set(k, v),
    removeItem: (k: string) => void store.delete(k),
  });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: RequestInit = {}) => {
      const u = String(url);
      if (u.endsWith("/stats")) {
        // 已全部索引，避免出现"补齐索引"提示卡片干扰断言
        return json({ messages: 10, indexed_messages: 10, indexable_messages: 10 });
      }
      if (u.endsWith("/search")) {
        lastSearchBody = JSON.parse(String(init.body ?? "{}"));
        return json({ mode: "hybrid", count: HITS.length, hits: HITS });
      }
      return json({});
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

/** 渲染一次并完成一次检索；返回 render 结果供断言 DOM（注意：只能渲染一次）。 */
async function searchFor(query: string) {
  const user = userEvent.setup();
  const result = render(
    <MemoryRouter>
      <Search />
    </MemoryRouter>,
  );
  // 页面大标题也叫「检索」，所以按钮必须按 role 精确定位，不能用 getByText
  await user.type(screen.getByRole("textbox", { name: "查询" }), query);
  await user.click(screen.getByRole("button", { name: "检索" }));
  await waitFor(() => expect(lastSearchBody).not.toBeNull());
  return result;
}

describe("检索页", () => {
  it("关键词检索会把查询词在原文明文标亮", async () => {
    const { container } = await searchFor("爱");

    await waitFor(() => {
      const marks = Array.from(container.querySelectorAll("mark")).map((m) => m.textContent);
      expect(marks).toContain("爱");
      // "我很爱她，爱得深沉。" 里有两个「爱」，两个都该标出来
      expect(marks.filter((t) => t === "爱").length).toBe(2);
    });
  });

  it("混合检索要能看出每条命中是语义还是关键词", async () => {
    await searchFor("爱");

    // 两条命中都带关键词标签，所以要用 All 版本
    expect((await screen.findAllByText("关键词")).length).toBeGreaterThan(0);
    expect((await screen.findAllByText("语义")).length).toBeGreaterThan(0);
  });

  it("语义命中要单独框出「命中片段」，而不是整条原文", async () => {
    const { container } = await searchFor("重点");

    await waitFor(() => {
      expect(screen.getByText(/语义命中片段/)).toBeTruthy();
    });
    expect(container.textContent).toContain("中间才是重点");
    expect(container.textContent).toContain("前面铺垫很多");
  });
});
