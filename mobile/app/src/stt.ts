/**
 * Nhận dạng giọng nói tiếng Việt bằng bộ nhận dạng của hệ điều hành (iOS: SFSpeechRecognizer, Android: SpeechRecognizer của Google)
 * qua expo-speech-recognition. Cùng lúc nhận dạng và GHI RA FILE WAV 16 kHz (recordingOptions.persist) để lưu / nghe lại.
 * Cần: iOS, hoặc Android 13+ (Android 12 trở xuống không ghi file + nhận dạng cùng lúc được) và có Google/Siri trên máy.
 * Máy không đủ điều kiện (sttSupport().ok = false): app tự dùng luồng cũ — ghi m4a, gửi audio cho server dịch.
 *
 * Dấu phẩy giữa các SKU: người nói nghỉ 1 nhịp giữa hai SKU, bộ nhận dạng của HĐH không tự chèn dấu câu, nên ta dựng lại từ khoảng nghỉ:
 *  - Android (continuous): mỗi lần nghỉ >= PAUSE_MS là kết thúc một "đoạn" -> nối các đoạn bằng ", ".
 *  - iOS: kết quả có mốc thời gian từng đoạn -> chèn ", " khi hở giữa hai đoạn >= PAUSE_MS.
 * Parser (src/parser) đã chịu được dấu phẩy thừa giữa tên SKU nên chỉnh PAUSE_MS hơi nhỏ không nguy hiểm.
 */
import { Platform } from "react-native";
import {
  AudioEncodingAndroid,
  ExpoSpeechRecognitionModule,
  type ExpoSpeechRecognitionResultSegment,
  type SetCategoryOptions,
} from "expo-speech-recognition";

export const STT_LANG = "vi-VN";
/** Khoảng lặng (ms) coi là "nghỉ 1 nhịp giữa hai SKU". Nhỏ quá -> chia nhỏ tên SKU; lớn quá -> không tách được dòng hàng. Chỉnh theo thực tế. */
export const PAUSE_MS = 800;
const STOP_WAIT_MS = 8000;      // đợi bộ nhận dạng trả kết quả cuối sau khi bấm dừng
const FILE_TIMEOUT_MS = 45000;  // nhận dạng lại từ file tối đa

export type SttSupport = { ok: boolean; reason?: string };

/** Máy này có chạy được "ghi + nhận dạng trên máy" không? Không ném lỗi (Expo Go / bản build thiếu module native -> ok=false). */
export function sttSupport(): SttSupport {
  try {
    if (Platform.OS === "android" && Number(Platform.Version) < 33) return { ok: false, reason: "Android 12 trở xuống" };
    if (Platform.OS !== "android" && Platform.OS !== "ios") return { ok: false, reason: "nền tảng không hỗ trợ" };
    if (!ExpoSpeechRecognitionModule.isRecognitionAvailable()) {
      return { ok: false, reason: Platform.OS === "ios" ? "chưa bật Siri & Đọc chính tả" : "máy thiếu dịch vụ giọng nói của Google" };
    }
    if (!ExpoSpeechRecognitionModule.supportsRecording()) return { ok: false, reason: "không ghi âm kèm nhận dạng được" };
    return { ok: true };
  } catch {
    return { ok: false, reason: "bản cài đặt chưa có module nhận dạng giọng nói" };
  }
}

/** Gói nhận dạng offline: Android dùng dịch vụ "com.google.android.as" (Google on-device); iOS dùng bộ nhận dạng trên máy. */
const ANDROID_ONDEVICE_PKG = "com.google.android.as";
export type OfflineStatus = { supported: boolean; installed: boolean; reason?: string };

/** Máy có nhận dạng offline tiếng Việt chưa? supported=false: máy/OS không hỗ trợ; installed=false: hỗ trợ nhưng chưa tải gói vi-VN. */
export async function offlineStatus(): Promise<OfflineStatus> {
  try {
    if (Platform.OS === "android" && Number(Platform.Version) < 33) return { supported: false, installed: false, reason: "Android 12 trở xuống" };
    if (!ExpoSpeechRecognitionModule.supportsOnDeviceRecognition()) return { supported: false, installed: false, reason: "máy không hỗ trợ nhận dạng offline" };
    const r = await ExpoSpeechRecognitionModule.getSupportedLocales(
      Platform.OS === "android" ? { androidRecognitionServicePackage: ANDROID_ONDEVICE_PKG } : {},
    );
    const isVi = (l: string) => l.replace("_", "-").toLowerCase() === "vi-vn";
    if (!r.locales.some(isVi) && !r.installedLocales.some(isVi)) return { supported: false, installed: false, reason: "chưa hỗ trợ tiếng Việt offline" };
    return { supported: true, installed: r.installedLocales.some(isVi) };
  } catch {
    return { supported: false, installed: false, reason: "không kiểm tra được gói ngôn ngữ" };
  }
}

/** Android 13+: yêu cầu tải gói vi-VN (Android 13 mở hộp thoại của hệ thống; 14+ tải ngầm, có thể chờ Wi-Fi). iOS: tải trong Cài đặt > Cài đặt chung > Bàn phím > Đọc chính tả. */
export async function downloadOfflineModel(): Promise<string> {
  if (Platform.OS !== "android") return "Trên iPhone: vào Cài đặt > Cài đặt chung > Bàn phím > Đọc chính tả, bật và tải tiếng Việt.";
  const r = await ExpoSpeechRecognitionModule.androidTriggerOfflineModelDownload({ locale: STT_LANG });
  return r.status === "download_success" ? "Đã tải xong gói tiếng Việt."
    : r.status === "download_scheduled" ? "Đã lên lịch tải gói tiếng Việt (có thể chờ Wi-Fi). Quay lại kiểm tra sau ít phút."
    : "Hãy hoàn tất việc tải gói tiếng Việt trong hộp thoại của hệ thống.";
}

export type SttResult = { uri: string | null; transcript: string; engine: string; error: string };
export type SttSession = { stop: () => Promise<SttResult>; abort: () => void };
export type StartOpts = {
  hotwords: string[];
  onLevel?: (v01: number) => void;
  onPartial?: (text: string) => void;
  /** Bộ nhận dạng tự kết thúc khi đang ghi (mất mạng, hết thời gian chờ...): màn hình nên gọi stop() để chốt bản ghi. */
  onEnded?: () => void;
  /** true: chỉ nhận dạng trên máy (không gửi âm thanh đi). Chỉ truyền true khi offlineStatus().installed. */
  offline?: boolean;
};

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));
const engineName = (offline?: boolean) => (Platform.OS === "ios" ? "ios-speech" : "android-speech") + (offline ? "-offline" : "");

/** Ghép một kết quả final thành chuỗi; iOS có mốc thời gian từng đoạn -> chèn dấu phẩy ở chỗ nghỉ. */
export function textOfFinal(r: { transcript: string; segments?: ExpoSpeechRecognitionResultSegment[] }): string {
  const segs = r.segments ?? [];
  if (segs.length > 1 && segs.every((s) => s.segment && s.endTimeMillis >= s.startTimeMillis)) {
    let out = segs[0].segment.trim();
    for (let i = 1; i < segs.length; i++) {
      const gap = segs[i].startTimeMillis - segs[i - 1].endTimeMillis;
      out += (gap >= PAUSE_MS ? ", " : " ") + segs[i].segment.trim();
    }
    return out;
  }
  return r.transcript.trim();
}

/** Nối các đoạn final (Android: mỗi đoạn = một lần nghỉ) bằng dấu phẩy, bỏ đoạn rỗng. */
export const joinFinals = (finals: string[], interim = ""): string =>
  [...finals, interim].map((t) => t.trim()).filter(Boolean).join(", ");

const contextual = (words: string[]) => (words.length ? words.slice(0, 100) : undefined);
// "measurement" của iOS làm giảm âm lượng phát lại sau khi ghi; dùng "default"
const IOS_CATEGORY: SetCategoryOptions = { category: "playAndRecord", categoryOptions: ["defaultToSpeaker", "allowBluetooth"], mode: "default" };
const ANDROID_INTENT = {
  EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS: PAUSE_MS,
  EXTRA_SPEECH_INPUT_POSSIBLY_COMPLETE_SILENCE_LENGTH_MILLIS: PAUSE_MS,
};

/** Bắt đầu ghi + nhận dạng. Ném lỗi nếu chưa được cấp quyền. */
export async function startStt(o: StartOpts): Promise<SttSession> {
  const perm = await ExpoSpeechRecognitionModule.requestPermissionsAsync();
  if (!perm.granted) throw new Error("Chưa được cấp quyền micro / nhận dạng giọng nói");

  const col = { finals: [] as string[], interim: "", uri: null as string | null, error: "" };
  let stopping = false;
  let resolveEnd!: () => void;
  const ended = new Promise<void>((r) => { resolveEnd = r; });

  const subs = [
    ExpoSpeechRecognitionModule.addListener("audiostart", (e) => { if (e.uri) col.uri = e.uri; }),
    ExpoSpeechRecognitionModule.addListener("audioend", (e) => { if (e.uri) col.uri = e.uri; }),
    ExpoSpeechRecognitionModule.addListener("result", (e) => {
      const r = e.results[0];
      if (!r) return;
      if (e.isFinal) {
        const t = textOfFinal(r);
        if (t) col.finals.push(t);
        col.interim = "";
      } else {
        col.interim = r.transcript;
      }
      o.onPartial?.(joinFinals(col.finals, col.interim));
    }),
    // "no-speech" rất hay gặp khi chưa ai nói: không phải lỗi nghiêm trọng, chỉ ghi lại
    ExpoSpeechRecognitionModule.addListener("error", (e) => { col.error = `${e.error}: ${e.message}`; }),
    ExpoSpeechRecognitionModule.addListener("volumechange", (e) => o.onLevel?.(Math.max(0, Math.min(1, (e.value + 2) / 12)))),
    ExpoSpeechRecognitionModule.addListener("end", () => {
      resolveEnd();
      if (!stopping) o.onEnded?.();
    }),
  ];
  const cleanup = () => subs.forEach((s) => s.remove());

  ExpoSpeechRecognitionModule.start({
    lang: STT_LANG,
    interimResults: true,
    continuous: true,                         // Android 13+: phiên "segmented" — mỗi lần nghỉ cho một kết quả final
    requiresOnDeviceRecognition: !!o.offline, // false: online-first (chính xác hơn); true: offline hoàn toàn, nhanh và không cần mạng
    contextualStrings: contextual(o.hotwords), // tên hãng/đơn vị để bộ nhận dạng ưu tiên (Omo, Clear, ki lô gam...)
    addsPunctuation: false,
    recordingOptions: {
      persist: true,                          // lưu WAV để nghe lại / gửi server
      outputSampleRate: 16000,                // iOS: 16 kHz (mặc định 44.1/48 kHz); Android luôn là 16 kHz
      outputEncoding: "pcmFormatInt16",       // iOS: PCM 16-bit (định dạng mà chế độ nhận dạng từ file hỗ trợ)
    },
    volumeChangeEventOptions: { enabled: true, intervalMillis: 120 },
    androidIntentOptions: ANDROID_INTENT,
    ...(o.offline && Platform.OS === "android" ? { androidRecognitionServicePackage: ANDROID_ONDEVICE_PKG } : {}),
    iosCategory: IOS_CATEGORY,
  });

  return {
    async stop() {
      stopping = true;
      ExpoSpeechRecognitionModule.stop();
      await Promise.race([ended, sleep(STOP_WAIT_MS)]);
      cleanup();
      return { uri: col.uri, transcript: joinFinals(col.finals, col.interim), engine: engineName(o.offline), error: col.error };
    },
    abort() {
      stopping = true;
      ExpoSpeechRecognitionModule.abort();
      cleanup();
    },
  };
}

/**
 * Nhận dạng lại từ file WAV đã lưu (lần ghi trước mất mạng / bộ nhận dạng trả rỗng): "lưu trước, dịch sau".
 * Chỉ WAV 16 kHz PCM 16-bit (đúng file startStt ghi ra) — m4a/AAC chưa được thư viện kiểm chứng.
 */
export function transcribeFile(uri: string, hotwords: string[], offline = false): Promise<string> {
  return new Promise((resolve) => {
    const finals: string[] = [];
    let interim = "";
    let done = false;
    const subs: { remove: () => void }[] = [];
    const finish = () => {
      if (done) return;
      done = true;
      subs.forEach((s) => s.remove());
      resolve(joinFinals(finals, interim));
    };
    subs.push(
      ExpoSpeechRecognitionModule.addListener("result", (e) => {
        const r = e.results[0];
        if (!r) return;
        if (e.isFinal) { const t = textOfFinal(r); if (t) finals.push(t); interim = ""; } else interim = r.transcript;
      }),
      ExpoSpeechRecognitionModule.addListener("error", finish),
      ExpoSpeechRecognitionModule.addListener("end", finish),
    );
    setTimeout(() => { if (!done) { ExpoSpeechRecognitionModule.abort(); finish(); } }, FILE_TIMEOUT_MS);
    try {
      ExpoSpeechRecognitionModule.start({
        lang: STT_LANG,
        interimResults: true,
        continuous: true,
        requiresOnDeviceRecognition: offline,
        contextualStrings: contextual(hotwords),
        androidIntentOptions: ANDROID_INTENT,
        ...(offline && Platform.OS === "android" ? { androidRecognitionServicePackage: ANDROID_ONDEVICE_PKG } : {}),
        audioSource: { uri, audioChannels: 1, audioEncoding: AudioEncodingAndroid.ENCODING_PCM_16BIT, sampleRate: 16000 },
      });
    } catch { finish(); }
  });
}
