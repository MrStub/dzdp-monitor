const LOCAL_BASE_URL = "http://127.0.0.1:8787";
const ONLINE_BASE_URL = "https://monitor.mrstub.workers.dev";

function resolveDefaultBaseUrl() {
  const fromEnv = String(import.meta.env.VITE_API_BASE_URL ?? "").trim();
  if (fromEnv) {
    return fromEnv;
  }

  if (typeof window !== "undefined") {
    const hostname = window.location.hostname;
    if (hostname === "localhost" || hostname === "127.0.0.1") {
      return LOCAL_BASE_URL;
    }
    return window.location.origin;
  }

  return ONLINE_BASE_URL;
}

const DEFAULT_BASE_URL = resolveDefaultBaseUrl();

export function getDefaultBaseUrl() {
  return DEFAULT_BASE_URL;
}

export type ApiRequestErrorCode = "http_error" | "network_error" | "parse_error" | "unknown_error";

type ApiRequestErrorOptions = {
  code: ApiRequestErrorCode;
  status?: number;
};

export class ApiRequestError extends Error {
  code: ApiRequestErrorCode;

  status?: number;

  constructor(message: string, options: ApiRequestErrorOptions) {
    super(message);
    this.name = "ApiRequestError";
    this.code = options.code;
    this.status = options.status;
  }
}

function stripTrailingSlash(value: string) {
  return String(value || "").replace(/\/+$/, "");
}

async function parseResponse(response: Response) {
  const text = await response.text();
  let data: Record<string, unknown> = {};
  if (text) {
    try {
      data = JSON.parse(text) as Record<string, unknown>;
    } catch {
      throw new ApiRequestError("服务返回了无法解析的数据，请稍后重试", {
        code: "parse_error",
        status: response.status,
      });
    }
  }
  if (!response.ok) {
    throw new ApiRequestError(String(data.error || `HTTP ${response.status}`), {
      code: "http_error",
      status: response.status,
    });
  }
  return data;
}

export async function apiRequest(
  baseUrl: string,
  token: string,
  path: string,
  options: RequestInit = {},
) {
  const headers = new Headers(options.headers ?? {});
  if (!headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (token.trim()) {
    headers.set("Authorization", `Bearer ${token.trim()}`);
  }

  try {
    const response = await fetch(`${stripTrailingSlash(baseUrl)}${path}`, {
      ...options,
      headers,
    });
    return parseResponse(response);
  } catch (error) {
    if (error instanceof ApiRequestError) {
      throw error;
    }
    if (error instanceof TypeError) {
      throw new ApiRequestError("网络请求失败", { code: "network_error" });
    }
    throw new ApiRequestError(
      error instanceof Error ? error.message : "请求失败",
      { code: "unknown_error" },
    );
  }
}
