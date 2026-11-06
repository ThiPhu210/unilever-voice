import { ReactNode, useState } from "react";
import { ActivityIndicator, StyleSheet, Text, TextInput, TextInputProps, TouchableOpacity, View, ViewStyle } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { C, R, S, shadow } from "./theme";

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

export function Button({ label, onPress, disabled, loading, kind = "primary", style }: {
  label: string; onPress: () => void; disabled?: boolean; loading?: boolean; kind?: "primary" | "ghost"; style?: ViewStyle;
}) {
  const ghost = kind === "ghost";
  const off = !!disabled || !!loading;
  return (
    <TouchableOpacity
      accessibilityRole="button" accessibilityLabel={label} accessibilityState={{ disabled: off, busy: !!loading }}
      disabled={off} onPress={onPress} activeOpacity={0.8}
      style={[st.btn, ghost ? st.btnGhost : { backgroundColor: C.primary }, disabled && { opacity: 0.4 }, style]}
    >
      {loading
        ? <ActivityIndicator color={ghost ? C.ink : "#fff"} />
        : <Text style={[st.btnT, ghost && { color: C.ink }]}>{label}</Text>}
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

/** Thông báo ngắn (lỗi / cảnh báo / thành công / thông tin). Lỗi được đọc to bởi trình đọc màn hình. */
export function Banner({ text, tone = "info", style }: { text: string; tone?: "info" | "ok" | "warn" | "bad"; style?: ViewStyle }) {
  const map = {
    info: [C.tint, C.ink, C.tint], ok: [C.greenBg, C.green, C.green],
    warn: [C.amberBg, C.amber, C.brand], bad: [C.redBg, C.red, C.red],
  } as const;
  const [bg, fg, bd] = map[tone];
  return (
    <View accessibilityRole={tone === "bad" ? "alert" : undefined}
      style={[st.banner, { backgroundColor: bg, borderColor: bd }, style]}>
      <Text style={[st.bannerT, { color: fg }]}>{text}</Text>
    </View>
  );
}

/** Ô nhập có nhãn phía trên. `secure`: ô mật khẩu, có nút hiện/ẩn. Viền đổi màu khi đang gõ hoặc có lỗi. */
export function Field({ label, error, secure, style, ...props }: TextInputProps & {
  label: string; error?: string; secure?: boolean; style?: ViewStyle;
}) {
  const [focus, setFocus] = useState(false);
  const [shown, setShown] = useState(false);
  return (
    <View style={[{ marginTop: S.lg }, style]}>
      <Text style={st.fLabel}>{label}</Text>
      <View style={[st.fBox, focus && { borderColor: C.ink }, !!error && { borderColor: C.red, backgroundColor: C.redBg }]}>
        <TextInput
          autoCapitalize="none" autoCorrect={false} placeholderTextColor={C.muted} accessibilityLabel={label}
          {...props}
          secureTextEntry={!!secure && !shown}
          onFocus={(e) => { setFocus(true); props.onFocus?.(e); }}
          onBlur={(e) => { setFocus(false); props.onBlur?.(e); }}
          style={st.fInput}
        />
        {!!secure && (
          <TouchableOpacity onPress={() => setShown(!shown)} hitSlop={10} accessibilityRole="button"
            accessibilityLabel={shown ? "Ẩn mật khẩu" : "Hiện mật khẩu"}>
            <Ionicons name={shown ? "eye-off-outline" : "eye-outline"} size={22} color={C.muted} />
          </TouchableOpacity>
        )}
      </View>
      {!!error && <Text style={st.fError}>{error}</Text>}
    </View>
  );
}

export function Title({ children, sub }: { children: string; sub?: string }) {
  return (
    <View style={{ marginBottom: 14 }}>
      <Text style={st.h1} accessibilityRole="header">{children}</Text>
      {!!sub && <Text style={st.sub}>{sub}</Text>}
    </View>
  );
}

const st = StyleSheet.create({
  pill: { alignSelf: "flex-start", paddingHorizontal: 10, paddingVertical: 4, borderRadius: R.pill },
  pillT: { fontSize: 12, fontWeight: "700" },
  btn: { minHeight: 52, borderRadius: R.input, alignItems: "center", justifyContent: "center", paddingHorizontal: 18 },
  btnGhost: { backgroundColor: C.card, borderWidth: 1.5, borderColor: C.line },
  btnT: { color: "#fff", fontWeight: "700", fontSize: 16 },
  card: { backgroundColor: C.card, borderRadius: R.card, padding: S.lg, marginBottom: S.md, borderWidth: 1, borderColor: C.line, ...shadow },
  banner: { borderRadius: R.input, borderWidth: 1, paddingVertical: S.md, paddingHorizontal: S.lg, marginBottom: S.md },
  bannerT: { fontWeight: "600", lineHeight: 20 },
  fLabel: { color: C.muted, fontSize: 13, fontWeight: "700", marginBottom: 6 },
  fBox: { flexDirection: "row", alignItems: "center", gap: S.sm, minHeight: 52, borderWidth: 1.5, borderColor: C.line, borderRadius: R.input, paddingHorizontal: 14, backgroundColor: C.card },
  fInput: { flex: 1, fontSize: 16, color: C.ink, paddingVertical: 12 },
  fError: { color: C.red, marginTop: 6, fontSize: 13, fontWeight: "600" },
  h1: { fontSize: 28, fontWeight: "800", color: C.ink },
  sub: { color: C.muted, marginTop: 4, lineHeight: 20 },
});
