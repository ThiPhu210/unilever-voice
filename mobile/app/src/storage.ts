import AsyncStorage from "@react-native-async-storage/async-storage";
import * as SecureStore from "expo-secure-store";
import { Settings } from "./types";

const K = "uv_settings";
const KEY_NAME = "uv_api_key";
const Q = "uv_queue";

export const DEFAULTS: Settings = { server: "", apiKey: "", saId: "sa01", saName: "SA Demo", store: "" };

export async function loadSettings(): Promise<Settings> {
  const raw = await AsyncStorage.getItem(K);
  const apiKey = (await SecureStore.getItemAsync(KEY_NAME)) || "";
  return { ...DEFAULTS, ...(raw ? JSON.parse(raw) : {}), apiKey };
}

export async function saveSettings(s: Settings) {
  const { apiKey, ...rest } = s;
  await AsyncStorage.setItem(K, JSON.stringify({ ...rest, server: rest.server.trim().replace(/\/+$/, "") }));
  await SecureStore.setItemAsync(KEY_NAME, apiKey.trim());
}

// Hàng đợi upload offline: lưu {uri, createdAt, sa...} chờ có mạng thì gửi.
export type Pending = { uri: string; saId: string; saName: string; store: string; createdAt: number };

export async function getQueue(): Promise<Pending[]> {
  const raw = await AsyncStorage.getItem(Q);
  return raw ? JSON.parse(raw) : [];
}
export async function setQueue(q: Pending[]) {
  await AsyncStorage.setItem(Q, JSON.stringify(q));
}
