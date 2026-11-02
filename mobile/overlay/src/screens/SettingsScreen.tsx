import { useState } from "react";
import { Alert, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity } from "react-native";
import { ping } from "../api";
import { saveSettings } from "../storage";
import { C } from "../theme";
import { Settings } from "../types";

export default function SettingsScreen({ settings, onSaved }: { settings: Settings; onSaved: (s: Settings) => void }) {
  const [s, setS] = useState(settings);
  const set = (k: keyof Settings) => (v: string) => setS({ ...s, [k]: v });

  async function save() {
    const clean = { ...s, server: s.server.trim().replace(/\/+$/, "") };
    await saveSettings(clean);
    onSaved(clean);
    try {
      const r = await ping(clean);
      Alert.alert("Kết nối OK", `Server có ${r.skus} SKU.`);
    } catch (e: any) {
      Alert.alert("Đã lưu, nhưng chưa kết nối được", String(e?.message || e));
    }
  }

  const field = (label: string, k: keyof Settings, props: object = {}) => (
    <>
      <Text style={st.label}>{label}</Text>
      <TextInput style={st.input} value={s[k]} onChangeText={set(k)} autoCapitalize="none" autoCorrect={false} {...props} />
    </>
  );

  return (
    <ScrollView contentContainerStyle={st.wrap} keyboardShouldPersistTaps="handled">
      <Text style={st.h}>Cài đặt</Text>
      {field("Địa chỉ server", "server", { placeholder: "http://1.2.3.4", keyboardType: "url" })}
      {field("API key", "apiKey", { secureTextEntry: true })}
      {field("Mã SA/BA", "saId", { placeholder: "sa01" })}
      {field("Tên SA/BA", "saName")}
      {field("Cửa hàng / điểm bán", "store")}
      <TouchableOpacity style={st.btn} onPress={save}><Text style={st.btnT}>Lưu & kiểm tra kết nối</Text></TouchableOpacity>
    </ScrollView>
  );
}

const st = StyleSheet.create({
  wrap: { padding: 20, paddingTop: 60 },
  h: { fontSize: 24, fontWeight: "700", color: C.ink, marginBottom: 12 },
  label: { color: C.muted, marginTop: 14, marginBottom: 6, fontSize: 13 },
  input: { backgroundColor: C.card, borderWidth: 1, borderColor: C.line, borderRadius: 10, padding: 12, fontSize: 16, color: C.ink },
  btn: { backgroundColor: C.blue, padding: 14, borderRadius: 12, marginTop: 24, alignItems: "center" },
  btnT: { color: "#fff", fontWeight: "600", fontSize: 16 },
});
