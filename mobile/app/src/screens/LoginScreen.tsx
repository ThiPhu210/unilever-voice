import { useState } from "react";
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { checkBa, login, setPassword } from "../api";
import { Banner, Button, Field } from "../components";
import { C, S } from "../theme";
import { AuthResult } from "../types";

type Step = "code" | "login" | "create";
const MIN_PW = 8;

/** "1.2.3.4:8000" -> "http://1.2.3.4:8000"; bỏ "/" cuối. */
function normalizeServer(v: string): string {
  const t = v.trim().replace(/\/+$/, "");
  return !t || /^https?:\/\//i.test(t) ? t : `http://${t}`;
}

export default function LoginScreen({ server: initialServer, initialCode, notice, onLoggedIn }: {
  server: string; initialCode: string; notice?: string;
  onLoggedIn: (r: AuthResult, server: string) => Promise<void>;
}) {
  const insets = useSafeAreaInsets();
  const [step, setStep] = useState<Step>("code");
  const [code, setCode] = useState(initialCode);
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [server, setServer] = useState(initialServer);
  const [showServer, setShowServer] = useState(!initialServer); // chưa có server thì mở sẵn ô nhập
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const baCode = code.trim();

  function back() {
    setStep("code"); setPw(""); setPw2(""); setError(null);
  }

  async function run(fn: () => Promise<void>) {
    setBusy(true); setError(null);
    try { await fn(); }
    catch (e: any) { setError(String(e?.message || e)); }
    finally { setBusy(false); }
  }

  const next = () => run(async () => {
    if (!baCode) throw new Error("Hãy nhập mã BA");
    const srv = normalizeServer(server);
    if (!srv) { setShowServer(true); throw new Error("Hãy nhập địa chỉ server"); }
    setServer(srv);
    const { status } = await checkBa(srv, baCode);
    if (status === "unknown") throw new Error("Mã BA này chưa được cấp. Hãy liên hệ quản lý.");
    setStep(status === "set_password" ? "create" : "login");
  });

  const doLogin = () => run(async () => {
    if (!pw) throw new Error("Hãy nhập mật khẩu");
    await onLoggedIn(await login(normalizeServer(server), baCode, pw), normalizeServer(server));
  });

  const doCreate = () => run(async () => {
    if (pw.length < MIN_PW) throw new Error(`Mật khẩu cần ít nhất ${MIN_PW} ký tự`);
    if (pw !== pw2) throw new Error("Hai lần nhập mật khẩu chưa giống nhau");
    await onLoggedIn(await setPassword(normalizeServer(server), baCode, pw), normalizeServer(server));
  });

  const title = step === "code" ? "Đăng nhập" : step === "login" ? "Chào mừng trở lại" : "Tạo mật khẩu";
  const sub =
    step === "code" ? "Nhập mã BA của bạn để bắt đầu ghi âm tư vấn."
    : step === "login" ? `Mã BA ${baCode}. Nhập mật khẩu để tiếp tục.`
    : `Đây là lần đầu bạn đăng nhập với mã ${baCode}. Hãy tự đặt mật khẩu của riêng bạn.`;

  return (
    <KeyboardAvoidingView style={{ flex: 1, backgroundColor: C.bg }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <ScrollView keyboardShouldPersistTaps="handled"
        contentContainerStyle={{ flexGrow: 1, padding: S.page, paddingTop: insets.top + 40, paddingBottom: insets.bottom + 24 }}>
        <View style={st.logo} accessibilityElementsHidden importantForAccessibility="no">
          <Ionicons name="mic" size={34} color={C.primary} />
        </View>
        <Text style={st.h1} accessibilityRole="header">{title}</Text>
        <Text style={st.sub}>{sub}</Text>

        {!!notice && step === "code" && <Banner tone="warn" text={notice} style={{ marginTop: S.lg, marginBottom: 0 }} />}

        {step === "code" && (
          <>
            <Field label="Mã BA" value={code} onChangeText={setCode} placeholder="vd BA001" autoComplete="username"
              textContentType="username" returnKeyType="go" onSubmitEditing={next} editable={!busy} />
            {showServer && (
              <Field label="Địa chỉ server" value={server} onChangeText={setServer} placeholder="http://1.2.3.4"
                keyboardType="url" returnKeyType="go" onSubmitEditing={next} editable={!busy} />
            )}
          </>
        )}

        {step === "login" && (
          <Field label="Mật khẩu" value={pw} onChangeText={setPw} secure autoComplete="current-password"
            textContentType="password" returnKeyType="go" onSubmitEditing={doLogin} editable={!busy} autoFocus />
        )}

        {step === "create" && (
          <>
            <Field label="Mật khẩu mới" value={pw} onChangeText={setPw} secure autoComplete="new-password"
              textContentType="newPassword" editable={!busy} autoFocus />
            <Text style={st.hint}>Ít nhất {MIN_PW} ký tự. Chỉ bạn biết mật khẩu này; quên thì liên hệ quản lý để đặt lại.</Text>
            <Field label="Nhập lại mật khẩu" value={pw2} onChangeText={setPw2} secure autoComplete="new-password"
              textContentType="newPassword" returnKeyType="go" onSubmitEditing={doCreate} editable={!busy} />
          </>
        )}

        {!!error && <Banner tone="bad" text={error} style={{ marginTop: S.lg, marginBottom: 0 }} />}

        <Button
          label={step === "code" ? "Tiếp tục" : step === "login" ? "Đăng nhập" : "Tạo mật khẩu và vào app"}
          onPress={step === "code" ? next : step === "login" ? doLogin : doCreate}
          loading={busy} style={{ marginTop: S.xl }} />

        {step !== "code" && (
          <Button kind="ghost" label="Dùng mã BA khác" onPress={back} disabled={busy} style={{ marginTop: S.md }} />
        )}

        {step === "code" && !showServer && (
          <TouchableOpacity onPress={() => setShowServer(true)} accessibilityRole="button" hitSlop={10} style={st.srvLink}>
            <Text style={st.srvT}>Cài đặt địa chỉ server</Text>
          </TouchableOpacity>
        )}
        {step === "login" && <Text style={[st.hint, { textAlign: "center", marginTop: S.xl }]}>Quên mật khẩu? Liên hệ quản lý để đặt lại.</Text>}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const st = StyleSheet.create({
  logo: { width: 72, height: 72, borderRadius: 22, backgroundColor: C.tint, alignItems: "center", justifyContent: "center", marginBottom: S.xl },
  h1: { fontSize: 30, fontWeight: "800", color: C.ink },
  sub: { color: C.muted, marginTop: 6, lineHeight: 21, fontSize: 15 },
  hint: { color: C.muted, marginTop: S.sm, lineHeight: 19, fontSize: 13 },
  srvLink: { alignSelf: "center", marginTop: S.xl, padding: S.sm },
  srvT: { color: C.primary, fontWeight: "700" },
});
