import { useEffect, useState } from "react";
import { ActivityIndicator, StatusBar, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { SafeAreaProvider, useSafeAreaInsets } from "react-native-safe-area-context";
import { loadSettings } from "./src/storage";
import { C } from "./src/theme";
import { Settings } from "./src/types";
import RecordScreen from "./src/screens/RecordScreen";
import HistoryScreen from "./src/screens/HistoryScreen";
import DetailScreen from "./src/screens/DetailScreen";
import SettingsScreen from "./src/screens/SettingsScreen";

type Tab = "record" | "history" | "settings";
const TABS: [Tab, string][] = [["record", "Ghi âm"], ["history", "Lịch sử"], ["settings", "Cài đặt"]];

function Shell() {
  const insets = useSafeAreaInsets();
  const [settings, setSettings] = useState<Settings | null>(null);
  const [tab, setTab] = useState<Tab>("record");
  const [detail, setDetail] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    loadSettings().then((s) => {
      setSettings(s);
      if (!s.server || !s.apiKey) setTab("settings"); // lần đầu: vào cài đặt
    });
  }, []);

  if (!settings) return <View style={st.center}><ActivityIndicator color={C.brand} /></View>;

  return (
    <View style={st.root}>
      <StatusBar barStyle="dark-content" />
      <View style={{ flex: 1 }}>
        {tab === "record" && (
          <RecordScreen settings={settings} onUploaded={(id) => {
            setRefreshKey((k) => k + 1);
            if (id) { setDetail(id); setTab("history"); } // ghi xong -> mở thẳng đơn để xác nhận/nhập giá
          }} />
        )}
        {tab === "history" && !detail && <HistoryScreen settings={settings} refreshKey={refreshKey} onOpen={setDetail} />}
        {tab === "history" && detail && <DetailScreen settings={settings} id={detail} onBack={() => { setDetail(null); setRefreshKey((k) => k + 1); }} />}
        {tab === "settings" && <SettingsScreen settings={settings} onSaved={setSettings} />}
      </View>
      <View style={[st.tabs, { paddingBottom: Math.max(insets.bottom, 8) }]}>
        {TABS.map(([k, label]) => {
          const on = tab === k;
          return (
            <TouchableOpacity key={k} style={st.tab} accessibilityRole="tab" accessibilityState={{ selected: on }}
              onPress={() => { setTab(k); setDetail(null); }}>
              <View style={[st.bar, on && { backgroundColor: C.red }]} />
              <Text style={[st.tabT, on && { color: C.ink, fontWeight: "800" }]}>{label}</Text>
            </TouchableOpacity>
          );
        })}
      </View>
    </View>
  );
}

export default function App() {
  return <SafeAreaProvider><Shell /></SafeAreaProvider>;
}

const st = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.bg },
  center: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: C.bg },
  tabs: { flexDirection: "row", borderTopWidth: 1, borderTopColor: C.line, backgroundColor: C.card },
  tab: { flex: 1, alignItems: "center", paddingBottom: 12 },
  bar: { height: 3, width: 36, borderRadius: 2, backgroundColor: "transparent", marginBottom: 10 },
  tabT: { color: C.muted, fontSize: 14, fontWeight: "600" },
});
