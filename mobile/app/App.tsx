import { useEffect, useState } from "react";
import { ActivityIndicator, SafeAreaView, StatusBar, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { loadSettings, DEFAULTS } from "./src/storage";
import { C } from "./src/theme";
import { Settings } from "./src/types";
import RecordScreen from "./src/screens/RecordScreen";
import HistoryScreen from "./src/screens/HistoryScreen";
import DetailScreen from "./src/screens/DetailScreen";
import SettingsScreen from "./src/screens/SettingsScreen";

type Tab = "record" | "history" | "settings";

export default function App() {
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

  if (!settings) return <View style={st.center}><ActivityIndicator /></View>;

  const tabs: [Tab, string][] = [["record", "Ghi âm"], ["history", "Lịch sử"], ["settings", "Cài đặt"]];
  return (
    <SafeAreaView style={st.root}>
      <StatusBar barStyle="dark-content" />
      <View style={{ flex: 1 }}>
        {tab === "record" && <RecordScreen settings={settings} onUploaded={() => setRefreshKey((k) => k + 1)} />}
        {tab === "history" && !detail && <HistoryScreen settings={settings} refreshKey={refreshKey} onOpen={setDetail} />}
        {tab === "history" && detail && <DetailScreen settings={settings} id={detail} onBack={() => setDetail(null)} />}
        {tab === "settings" && <SettingsScreen settings={settings} onSaved={setSettings} />}
      </View>
      <View style={st.tabs}>
        {tabs.map(([k, label]) => (
          <TouchableOpacity key={k} style={st.tab} onPress={() => { setTab(k); setDetail(null); }}>
            <Text style={[st.tabT, tab === k && { color: C.blue, fontWeight: "700" }]}>{label}</Text>
          </TouchableOpacity>
        ))}
      </View>
    </SafeAreaView>
  );
}

const st = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.bg },
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  tabs: { flexDirection: "row", borderTopWidth: 1, borderTopColor: C.line, backgroundColor: C.card },
  tab: { flex: 1, alignItems: "center", paddingVertical: 14 },
  tabT: { color: C.muted, fontSize: 14 },
});
