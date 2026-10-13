// @vitest-environment jsdom
/* Genesis 视图：版本史、来源片段、双时间必须都渲染出来（可追溯的入口在这里）。 */

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import MemoryDetail from "./MemoryDetail";

const DETAIL = {
  memory: {
    id: "mem-1",
    title: "居住偏好",
    body: "Owner偏好安静、有空间感的家。",
    memory_type: "preference",
    status: "active",
    importance: 4,
    event_time_start: "2025-03-14",
    event_time_end: "2025-03-14",
    tags: ["home"],
    extra_metadata: {},
    current_version: 2,
    created_by_actor: "owner",
    created_by_model: "gpt-5.6-sol",
    created_at: "2026-10-11T02:00:00Z",
    updated_at: "2026-10-11T02:05:00Z",
    deleted_at: null,
  },
  spans: [
    {
      id: "span-1",
      memory_id: "mem-1",
      conversation_id: "conv-1",
      start_message_id: "aaaaaaaa-0000-0000-0000-000000000001",
      end_message_id: "aaaaaaaa-0000-0000-0000-000000000002",
      span_type: "evidence",
      note: null,
      sort_order: 0,
      created_at: "2026-10-11T02:01:00Z",
      created_by_actor: "zhan_mcp",
      created_by_model: "gpt-5.6-sol",
    },
  ],
  versions: [
    {
      id: "v1",
      memory_id: "mem-1",
      version_number: 1,
      snapshot: { body: "Owner偏好安静的环境。" },
      edited_by_actor: "owner",
      edited_by_model: null,
      edit_reason: null,
      created_at: "2026-10-11T02:00:00Z",
    },
    {
      id: "v2",
      memory_id: "mem-1",
      version_number: 2,
      snapshot: { body: "Owner偏好安静、有空间感的家。" },
      edited_by_actor: "owner",
      edited_by_model: null,
      edit_reason: "补充空间感",
      created_at: "2026-10-11T02:05:00Z",
    },
  ],
  audit_events: [
    {
      id: "a1",
      event_type: "memory_created",
      actor: "owner",
      actor_model: null,
      target_type: "memory",
      target_id: "mem-1",
      detail: {},
      created_at: "2026-10-11T02:00:00Z",
    },
    {
      id: "a2",
      event_type: "memory_updated",
      actor: "owner",
      actor_model: null,
      target_type: "memory",
      target_id: "mem-1",
      detail: { version: 2 },
      created_at: "2026-10-11T02:05:00Z",
    },
  ],
};

type Call = { method: string; url: string; body?: unknown };
let calls: Call[] = [];

const CONVERSATION_MESSAGES = [
  { id: "aaaaaaaa-0000-0000-0000-000000000001", role: "user", content_text: "把这件事加入记忆库", sort_order: 1, event_time: "2026-08-15T08:00:00Z", source_model: null },
  { id: "msg-2", role: "assistant", content_text: "好的，已经记住了：咖啡要浅烘。", sort_order: 2, event_time: "2026-08-15T08:00:30Z", source_model: "gpt-4o" },
  { id: "msg-3", role: "user", content_text: "谢谢，下次记得提醒我。", sort_order: 3, event_time: "2026-08-15T08:01:00Z", source_model: null },
];

beforeEach(() => {
  calls = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: RequestInit = {}) => {
      const method = init.method ?? "GET";
      const body = typeof init.body === "string" ? JSON.parse(init.body) : undefined;
      calls.push({ method, url: String(url), body });
      const path = String(url);
      if (path.startsWith("/api/conversations/") && path.endsWith("/messages")) {
        return json(CONVERSATION_MESSAGES);
      }
      return json(DETAIL);
    }),
  );
});

function json(value: unknown) {
  return {
    ok: true,
    status: 200,
    statusText: "OK",
    text: async () => JSON.stringify(value),
  };
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/memories/mem-1"]}>
      <Routes>
        <Route path="/memories/:id" element={<MemoryDetail />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("MemoryDetail / Genesis", () => {
  it("渲染版本史（两个版本与正文快照）", async () => {
    renderPage();
    expect(await screen.findByText("版本史（2）")).toBeTruthy();
    // 快照正文：父子元素都会命中，所以用 getAll 判存在
    expect(screen.getAllByText(/Owner偏好安静的环境。/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Owner偏好安静、有空间感的家。/).length).toBeGreaterThan(0);
  });

  it("区分发生时间与创建时间", async () => {
    renderPage();
    const node = await screen.findByText(/发生时间/);
    expect(node.textContent).toContain("2025-03-14");
    expect(screen.getByText(/创建时间/).textContent).toBeTruthy();
  });

  it("渲染来源片段并可跳回原文", async () => {
    renderPage();
    expect(await screen.findByText("来源片段")).toBeTruthy();
    expect(screen.getByText("evidence")).toBeTruthy();
    const link = screen.getByText("跳回原文") as HTMLAnchorElement;
    expect(link.getAttribute("href")).toBe("/conversations/conv-1");
  });

  it("能调整来源片段的起止范围（PATCH 带正确 payload）", async () => {
    calls = [];
    const user = userEvent.setup();
    renderPage();

    const button = await screen.findByText("调整范围");
    await user.click(button);

    // 起止下拉会列出该会话的消息
    await waitFor(() => {
      expect(screen.getByLabelText("起始消息")).toBeTruthy();
    });
    await user.selectOptions(screen.getByLabelText("结束消息"), "msg-3");
    await user.click(screen.getByText("保存范围"));

    await waitFor(() => {
      expect(calls.some((c) => c.method === "PATCH" && c.url === "/api/memories/mem-1/spans/span-1")).toBe(true);
    });
    const patch = calls.find((c) => c.method === "PATCH" && c.url?.includes("/spans/"));
    expect(patch?.body).toMatchObject({ start_message_id: DETAIL.spans[0].start_message_id, end_message_id: "msg-3" });
  });

  it("渲染审计史事件", async () => {
    renderPage();
    expect(await screen.findByText("审计史")).toBeTruthy();
    expect(screen.getByText(/memory_created/)).toBeTruthy();
    expect(screen.getByText(/memory_updated/)).toBeTruthy();
  });
});
