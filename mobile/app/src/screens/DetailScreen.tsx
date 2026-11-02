import { useEffect, useMemo, useState } from "react";
import { Alert, FlatList, Modal, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View } from "react-native";
import { fixOrder, getCatalog, getSession } from "../api";
import { C } from "../theme";
import { CatalogItem, Order, SessionDetail, Settings } from "../types";

type Row = { sku_id: string; sku_name: string; qty: number; need: boolean; cands: { sku_id: string; name: string }[] };

function OrderCard({ order, idx, settings, catalog, onSaved }: {
  order: Order; idx: number; settings: Settings; catalog: CatalogItem[]; onSaved: () => void;
}) {
  const [rows, setRows] = useState<Row[]>(
    order.items.map((i) => ({
      sku_id: i.sku_id, sku_name: i.sku_name, qty: i.qty, need: i.need_confirm && !order.reviewed,
      cands: (i.candidates || []).map((c) => ({ sku_id: c.sku_id, name: c.name })),
    }))
  );
  const [picker, setPicker] = useState<number | null>(null);
  const [q, setQ] = useState("");
  const needs = !!order.needs_review && !order.reviewed;

  const upd = (i: number, p: Partial<Row>) => setRows(rows.map((r, k) => (k === i ? { ...r, ...p } : r)));
  const filtered = useMemo(
    () => catalog.filter((c) => c.name.toLowerCase().includes(q.toLowerCase())).slice(0, 40), [q, catalog]);

  async function confirm() {
    try {
      await fixOrder(settings, order.id, rows.map((r) => ({ sku_id: r.sku_id, qty: r.qty })));
      Alert.alert("Đã xác nhận đơn");
      onSaved();
    } catch (e: any) { Alert.alert("Lỗi", String(e?.message || e)); }
  }

  return (
    <View style={[st.card, needs && { borderColor: C.amber }]}>
      <Text style={st.oh}>Đơn {idx + 1} · khách {order.customer_confirm === "yes" ? "đồng ý" : order.customer_confirm === "no" ? "từ chối" : "chưa phản hồi"}</Text>
      {rows.map((r, i) => (
        <View key={i} style={st.item}>
          <TouchableOpacity onPress={() => { setQ(""); setPicker(i); }} style={{ flex: 1 }}>
            <Text style={[st.name, r.need && { color: C.amber }]}>{r.need ? "⚠ " : ""}{r.sku_name}</Text>
            <Text style={st.change}>Đổi SKU</Text>
          </TouchableOpacity>
          <View style={st.stepper}>
            <TouchableOpacity onPress={() => upd(i, { qty: Math.max(1, r.qty - 1) })}><Text style={st.sb}>−</Text></TouchableOpacity>
            <Text style={st.qty}>{r.qty}</Text>
            <TouchableOpacity onPress={() => upd(i, { qty: r.qty + 1 })}><Text style={st.sb}>＋</Text></TouchableOpacity>
          </View>
          {r.need && r.cands.length > 0 && (
            <View style={st.chips}>
              {r.cands.map((c) => (
                <TouchableOpacity key={c.sku_id} style={[st.chip, c.sku_id === r.sku_id && st.chipOn]}
                  onPress={() => upd(i, { sku_id: c.sku_id, sku_name: c.name })}>
                  <Text style={[st.chipT, c.sku_id === r.sku_id && { color: "#fff" }]}>{c.name}</Text>
                </TouchableOpacity>
              ))}
            </View>
          )}
        </View>
      ))}
      {(needs || order.reviewed === 0) && (
        <TouchableOpacity style={st.btn} onPress={confirm}><Text style={st.btnT}>{needs ? "Xác nhận đơn" : "Lưu chỉnh sửa"}</Text></TouchableOpacity>
      )}

      <Modal visible={picker !== null} animationType="slide" onRequestClose={() => setPicker(null)}>
        <View style={{ flex: 1, paddingTop: 60, padding: 16 }}>
          <TextInput style={st.search} placeholder="Tìm SKU..." value={q} onChangeText={setQ} autoFocus />
          <FlatList data={filtered} keyExtractor={(c) => c.sku_id} keyboardShouldPersistTaps="handled"
            renderItem={({ item }) => (
              <TouchableOpacity style={st.pick} onPress={() => { upd(picker!, { sku_id: item.sku_id, sku_name: item.name }); setPicker(null); }}>
                <Text style={{ color: C.ink, fontSize: 16 }}>{item.name}</Text>
              </TouchableOpacity>
            )} />
          <TouchableOpacity onPress={() => setPicker(null)}><Text style={{ color: C.blue, textAlign: "center", padding: 14 }}>Đóng</Text></TouchableOpacity>
        </View>
      </Modal>
    </View>
  );
}

export default function DetailScreen({ settings, id, onBack }: { settings: Settings; id: string; onBack: () => void }) {
  const [s, setS] = useState<SessionDetail | null>(null);
  const [catalog, setCatalog] = useState<CatalogItem[]>([]);
  const [err, setErr] = useState("");

  const load = () => getSession(settings, id).then(setS).catch((e) => setErr(String(e?.message || e)));
  useEffect(() => { load(); getCatalog(settings).then(setCatalog).catch(() => {}); }, [id]);

  return (
    <ScrollView contentContainerStyle={{ padding: 16, paddingTop: 56 }}>
      <TouchableOpacity onPress={onBack}><Text style={{ color: C.blue, marginBottom: 12 }}>← Quay lại</Text></TouchableOpacity>
      {!!err && <Text style={{ color: C.red }}>{err}</Text>}
      {s && (
        <>
          <Text style={st.title}>{new Date(s.created_at.replace(" ", "T") + "Z").toLocaleString("vi-VN")}</Text>
          {(s.status === "queued" || s.status === "processing") && <Text style={st.note}>Đang dịch giọng nói, kéo xuống ở màn Lịch sử để cập nhật.</Text>}
          {s.status === "error" && <Text style={{ color: C.red }}>Lỗi: {s.error}</Text>}
          {s.status === "done" && s.orders.length === 0 && <Text style={st.note}>Không phát hiện câu chốt đơn trong cuộc này.</Text>}
          {s.orders.map((o, i) => (
            <OrderCard key={o.id + ":" + o.reviewed} order={o} idx={i} settings={settings} catalog={catalog} onSaved={load} />
          ))}
          {!!s.transcript_text && (
            <View style={st.card}><Text style={st.oh}>Transcript</Text><Text style={{ color: C.ink, lineHeight: 21 }}>{s.transcript_text}</Text></View>
          )}
        </>
      )}
    </ScrollView>
  );
}

const st = StyleSheet.create({
  title: { fontSize: 20, fontWeight: "700", color: C.ink, marginBottom: 12 },
  note: { color: C.muted, marginBottom: 12 },
  card: { backgroundColor: C.card, borderRadius: 12, padding: 14, marginBottom: 12, borderWidth: 1, borderColor: C.line },
  oh: { fontWeight: "700", color: C.ink, marginBottom: 8 },
  item: { flexDirection: "row", flexWrap: "wrap", alignItems: "center", paddingVertical: 8, borderTopWidth: 1, borderTopColor: C.line },
  name: { color: C.ink, fontSize: 15 }, change: { color: C.blue, fontSize: 12, marginTop: 2 },
  stepper: { flexDirection: "row", alignItems: "center", gap: 12 },
  sb: { fontSize: 24, color: C.blue, paddingHorizontal: 6 }, qty: { fontSize: 18, fontWeight: "700", minWidth: 24, textAlign: "center", color: C.ink },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: 8, width: "100%" },
  chip: { borderWidth: 1, borderColor: C.line, borderRadius: 99, paddingVertical: 5, paddingHorizontal: 10 },
  chipOn: { backgroundColor: C.blue, borderColor: C.blue }, chipT: { fontSize: 12, color: C.ink },
  btn: { backgroundColor: C.blue, padding: 12, borderRadius: 10, alignItems: "center", marginTop: 12 }, btnT: { color: "#fff", fontWeight: "600" },
  search: { borderWidth: 1, borderColor: C.line, borderRadius: 10, padding: 12, fontSize: 16, marginBottom: 8, color: C.ink },
  pick: { paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: C.line },
});
