import { ComponentProps, useCallback, useEffect, useState } from "react";
import { ActivityIndicator, StatusBar, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { SafeAreaProvider, SafeAreaView, useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";

import { setUnauthorizedHandler } from "./src/api";
import { clearToken, loadSettings, saveSettings } from "./src/storage";
import { C, S, shadow } from "./src/theme";
import { AuthResult, Settings } from "./src/types";

import LoginScreen from "./src/screens/LoginScreen";
import RecordScreen from "./src/screens/RecordScreen";
import HistoryScreen from "./src/screens/HistoryScreen";
import DetailScreen from "./src/screens/DetailScreen";
import SettingsScreen from "./src/screens/SettingsScreen";

type Tab = "record" | "history" | "settings";
type IconName = ComponentProps<typeof Ionicons>["name"];

const TABS: { key: Tab; label: string; icon: IconName; on: IconName }[] = [
  { key: "record", label: "Ghi âm", icon: "mic-outline", on: "mic" },
  { key: "history", label: "Lịch sử", icon: "time-outline", on: "time" },
  { key: "settings", label: "Cài đặt", icon: "settings-outline", on: "settings" },
];

export default function App() {
  return (
    <SafeAreaProvider>
      <AppContent />
    </SafeAreaProvider>
  );
}

function AppContent() {
  const insets = useSafeAreaInsets();
  const [settings, setSettings] = useState<Settings | null>(null);
  const [notice, setNotice] = useState<string | undefined>();
  const [tab, setTab] = useState<Tab>("record");
  const [detail, setDetail] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => { loadSettings().then(setSettings); }, []);

  /** Đăng xuất (BA bấm, hoặc server báo token hết hạn): xoá token, về màn đăng nhập. */
  const signOut = useCallback(async (msg?: string) => {
    await clearToken();
    setSettings((s) => (s ? { ...s, token: "" } : s));
    setNotice(msg);
    setTab("record");
    setDetail(null);
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(() => { signOut("Phiên đăng nhập đã hết hạn. Hãy đăng nhập lại."); });
    return () => setUnauthorizedHandler(null);
  }, [signOut]);

  async function handleLoggedIn(r: AuthResult, server: string) {
    if (!settings) return;
    const sameBa = settings.saId.toLowerCase() === r.sa_id.toLowerCase();
    const next: Settings = {
      ...settings, server, token: r.token, saId: r.sa_id, saName: r.sa_name || r.sa_id,
      // đổi sang BA khác thì không mang cửa hàng của người trước sang
      store: sameBa && settings.store ? settings.store : (r.store || ""),
    };
    await saveSettings(next);
    setNotice(undefined);
    setTab("record");
    setSettings(next);
  }

  if (!settings) {
    return (
      <View style={st.center}>
        <ActivityIndicator color={C.brand} />
      </View>
    );
  }

  // Chưa đăng nhập: màn đăng nhập là màn đầu tiên (tự xử lý vùng an toàn, không có thanh tab).
  if (!settings.token) {
    return (
      <>
        <StatusBar barStyle="dark-content" />
        <LoginScreen server={settings.server} initialCode={settings.saId} notice={notice} onLoggedIn={handleLoggedIn} />
      </>
    );
  }

  return (
    <SafeAreaView style={st.root} edges={["top", "left", "right"]}>
      <StatusBar barStyle="dark-content" />

      <View style={{ flex: 1 }}>
        {tab === "record" && (
          <RecordScreen settings={settings} onUploaded={() => setRefreshKey((k) => k + 1)} />
        )}
        {tab === "history" && !detail && (
          <HistoryScreen settings={settings} refreshKey={refreshKey} onOpen={setDetail} />
        )}
        {tab === "history" && detail && (
          <DetailScreen settings={settings} id={detail} onBack={() => setDetail(null)} />
        )}
        {tab === "settings" && (
          <SettingsScreen settings={settings} onSaved={setSettings} onLogout={() => signOut()} />
        )}
      </View>

      <View style={[st.tabs, { paddingBottom: Math.max(insets.bottom, S.sm) }]}>
        {TABS.map((t) => {
          const active = tab === t.key;
          return (
            <TouchableOpacity
              key={t.key} style={st.tab} accessibilityRole="tab" accessibilityState={{ selected: active }}
              accessibilityLabel={t.label} activeOpacity={0.7}
              onPress={() => { setTab(t.key); setDetail(null); }}
            >
              <View style={[st.bar, active && { backgroundColor: C.primary }]} />
              <Ionicons name={active ? t.on : t.icon} size={24} color={active ? C.primary : C.muted} />
              <Text style={[st.tabT, active && { color: C.primary, fontWeight: "700" }]}>{t.label}</Text>
            </TouchableOpacity>
          );
        })}
      </View>
    </SafeAreaView>
  );
}

const st = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.bg },
  center: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: C.bg },
  tabs: { flexDirection: "row", backgroundColor: C.card, borderTopWidth: 1, borderTopColor: C.line, ...shadow },
  tab: { flex: 1, alignItems: "center", paddingBottom: 2, gap: 2 },
  bar: { alignSelf: "stretch", marginHorizontal: S.xl, height: 3, borderBottomLeftRadius: 3, borderBottomRightRadius: 3, marginBottom: 6, backgroundColor: "transparent" },
  tabT: { color: C.muted, fontSize: 12 },
});
