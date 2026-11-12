/**
 * Danh mục SKU cho parser trên máy. Server dựng sẵn chỉ mục (GET /api/catalog/index, có ETag = version);
 * app lưu file trong bộ nhớ máy nên parse được cả khi offline, và chỉ tải lại khi server đổi danh mục.
 */
import * as FileSystem from "expo-file-system/legacy";
import { Catalog, CatalogPayload } from "./parser";
import { Settings } from "./types";

const FILE = `${FileSystem.documentDirectory}catalog-index.json`;
const REFRESH_EVERY_MS = 10 * 60 * 1000;
const FIRST_LOAD_TIMEOUT_MS = 10000;

let mem: Catalog | null = null;
let inflight: Promise<Catalog | null> | null = null;
let lastCheck = 0;

async function readCache(): Promise<Catalog | null> {
  try {
    const info = await FileSystem.getInfoAsync(FILE);
    if (!info.exists) return null;
    return new Catalog(JSON.parse(await FileSystem.readAsStringAsync(FILE)) as CatalogPayload);
  } catch {
    return null;   // file hỏng: coi như chưa có, lần tải sau ghi đè
  }
}

/** Danh mục đã có sẵn trên máy (không đụng tới mạng). null nếu chưa từng tải. */
export async function cachedCatalog(): Promise<Catalog | null> {
  if (!mem) mem = await readCache();
  return mem;
}

/** Hỏi server có danh mục mới không (If-None-Match); lỗi mạng thì giữ bản đang có. */
export function refreshCatalog(s: Settings, force = false): Promise<Catalog | null> {
  if (!s.server || !s.token) return cachedCatalog();
  if (inflight) return inflight;
  if (!force && mem && Date.now() - lastCheck < REFRESH_EVERY_MS) return Promise.resolve(mem);
  inflight = (async () => {
    try {
      const have = await cachedCatalog();
      const headers: Record<string, string> = { Authorization: `Bearer ${s.token}` };
      if (have) headers["If-None-Match"] = `"${have.version}"`;
      const ctl = new AbortController();
      const timer = setTimeout(() => ctl.abort(), FIRST_LOAD_TIMEOUT_MS);
      const res = await fetch(`${s.server}/api/catalog/index`, { headers, signal: ctl.signal }).finally(() => clearTimeout(timer));
      lastCheck = Date.now();
      if (res.status === 304) return have;
      if (!res.ok) return have;
      const text = await res.text();
      const cat = new Catalog(JSON.parse(text) as CatalogPayload);   // dựng được rồi mới ghi file: không để lại bản hỏng
      await FileSystem.writeAsStringAsync(FILE, text);
      mem = cat;
      return cat;
    } catch {
      return mem;
    } finally {
      inflight = null;
    }
  })();
  return inflight;
}

/** Danh mục để parse ngay: có sẵn thì dùng luôn (và kiểm tra bản mới ở nền), chưa có thì đợi tải lần đầu. */
export async function loadCatalog(s: Settings): Promise<Catalog | null> {
  const have = await cachedCatalog();
  if (have) { refreshCatalog(s).catch(() => {}); return have; }
  return refreshCatalog(s, true);
}
