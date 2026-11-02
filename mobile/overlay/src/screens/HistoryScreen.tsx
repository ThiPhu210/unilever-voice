import { useCallback, useEffect, useMemo, useState } from "react";
import { FlatList, RefreshControl, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { listSessions } from "../api";
import { Pill } from "../components";
import { fmtTime, isToday, vnd } from "../format";
import { C, R } from "../theme";
import { SessionRow, Settings } from "../types";

const LABEL: Record<string, string> = { queued: "Đang chờ", processing: "Đang dịch", done: "Đã xong", error: "Lỗi" };

export default function HistoryScreen({ settings, refreshKey, onOpen }: { settings: Settings; refreshKey: number; onOpen: (id: string) => void }) {
  const insets = useSafeAreaInsets();
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

  const today = useMemo(() => {
    const t = rows.filter((r) => isToday(r.created_at));
    return {
      sessions: t.length, orders: t.reduce((a, r) => a + r.orders, 0),
      units: t.reduce((a, r) => a + r.units, 0), revenue: t.reduce((a, r) => a + r.revenue, 0),
    };
  }, [rows]);
  const todo = rows.filter((r) => r.pending_review > 0 || r.missing_price > 0).length;

  return (
    <FlatList
      data={rows}
      keyExtractor={(r) => r.id}
      refreshControl={<RefreshControl refreshing={loading} onRefresh={load} tintColor={C.brand} />}
      contentContainerStyle={{ padding: 20, paddingTop: insets.top + 16, paddingBottom: 40 }}
      ListHeaderComponent={
        <View style={{ marginBottom: 8 }}>
          <Text style={st.h}>Lịch sử tư vấn</Text>
          <View style={st.sum}>
            <Stat n={String(today.sessions)} l="cuộc hôm nay" />
            <Stat n={String(today.orders)} l="đơn chốt" />
            <Stat n={String(today.units)} l="sản phẩm" />
            <Stat n={vnd(today.revenue)} l="doanh thu" wide />
          </View>
          {todo > 0 && <Text style={st.todo}>{todo} cuộc cần bạn xác nhận SKU hoặc nhập giá</Text>}
          {!!err && <Text style={st.err}>{err}</Text>}
        </View>
      }
      ListEmptyComponent={<Text style={st.empty}>{err ? "" : "Chưa có cuộc tư vấn nào. Qua tab Ghi âm để bắt đầu."}</Text>}
      renderItem={({ item: r }) => (
        <TouchableOpacity style={st.card} onPress={() => onOpen(r.id)} accessibilityRole="button" activeOpacity={0.8}>
          <View style={st.row}>
            <Text style={st.time}>{fmtTime(r.created_at)}</Text>
            <Text style={[st.badge, r.status === "error" && { color: C.red }]}>{LABEL[r.status] || r.status}</Text>
          </View>
          {!!r.store && <Text style={st.store}>{r.store}</Text>}
          <View style={st.row}>
            <Text style={st.sub}>{r.orders ? `${r.orders} đơn · ${r.units} sản phẩm` : "Không có đơn chốt"}</Text>
            {r.revenue > 0 && <Text style={st.rev}>{vnd(r.revenue)}</Text>}
          </View>
          <View style={st.tags}>
            {r.missing_price > 0 && <Pill text="Thiếu giá" tone="red" />}
            {r.pending_review > 0 && <Pill text="Cần xác nhận SKU" tone="amber" />}
          </View>
        </TouchableOpacity>
      )}
    />
  );
}

const Stat = ({ n, l, wide }: { n: string; l: string; wide?: boolean }) => (
  <View style={[st.stat, wide && { flex: 1.6 }]}>
    <Text style={st.statN} numberOfLines={1} adjustsFontSizeToFit>{n}</Text>
    <Text style={st.statL}>{l}</Text>
  </View>
);

const st = StyleSheet.create({
  h: { fontSize: 28, fontWeight: "800", color: C.ink },
  sum: { flexDirection: "row", gap: 8, marginTop: 14, backgroundColor: C.tint, borderRadius: R.card, padding: 14 },
  stat: { flex: 1 },
  statN: { fontSize: 20, fontWeight: "800", color: C.ink },
  statL: { fontSize: 11.5, color: C.muted, marginTop: 2 },
  todo: { color: C.amber, fontWeight: "700", marginTop: 12 },
  err: { color: C.red, marginTop: 10 },
  empty: { color: C.muted, textAlign: "center", marginTop: 40, lineHeight: 21 },
  card: { backgroundColor: C.card, borderRadius: R.card, padding: 14, marginTop: 10, borderWidth: 1.5, borderColor: C.line },
  row: { flexDirection: "row", justifyContent: "space-between", alignItems: "baseline", gap: 8 },
  time: { color: C.ink, fontWeight: "800", fontSize: 16 },
  badge: { color: C.muted, fontSize: 12, fontWeight: "600" },
  store: { color: C.muted, marginTop: 2 },
  sub: { color: C.muted, marginTop: 8 },
  rev: { color: C.ink, fontWeight: "800", marginTop: 8 },
  tags: { flexDirection: "row", gap: 6, marginTop: 8, flexWrap: "wrap" },
});
