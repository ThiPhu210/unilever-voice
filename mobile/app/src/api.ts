import { CatalogItem, LineIn, SessionDetail, SessionRow, Settings } from "./types";
import * as FileSystem from "expo-file-system/legacy";
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
export const fixOrder = (s: Settings, orderId: number, items: LineIn[]) =>
  req(s, `/api/orders/${orderId}/items`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(items),
  });
/** SA/BA tự thêm đơn khi hệ thống không nghe thấy câu chốt đơn. */
export const addOrder = (s: Settings, sessionId: string, items: LineIn[]) =>
  req(s, `/api/sessions/${sessionId}/orders`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(items),
  });

async function uploadOne(s: Settings, p: Pending): Promise<string> {
  // Không dùng FormData + {uri,name,type}: fetch của Expo SDK mới báo "Unsupported FormDataPart implementation".
  // uploadAsync gửi multipart trực tiếp từ file trên máy (không nạp cả file vào RAM).
  const res = await FileSystem.uploadAsync(s.server + "/api/sessions", p.uri, {
    httpMethod: "POST",
    uploadType: FileSystem.FileSystemUploadType.MULTIPART,
    fieldName: "audio",
    mimeType: "audio/m4a",
    headers: { "x-api-key": s.apiKey },
    parameters: { sa_id: p.saId, sa_name: p.saName, store: p.store },
  });
  if (res.status === 401) throw new Error("API key không đúng (vào Cài đặt kiểm tra lại)");
  if (res.status < 200 || res.status >= 300) throw new Error(`Server trả lỗi ${res.status}`);
  return JSON.parse(res.body).id as string;
}

/** Thêm bản ghi vào hàng đợi rồi thử gửi toàn bộ. Trả về số bản còn tồn + id các cuộc vừa gửi được. */
export async function enqueueAndFlush(s: Settings, uri?: string): Promise<{ left: number; ids: string[]; error?: string }> {
  const q = await getQueue();
  if (uri) q.push({ uri, saId: s.saId, saName: s.saName, store: s.store, createdAt: Date.now() });
  const left: Pending[] = [];
  const ids: string[] = [];
  let error: string | undefined;
  if (!s.server) return { left: q.length, ids, error: "Chưa nhập địa chỉ server (tab Cài đặt)" };
  for (const p of q) {
    try {
      ids.push(await uploadOne(s, p));
    } catch (e: any) {
      const m = String(e?.message || e);
      error = /Network request failed|Failed to fetch/i.test(m)
        ? `Không kết nối được tới ${s.server}. Kiểm tra: đúng IP/cổng chưa, server còn chạy không, điện thoại có mạng không, và Android bản build cần HTTPS.`
        : m;
      left.push(p); // mất mạng/server lỗi: giữ lại gửi sau
    }
  }
  await setQueue(left);
  return { left: left.length, ids, error };
}
export const pendingCount = async () => (await getQueue()).length;
