import { CatalogItem, SessionDetail, SessionRow, Settings } from "./types";
import { getQueue, Pending, setQueue } from "./storage";

async function req<T>(s: Settings, path: string, init: RequestInit = {}): Promise<T> {
  if (!s.server) throw new Error("Chưa cấu hình địa chỉ server (tab Cài đặt)");
  const res = await fetch(s.server + path, {
    ...init,
    headers: { ...(init.headers || {}), "x-api-key": s.apiKey },
  });
  if (res.status === 401) throw new Error("API key không đúng");
  if (!res.ok) throw new Error(`Lỗi server ${res.status}`);
  return res.json();
}

export const ping = (s: Settings) => req<{ ok: boolean; skus: number }>(s, "/api/health");
export const listSessions = (s: Settings) =>
  req<SessionRow[]>(s, `/api/sessions?sa_id=${encodeURIComponent(s.saId)}&limit=50`);
export const getSession = (s: Settings, id: string) => req<SessionDetail>(s, `/api/sessions/${id}`);
export const getCatalog = (s: Settings) => req<CatalogItem[]>(s, "/api/catalog");
export const fixOrder = (s: Settings, orderId: number, items: { sku_id: string; qty: number }[]) =>
  req(s, `/api/orders/${orderId}/items`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(items),
  });

async function uploadOne(s: Settings, p: Pending) {
  const form = new FormData();
  form.append("audio", { uri: p.uri, name: `rec-${p.createdAt}.m4a`, type: "audio/m4a" } as any);
  form.append("sa_id", p.saId);
  form.append("sa_name", p.saName);
  form.append("store", p.store);
  const res = await fetch(s.server + "/api/sessions", {
    method: "POST",
    headers: { "x-api-key": s.apiKey },
    body: form,
  });
  if (!res.ok) throw new Error(`Upload lỗi ${res.status}`);
}

/** Thêm bản ghi vào hàng đợi rồi thử gửi toàn bộ. Trả về số bản còn tồn. */
export async function enqueueAndFlush(s: Settings, uri?: string): Promise<number> {
  const q = await getQueue();
  if (uri) q.push({ uri, saId: s.saId, saName: s.saName, store: s.store, createdAt: Date.now() });
  const left: Pending[] = [];
  for (const p of q) {
    try {
      await uploadOne(s, p);
    } catch {
      left.push(p); // mất mạng/server lỗi: giữ lại gửi sau
    }
  }
  await setQueue(left);
  return left.length;
}
export const pendingCount = async () => (await getQueue()).length;
