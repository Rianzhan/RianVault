// @vitest-environment jsdom
/* 导出页：下载必须带 Authorization（浏览器直接点链接会 401，这是这次修的 bug）。 */

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ExportPage from "./ExportPage";

let calls: { url: string; auth: string | null }[] = [];

beforeEach(() => {
  calls = [];
  // sessionStorage：下载前要先保存 token
  const store = new Map<string, string>();
  store.set("rianvault.token", "rv_test_token");
  vi.stubGlobal("sessionStorage", {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => void store.set(k, v),
    removeItem: (k: string) => void store.delete(k),
  });
  vi.stubGlobal("URL", { ...URL, createObjectURL: vi.fn(() => "blob:x"), revokeObjectURL: vi.fn() });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: RequestInit = {}) => {
      const auth = (init.headers as Record<string, string> | undefined)?.Authorization ?? null;
      calls.push({ url: String(url), auth });
      const zipBytes = new Uint8Array([0x50, 0x4b, 0x03, 0x04]); // "PK…"
      return {
        ok: true,
        status: 200,
        statusText: "OK",
        text: async () => JSON.stringify([{ export_id: "rianvault-export-20261012-133713.zip", size_bytes: 4, created_at: "2026-10-12T13:37:13Z" }]),
        blob: async () => new Blob([zipBytes]),
      };
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
      <ExportPage />
    </MemoryRouter>,
  );
}

describe("导出下载", () => {
  it("点击下载会带上 Authorization 并触发浏览器保存", async () => {
    const user = userEvent.setup();
    renderPage();

    const link = await screen.findByText("rianvault-export-20261012-133713.zip");
    await user.click(link);

    await waitFor(() => {
      expect(calls.some((c) => c.url.endsWith("/download") && c.auth === "Bearer rv_test_token")).toBe(true);
    });
    expect(URL.createObjectURL).toHaveBeenCalled();
  });
});
