import { useEffect, useRef, useState } from "react";
import { Alert, Animated, Easing, ScrollView, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { AudioModule, RecordingPresets, setAudioModeAsync, useAudioRecorder, useAudioRecorderState } from "expo-audio";
import { activateKeepAwakeAsync, deactivateKeepAwake } from "expo-keep-awake";
import { enqueueAndFlush, pendingCount } from "../api";
import AudioPlayer from "../AudioPlayer";
import { Button, Card, Pill } from "../components";
import { mmss } from "../format";
import { C } from "../theme";
import { Settings } from "../types";

// Ghi âm mono 16kHz AAC ~ 0.35 MB/phút: đủ cho ASR, nhẹ khi upload qua 4G.
const OPTIONS = { ...RecordingPresets.HIGH_QUALITY, sampleRate: 16000, numberOfChannels: 1, bitRate: 48000, isMeteringEnabled: true };
const MAX_CHUNK_MS = 15 * 60 * 1000; // tự cắt file mỗi 15 phút để an toàn (đoạn tự cắt được gửi luôn, không qua bước nghe lại)
const BARS = 30;

type Result = { kind: "sent" | "queued" | "error"; text: string };
type Draft = { uri: string; ms: number }; // bản ghi vừa dừng, chưa gửi

export default function RecordScreen({ settings, onUploaded }: { settings: Settings; onUploaded: (id?: string) => void }) {
  const insets = useSafeAreaInsets();
  const recorder = useAudioRecorder(OPTIONS);
  const state = useAudioRecorderState(recorder, 150);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Result | null>(null);
  const [pending, setPending] = useState(0);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [levels, setLevels] = useState<number[]>(() => Array(BARS).fill(0));
  const rotating = useRef(false);
  const pulse = useRef(new Animated.Value(0)).current;
  const rec = state.isRecording;

  useEffect(() => {
    pendingCount().then(setPending);
    enqueueAndFlush(settings).then((r) => { setPending(r.left); if (r.error) setResult({ kind: "error", text: r.error }); }).catch(() => {}); // thử gửi lại các bản tồn
  }, [settings]);

  // Sóng âm: dB (-60..0) -> 0..1
  useEffect(() => {
    if (!rec) { setLevels(Array(BARS).fill(0)); return; }
    const m = typeof state.metering === "number" ? state.metering : -60;
    const v = Math.max(0, Math.min(1, (m + 60) / 60));
    setLevels((l) => [...l.slice(1), v]);
  }, [state.metering, state.durationMillis, rec]);

  useEffect(() => {
    if (!rec) { pulse.setValue(0); return; }
    const loop = Animated.loop(Animated.timing(pulse, { toValue: 1, duration: 1600, easing: Easing.out(Easing.quad), useNativeDriver: true }));
    loop.start();
    return () => loop.stop();
  }, [rec, pulse]);

  async function begin() {
    try {
      const perm = await AudioModule.requestRecordingPermissionsAsync();
      if (!perm.granted) return Alert.alert("Cần quyền micro", "Hãy cấp quyền micro cho ứng dụng.");
      await setAudioModeAsync({ playsInSilentMode: true, allowsRecording: true });
      await recorder.prepareToRecordAsync();
      recorder.record();
      activateKeepAwakeAsync("rec");
      setResult(null);
    } catch (e: any) {
      setResult({ kind: "error", text: "Không bật được micro: " + String(e?.message || e) });
    }
  }

  /** Đưa file lên hàng đợi và gửi; openDetail = gửi xong thì mở thẳng màn xác nhận đơn. */
  async function uploadUri(uri: string, openDetail: boolean) {
    const { left, ids, error } = await enqueueAndFlush(settings, uri);
    setPending(left);
    const id = ids[ids.length - 1];
    setResult(left
      ? { kind: "queued", text: `Đã lưu trên máy. ${left} bản chờ gửi. ${error ?? ""}` }
      : { kind: "sent", text: "Đã gửi lên server. Hệ thống đang dịch giọng nói." });
    onUploaded(openDetail && !left ? id : undefined);
  }

  /** Dừng ghi: KHÔNG gửi ngay, giữ làm bản nháp để SA nghe lại rồi chọn gửi hoặc xoá. */
  async function stop() {
    setBusy(true);
    const ms = state.durationMillis;
    try {
      await recorder.stop();
      deactivateKeepAwake("rec");
      const uri = recorder.uri;
      if (!uri) throw new Error("Không lấy được file ghi âm");
      setDraft({ uri, ms });
      setResult(null);
    } catch (e: any) {
      setResult({ kind: "error", text: "Lỗi: " + String(e?.message || e) });
    } finally {
      setBusy(false);
    }
  }

  async function send() {
    if (!draft) return;
    setBusy(true);
    try {
      await uploadUri(draft.uri, true);
      setDraft(null);
    } catch (e: any) {   // lỗi bất ngờ: giữ nguyên bản nháp để bấm gửi lại
      setResult({ kind: "error", text: "Lỗi: " + String(e?.message || e) });
    } finally {
      setBusy(false);
    }
  }

  function discard() {
    Alert.alert("Xoá bản ghi này?", "Bản ghi chưa gửi sẽ bị xoá, bạn cần ghi âm lại từ đầu.", [
      { text: "Giữ lại", style: "cancel" },
      { text: "Xoá", style: "destructive", onPress: () => { setDraft(null); setResult(null); } },
    ]);
  }

  /** Ghi quá lâu: gửi đoạn hiện tại luôn và ghi tiếp đoạn mới. */
  async function rotate() {
    setBusy(true);
    try {
      await recorder.stop();
      const uri = recorder.uri;
      if (uri) await uploadUri(uri, false);
      await recorder.prepareToRecordAsync();
      recorder.record();
    } catch (e: any) {
      setResult({ kind: "error", text: "Lỗi: " + String(e?.message || e) });
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (rec && state.durationMillis > MAX_CHUNK_MS && !rotating.current) {
      rotating.current = true;
      rotate().finally(() => { rotating.current = false; });
    }
  }, [state.durationMillis, rec]);

  const ringScale = pulse.interpolate({ inputRange: [0, 1], outputRange: [1, 1.55] });
  const ringOpacity = pulse.interpolate({ inputRange: [0, 1], outputRange: [0.35, 0] });

  return (
    <ScrollView contentContainerStyle={[st.wrap, { paddingTop: insets.top + 16 }]} keyboardShouldPersistTaps="handled">
      <View style={st.top}>
        <View style={{ flex: 1 }}>
          <Text style={st.hello}>Xin chào, {settings.saName || "SA/BA"}</Text>
          <Text style={st.store}>{settings.store || "Chưa đặt điểm bán (vào Cài đặt)"}</Text>
        </View>
        {rec ? <Pill text="ĐANG GHI ÂM" tone="red" /> : draft ? <Pill text="CHỜ GỬI" tone="amber" /> : <Pill text="Sẵn sàng" tone="green" />}
      </View>

      {draft ? (
        <Card style={{ marginTop: 16 }}>
          <Text style={st.draftH}>Bản ghi vừa xong · {mmss(draft.ms)}</Text>
          <Text style={st.draftSub}>Nghe lại trước khi gửi. Chưa ổn thì xoá và ghi âm lại.</Text>
          <AudioPlayer uri={draft.uri} />
          <Button label={busy ? "Đang gửi..." : "Gửi lên server"} onPress={send} disabled={busy} style={{ marginTop: 16 }} />
          <Button kind="ghost" label="Xoá và ghi âm lại" onPress={discard} disabled={busy} style={{ marginTop: 10 }} />
        </Card>
      ) : (
        <View style={st.stage}>
          <Text style={[st.timer, rec && { color: C.red }]}>{mmss(rec ? state.durationMillis : 0)}</Text>
          <View style={st.wave} accessibilityLabel="Mức âm thanh">
            {levels.map((v, i) => (
              <View key={i} style={[st.bar, { height: 4 + v * 44, backgroundColor: rec ? C.red : C.line }]} />
            ))}
          </View>
          <View style={st.btnWrap}>
            {rec && <Animated.View pointerEvents="none" style={[st.ring, { transform: [{ scale: ringScale }], opacity: ringOpacity }]} />}
            <TouchableOpacity
              accessibilityRole="button"
              accessibilityLabel={rec ? "Kết thúc tư vấn" : "Bắt đầu tư vấn"}
              disabled={busy} activeOpacity={0.85}
              onPress={() => (rec ? stop() : begin())}
              style={[st.rec, busy && { opacity: 0.5 }]}
            >
              {rec ? <View style={st.stopSq} /> : <View style={st.dot} />}
            </TouchableOpacity>
          </View>
          <Text style={st.cta}>{rec ? "Chạm để kết thúc tư vấn" : "Chạm để bắt đầu tư vấn"}</Text>
        </View>
      )}

      {result && (
        <Card tone={result.kind === "error" ? "bad" : undefined} style={result.kind === "sent" ? { backgroundColor: C.greenBg, borderColor: C.green } : undefined}>
          <Text style={[st.resT, { color: result.kind === "error" ? C.red : result.kind === "sent" ? C.green : C.amber }]}>{result.text}</Text>
        </Card>
      )}
      {pending > 0 && (
        <Card tone="warn">
          <Text style={{ color: C.amber, fontWeight: "700" }}>{pending} bản ghi đang chờ gửi</Text>
          <Button kind="ghost" label="Gửi lại ngay" style={{ marginTop: 10 }}
            onPress={() => enqueueAndFlush(settings).then((r) => {
              setPending(r.left);
              setResult(r.error ? { kind: "error", text: r.error } : { kind: "sent", text: "Đã gửi xong các bản đang chờ." });
              if (r.ids.length) onUploaded(r.ids[r.ids.length - 1]);
            }).catch((e) => setResult({ kind: "error", text: String(e?.message || e) }))} />
        </Card>
      )}

      <Card style={{ backgroundColor: C.tint, borderColor: C.tint }}>
        <Text style={st.tplH}>Câu chốt đơn mẫu</Text>
        <Text style={st.tpl}>
          “Dạ em xin cảm ơn anh/chị, vậy mình chốt{" "}
          <Text style={st.ph}>{"{số lượng}"}</Text> <Text style={st.ph}>{"{tên SKU 1}"}</Text> <Text style={st.ph}>{"{giá}"}</Text> nghìn đồng,{" "}
          <Text style={st.ph}>{"{số lượng}"}</Text> <Text style={st.ph}>{"{tên SKU 2}"}</Text> <Text style={st.ph}>{"{giá}"}</Text> nghìn đồng,{" "}
          <Text style={st.ph}>{"{số lượng}"}</Text> <Text style={st.ph}>{"{tên SKU 3}"}</Text> <Text style={st.ph}>{"{giá}"}</Text> nghìn đồng, …”
        </Text>
        <Text style={st.tplEx}>
          Ví dụ: “Dạ em xin cảm ơn anh/chị, vậy mình chốt 3 Hazeline sữa dưỡng thể matcha lựu đỏ 370 mi li lít giá 100 nghìn đồng, …”
        </Text>
        <Text style={st.tplNote}>Nhớ đọc đủ số lượng, tên SKU và giá cho từng sản phẩm. Dòng thiếu giá sẽ không được ghi nhận, nhưng bạn có thể thêm tay ở màn hình xác nhận đơn.</Text>
      </Card>
    </ScrollView>
  );
}

const st = StyleSheet.create({
  wrap: { paddingHorizontal: 20, paddingBottom: 28 },
  top: { flexDirection: "row", alignItems: "center", gap: 12 },
  hello: { fontSize: 22, fontWeight: "800", color: C.ink },
  store: { color: C.muted, marginTop: 2 },
  stage: { alignItems: "center", paddingVertical: 28 },
  timer: { fontSize: 64, fontWeight: "300", color: C.ink, fontVariant: ["tabular-nums"] },
  wave: { height: 52, flexDirection: "row", alignItems: "center", gap: 4, marginVertical: 18 },
  bar: { width: 5, borderRadius: 3 },
  btnWrap: { width: 112, height: 112, alignItems: "center", justifyContent: "center" },
  ring: { position: "absolute", width: 96, height: 96, borderRadius: 48, backgroundColor: C.red },
  rec: { width: 96, height: 96, borderRadius: 48, backgroundColor: C.card, borderWidth: 5, borderColor: C.red, alignItems: "center", justifyContent: "center" },
  dot: { width: 52, height: 52, borderRadius: 26, backgroundColor: C.red },
  stopSq: { width: 36, height: 36, borderRadius: 8, backgroundColor: C.red },
  cta: { marginTop: 14, color: C.muted, fontWeight: "600" },
  draftH: { fontWeight: "800", color: C.ink, fontSize: 17 },
  draftSub: { color: C.muted, marginTop: 4, lineHeight: 20 },
  resT: { fontWeight: "700", lineHeight: 21 },
  tplH: { fontWeight: "800", color: C.ink, marginBottom: 6 },
  tpl: { color: C.ink, lineHeight: 22 },
  ph: { color: C.red, fontWeight: "700" },
  tplEx: { color: C.muted, marginTop: 8, lineHeight: 20, fontStyle: "italic" },
  tplNote: { color: C.amber, marginTop: 8, fontWeight: "600", lineHeight: 20 },
});
