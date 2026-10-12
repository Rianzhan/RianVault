// @vitest-environment jsdom
/* 审计页：扫描 + 人工判定。系统绝不自动认定，只负责把候选与上下文摆出来。 */

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import MigrationAudit from "./MigrationAudit";

type Call = { method: string; url: string; body?: unknown };
let calls: Call[] = [];

const CANDIDATES = [
  {
    id: "cand-1",
    matched_signal: "已经记住了",
    verdict: "unreviewed",
    signal_message: {
      id: "msg-9",
      role: "assistant",
      content_text: "好的，已经记住了。",
      event_time: "2026-06-21T10:00:00Z",
    },
    context: [
      { id: "msg-8", role: "user", content_text: "把这件事加入记忆库", event_time: "2026-06-21T09:59:00Z" },
      { id: "msg-9", role: "assistant", content_text: "好的，已经记住了。", event_time: "2026-06-21T10:00:00Z" },
    ],
    linked_memory_id: null,
    note: null,
  },
];

beforeEach(() => {
  calls = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: RequestInit = {}) => {
      const method = init.method ?? "GET";
      const body = typeof init.body === "string" ? JSON.parse(init.body) : undefined;
      calls.push({ method, url: String(url), body });
      if (String(url).includes("/scan")) return json({ created: 1, existing: 0, total: 1 });
      if (String(url).includes("migration-candidates") && method === "GET") return json(CANDIDATES);
      return json({});
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function json(value: unknown) {
  return { ok: true, status: 200, statusText: "OK", text: async () => JSON.stringify(value) };
}

describe("遗失记忆审计页", () => {
  it("扫描后列出候选与上下文", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <MigrationAudit />
      </MemoryRouter>,
    );

    await user.click(await screen.findByText("扫描候选"));
    expect(await screen.findByText(/命中信号/)).toBeTruthy();
    // 信号句在正文里出现两次（信号本身 + 上下文），所以用 getAll
    expect(screen.getAllByText(/好的，已经记住了。/).length).toBeGreaterThan(0);
    expect(screen.getByText(/上下文（2 条）/)).toBeTruthy();
  });

  it("点击判定会带上正确的 verdict", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <MigrationAudit />
      </MemoryRouter>,
    );

    await user.click(await screen.findByText("不确定"));
    await waitFor(() => {
      expect(calls.some((c) => String(c.url).endsWith("/verdict"))).toBe(true);
    });
    const verdictCall = calls.find((c) => String(c.url).endsWith("/verdict"));
    expect(verdictCall?.method).toBe("POST");
    expect(verdictCall?.body).toEqual({ verdict: "uncertain" });
  });
});
