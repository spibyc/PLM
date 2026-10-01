let csrfToken = "";
export function setCsrf(token: string) {
  csrfToken = token;
}

export class ApiError extends Error {
  status: number;
  code: string;
  constructor(status: number, message: string, code: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

type Opts = { method?: string; body?: unknown; form?: FormData };

export async function api<T = any>(path: string, opts: Opts = {}): Promise<T> {
  const method = opts.method ?? (opts.body !== undefined || opts.form ? "POST" : "GET");
  const headers: Record<string, string> = {};
  if (method !== "GET") headers["X-CSRF-Token"] = csrfToken;
  let body: BodyInit | undefined;
  if (opts.form) body = opts.form;
  else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  const res = await fetch(path, { method, headers, body, credentials: "same-origin" });
  if (res.status === 401 && !path.startsWith("/api/auth/")) {
    window.dispatchEvent(new CustomEvent("plm:unauthenticated"));
  }
  const ct = res.headers.get("content-type") ?? "";
  const data = ct.includes("application/json") ? await res.json() : await res.text();
  if (!res.ok) {
    const msg = typeof data === "object" && data?.detail ? String(data.detail) : `Request failed (${res.status})`;
    throw new ApiError(res.status, msg, (typeof data === "object" && data?.code) || "error");
  }
  return data as T;
}

export const qs = (params: Record<string, unknown>) => {
  const u = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") u.set(k, String(v));
  });
  const s = u.toString();
  return s ? `?${s}` : "";
};

export const fmtDate = (s?: string | null) => (s ? new Date(s).toLocaleString(undefined, {
  year: "numeric", month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit",
}) : "");
export const fmtDay = (s?: string | null) => (s ? new Date(s).toLocaleDateString(undefined, {
  year: "numeric", month: "short", day: "2-digit" }) : "");
export const fmtQty = (n?: number | null) =>
  n === undefined || n === null ? "" : Number(n).toLocaleString(undefined, { maximumFractionDigits: 6 });

export interface Me {
  anonymous: boolean; id: string | null; username: string; full_name: string; permissions: string[]; roles: string[]; csrf_token: string;
}

/** Consistent purchasing/receipt label; multiple approved MPNs stay visible. */
export const partOptionLabel = (part: { part_number?: string; id?: string; item_id?: string; mpns?: string[]; mpn?: string | null; description?: string | null }) =>
  `${part.part_number || part.item_id || part.id || ""} — ${part.mpns?.length ? part.mpns.join(" / ") : part.mpn || "No approved MPN"} — ${part.description || "No description"}`;
