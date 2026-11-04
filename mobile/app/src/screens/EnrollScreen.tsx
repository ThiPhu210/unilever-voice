import { useState } from "react";
import { Alert, ScrollView, StyleSheet, Switch, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { AudioModule, RecordingPresets, setAudioModeAsync, useAudioRecorder, useAudioRecorderState } from "expo-audio";
import { enrollVoiceprint } from "../api";
import { Button, Card, Pill } from "../components";
import { mmss } from "../format";
import { C } from "../theme";
import { Settings } from "../types";

const OPTIONS = { ...RecordingPresets.HIGH_QUALITY, sampleRate: 16000, numberOfChannels: 1, bitRate: 64000 };
const MIN_MS = 12000; // cần >= 12 giây để server lấy đủ >= 8 giây có tiếng
const SCRIPT = [
  "Xin chào chị, em là nhân viên tư vấn của nhãn hàng, em xin giới thiệu sản phẩm đang có khuyến mãi hôm nay ạ.",
  "Dạ em xin cảm ơn anh chị, vậy mình chốt hai OMO tám trăm gam, một Clear Men sáu trăm năm mươi mi li lít.",
  "Sữa tắm Hazeline hương sữa gạo hoa nhài chín trăm gam, và sữa dưỡng thể matcha lựu đỏ ba trăm bảy mươi mi li lít.",
];

type Step = "consent" | "record" | "upload" | "done";

export default function EnrollScreen({ settings, alreadyEnrolled, onClose }: {
  settings: Settings; alreadyEnrolled: boolean; onClose: (enrolled: boolean) => void;
}) {
  const insets = useSafeAreaInsets();
  const recorder = useAudioRecorder(OPTIONS);
  const state = useAudioRecorderState(recorder, 200);
  const [step, setStep] = useState<Step>("consent");
  const [agree, setAgree] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const rec = state.isRecording;
  const left = Math.max(0, Math.ceil((MIN_MS - state.durationMillis) / 1000));

  async function start() {
    setError(null);
    try {
      const perm = await AudioModule.requestRecordingPermissionsAsync();
      if (!perm.granted) return Alert.alert("Cần quyền micro", "Hãy cấp quyền micro cho ứng dụng.");
      await setAudioModeAsync({ playsInSilentMode: true, allowsRecording: true });
      await recorder.prepareToRecordAsync();
      recorder.record();
    } catch (e: any) {
      setError("Không bật được micro: " + String(e?.message || e));
    }
  }

  async function stopAndSend() {
    setStep("upload");
    setError(null);
    try {
      await recorder.stop();
      const uri = recorder.uri;
      if (!uri) throw new Error("Không lấy được file ghi âm");
      await enrollVoiceprint(settings, uri, alreadyEnrolled);
      setStep("done");
    } catch (e: any) {
      const m = String(e?.message || e);
      setError(/Network request failed|Failed to fetch/i.test(m) ? "Không kết nối được server. Kiểm tra mạng và địa chỉ server trong Cài đặt." : m);
      setStep("record");
    }
  }

  return (
    <ScrollView contentContainerStyle={{ padding: 20, paddingTop: insets.top + 16, paddingBottom: 40 }}>
      <Text style={st.h}>Đăng ký giọng nói</Text>
      <Text style={st.sub}>Để hệ thống biết đâu là lời của bạn, đâu là lời khách khi chốt đơn.</Text>

      {step === "consent" && (
        <>
          <Card style={{ marginTop: 16 }}>
            <Text style={st.b}>Trước khi đăng ký, bạn cần biết:</Text>
            <Text style={st.p}>• Giọng bạn được chuyển thành một dãy số (dấu giọng) để so khớp với các cuộc tư vấn. Đây là dữ liệu sinh trắc học.</Text>
            <Text style={st.p}>• Hệ thống KHÔNG lưu file ghi âm đăng ký, chỉ lưu dãy số.</Text>
            <Text style={st.p}>• Bạn có quyền xoá dấu giọng bất cứ lúc nào trong Cài đặt.</Text>
          </Card>
          <View style={st.row}>
            <Switch value={agree} onValueChange={setAgree} accessibilityLabel="Tôi đồng ý" />
            <Text style={[st.p, { flex: 1, marginLeft: 12 }]}>Tôi đồng ý cho lưu dấu giọng của tôi để dùng cho việc phân tách lời nói trong cuộc tư vấn.</Text>
          </View>
          <Button label="Tiếp tục" onPress={() => setStep("record")} disabled={!agree} style={{ marginTop: 18 }} />
          <Button kind="ghost" label="Để sau" onPress={() => onClose(false)} style={{ marginTop: 10 }} />
        </>
      )}

      {(step === "record" || step === "upload") && (
        <>
          <Card style={{ marginTop: 16, backgroundColor: C.tint, borderColor: C.tint }}>
            <Text style={st.b}>Đọc to, rõ, tốc độ bình thường, ở nơi yên tĩnh:</Text>
            {SCRIPT.map((t, i) => <Text key={i} style={st.script}>{i + 1}. {t}</Text>)}
          </Card>
          <Text style={[st.timer, rec && { color: C.red }]}>{mmss(state.durationMillis)}</Text>
          {rec && left > 0 && <Text style={st.hint}>Cần đọc thêm khoảng {left} giây</Text>}
          {error && <Card tone="bad"><Text style={{ color: C.red, fontWeight: "700", lineHeight: 20 }}>{error}</Text></Card>}
          {step === "upload" ? (
            <Pill text="Đang xử lý giọng nói..." tone="amber" />
          ) : rec ? (
            <Button label={left > 0 ? "Đang ghi..." : "Xong, gửi lên"} onPress={stopAndSend} disabled={left > 0} />
          ) : (
            <Button label="Bắt đầu đọc" onPress={start} />
          )}
          {!rec && step === "record" && <Button kind="ghost" label="Huỷ" onPress={() => onClose(false)} style={{ marginTop: 10 }} />}
        </>
      )}

      {step === "done" && (
        <>
          <Card style={{ marginTop: 16, backgroundColor: C.greenBg, borderColor: C.green }}>
            <Text style={{ color: C.green, fontWeight: "700", lineHeight: 22 }}>
              Đã đăng ký giọng nói. Từ cuộc tư vấn tiếp theo, hệ thống sẽ phân biệt lời bạn và lời khách.
            </Text>
          </Card>
          <Button label="Xong" onPress={() => onClose(true)} style={{ marginTop: 14 }} />
        </>
      )}
    </ScrollView>
  );
}

const st = StyleSheet.create({
  h: { fontSize: 28, fontWeight: "800", color: C.ink },
  sub: { color: C.muted, marginTop: 4, lineHeight: 20 },
  b: { color: C.ink, fontWeight: "800", marginBottom: 6, lineHeight: 20 },
  p: { color: C.ink, lineHeight: 21, marginTop: 4 },
  row: { flexDirection: "row", alignItems: "center", marginTop: 8 },
  script: { color: C.ink, fontSize: 17, lineHeight: 26, marginTop: 8 },
  timer: { fontSize: 44, fontWeight: "800", color: C.ink, textAlign: "center", marginVertical: 14 },
  hint: { color: C.muted, textAlign: "center", marginBottom: 12 },
});
