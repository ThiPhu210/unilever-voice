import { useCallback, useEffect, useMemo, useState } from "react";
import { FlatList, RefreshControl, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { listSessions } from "../api";
import { Banner, Pill, Title } from "../components";
import { fmtTime, isToday, vnd } from "../format";
import { C, R, S, shadow } from "../theme";
import { SessionRow, Settings } from "../types";

const LABEL: Record<string, string> = { queued: "Đang chờ", processing: "Đang dịch", done: "Đã xong", error: "Lỗi" };

/** Màu vạch bên trái thẻ: đỏ = lỗi, cam = đang xử lý hoặc cần BA làm gì đó, xanh = xong. */
function accent(r: SessionRow): string {
  if (r.status === "error") return C.red;
  if (r.status !== "done" || r.pending_review > 0 || r.missing_price > 0) return C.brand;
  return C.green;
}

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
      contentContainerStyle={{ padding: S.page, paddingTop: insets.top + S.lg, paddingBottom: 40 }}
      ListHeaderComponent={
        <View style={{ marginBottom: S.sm }}>
          <Title>Lịch sử tư vấn</Title>
          <View style={st.hero}>
            <Text style={st.heroL}>Doanh thu hôm nay</Text>
            <Text style={st.heroN} numberOfLines={1} adjustsFontSizeToFit>{vnd(today.revenue)}</Text>
            <View style={st.stats}>
              <Stat n={String(today.sessions)} l="cuộc tư vấn" />
              <Stat n={String(today.orders)} l="đơn chốt" />
              <Stat n={String(today.units)} l="sản phẩm" />
            </View>
          </View>
          {todo > 0 && <Banner tone="warn" text={`${todo} cuộc cần bạn xác nhận SKU hoặc nhập giá`} style={{ marginTop: S.md, marginBottom: 0 }} />}
          {!!err && <Banner tone="bad" text={err} style={{ marginTop: S.md, marginBottom: 0 }} />}
        </View>
      }
      ListEmptyComponent={<Text style={st.empty}>{err ? "" : "Chưa có cuộc tư vấn nào. Qua tab Ghi âm để bắt đầu."}</Text>}
      renderItem={({ item: r }) => (
        <TouchableOpacity style={[st.card, { borderLeftColor: accent(r) }]} onPress={() => onOpen(r.id)} accessibilityRole="button" activeOpacity={0.8}>
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

const Stat = ({ n, l }: { n: string; l: string }) => (
  <View style={st.stat}>
    <Text style={st.statN}>{n}</Text>
    <Text style={st.statL}>{l}</Text>
  </View>
);

const st = StyleSheet.create({
  hero: { backgroundColor: C.tint, borderRadius: R.card, padding: S.lg + 2 },
  heroL: { color: C.muted, fontWeight: "700", fontSize: 13 },
  heroN: { fontSize: 34, fontWeight: "800", color: C.ink, marginTop: 2 },
  stats: { flexDirection: "row", marginTop: S.md, paddingTop: S.md, borderTopWidth: 1, borderTopColor: "rgba(58,35,22,0.12)" },
  stat: { flex: 1 },
  statN: { fontSize: 20, fontWeight: "800", color: C.ink },
  statL: { fontSize: 12, color: C.muted, marginTop: 2 },
  empty: { color: C.muted, textAlign: "center", marginTop: 40, lineHeight: 21 },
  card: { backgroundColor: C.card, borderRadius: R.card, padding: S.lg, marginTop: S.md, borderWidth: 1, borderColor: C.line, borderLeftWidth: 5, ...shadow },
  row: { flexDirection: "row", justifyContent: "space-between", alignItems: "baseline", gap: S.sm },
  time: { color: C.ink, fontWeight: "800", fontSize: 16 },
  badge: { color: C.muted, fontSize: 12, fontWeight: "600" },
  store: { color: C.muted, marginTop: 2 },
  sub: { color: C.muted, marginTop: S.sm },
  rev: { color: C.ink, fontWeight: "800", marginTop: S.sm },
  tags: { flexDirection: "row", gap: 6, marginTop: S.sm, flexWrap: "wrap" },
});
