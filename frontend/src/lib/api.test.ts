/* api client 的行为契约：错误绝不吞，绝不把失败伪装成成功。 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, getToken, setToken } from "./api";

function stubSessionStorage() {
  const store = new Map<string, string>();
  vi.stubGlobal("sessionStorage", {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => void store.set(k, v),
    removeItem: (k: string) => void store.delete(k),
  });
}

function respond(body: string, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: "x",
    text: async () => body,
  };
}

beforeEach(() => {
  stubSessionStorage();
  setToken(null);
});

describe("api client", () => {
  it("5xx 抛 ApiError，不返回假成功", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respond("boom", 500)));
    await expect(api.get("/memories")).rejects.toBeInstanceOf(ApiError);
    await expect(api.get("/memories")).rejects.toThrow(/500/);
  });

  it("403/404 也抛错，并把服务端 detail 带出来", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respond("forbidden", 403)));
    await expect(api.get("/export")).rejects.toMatchObject({ status: 403, detail: "forbidden" });
  });

  it("网络异常原样抛出，不静默", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("fetch failed")));
    await expect(api.get("/health")).rejects.toThrow("fetch failed");
  });

  it("2xx 解析 JSON", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respond('{"count":3}')));
    await expect(api.get("/index/status")).resolves.toEqual({ count: 3 });
  });

  it("带上 Authorization 头（token 只在本会话里）", async () => {
    const fetchMock = vi.fn().mockResolvedValue(respond("{}"));
    vi.stubGlobal("fetch", fetchMock);
    setToken("rv_test_token");
    await api.get("/health");
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer rv_test_token");
    expect(getToken()).toBe("rv_test_token");
  });

  it("查询走 body 而不是 URL（私人查询词不进地址栏/日志）", async () => {
    const fetchMock = vi.fn().mockResolvedValue(respond('{"count":0,"hits":[]}'));
    vi.stubGlobal("fetch", fetchMock);
    await api.post("/search", { query: "搬家", mode: "hybrid" });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/search");
    expect(String(init.body)).toContain("搬家");
    expect(url).not.toContain("搬家");
  });
});
