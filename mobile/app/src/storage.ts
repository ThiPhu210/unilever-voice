import AsyncStorage from "@react-native-async-storage/async-storage";
import * as SecureStore from "expo-secure-store";
import type { Order as ParsedOrder } from "./parser";
import { Settings } from "./types";

const K = "uv_settings";
const KEY_TOKEN = "uv_token";   // khoá mới: khoá cũ "uv_api_key" (API key dùng chung) không còn được dùng
const Q = "uv_queue";

export const DEFAULTS: Settings = { server: "", token: "", saId: "", saName: "", store: "" };

export async function loadSettings(): Promise<Settings> {
  const raw = await AsyncStorage.getItem(K);
  const token = (await SecureStore.getItemAsync(KEY_TOKEN)) || "";
  return { ...DEFAULTS, ...(raw ? JSON.parse(raw) : {}), token };
}

export async function saveSettings(s: Settings) {
  const { token, ...rest } = s;
  await AsyncStorage.setItem(K, JSON.stringify({ ...rest, server: rest.server.trim().replace(/\/+$/, "") }));
  if (token) await SecureStore.setItemAsync(KEY_TOKEN, token.trim());
  else await SecureStore.deleteItemAsync(KEY_TOKEN);
}

/** Đăng xuất: xoá token, giữ lại server / mã BA / cửa hàng để lần sau đăng nhập nhanh. */
export async function clearToken() {
  await SecureStore.deleteItemAsync(KEY_TOKEN);
}

// Hàng đợi upload offline: lưu {uri, createdAt, sa...} chờ có mạng thì gửi.
// Bản ghi có `cid` + `transcript` đã được nhận dạng và tách đơn NGAY TRÊN MÁY: gửi kết quả (JSON) rồi mới gửi audio.
// Bản ghi cũ / máy không nhận dạng được: chỉ có `uri` -> gửi audio cho server dịch (luồng cũ).
export type Pending = {
  uri: string; saId: string; saName: string; store: string; createdAt: number;
  cid?: string;                    // client_id: server dùng để gửi lại không bị tạo trùng
  transcript?: string;
  engine?: string;                 // "ios-speech" | "android-speech"
  durationSec?: number;
  orders?: ParsedOrder[] | null;   // null: máy chưa có danh mục để tách đơn -> server tách từ transcript
  parserVersion?: string;
  sessionId?: string;              // đã tạo phiên trên server; còn lại bước gửi audio
};

export async function getQueue(): Promise<Pending[]> {
  const raw = await AsyncStorage.getItem(Q);
  return raw ? JSON.parse(raw) : [];
}
export async function setQueue(q: Pending[]) {
  await AsyncStorage.setItem(Q, JSON.stringify(q));
}
