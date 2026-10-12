// @vitest-environment jsdom
/* Genesis 视图：版本史、来源片段、双时间必须都渲染出来（可追溯的入口在这里）。 */

import { cleanup, render, screen } from "@testing-library/react";
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

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: true,
      status: 200,
      statusText: "OK",
      text: async () => JSON.stringify(DETAIL),
    })),
  );
});

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

  it("渲染审计史事件", async () => {
    renderPage();
    expect(await screen.findByText("审计史")).toBeTruthy();
    expect(screen.getByText(/memory_created/)).toBeTruthy();
    expect(screen.getByText(/memory_updated/)).toBeTruthy();
  });
});
