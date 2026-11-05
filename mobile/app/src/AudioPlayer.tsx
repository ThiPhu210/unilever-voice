import { useEffect, useState } from "react";
import { StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { setAudioModeAsync, useAudioPlayer, useAudioPlayerStatus } from "expo-audio";
import { mmss } from "./format";
import { C, R } from "./theme";

/** Trình phát âm thanh gọn: phát/tạm dừng, tua ±10 giây, chạm vào thanh để tua. `uri` là file trên máy hoặc URL. */
export default function AudioPlayer({ uri }: { uri: string }) {
  const player = useAudioPlayer(uri);
  const status = useAudioPlayerStatus(player);
  const [barW, setBarW] = useState(1);

  const dur = status.duration || 0;
  const cur = status.currentTime || 0;
  const pct = dur > 0 ? Math.min(1, cur / dur) : 0;

  // phát xong -> tua về đầu để nghe lại được
  useEffect(() => { if (status.didJustFinish) player.seekTo(0); }, [status.didJustFinish]);

  async function toggle() {
    if (status.playing) return player.pause();
    // iOS: sau khi ghi âm phải tắt chế độ ghi thì mới ra loa ngoài
    await setAudioModeAsync({ playsInSilentMode: true, allowsRecording: false }).catch(() => {});
    if (dur > 0 && cur >= dur - 0.1) await player.seekTo(0);
    player.play();
  }
  const skip = (sec: number) => player.seekTo(Math.max(0, Math.min(dur, cur + sec)));

  return (
    <View style={st.wrap}>
      <View style={st.row}>
        <TouchableOpacity style={st.btn} onPress={() => skip(-10)} disabled={!status.isLoaded} accessibilityRole="button" accessibilityLabel="Lùi 10 giây">
          <Text style={st.btnT}>−10s</Text>
        </TouchableOpacity>
        <TouchableOpacity style={[st.play, !status.isLoaded && { opacity: 0.5 }]} onPress={toggle} disabled={!status.isLoaded}
          accessibilityRole="button" accessibilityLabel={status.playing ? "Tạm dừng" : "Nghe"}>
          <Text style={st.playT}>{status.playing ? "❚❚" : "▶"}</Text>
        </TouchableOpacity>
        <TouchableOpacity style={st.btn} onPress={() => skip(10)} disabled={!status.isLoaded} accessibilityRole="button" accessibilityLabel="Tua 10 giây">
          <Text style={st.btnT}>+10s</Text>
        </TouchableOpacity>
      </View>
      <TouchableOpacity activeOpacity={1} disabled={!status.isLoaded} accessibilityLabel="Thanh tua"
        onLayout={(e) => setBarW(Math.max(1, e.nativeEvent.layout.width))}
        onPress={(e) => dur > 0 && player.seekTo((e.nativeEvent.locationX / barW) * dur)}
        style={st.barHit}>
        <View style={st.bar}><View style={[st.fill, { width: `${pct * 100}%` }]} /></View>
      </TouchableOpacity>
      <Text style={st.time}>{status.isLoaded ? `${mmss(cur * 1000)} / ${mmss(dur * 1000)}` : "Đang tải âm thanh..."}</Text>
    </View>
  );
}

const st = StyleSheet.create({
  wrap: { marginTop: 10 },
  row: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 16 },
  btn: { paddingVertical: 10, paddingHorizontal: 12 },
  btnT: { color: C.muted, fontWeight: "700" },
  play: { width: 56, height: 56, borderRadius: 28, backgroundColor: C.brand, alignItems: "center", justifyContent: "center" },
  playT: { color: "#fff", fontSize: 20, fontWeight: "800" },
  barHit: { paddingVertical: 12 },
  bar: { height: 6, borderRadius: R.pill, backgroundColor: C.line, overflow: "hidden" },
  fill: { height: 6, backgroundColor: C.brand },
  time: { textAlign: "center", color: C.muted, fontVariant: ["tabular-nums"] },
});
