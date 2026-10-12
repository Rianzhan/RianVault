/* 与后端通信的唯一入口。

纪律：错误绝不吞。非 2xx 一律抛 ApiError（带 status 与服务端 detail），
网络失败原样抛出，绝不返回"看起来成功"的空结果。
后端是本机/自有 VPS，token 只存在浏览器会话里，不写进 URL、不上报。 */

const TOKEN_KEY = "rianvault.token";

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(`API ${status}: ${detail}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

function storage(): Storage | null {
  try {
    return typeof sessionStorage === "undefined" ? null : sessionStorage;
  } catch {
    return null;
  }
}

export function getToken(): string | null {
  return storage()?.getItem(TOKEN_KEY) ?? null;
}

export function setToken(token: string | null): void {
  const store = storage();
  if (!store) return;
  if (token) store.setItem(TOKEN_KEY, token);
  else store.removeItem(TOKEN_KEY);
}

type Method = "GET" | "POST" | "PATCH" | "DELETE";

async function request<T>(method: Method, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(`/api${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  const raw = await response.text();
  if (!response.ok) {
    throw new ApiError(response.status, raw || response.statusText || "请求失败");
  }
  if (!raw) return undefined as T;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return raw as unknown as T;
  }
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body ?? {}),
  patch: <T>(path: string, body: unknown) => request<T>("PATCH", path, body),
  del: <T>(path: string) => request<T>("DELETE", path),
};

/** 上传文件走 multipart，不经过 JSON 序列化（导入导出用）。 */
export async function upload<T>(path: string, file: File, field = "file"): Promise<T> {
  const form = new FormData();
  form.append(field, file);
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(`/api${path}`, { method: "POST", headers, body: form });
  const raw = await response.text();
  if (!response.ok) throw new ApiError(response.status, raw || "上传失败");
  return (raw ? JSON.parse(raw) : undefined) as T;
}

/** 下载文件（带 token）：返回 Blob，由调用方触发浏览器保存。 */
export async function downloadFile(path: string): Promise<Blob> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(`/api${path}`, { headers });
  if (!response.ok) throw new ApiError(response.status, await response.text());
  return await response.blob();
}
