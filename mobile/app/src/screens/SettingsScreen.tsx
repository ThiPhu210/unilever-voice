import { useEffect, useState } from "react";
import { Alert, KeyboardAvoidingView, Platform, ScrollView, StyleSheet, Text, TextInput } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { deleteVoiceprint, ping, voiceprintStatus } from "../api";
import { Button, Card, Pill } from "../components";
import EnrollScreen from "./EnrollScreen";
import { saveSettings } from "../storage";
import { C, R } from "../theme";
import { Settings } from "../types";

export default function SettingsScreen({ settings, onSaved }: { settings: Settings; onSaved: (s: Settings) => void }) {
  const insets = useSafeAreaInsets();
  const [s, setS] = useState(settings);
  const [status, setStatus] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof Settings) => (v: string) => setS({ ...s, [k]: v });
  const [enrolled, setEnrolled] = useState<boolean | null>(null);  // null: chưa biết (chưa kết nối server)
  const [enrolling, setEnrolling] = useState(false);

  useEffect(() => {
    if (!settings.server || !settings.apiKey) { setEnrolled(null); return; }
    voiceprintStatus(settings).then((r) => setEnrolled(r.enrolled)).catch(() => setEnrolled(null));
  }, [settings.server, settings.apiKey, settings.saId]);

  function removeVoice() {
    Alert.alert("Xoá dấu giọng?", "Hệ thống sẽ không còn phân biệt lời bạn và lời khách trong các cuộc tư vấn mới.", [
      { text: "Huỷ", style: "cancel" },
      { text: "Xoá", style: "destructive", onPress: () => deleteVoiceprint(settings).then(() => setEnrolled(false)).catch((e) => Alert.alert("Lỗi", String(e?.message || e))) },
    ]);
  }

  if (enrolling) {
    return <EnrollScreen settings={settings} alreadyEnrolled={!!enrolled}
      onClose={(ok) => { setEnrolling(false); if (ok) setEnrolled(true); }} />;
  }

  async function save() {
    setBusy(true);
    const clean = { ...s, server: s.server.trim().replace(/\/+$/, "") };
    await saveSettings(clean);
    onSaved(clean);
    try {
      const r = await ping(clean);
      setStatus({ ok: true, text: `Kết nối OK. Server có ${r.skus} SKU.` });
    } catch (e: any) {
      setStatus({ ok: false, text: `Đã lưu, nhưng chưa kết nối được: ${String(e?.message || e)}` });
    } finally { setBusy(false); }
  }

  const field = (label: string, k: keyof Settings, props: object = {}) => (
    <>
      <Text style={st.label}>{label}</Text>
      <TextInput style={st.input} value={s[k]} onChangeText={set(k)} autoCapitalize="none" autoCorrect={false}
        placeholderTextColor={C.muted} accessibilityLabel={label} {...props} />
    </>
  );

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <ScrollView contentContainerStyle={{ padding: 20, paddingTop: insets.top + 16, paddingBottom: 40 }} keyboardShouldPersistTaps="handled">
        <Text style={st.h}>Cài đặt</Text>
        <Text style={st.sec}>Kết nối server</Text>
        {field("Địa chỉ server", "server", { placeholder: "http://1.2.3.4", keyboardType: "url" })}
        {field("API key", "apiKey", { secureTextEntry: true })}
        <Text style={st.sec}>Thông tin SA/BA</Text>
        {field("Mã SA/BA", "saId", { placeholder: "sa01" })}
        {field("Tên SA/BA", "saName", { autoCapitalize: "words" })}
        {field("Cửa hàng / điểm bán", "store", { autoCapitalize: "words" })}
        <Text style={st.sec}>Giọng nói của bạn</Text>
        <Card style={{ marginTop: 10 }}>
          <Pill text={enrolled ? "Đã đăng ký" : enrolled === false ? "Chưa đăng ký" : "Chưa kiểm tra được"} tone={enrolled ? "green" : "amber"} />
          <Text style={{ color: C.muted, lineHeight: 20, marginTop: 8 }}>
            Đăng ký giọng để hệ thống tách lời bạn và lời khách, giúp đọc đúng khách đồng ý hay từ chối. Cần lưu cài đặt (mã SA/BA, server) trước.
          </Text>
          <Button kind="ghost" label={enrolled ? "Đăng ký lại giọng" : "Đăng ký giọng nói"} disabled={!settings.server || !settings.apiKey}
            onPress={() => setEnrolling(true)} style={{ marginTop: 10 }} />
          {enrolled && <Button kind="ghost" label="Xoá dấu giọng" onPress={removeVoice} style={{ marginTop: 8 }} />}
        </Card>
        <Button label={busy ? "Đang kiểm tra..." : "Lưu và kiểm tra kết nối"} onPress={save} disabled={busy} style={{ marginTop: 24 }} />
        {status && (
          <Card tone={status.ok ? undefined : "bad"} style={{ marginTop: 14, ...(status.ok ? { backgroundColor: C.greenBg, borderColor: C.green } : {}) }}>
            <Text style={{ color: status.ok ? C.green : C.red, fontWeight: "700", lineHeight: 20 }}>{status.text}</Text>
          </Card>
        )}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const st = StyleSheet.create({
  h: { fontSize: 28, fontWeight: "800", color: C.ink },
  sec: { marginTop: 22, fontSize: 13, fontWeight: "800", color: C.brand, textTransform: "uppercase", letterSpacing: 0.6 },
  label: { color: C.muted, marginTop: 12, marginBottom: 6, fontSize: 13, fontWeight: "600" },
  input: { backgroundColor: C.card, borderWidth: 1.5, borderColor: C.line, borderRadius: R.input, paddingHorizontal: 14, height: 50, fontSize: 16, color: C.ink },
});
