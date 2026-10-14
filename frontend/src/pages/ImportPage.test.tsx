// @vitest-environment jsdom
/* 导入页：多文件逐个上传、结果累加不互顶、历史列表可见。 */

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ImportPage from "./ImportPage";

type Call = { method: string; url: string };
let calls: Call[] = [];

function json(value: unknown) {
  return {
    ok: true,
    status: 200,
    statusText: "OK",
    text: async () => JSON.stringify(value),
  };
}

const HISTORY = [
  { id: "i-old", original_filename: "旧的.json", source_type: "chatgpt_export", status: "completed", created_at: "2026-10-12T10:00:00Z" },
];

beforeEach(() => {
  calls = [];
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
      calls.push({ method, url: String(url) });
      if (String(url).endsWith("/imports") && method === "GET") return json(HISTORY);
      if (String(url).endsWith("/stats")) return json({ messages: 4 });
      const filename = JSON.stringify(init.body ?? "").match(/name":"(.*?)\\/)?.[1] ?? "x";
      return json({
        already_imported: false,
        import_: {
          id: `i-${filename}-${calls.length}`,
          status: "completed",
          source_type: "chatgpt_export",
          original_filename: String(url) + String(calls.length),
          stats: { messages_parsed: 4, imported: 4, duplicates: 0, quarantined: 0 },
          warnings: [],
          error: null,
        },
        quarantine: [],
      });
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function renderPage() {
  return render(
    <MemoryRouter>
      <ImportPage />
    </MemoryRouter>,
  );
}

describe("导入页", () => {
  it("页面显示历史导入列表（旧记录不会被顶掉）", async () => {
    renderPage();
    expect(await screen.findByText(/旧的\.json/)).toBeTruthy();
  });

  it("选了多个文件会逐个上传，结果全部累加展示", async () => {
    const user = userEvent.setup();
    renderPage();

    const input = screen.getByLabelText("选择导出文件（可多选）") as HTMLInputElement;
    const f1 = new File(["[]"], "a.json", { type: "application/json" });
    const f2 = new File(["[]"], "b.json", { type: "application/json" });
    await user.upload(input, [f1, f2]);

    const button = await screen.findByText(/开始导入（2 个文件）/);
    await user.click(button);

    await waitFor(() => {
      const importCalls = calls.filter((c) => c.method === "POST" && c.url.endsWith("/imports"));
      expect(importCalls.length).toBe(2);
    });
    // 两个文件的结果卡片都在页面上
    await waitFor(() => {
      expect(screen.getAllByText(/状态：/).length).toBe(2);
    });
  });
});
