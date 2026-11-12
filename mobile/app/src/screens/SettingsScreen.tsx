import { useEffect, useState } from "react";
import { Alert, KeyboardAvoidingView, Platform, ScrollView, StyleSheet, Switch, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { deleteVoiceprint, pendingCount, ping, revokeToken, voiceprintStatus } from "../api";
import { Banner, Button, Card, Field, Pill, Title } from "../components";
import EnrollScreen from "./EnrollScreen";
import { saveSettings } from "../storage";
import { OfflineStatus, downloadOfflineModel, offlineStatus } from "../stt";
import { C, S } from "../theme";
import { Settings } from "../types";

export default function SettingsScreen({ settings, onSaved, onLogout }: {
  settings: Settings; onSaved: (s: Settings) => void; onLogout: () => void;
}) {
  const insets = useSafeAreaInsets();
  const [store, setStore] = useState(settings.store);
  const [status, setStatus] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [enrolled, setEnrolled] = useState<boolean | null>(null);  // null: chưa biết (chưa kết nối server)
  const [enrolling, setEnrolling] = useState(false);
  const [offline, setOffline] = useState<OfflineStatus | null>(null);
  const [offlineMsg, setOfflineMsg] = useState("");
  const [dl, setDl] = useState(false);

  const checkOffline = () => offlineStatus().then(setOffline);
  useEffect(() => { checkOffline(); }, []);

  async function toggleOffline(v: boolean) {
    const next = { ...settings, offlineStt: v };
    await saveSettings(next);
    onSaved(next);
  }

  async function getModel() {
    setDl(true);
    try { setOfflineMsg(await downloadOfflineModel()); } catch (e: any) { setOfflineMsg("Không tải được: " + String(e?.message || e)); }
    finally { setDl(false); checkOffline(); }
  }

  useEffect(() => {
    if (!settings.server || !settings.token) { setEnrolled(null); return; }
    voiceprintStatus(settings).then((r) => setEnrolled(r.enrolled)).catch(() => setEnrolled(null));
  }, [settings.server, settings.token, settings.saId]);

  function removeVoice() {
    Alert.alert("Xoá dấu giọng?", "Hệ thống sẽ không còn phân biệt lời bạn và lời khách trong các cuộc tư vấn mới.", [
      { text: "Huỷ", style: "cancel" },
      { text: "Xoá", style: "destructive", onPress: () => deleteVoiceprint(settings).then(() => setEnrolled(false)).catch((e) => Alert.alert("Lỗi", String(e?.message || e))) },
    ]);
  }

  async function confirmLogout() {
    const n = await pendingCount().catch(() => 0);
    Alert.alert(
      "Đăng xuất?",
      n > 0
        ? `Còn ${n} bản ghi chưa gửi. Chúng được giữ trên máy và tự gửi khi bạn đăng nhập lại.`
        : "Bạn sẽ cần nhập lại mật khẩu để vào app.",
      [
        { text: "Huỷ", style: "cancel" },
        { text: "Đăng xuất", style: "destructive", onPress: async () => { await revokeToken(settings); onLogout(); } },
      ],
    );
  }

  if (enrolling) {
    return <EnrollScreen settings={settings} alreadyEnrolled={!!enrolled}
      onClose={(ok) => { setEnrolling(false); if (ok) setEnrolled(true); }} />;
  }

  async function save() {
    setBusy(true);
    const next = { ...settings, store: store.trim() };
    await saveSettings(next);
    onSaved(next);
    try {
      const r = await ping(next);
      setStatus({ ok: true, text: `Đã lưu. Kết nối OK, server có ${r.skus} SKU.` });
    } catch (e: any) {
      setStatus({ ok: false, text: `Đã lưu, nhưng chưa kết nối được: ${String(e?.message || e)}` });
    } finally { setBusy(false); }
  }

  const initial = (settings.saName || settings.saId || "?").trim().charAt(0).toUpperCase();
  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <ScrollView contentContainerStyle={{ padding: S.page, paddingTop: insets.top + S.lg, paddingBottom: 40 }} keyboardShouldPersistTaps="handled">
        <Title>Cài đặt</Title>

        <Card>
          <View style={st.acc}>
            <View style={st.avatar}><Text style={st.avatarT}>{initial}</Text></View>
            <View style={{ flex: 1 }}>
              <Text style={st.name} numberOfLines={1}>{settings.saName || settings.saId}</Text>
              <Text style={st.meta}>Mã BA: {settings.saId}</Text>
              <Text style={st.meta} numberOfLines={1}>{settings.server.replace(/^https?:\/\//, "")}</Text>
            </View>
          </View>
        </Card>

        <Text style={st.sec}>Điểm bán</Text>
        <Field label="Cửa hàng / điểm bán" value={store} onChangeText={setStore} autoCapitalize="words" style={{ marginTop: S.sm }} />
        <Button label="Lưu và kiểm tra kết nối" onPress={save} loading={busy} style={{ marginTop: S.lg }} />
        {status && <Banner tone={status.ok ? "ok" : "bad"} text={status.text} style={{ marginTop: S.md, marginBottom: 0 }} />}

        <Text style={st.sec}>Nhận dạng giọng nói</Text>
        <Card style={{ marginTop: S.sm }}>
          <Pill
            text={!offline ? "Đang kiểm tra..." : !offline.supported ? "Máy không hỗ trợ offline" : offline.installed ? "Đã cài gói tiếng Việt" : "Chưa cài gói tiếng Việt"}
            tone={offline?.installed ? "green" : "amber"} />
          <View style={{ flexDirection: "row", alignItems: "center", marginTop: S.md, gap: S.md }}>
            <Text style={{ flex: 1, color: C.ink, fontWeight: "700" }}>Nhận dạng offline trên máy</Text>
            <Switch value={!!settings.offlineStt} onValueChange={toggleOffline} disabled={!offline?.installed} accessibilityLabel="Nhận dạng offline" />
          </View>
          <Text style={{ color: C.muted, lineHeight: 20, marginTop: S.sm }}>
            Nhanh hơn, dùng được khi không có mạng và không gửi âm thanh cho Google/Apple. Cần tải gói tiếng Việt một lần (khoảng vài chục MB). Chất lượng có thể khác chế độ online.
          </Text>
          {offline?.supported && !offline.installed && (
            <Button kind="ghost" label="Tải gói tiếng Việt" onPress={getModel} loading={dl} style={{ marginTop: S.md }} />
          )}
          {!!offline?.reason && <Text style={{ color: C.muted, marginTop: S.sm }}>Lý do: {offline.reason}.</Text>}
          {!!offlineMsg && <Banner tone="info" text={offlineMsg} style={{ marginTop: S.md, marginBottom: 0 }} />}
        </Card>

        <Text style={st.sec}>Giọng nói của bạn</Text>
        <Card style={{ marginTop: S.sm }}>
          <Pill text={enrolled ? "Đã đăng ký" : enrolled === false ? "Chưa đăng ký" : "Chưa kiểm tra được"} tone={enrolled ? "green" : "amber"} />
          <Text style={{ color: C.muted, lineHeight: 20, marginTop: S.sm }}>
            Đăng ký giọng để hệ thống tách lời bạn và lời khách, giúp đọc đúng khách đồng ý hay từ chối.
          </Text>
          <Button kind="ghost" label={enrolled ? "Đăng ký lại giọng" : "Đăng ký giọng nói"} disabled={!settings.server || !settings.token}
            onPress={() => setEnrolling(true)} style={{ marginTop: S.md }} />
          {enrolled && <Button kind="ghost" label="Xoá dấu giọng" onPress={removeVoice} style={{ marginTop: S.sm }} />}
        </Card>

        <Button kind="ghost" label="Đăng xuất" onPress={confirmLogout} style={{ marginTop: S.xl }} />
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const st = StyleSheet.create({
  sec: { marginTop: S.xl, fontSize: 13, fontWeight: "800", color: C.brand, textTransform: "uppercase", letterSpacing: 0.6 },
  acc: { flexDirection: "row", alignItems: "center", gap: S.md },
  avatar: { width: 52, height: 52, borderRadius: 26, backgroundColor: C.tint, alignItems: "center", justifyContent: "center" },
  avatarT: { fontSize: 22, fontWeight: "800", color: C.brand },
  name: { fontSize: 18, fontWeight: "800", color: C.ink },
  meta: { color: C.muted, marginTop: 2 },
});
