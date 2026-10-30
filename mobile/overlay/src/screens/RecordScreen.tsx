import { useEffect, useRef, useState } from "react";
import { Alert, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { AudioModule, RecordingPresets, setAudioModeAsync, useAudioRecorder, useAudioRecorderState } from "expo-audio";
import { activateKeepAwakeAsync, deactivateKeepAwake } from "expo-keep-awake";
import { enqueueAndFlush, pendingCount } from "../api";
import { C } from "../theme";
import { Settings } from "../types";

// Ghi âm mono 16kHz AAC ~ 0.35 MB/phút: đủ cho ASR, nhẹ khi upload qua 4G.
const OPTIONS = { ...RecordingPresets.HIGH_QUALITY, sampleRate: 16000, numberOfChannels: 1, bitRate: 48000 };
const MAX_CHUNK_MS = 15 * 60 * 1000; // tự cắt file mỗi 15 phút để an toàn

const mmss = (ms: number) => {
  const s = Math.floor(ms / 1000);
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
};

export default function RecordScreen({ settings, onUploaded }: { settings: Settings; onUploaded: () => void }) {
  const recorder = useAudioRecorder(OPTIONS);
  const state = useAudioRecorderState(recorder, 500);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [pending, setPending] = useState(0);
  const rotating = useRef(false);

  useEffect(() => {
    pendingCount().then(setPending);
    enqueueAndFlush(settings).then(setPending).catch(() => {}); // thử gửi lại các bản tồn
  }, [settings]);

  async function begin() {
    const perm = await AudioModule.requestRecordingPermissionsAsync();
    if (!perm.granted) return Alert.alert("Cần quyền micro", "Hãy cấp quyền micro cho ứng dụng.");
    await setAudioModeAsync({ playsInSilentMode: true, allowsRecording: true });
    await recorder.prepareToRecordAsync();
    recorder.record();
    activateKeepAwakeAsync("rec");
    setMsg("");
  }

  async function finish(restart = false) {
    setBusy(true);
    try {
      await recorder.stop();
      const uri = recorder.uri;
      if (!restart) deactivateKeepAwake("rec");
      if (uri) {
        const left = await enqueueAndFlush(settings, uri);
        setPending(left);
        setMsg(left ? `Đã lưu. ${left} bản chờ gửi (mất mạng?).` : "Đã gửi lên server ✔");
        onUploaded();
      }
      if (restart) { await recorder.prepareToRecordAsync(); recorder.record(); }
    } catch (e: any) {
      setMsg("Lỗi: " + String(e?.message || e));
    } finally {
      setBusy(false);
    }
  }

  // Tự cắt đoạn khi ghi quá lâu
  useEffect(() => {
    if (state.isRecording && state.durationMillis > MAX_CHUNK_MS && !rotating.current) {
      rotating.current = true;
      finish(true).finally(() => { rotating.current = false; });
    }
  }, [state.durationMillis, state.isRecording]);

  const rec = state.isRecording;
  return (
    <View style={st.wrap}>
      <Text style={st.who}>{settings.saName} · {settings.store || "chưa đặt cửa hàng"}</Text>
      <Text style={st.timer}>{mmss(rec ? state.durationMillis : 0)}</Text>
      <TouchableOpacity
        disabled={busy}
        onPress={() => (rec ? finish() : begin())}
        style={[st.btn, { backgroundColor: rec ? C.red : C.blue }]}
      >
        <Text style={st.btnT}>{rec ? "Kết thúc tư vấn" : "Bắt đầu tư vấn"}</Text>
      </TouchableOpacity>
      <Text style={st.hint}>
        {rec ? "Đang ghi âm... nhớ nói câu chốt đơn theo mẫu:\n“Dạ em xin cảm ơn anh chị, vậy mình chốt 2 OMO 800g, 1 Clear Men 650ml”"
             : "Bấm khi bắt đầu tư vấn một khách, bấm kết thúc khi xong."}
      </Text>
      {!!msg && <Text style={st.msg}>{msg}</Text>}
      {pending > 0 && <Text style={st.warn}>{pending} bản ghi đang chờ gửi</Text>}
    </View>
  );
}

const st = StyleSheet.create({
  wrap: { flex: 1, alignItems: "center", justifyContent: "center", padding: 24 },
  who: { color: C.muted, marginBottom: 12 },
  timer: { fontSize: 64, fontWeight: "200", color: C.ink, fontVariant: ["tabular-nums"], marginBottom: 32 },
  btn: { paddingVertical: 20, paddingHorizontal: 40, borderRadius: 40 },
  btnT: { color: "#fff", fontSize: 18, fontWeight: "700" },
  hint: { color: C.muted, textAlign: "center", marginTop: 28, lineHeight: 20 },
  msg: { color: C.green, marginTop: 20, textAlign: "center" },
  warn: { color: C.amber, marginTop: 10 },
});
