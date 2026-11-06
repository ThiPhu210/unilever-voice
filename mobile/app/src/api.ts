import { AuthResult, AuthStatus, CatalogItem, LineIn, SessionDetail, SessionRow, Settings } from "./types";
import * as FileSystem from "expo-file-system/legacy";
import { getQueue, Pending, setQueue } from "./storage";

// ---------- Phiên đăng nhập ----------
// Mọi request đã đăng nhập gửi "Authorization: Bearer <token>". Server trả 401 (token hết hạn / bị thu hồi)
// thì gọi handler này để App đưa người dùng về màn đăng nhập.
let onUnauthorized: (() => void) | null = null;
export const setUnauthorizedHandler = (fn: (() => void) | null) => { onUnauthorized = fn; };
const EXPIRED = "Phiên đăng nhập đã hết hạn. Hãy đăng nhập lại.";
function expired(): Error { onUnauthorized?.(); return new Error(EXPIRED); }
const bearer = (s: Settings): Record<string, string> => (s.token ? { Authorization: `Bearer ${s.token}` } : {});

async function req<T>(s: Settings, path: string, init: RequestInit = {}): Promise<T> {
  if (!s.server) throw new Error("Chưa cấu hình địa chỉ server");
  const res = await fetch(s.server + path, {
    ...init,
    headers: { ...(init.headers || {}), ...bearer(s) },
  });
  if (res.status === 401) throw expired();
  if (!res.ok) throw new Error(`Lỗi server ${res.status}`);
  return res.json();
}

// ---------- Đăng nhập (chưa có token) ----------
async function authCall<T>(server: string, path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try { res = await fetch(server + path, init); }
  catch { throw new Error(`Không kết nối được tới ${server}. Kiểm tra mạng và địa chỉ server.`); }
  let body: any = null;
  try { body = await res.json(); } catch {}
  if (!res.ok) throw new Error(typeof body?.detail === "string" ? body.detail : `Lỗi server ${res.status}`);
  return body as T;
}
const postJson = (body: object): RequestInit => ({
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
});

/** Bước 1: mã BA này chưa được cấp / lần đầu (cần tự đặt mật khẩu) / đã có mật khẩu? */
export const checkBa = (server: string, saId: string) =>
  authCall<{ status: AuthStatus }>(server, `/api/auth/status?sa_id=${encodeURIComponent(saId)}`);
export const login = (server: string, saId: string, password: string) =>
  authCall<AuthResult>(server, "/api/auth/login", postJson({ sa_id: saId, password }));
/** Lần đầu: BA tự đặt mật khẩu (chỉ server chấp nhận khi mã này chưa có mật khẩu). Trả luôn token. */
export const setPassword = (server: string, saId: string, password: string) =>
  authCall<AuthResult>(server, "/api/auth/set-password", postJson({ sa_id: saId, password }));
/** Thu hồi token trên server. Chỉ cố gắng hết sức: lỗi mạng không được chặn việc đăng xuất trên máy. */
export const revokeToken = (s: Settings) =>
  fetch(s.server + "/api/auth/logout", { method: "POST", headers: bearer(s) }).then(() => {}, () => {});

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
/** SA/BA tự thêm đơn khi hệ thống không nhận ra đơn nào trong cuộc tư vấn. */
export const addOrder = (s: Settings, sessionId: string, items: LineIn[]) =>
  req(s, `/api/sessions/${sessionId}/orders`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(items),
  });

/** URL phát lại file ghi âm của một cuộc tư vấn. Trình phát không gắn được header nên server nhận token qua ?token=. */
export const audioUrl = (s: Settings, id: string) =>
  `${s.server.replace(/\/+$/, "")}/api/sessions/${id}/audio` +
  (s.token ? `?token=${encodeURIComponent(s.token)}` : "");

/** Tải file ghi âm của một cuộc tư vấn về bộ nhớ đệm (gửi token bằng header) rồi trả về đường dẫn file trên máy.
 *  Phát file local ổn định hơn stream trực tiếp (không lo Range, HTTP cleartext, header...), và báo lỗi rõ ràng. */
export async function downloadAudio(s: Settings, id: string): Promise<string> {
  if (!s.server) throw new Error("Chưa cấu hình địa chỉ server");
  const dest = `${FileSystem.cacheDirectory}audio-${id}.m4a`;
  const info = await FileSystem.getInfoAsync(dest);
  if (info.exists && (info as any).size > 0) return dest;
  const res = await FileSystem.downloadAsync(`${s.server}/api/sessions/${id}/audio`, dest, { headers: bearer(s) });
  if (res.status === 401) throw expired();
  if (res.status !== 200) {
    await FileSystem.deleteAsync(dest, { idempotent: true });
    throw new Error(`Server trả lỗi ${res.status}`);
  }
  return res.uri;
}

async function uploadOne(s: Settings, p: Pending): Promise<string> {
  // Không dùng FormData + {uri,name,type}: fetch của Expo SDK mới báo "Unsupported FormDataPart implementation".
  // uploadAsync gửi multipart trực tiếp từ file trên máy (không nạp cả file vào RAM).
  const res = await FileSystem.uploadAsync(s.server + "/api/sessions", p.uri, {
    httpMethod: "POST",
    uploadType: FileSystem.FileSystemUploadType.MULTIPART,
    fieldName: "audio",
    mimeType: "audio/m4a",
    headers: bearer(s),
    parameters: { sa_id: p.saId, sa_name: p.saName, store: p.store },
  });
  if (res.status === 401) throw expired();
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
  if (!s.server) return { left: q.length, ids, error: "Chưa nhập địa chỉ server" };
  for (const p of q) {
    if (p.saId && p.saId !== s.saId) { left.push(p); continue; }   // bản ghi của BA khác: giữ lại, chỉ gửi khi BA đó đăng nhập
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

// ---------- Đăng ký giọng nói SA (để hệ thống tách lời SA / lời khách) ----------
export const voiceprintStatus = (s: Settings) =>
  req<{ enrolled: boolean; n_samples?: number; updated_at?: string }>(s, `/api/voiceprints/${encodeURIComponent(s.saId)}`);

export const deleteVoiceprint = (s: Settings) =>
  req<{ ok: boolean }>(s, `/api/voiceprints/${encodeURIComponent(s.saId)}`, { method: "DELETE" });

/** Gửi 1 đoạn ghi mẫu (đọc 3 câu, >= 10 giây). consent=true: SA đã bấm đồng ý trên màn hình. */
export async function enrollVoiceprint(s: Settings, uri: string, replace: boolean): Promise<void> {
  const res = await FileSystem.uploadAsync(`${s.server}/api/voiceprints/${encodeURIComponent(s.saId)}`, uri, {
    httpMethod: "POST",
    uploadType: FileSystem.FileSystemUploadType.MULTIPART,
    fieldName: "audio",
    mimeType: "audio/m4a",
    headers: bearer(s),
    parameters: { consent: "true", replace: replace ? "true" : "false" },
  });
  if (res.status === 401) throw expired();
  if (res.status < 200 || res.status >= 300) {
    let detail = `Server trả lỗi ${res.status}`;
    try { detail = JSON.parse(res.body).detail || detail; } catch {}
    throw new Error(detail);
  }
}
