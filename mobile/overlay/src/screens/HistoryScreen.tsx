import { useCallback, useEffect, useState } from "react";
import { FlatList, RefreshControl, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { listSessions } from "../api";
import { C } from "../theme";
import { SessionRow, Settings } from "../types";

const LABEL: Record<string, string> = { queued: "Đang chờ", processing: "Đang dịch", done: "Xong", error: "Lỗi" };

export default function HistoryScreen({ settings, refreshKey, onOpen }: { settings: Settings; refreshKey: number; onOpen: (id: string) => void }) {
  const [rows, setRows] = useState<SessionRow[]>([]);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try { setRows(await listSessions(settings)); setErr(""); }
    catch (e: any) { setErr(String(e?.message || e)); }
    finally { setLoading(false); }
  }, [settings]);

  useEffect(() => { load(); }, [load, refreshKey]);
  useEffect(() => {
    const busy = rows.some((r) => r.status === "queued" || r.status === "processing");
    if (!busy) return;
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [rows, load]);

  return (
    <View style={{ flex: 1 }}>
      <Text style={st.h}>Lịch sử tư vấn</Text>
      {!!err && <Text style={st.err}>{err}</Text>}
      <FlatList
        data={rows}
        keyExtractor={(r) => r.id}
        refreshControl={<RefreshControl refreshing={loading} onRefresh={load} />}
        contentContainerStyle={{ padding: 16 }}
        ListEmptyComponent={<Text style={st.empty}>Chưa có cuộc tư vấn nào.</Text>}
        renderItem={({ item: r }) => (
          <TouchableOpacity style={st.card} onPress={() => onOpen(r.id)}>
            <View style={st.row}>
              <Text style={st.time}>{new Date(r.created_at.replace(" ", "T") + "Z").toLocaleString("vi-VN")}</Text>
              <Text style={[st.badge, r.status === "error" && { color: C.red }]}>{LABEL[r.status] || r.status}</Text>
            </View>
            <Text style={st.sub}>{r.orders} đơn · {r.units} sản phẩm</Text>
            {r.pending_review > 0 && <Text style={st.warn}>⚠ Cần xác nhận lại SKU</Text>}
          </TouchableOpacity>
        )}
      />
    </View>
  );
}

const st = StyleSheet.create({
  h: { fontSize: 24, fontWeight: "700", color: C.ink, padding: 20, paddingTop: 60, paddingBottom: 0 },
  err: { color: C.red, paddingHorizontal: 20, paddingTop: 8 },
  empty: { color: C.muted, textAlign: "center", marginTop: 40 },
  card: { backgroundColor: C.card, borderRadius: 12, padding: 14, marginBottom: 10, borderWidth: 1, borderColor: C.line },
  row: { flexDirection: "row", justifyContent: "space-between" },
  time: { color: C.ink, fontWeight: "600" },
  badge: { color: C.blue, fontSize: 12 },
  sub: { color: C.muted, marginTop: 6 },
  warn: { color: C.amber, marginTop: 6, fontWeight: "600" },
});
