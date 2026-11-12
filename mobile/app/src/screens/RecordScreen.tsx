import { useEffect, useMemo, useRef, useState } from "react";
import { Alert, Animated, Easing, ScrollView, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { AudioModule, RecordingPresets, setAudioModeAsync, useAudioRecorder, useAudioRecorderState } from "expo-audio";
import { activateKeepAwakeAsync, deactivateKeepAwake } from "expo-keep-awake";
import { enqueueAndFlush, NewRecording, pendingCount } from "../api";
import AudioPlayer from "../AudioPlayer";
import { cachedCatalog, loadCatalog, refreshCatalog } from "../catalogStore";
import { Button, Card, Pill } from "../components";
import { mmss, vnd } from "../format";
import { Order as ParsedOrder, PARSER_VERSION, parseTranscript } from "../parser";
import { SttSession, offlineStatus, startStt, sttSupport, transcribeFile } from "../stt";
import { C } from "../theme";
import { Settings } from "../types";

// Ghi âm mono 16kHz AAC ~ 0.35 MB/phút: đủ cho ASR, nhẹ khi upload qua 4G.
const OPTIONS = { ...RecordingPresets.HIGH_QUALITY, sampleRate: 16000, numberOfChannels: 1, bitRate: 48000, isMeteringEnabled: true };
const MAX_CHUNK_MS = 15 * 60 * 1000; // tự cắt file mỗi 15 phút để an toàn (đoạn tự cắt được gửi luôn, không qua bước nghe lại)
const MAX_NATIVE_MS = 3 * 60 * 1000; // ghi + nhận dạng trên máy: cuộc tư vấn <1 phút, quá 3 phút thì tự dừng
const BARS = 30;
const tick = () => new Promise<void>((r) => setTimeout(r, 0)); // nhường luồng UI để kịp vẽ "Đang xử lý" trước khi parser chạy

type Result = { kind: "sent" | "queued" | "error"; text: string };
/** Bản ghi vừa dừng, chưa gửi. native = ghi + nhận dạng trên máy (file WAV); transcript/orders là kết quả trên máy. */
type Draft = { uri: string; ms: number; native?: boolean; transcript?: string; engine?: string; orders?: ParsedOrder[] | null };

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
  // Ghi + nhận dạng trên máy (iOS / Android 13+); máy không đủ điều kiện thì dùng luồng cũ (ghi m4a, server dịch)
  const support = useMemo(() => sttSupport(), []);
  const [nativeRec, setNativeRec] = useState(false);
  const [nativeMs, setNativeMs] = useState(0);
  const [partial, setPartial] = useState("");
  const session = useRef<SttSession | null>(null);
  const offlineRun = useRef(false);   // lần ghi này có chạy offline không (để dịch lại từ file cùng chế độ)
  const startedAt = useRef(0);
  const rec = nativeRec || state.isRecording;
  const elapsed = nativeRec ? nativeMs : state.durationMillis;

  useEffect(() => {
    pendingCount().then(setPending);
    enqueueAndFlush(settings).then((r) => { setPending(r.left); if (r.error) setResult({ kind: "error", text: r.error }); }).catch(() => {}); // thử gửi lại các bản tồn
    refreshCatalog(settings).catch(() => {});   // danh mục SKU cho parser trên máy: tải/cập nhật ở nền
  }, [settings]);

  // Đồng hồ khi ghi bằng bộ nhận dạng (không có state.durationMillis của expo-audio) + tự dừng nếu quá lâu
  useEffect(() => {
    if (!nativeRec) return;
    const t = setInterval(() => {
      const ms = Date.now() - startedAt.current;
      setNativeMs(ms);
      if (ms > MAX_NATIVE_MS) stopNative();
    }, 200);
    return () => clearInterval(t);
  }, [nativeRec]);

  // Sóng âm: dB (-60..0) -> 0..1 (ghi bằng bộ nhận dạng thì mức âm đến từ onLevel)
  useEffect(() => {
    if (!rec) { setLevels(Array(BARS).fill(0)); return; }
    if (nativeRec) return;
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
    if (support.ok) return beginNative();
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

  async function beginNative() {
    try {
      setResult(null); setPartial("");
      const cat = await cachedCatalog();          // không chờ mạng: chưa có thì bỏ qua gợi ý từ khoá
      // Bật offline chỉ khi người dùng đã chọn VÀ gói vi-VN đã cài; thiếu gói thì lùi về online thay vì lỗi
      offlineRun.current = !!settings.offlineStt && (await offlineStatus()).installed;
      session.current = await startStt({
        offline: offlineRun.current,
        hotwords: cat?.hotwords ?? [],
        onLevel: (v) => setLevels((l) => [...l.slice(1), v]),
        onPartial: setPartial,
        onEnded: () => { if (session.current) stopNative(); },   // bộ nhận dạng tự kết thúc (mất mạng...): chốt bản ghi
      });
      startedAt.current = Date.now();
      setNativeMs(0); setNativeRec(true);
      activateKeepAwakeAsync("rec");
    } catch (e: any) {
      session.current = null;
      setResult({ kind: "error", text: "Không bật được nhận dạng giọng nói: " + String(e?.message || e) });
    }
  }

  /** Dừng ghi + nhận dạng: lấy WAV và transcript, tách đơn ngay trên máy, rồi để SA xem lại trước khi gửi. */
  async function stopNative() {
    const sess = session.current;
    if (!sess) return;
    session.current = null;
    setBusy(true);
    const ms = Date.now() - startedAt.current;
    setNativeRec(false);
    deactivateKeepAwake("rec");
    try {
      const r = await sess.stop();
      if (!r.uri) throw new Error("Không lưu được file ghi âm" + (r.error ? ` (${r.error})` : ""));
      const cat = await cachedCatalog();
      let transcript = r.transcript.trim();
      if (!transcript) transcript = (await transcribeFile(r.uri, cat?.hotwords ?? [], offlineRun.current)).trim();   // dịch lại từ file đã lưu
      let orders: ParsedOrder[] | null = null;
      if (transcript) {
        try {
          const catalog = cat ?? (await loadCatalog(settings));   // lần đầu chưa có danh mục: tải về (cần mạng)
          if (catalog) { await tick(); orders = parseTranscript(transcript, catalog).orders; }
        } catch (e) {
          console.warn("Parser trên máy lỗi, để server tách đơn:", e);   // vd Hermes thiếu một tính năng regex
        }
      }
      setDraft({ uri: r.uri, ms, native: true, transcript, engine: r.engine, orders });
      setResult(null); setPartial("");
    } catch (e: any) {
      setResult({ kind: "error", text: "Lỗi: " + String(e?.message || e) });
    } finally {
      setBusy(false);
    }
  }

  /** Đưa bản ghi lên hàng đợi và gửi; openDetail = gửi xong thì mở thẳng màn xác nhận đơn. */
  async function uploadUri(rec: string | NewRecording, openDetail: boolean) {
    const { left, ids, error } = await enqueueAndFlush(settings, rec);
    setPending(left);
    const id = ids[ids.length - 1];
    const onDevice = typeof rec !== "string" && rec.transcript !== undefined;
    setResult(left
      ? { kind: "queued", text: `Đã lưu trên máy. ${left} bản chờ gửi. ${error ?? ""}` }
      : { kind: "sent", text: onDevice ? "Đã tạo đơn từ nội dung nhận dạng trên máy." : "Đã gửi lên server. Hệ thống đang dịch giọng nói." });
    onUploaded(openDetail && id ? id : undefined);
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
      // Có transcript từ máy: gửi kết quả (đơn đã tách) + audio. Trống (không nhận dạng được): gửi audio cho server dịch như cũ.
      const rec: string | NewRecording = draft.native && draft.transcript
        ? { uri: draft.uri, durationMs: draft.ms, transcript: draft.transcript, engine: draft.engine, orders: draft.orders ?? null,
            parserVersion: draft.orders ? PARSER_VERSION : undefined }
        : draft.uri;
      await uploadUri(rec, true);
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
          {draft.native && <OnDeviceResult draft={draft} />}
          <Button label={busy ? "Đang gửi..." : draft.native && draft.transcript ? "Tạo đơn & gửi" : "Gửi lên server"} onPress={send} disabled={busy} style={{ marginTop: 16 }} />
          <Button kind="ghost" label="Xoá và ghi âm lại" onPress={discard} disabled={busy} style={{ marginTop: 10 }} />
        </Card>
      ) : (
        <View style={st.stage}>
          <Text style={[st.timer, rec && { color: C.red }]}>{mmss(rec ? elapsed : 0)}</Text>
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
              onPress={() => (rec ? (nativeRec ? stopNative() : stop()) : begin())}
              style={[st.rec, busy && { opacity: 0.5 }]}
            >
              {rec ? <View style={st.stopSq} /> : <View style={st.dot} />}
            </TouchableOpacity>
          </View>
          <Text style={st.cta}>{rec ? "Chạm để kết thúc tư vấn" : busy ? "Đang xử lý..." : "Chạm để bắt đầu tư vấn"}</Text>
          {nativeRec && !!partial && <Text style={st.partial} numberOfLines={3}>{partial}</Text>}
          {!rec && !support.ok && <Text style={st.fallback}>Máy này chưa nhận dạng giọng nói trên máy được ({support.reason}): bản ghi sẽ gửi cho server dịch.</Text>}
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

/** Kết quả nhận dạng + đơn tách ngay trên máy: SA xem nhanh trước khi gửi (chỉnh sửa chi tiết ở màn xác nhận đơn sau khi gửi). */
function OnDeviceResult({ draft }: { draft: Draft }) {
  const orders = draft.orders ?? [];
  const items = orders.flatMap((o) => o.items);
  return (
    <View style={st.parsed}>
      <Text style={st.parsedH}>Nhận dạng trên máy</Text>
      {!draft.transcript ? (
        <Text style={st.warnTxt}>Không nhận dạng được trên máy (có thể do mất mạng hoặc nói quá nhỏ). Bản ghi sẽ được gửi cho server dịch.</Text>
      ) : (
        <>
          <Text style={st.transcript}>“{draft.transcript}”</Text>
          {draft.orders === null ? (
            <Text style={st.muted}>Chưa có danh mục SKU trên máy: đơn sẽ được tách khi gửi lên server.</Text>
          ) : items.length === 0 ? (
            <Text style={st.warnTxt}>Chưa nhận ra đơn nào (cần đủ số lượng, tên SKU và giá). Vẫn có thể gửi rồi thêm tay ở màn xác nhận đơn.</Text>
          ) : (
            items.map((it, i) => (
              <View key={i} style={st.itemRow}>
                <Text style={st.itemName} numberOfLines={2}>{it.qty} × {it.sku_name}</Text>
                <Text style={[st.itemPrice, it.need_confirm && { color: C.amber }]}>{it.need_confirm ? "⚠ " : ""}{vnd(it.price)}</Text>
              </View>
            ))
          )}
        </>
      )}
    </View>
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
  partial: { marginTop: 12, color: C.muted, textAlign: "center", lineHeight: 20, paddingHorizontal: 12 },
  fallback: { marginTop: 10, color: C.muted, textAlign: "center", lineHeight: 19, fontSize: 12, paddingHorizontal: 12 },
  parsed: { marginTop: 14, paddingTop: 12, borderTopWidth: 1, borderTopColor: C.line },
  parsedH: { fontWeight: "800", color: C.ink, marginBottom: 6 },
  transcript: { color: C.muted, fontStyle: "italic", lineHeight: 20, marginBottom: 8 },
  muted: { color: C.muted, lineHeight: 20 },
  warnTxt: { color: C.amber, fontWeight: "600", lineHeight: 20 },
  itemRow: { flexDirection: "row", justifyContent: "space-between", gap: 12, paddingVertical: 4 },
  itemName: { flex: 1, color: C.ink, lineHeight: 20 },
  itemPrice: { color: C.ink, fontWeight: "700", fontVariant: ["tabular-nums"] },
  tplH: { fontWeight: "800", color: C.ink, marginBottom: 6 },
  tpl: { color: C.ink, lineHeight: 22 },
  ph: { color: C.red, fontWeight: "700" },
  tplEx: { color: C.muted, marginTop: 8, lineHeight: 20, fontStyle: "italic" },
  tplNote: { color: C.amber, marginTop: 8, fontWeight: "600", lineHeight: 20 },
});
