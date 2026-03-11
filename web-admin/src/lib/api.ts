const LOCAL_BASE_URL = "http://127.0.0.1:8787";
const GRAY_BASE_URL = "http://127.0.0.1:18788";

function resolveDefaultBaseUrl() {
  const fromEnv = String(import.meta.env.VITE_API_BASE_URL ?? "").trim();
  if (fromEnv) {
    return fromEnv;
  }

  const hostname = typeof window !== "undefined" ? window.location.hostname : "";
  if (hostname === "localhost" || hostname === "127.0.0.1") {
    return LOCAL_BASE_URL;
  }
  return GRAY_BASE_URL;
}

const DEFAULT_BASE_URL = resolveDefaultBaseUrl();

export function getDefaultBaseUrl() {
  return DEFAULT_BASE_URL;
}

function stripTrailingSlash(value: string) {
  return String(value || "").replace(/\/+$/, "");
}

async function parseResponse(response: Response) {
  const text = await response.text();
  const data = text ? (JSON.parse(text) as Record<string, unknown>) : {};
  if (!response.ok) {
    throw new Error(String(data.error || `HTTP ${response.status}`));
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

  const response = await fetch(`${stripTrailingSlash(baseUrl)}${path}`, {
    ...options,
    headers,
  });

  return parseResponse(response);
}
