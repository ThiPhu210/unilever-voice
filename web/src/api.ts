const KEY = "uv_api_key";
export const getKey = () => localStorage.getItem(KEY) || "";
export const setKey = (k: string) => localStorage.setItem(KEY, k);
export const clearKey = () => localStorage.removeItem(KEY);

export class Unauthorized extends Error {}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { ...(init.headers || {}), "x-api-key": getKey() },
  });
  if (res.status === 401) throw new Unauthorized("401");
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export const audioUrl = (id: string) => `/api/sessions/${id}/audio?key=${encodeURIComponent(getKey())}`;

export type Item = {
  sku_id: string; sku_name: string; qty: number; conf: number;
  need_confirm: boolean; manual?: boolean; raw?: string;
};
export type Order = {
  id: number; closing_text: string; customer_confirm: "yes" | "no" | "none";
  items: Item[]; needs_review: number; reviewed: number;
};
export type SessionRow = {
  id: string; sa_id: string; sa_name: string; store: string; created_at: string;
  duration: number | null; status: string; orders: number; units: number;
  confirm: string[]; pending_review: number;
};
export type Segment = { start: number; end: number; text: string };
export type SessionDetail = SessionRow & {
  transcript_text: string; segments: Segment[]; has_audio: boolean; orders: Order[]; error?: string;
  coaching: { score: number; checklist: { key: string; label: string; passed: boolean }[]; objections: string[] };
};
export type Overview = {
  days: number;
  kpi: {
    sessions: number; orders: number; confirmed: number; declined: number; confirm_rate: number;
    avg_units_per_order: number; avg_skus_per_order: number; pending_review: number; avg_compliance: number;
  };
  by_day: { date: string; sessions: number; orders: number; units: number }[];
  by_sa: { sa_id: string; sa_name: string; sessions: number; orders: number; confirmed: number; units: number; avg_compliance: number }[];
  objections: { key: string; label: string; count: number }[];
  top_skus: { sku_id: string; name: string; qty: number; orders: number }[];
};

// created_at từ server là UTC "YYYY-MM-DD HH:MM:SS"
export const fmtTime = (ts: string) =>
  new Date(ts.replace(" ", "T") + "Z").toLocaleString("vi-VN", { dateStyle: "short", timeStyle: "short" });
export const fmtDur = (s: number | null) => (s == null ? "–" : `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`);
