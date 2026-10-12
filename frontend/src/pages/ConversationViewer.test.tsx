// @vitest-environment jsdom
/* 选段 → 建记忆 → 绑定 span：payload 必须正确（这是记忆可追溯的根）。 */

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ConversationViewer from "./ConversationViewer";

type Call = { method: string; url: string; body?: unknown };
let calls: Call[] = [];

const CONVERSATIONS = [
  { id: "c1", title: "测试会话", source_platform: "chatgpt", message_count: 2 },
];
const MESSAGES = [
  {
    id: "m1",
    role: "user",
    content_text: "第一条：我们打算搬家。",
    event_time: "2023-11-14T22:13:21Z",
    sort_order: 1,
    source_model: null,
  },
  {
    id: "m2",
    role: "assistant",
    content_text: "第二条：明白，安静和采光是硬条件。",
    event_time: "2023-11-14T22:14:00Z",
    sort_order: 2,
    source_model: "gpt-4o",
  },
];

function json(value: unknown) {
  return {
    ok: true,
    status: 200,
    statusText: "OK",
    text: async () => JSON.stringify(value),
  };
}

function mockFetch() {
  calls = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: RequestInit = {}) => {
      const method = init.method ?? "GET";
      const body = typeof init.body === "string" ? JSON.parse(init.body) : undefined;
      calls.push({ method, url: String(url), body });
      const path = String(url);
      if (path === "/api/conversations" && method === "GET") return json(CONVERSATIONS);
      if (path.startsWith("/api/conversations/") && path.endsWith("/messages"))
        return json(MESSAGES);
      if (path === "/api/memories?limit=200" && method === "GET") return json([]);
      if (path === "/api/memories" && method === "POST")
        return json({ id: "new-mem", current_version: 1, body: (body as { body: string }).body });
      if (path.endsWith("/spans") && method === "POST") return json({ ok: true });
      return json({});
    }),
  );
}

function renderPage() {
  return render(
    <MemoryRouter>
      <ConversationViewer />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  mockFetch();
});

afterEach(() => {
  cleanup(); // vitest 未开 globals，RTL 不会自动清理，必须手动
  vi.unstubAllGlobals();
});

describe("ConversationViewer 选段", () => {
  it("选两段后新建记忆：span payload 指向正确的起止消息", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByText("测试会话"));
    await user.click(await screen.findByText(/第一条：我们打算搬家。/));
    await user.click(await screen.findByText(/第二条：明白，安静和采光是硬条件。/));

    await user.type(screen.getByLabelText("记忆正文"), "Owner要求找安静、采光好的房子");
    const button = await screen.findByText("新建记忆 · 作为证据");
    await user.click(button);

    await waitFor(() => {
      expect(calls.some((c) => c.url === "/api/memories" && c.method === "POST")).toBe(true);
    });

    const create = calls.find((c) => c.url === "/api/memories" && c.method === "POST");
    expect((create?.body as { body: string }).body).toBe("Owner要求找安静、采光好的房子");

    const span = calls.find((c) => c.url === "/api/memories/new-mem/spans");
    expect(span).toBeDefined();
    expect(span?.body).toEqual({
      conversation_id: "c1",
      start_message_id: "m1",
      end_message_id: "m2",
      span_type: "evidence",
    });
  });

  it("反向点选也能得到正确的起止顺序", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByText("测试会话"));
    await user.click(await screen.findByText(/第二条：明白/));
    await user.click(await screen.findByText(/第一条：我们打算搬家。/));

    await user.type(screen.getByLabelText("记忆正文"), "顺序无关");
    await user.click(await screen.findByText("新建记忆 · 作为上下文"));

    await waitFor(() => {
      expect(calls.some((c) => c.url?.endsWith("/spans"))).toBe(true);
    });
    const span = calls.find((c) => c.url?.endsWith("/spans"));
    expect(span?.body).toMatchObject({
      start_message_id: "m1",
      end_message_id: "m2",
      span_type: "context",
    });
  });

  it("正文为空时不允许提交", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByText("测试会话"));
    await user.click(await screen.findByText(/第一条：我们打算搬家。/));
    const button = await screen.findByText("新建记忆 · 作为证据");
    expect((button as HTMLButtonElement).disabled).toBe(true);
  });
});
