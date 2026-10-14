// @vitest-environment jsdom
/* 回收站：软删除的记忆能看见、能还原、能彻底删除——但彻底删除必须点两次。 */

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import MemoryLibrary from "./MemoryLibrary";

type Call = { method: string; url: string };
let calls: Call[] = [];

const ACTIVE = [
  {
    id: "m-alive",
    title: "还活着的记忆",
    body: "正文 A",
    memory_type: "note",
    status: "active",
    event_time_start: null,
    event_time_end: null,
    created_at: "2026-10-01T10:00:00Z",
    created_by_actor: "owner",
    created_by_model: null,
    current_version: 1,
    tags: [],
  },
];

const TRASHED = [
  {
    id: "m-gone",
    title: "被删掉的记忆",
    body: "正文 B",
    memory_type: "note",
    status: "deleted",
    event_time_start: null,
    event_time_end: null,
    created_at: "2026-10-02T10:00:00Z",
    created_by_actor: "owner",
    created_by_model: null,
    current_version: 3,
    tags: [],
  },
];

function json(value: unknown) {
  return { ok: true, status: 200, statusText: "OK", text: async () => JSON.stringify(value) };
}

let isOwner = true;

beforeEach(() => {
  calls = [];
  isOwner = true;
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
      const method = init.method ?? "GET";
      const u = String(url);
      calls.push({ method, url: u });
      if (u.includes("/auth/me")) {
        return json({ name: "laptop", role: isOwner ? "owner" : "zhan_mcp", can_admin: isOwner });
      }
      if (u.includes("/memories")) {
        return json(u.includes("status=deleted") ? TRASHED : ACTIVE);
      }
      return json({});
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function countOf(method: string, fragment: string) {
  return calls.filter((c) => c.method === method && c.url.includes(fragment)).length;
}

function renderPage() {
  return render(
    <MemoryRouter>
      <MemoryLibrary />
    </MemoryRouter>,
  );
}

async function openBin() {
  const user = userEvent.setup();
  renderPage();
  await screen.findByText("还活着的记忆");
  expect(screen.queryByText("被删掉的记忆")).toBeNull(); // 回收站内容不该混进正常列表
  await user.click(screen.getByLabelText("切换回收站"));
  await screen.findByText("被删掉的记忆");
  return user;
}

describe("回收站", () => {
  it("入口显示已删除数量，切进去能看到软删除的记忆", async () => {
    await openBin();
    const toggle = await screen.findByLabelText("切换回收站");
    expect(toggle.textContent).toContain("回收站（1）");
  });

  it("彻底删除要点两次，第一次只是确认不会发请求", async () => {
    const user = await openBin();

    const purge = screen.getByRole("button", { name: "彻底删除" });
    await user.click(purge);
    expect(countOf("DELETE", "/purge")).toBe(0); // 第一次点击：还没真删
    expect(screen.getByRole("button", { name: "确认彻底删除？" })).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "确认彻底删除？" }));
    await waitFor(() => expect(countOf("DELETE", "/purge")).toBe(1));
  });

  it("还原一次点击就生效（走 /undelete）", async () => {
    const user = await openBin();

    await user.click(screen.getByRole("button", { name: "还原" }));
    await waitFor(() => expect(countOf("POST", "/undelete")).toBe(1));
    expect(countOf("DELETE", "/purge")).toBe(0);
  });

  it("AI 身份（非 Owner）看不到彻底删除和还原按钮", async () => {
    isOwner = false;
    await openBin();

    expect(screen.queryByRole("button", { name: "彻底删除" })).toBeNull();
    expect(screen.queryByRole("button", { name: "还原" })).toBeNull();
  });
});
