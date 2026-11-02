import { ReactNode } from "react";
import { StyleSheet, Text, TouchableOpacity, View, ViewStyle } from "react-native";
import { C, R } from "./theme";

export function Pill({ text, tone = "muted" }: { text: string; tone?: "muted" | "green" | "red" | "amber" | "brand" }) {
  const map = {
    muted: [C.line, C.muted], green: [C.greenBg, C.green], red: [C.redBg, C.red],
    amber: [C.amberBg, C.amber], brand: [C.tint, C.brand],
  } as const;
  const [bg, fg] = map[tone];
  return (
    <View style={[st.pill, { backgroundColor: bg }]}>
      <Text style={[st.pillT, { color: fg }]}>{text}</Text>
    </View>
  );
}

export function Button({ label, onPress, disabled, kind = "primary", style }: {
  label: string; onPress: () => void; disabled?: boolean; kind?: "primary" | "ghost"; style?: ViewStyle;
}) {
  const ghost = kind === "ghost";
  return (
    <TouchableOpacity
      accessibilityRole="button" accessibilityState={{ disabled: !!disabled }}
      disabled={disabled} onPress={onPress} activeOpacity={0.8}
      style={[st.btn, ghost ? st.btnGhost : { backgroundColor: C.red }, disabled && { opacity: 0.4 }, style]}
    >
      <Text style={[st.btnT, ghost && { color: C.ink }]}>{label}</Text>
    </TouchableOpacity>
  );
}

export function Card({ children, tone, style }: { children: ReactNode; tone?: "warn" | "bad"; style?: ViewStyle }) {
  return (
    <View style={[st.card, tone === "warn" && { borderColor: C.brand }, tone === "bad" && { borderColor: C.red }, style]}>
      {children}
    </View>
  );
}

export function Title({ children, sub }: { children: string; sub?: string }) {
  return (
    <View style={{ marginBottom: 14 }}>
      <Text style={st.h1}>{children}</Text>
      {!!sub && <Text style={st.sub}>{sub}</Text>}
    </View>
  );
}

const st = StyleSheet.create({
  pill: { alignSelf: "flex-start", paddingHorizontal: 10, paddingVertical: 4, borderRadius: R.pill },
  pillT: { fontSize: 12, fontWeight: "700" },
  btn: { minHeight: 50, borderRadius: R.input, alignItems: "center", justifyContent: "center", paddingHorizontal: 18 },
  btnGhost: { backgroundColor: C.card, borderWidth: 1.5, borderColor: C.ink },
  btnT: { color: "#fff", fontWeight: "700", fontSize: 16 },
  card: { backgroundColor: C.card, borderRadius: R.card, padding: 14, marginBottom: 12, borderWidth: 1.5, borderColor: C.line },
  h1: { fontSize: 28, fontWeight: "800", color: C.ink },
  sub: { color: C.muted, marginTop: 4, lineHeight: 20 },
});
