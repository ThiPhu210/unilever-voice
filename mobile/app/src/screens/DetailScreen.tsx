import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator, Alert, FlatList, KeyboardAvoidingView, Modal, Platform, ScrollView, StyleSheet, Text,
  TextInput, TouchableOpacity, View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { addOrder, downloadAudio, fixOrder, getCatalog, getSession } from "../api";
import AudioPlayer from "../AudioPlayer";
import { Button, Card, Pill } from "../components";
import { fmtTime, inputToPrice, plain, priceToInput, vnd } from "../format";
import { C, R } from "../theme";
import { CatalogItem, Order, SessionDetail, Settings } from "../types";

type Row = {
  key: string; sku_id: string; sku_name: string; qty: number; priceTxt: string;
  uncertain: boolean; cands: { sku_id: string; name: string }[];
};
let seq = 0;
const newKey = () => `r${++seq}`;

const CONFIRM: Record<string, [string, "green" | "red" | "muted"]> = {
  yes: ["Khách đồng ý", "green"], no: ["Khách từ chối", "red"], none: ["Khách chưa phản hồi", "muted"],
};

function toRows(o: Order | null): Row[] {
  if (!o) return [];
  return o.items.map((i) => ({
    key: newKey(), sku_id: i.sku_id, sku_name: i.sku_name, qty: i.qty, priceTxt: priceToInput(i.price),
    uncertain: i.need_confirm && !o.reviewed,
    cands: (i.candidates || []).map((c) => ({ sku_id: c.sku_id, name: c.name })),
  }));
}
const sig = (rows: Row[]) => JSON.stringify(rows.map((r) => [r.sku_id, r.qty, inputToPrice(r.priceTxt)]));

/** Màn chọn SKU (đổi SKU hoặc thêm SKU mới) */
function SkuPicker({ visible, catalog, onPick, onClose }: {
  visible: boolean; catalog: CatalogItem[]; onPick: (c: CatalogItem) => void; onClose: () => void;
}) {
  const insets = useSafeAreaInsets();
  const [q, setQ] = useState("");
  useEffect(() => { if (visible) setQ(""); }, [visible]);
  const list = useMemo(() => {
    const k = plain(q.trim());
    return catalog.filter((c) => !k || plain(c.name).includes(k) || plain(c.sku_id).includes(k));
  }, [q, catalog]);
  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onClose}>
      <View style={{ flex: 1, backgroundColor: C.bg, paddingTop: insets.top + 8, paddingHorizontal: 16 }}>
        <View style={st.pickHead}>
          <Text style={st.pickTitle}>Chọn sản phẩm</Text>
          <TouchableOpacity onPress={onClose} accessibilityRole="button" hitSlop={12}><Text style={st.link}>Đóng</Text></TouchableOpacity>
        </View>
        <TextInput style={st.search} placeholder="Tìm tên SKU, ví dụ: omo 800" placeholderTextColor={C.muted}
          value={q} onChangeText={setQ} autoFocus autoCorrect={false} />
        <FlatList data={list} keyExtractor={(c) => c.sku_id} keyboardShouldPersistTaps="handled"
          contentContainerStyle={{ paddingBottom: insets.bottom + 20 }}
          ListEmptyComponent={<Text style={st.muted}>Không có SKU nào khớp “{q}”.</Text>}
          renderItem={({ item }) => (
            <TouchableOpacity style={st.pick} onPress={() => onPick(item)}>
              <Text style={st.pickName}>{item.name}</Text>
              <Text style={st.muted}>{item.unit}</Text>
            </TouchableOpacity>
          )} />
      </View>
    </Modal>
  );
}

function OrderCard({ order, idx, settings, catalog, onSaved, sessionId }: {
  order: Order | null; idx: number; settings: Settings; catalog: CatalogItem[]; onSaved: () => void; sessionId?: string;
}) {
  const [rows, setRows] = useState<Row[]>(() => toRows(order));
  const [base, setBase] = useState(() => sig(toRows(order)));
  const [picker, setPicker] = useState<{ mode: "change"; key: string } | { mode: "add" } | null>(null);
  const [saving, setSaving] = useState(false);

  const isNew = !order;
  const dirty = sig(rows) !== base;
  const missing = rows.filter((r) => inputToPrice(r.priceTxt) === null).length;
  const needs = !!order && !!order.needs_review && !order.reviewed;
  const total = rows.reduce((a, r) => a + r.qty * (inputToPrice(r.priceTxt) ?? 0), 0);
  const canSave = rows.length > 0 && missing === 0 && (dirty || needs || isNew);

  const upd = (key: string, p: Partial<Row>) => setRows((rs) => rs.map((r) => (r.key === key ? { ...r, ...p } : r)));
  const del = (key: string) => setRows((rs) => rs.filter((r) => r.key !== key));

  async function save() {
    setSaving(true);
    try {
      const items = rows.map((r) => ({ sku_id: r.sku_id, qty: r.qty, price: inputToPrice(r.priceTxt) }));
      if (order) await fixOrder(settings, order.id, items); else await addOrder(settings, sessionId!, items);
      onSaved();
    } catch (e: any) { Alert.alert("Lỗi", String(e?.message || e)); }
    finally { setSaving(false); }
  }

  const [label, tone] = order ? CONFIRM[order.customer_confirm] : ["Nhập tay", "muted" as const];
  return (
    <Card tone={missing ? "bad" : needs ? "warn" : undefined}>
      <View style={st.oHead}>
        <Text style={st.oTitle}>{isNew ? "Thêm đơn thủ công" : `Đơn ${idx + 1}`}</Text>
        <View style={{ flexDirection: "row", gap: 6 }}>
          {!!order?.reviewed && !dirty && <Pill text="Đã xác nhận" tone="green" />}
          <Pill text={label} tone={tone} />
        </View>
      </View>

      {rows.map((r) => {
        const price = inputToPrice(r.priceTxt);
        return (
          <View key={r.key} style={st.item}>
            <View style={st.itemTop}>
              <TouchableOpacity style={{ flex: 1 }} onPress={() => setPicker({ mode: "change", key: r.key })} accessibilityRole="button" accessibilityLabel={`Đổi SKU ${r.sku_name}`}>
                <Text style={[st.name, r.uncertain && { color: C.amber }]}>{r.uncertain ? "⚠ " : ""}{r.sku_name}</Text>
                <Text style={st.link}>Đổi sản phẩm</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={() => del(r.key)} hitSlop={10} accessibilityRole="button" accessibilityLabel={`Xoá ${r.sku_name}`}>
                <Text style={st.del}>Xoá</Text>
              </TouchableOpacity>
            </View>

            {r.uncertain && r.cands.length > 0 && (
              <View style={st.chips}>
                <Text style={st.chipsLbl}>Chưa chắc, có phải:</Text>
                {r.cands.map((c) => (
                  <TouchableOpacity key={c.sku_id} style={[st.chip, c.sku_id === r.sku_id && st.chipOn]}
                    onPress={() => upd(r.key, { sku_id: c.sku_id, sku_name: c.name, uncertain: false })}>
                    <Text style={[st.chipT, c.sku_id === r.sku_id && { color: "#fff" }]}>{c.name}</Text>
                  </TouchableOpacity>
                ))}
              </View>
            )}

            <View style={st.itemBottom}>
              <View style={st.field}>
                <Text style={st.lbl}>Số lượng</Text>
                <View style={st.stepper}>
                  <TouchableOpacity style={st.sBtn} onPress={() => upd(r.key, { qty: Math.max(1, r.qty - 1) })} accessibilityLabel="Giảm số lượng"><Text style={st.sT}>−</Text></TouchableOpacity>
                  <Text style={st.qty}>{r.qty}</Text>
                  <TouchableOpacity style={st.sBtn} onPress={() => upd(r.key, { qty: Math.min(999, r.qty + 1) })} accessibilityLabel="Tăng số lượng"><Text style={st.sT}>＋</Text></TouchableOpacity>
                </View>
              </View>
              <View style={[st.field, { flex: 1 }]}>
                <Text style={[st.lbl, price === null && { color: C.red }]}>{price === null ? "Chưa có giá, nhập giá" : "Giá (nghìn đồng)"}</Text>
                <View style={[st.priceBox, price === null && { borderColor: C.red, backgroundColor: C.redBg }]}>
                  <TextInput style={st.priceIn} value={r.priceTxt} onChangeText={(t) => upd(r.key, { priceTxt: t.replace(/[^0-9.,]/g, "") })}
                    keyboardType="decimal-pad" placeholder="vd 65" placeholderTextColor={C.muted} accessibilityLabel={`Giá ${r.sku_name}`} />
                  <Text style={st.unit}>nghìn đ</Text>
                </View>
              </View>
            </View>
            {price !== null && <Text style={st.lineTotal}>{r.qty} × {vnd(price)} = <Text style={{ fontWeight: "800", color: C.ink }}>{vnd(r.qty * price)}</Text></Text>}
          </View>
        );
      })}

      <TouchableOpacity style={st.add} onPress={() => setPicker({ mode: "add" })} accessibilityRole="button">
        <Text style={st.addT}>＋ Thêm sản phẩm</Text>
      </TouchableOpacity>

      <View style={st.totalRow}>
        <Text style={st.totalLbl}>Tổng đơn{missing ? ` (thiếu giá ${missing} SKU)` : ""}</Text>
        <Text style={st.total}>{vnd(total)}</Text>
      </View>

      {(canSave || missing > 0 || needs) && (
        <Button
          label={saving ? "Đang lưu..." : missing ? `Còn ${missing} SKU chưa có giá` : isNew ? "Lưu đơn" : needs ? "Xác nhận đơn" : "Lưu chỉnh sửa"}
          disabled={!canSave || saving} onPress={save} style={{ marginTop: 12 }} />
      )}

      <SkuPicker visible={picker !== null} catalog={catalog} onClose={() => setPicker(null)}
        onPick={(c) => {
          if (picker?.mode === "change") upd(picker.key, { sku_id: c.sku_id, sku_name: c.name, uncertain: false });
          else if (picker?.mode === "add") setRows((rs) => [...rs, { key: newKey(), sku_id: c.sku_id, sku_name: c.name, qty: 1, priceTxt: "", uncertain: false, cands: [] }]);
          setPicker(null);
        }} />
    </Card>
  );
}

/** Tải file ghi âm từ server về máy rồi mới phát; lỗi thì hiện rõ lý do + nút thử lại. */
function ServerAudio({ settings, id }: { settings: Settings; id: string }) {
  const [uri, setUri] = useState<string | null>(null);
  const [err, setErr] = useState("");
  const [tries, setTries] = useState(0);
  useEffect(() => {
    let alive = true;
    setUri(null); setErr("");
    downloadAudio(settings, id)
      .then((u) => alive && setUri(u))
      .catch((e) => alive && setErr(String(e?.message || e)));
    return () => { alive = false; };
  }, [settings, id, tries]);
  if (uri) return <AudioPlayer uri={uri} />;
  if (err) return (
    <View>
      <Text style={{ color: C.red, marginTop: 8, lineHeight: 20 }}>Không tải được âm thanh: {err}</Text>
      <Button kind="ghost" label="Thử lại" onPress={() => setTries((t) => t + 1)} style={{ marginTop: 10 }} />
    </View>
  );
  return (
    <View style={{ flexDirection: "row", alignItems: "center", gap: 10, marginTop: 10 }}>
      <ActivityIndicator color={C.brand} />
      <Text style={st.muted}>Đang tải âm thanh...</Text>
    </View>
  );
}

export default function DetailScreen({ settings, id, onBack }: { settings: Settings; id: string; onBack: () => void }) {
  const insets = useSafeAreaInsets();
  const [s, setS] = useState<SessionDetail | null>(null);
  const [catalog, setCatalog] = useState<CatalogItem[]>([]);
  const [err, setErr] = useState("");
  const [showTx, setShowTx] = useState(false);
  const [manual, setManual] = useState(false);

  const load = useCallback(
    () => getSession(settings, id).then((d) => { setS(d); setErr(""); }).catch((e) => setErr(String(e?.message || e))),
    [settings, id]);
  useEffect(() => { load(); getCatalog(settings).then(setCatalog).catch(() => {}); }, [id]);
  useEffect(() => { // đang dịch giọng nói -> tự cập nhật
    if (!s || (s.status !== "queued" && s.status !== "processing")) return;
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [s?.status, load]);

  const working = s && (s.status === "queued" || s.status === "processing");
  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <ScrollView contentContainerStyle={{ padding: 20, paddingTop: insets.top + 12, paddingBottom: 60 }} keyboardShouldPersistTaps="handled">
        <TouchableOpacity onPress={onBack} accessibilityRole="button" hitSlop={10}><Text style={[st.link, { fontSize: 15, marginBottom: 10 }]}>← Lịch sử</Text></TouchableOpacity>
        {!!err && <Card tone="bad"><Text style={{ color: C.red }}>{err}</Text></Card>}
        {!s && !err && <ActivityIndicator style={{ marginTop: 40 }} color={C.brand} />}
        {s && (
          <>
            <Text style={st.h1}>{fmtTime(s.created_at)}</Text>
            <Text style={[st.muted, { marginBottom: 14 }]}>{s.store || "Chưa đặt điểm bán"}</Text>

            {working && (
              <Card style={{ backgroundColor: C.tint, borderColor: C.tint }}>
                <View style={{ flexDirection: "row", alignItems: "center", gap: 12 }}>
                  <ActivityIndicator color={C.brand} />
                  <Text style={{ flex: 1, color: C.ink, lineHeight: 20 }}>Đang dịch giọng nói và bắt SKU. Màn hình tự cập nhật, thường mất dưới 1 phút.</Text>
                </View>
              </Card>
            )}
            {s.status === "error" && <Card tone="bad"><Text style={{ color: C.red }}>Chưa xử lý được file ghi âm: {s.error}. Hãy ghi âm lại hoặc báo quản trị viên.</Text></Card>}

            {s.status === "done" && s.orders.length === 0 && !manual && (
              <Card>
                <Text style={st.oTitle}>Không nhận ra đơn hàng nào</Text>
                <Text style={[st.muted, { marginVertical: 8, lineHeight: 20 }]}>Nếu khách có mua, hãy nhập tay để Coach vẫn thấy được đơn này.</Text>
                <Button kind="ghost" label="Nhập đơn thủ công" onPress={() => setManual(true)} />
              </Card>
            )}
            {s.orders.map((o, i) => (
              <OrderCard key={`${o.id}:${o.reviewed}:${o.total}`} order={o} idx={i} settings={settings} catalog={catalog} onSaved={load} />
            ))}
            {s.status === "done" && s.orders.length === 0 && manual && (
              <OrderCard key="manual" order={null} idx={0} settings={settings} catalog={catalog}
                onSaved={() => { setManual(false); load(); }} sessionId={s.id} />
            )}

            {s.status === "done" && !!(s as any).has_audio && (
              <Card>
                <Text style={st.oTitle}>Nghe lại cuộc tư vấn</Text>
                <ServerAudio settings={settings} id={s.id} />
              </Card>
            )}

            {!!s.transcript_text && (
              <Card>
                <TouchableOpacity onPress={() => setShowTx(!showTx)} accessibilityRole="button" style={st.oHead}>
                  <Text style={st.oTitle}>Transcript cuộc tư vấn</Text>
                  <Text style={st.link}>{showTx ? "Thu gọn" : "Xem"}</Text>
                </TouchableOpacity>
                {showTx && ((s as any).segments?.some((g: any) => g.speaker)
                  ? (s as any).segments.map((g: any, i: number) => (
                      <Text key={i} style={st.tx}>
                        <Text style={{ fontWeight: "800", color: g.speaker === "sa" ? C.brand : C.green }}>{g.speaker === "sa" ? "SA: " : "Khách: "}</Text>
                        {g.text}
                      </Text>))
                  : <Text style={st.tx}>{s.transcript_text}</Text>)}
              </Card>
            )}
          </>
        )}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const st = StyleSheet.create({
  h1: { fontSize: 28, fontWeight: "800", color: C.ink },
  muted: { color: C.muted },
  link: { color: C.red, fontSize: 13, fontWeight: "700", marginTop: 2 },
  oHead: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 6, gap: 8 },
  oTitle: { fontWeight: "800", color: C.ink, fontSize: 17 },
  item: { paddingVertical: 12, borderTopWidth: 1, borderTopColor: C.line },
  itemTop: { flexDirection: "row", alignItems: "flex-start", gap: 12 },
  name: { color: C.ink, fontSize: 16, fontWeight: "700", lineHeight: 21 },
  del: { color: C.muted, fontWeight: "600", textDecorationLine: "underline" },
  chips: { flexDirection: "row", flexWrap: "wrap", alignItems: "center", gap: 6, marginTop: 8 },
  chipsLbl: { color: C.amber, fontSize: 12, fontWeight: "700" },
  chip: { borderWidth: 1.5, borderColor: C.line, borderRadius: R.pill, paddingVertical: 6, paddingHorizontal: 12, backgroundColor: C.card },
  chipOn: { backgroundColor: C.ink, borderColor: C.ink }, chipT: { fontSize: 12.5, color: C.ink, fontWeight: "600" },
  itemBottom: { flexDirection: "row", gap: 14, marginTop: 12, alignItems: "flex-end" },
  field: { gap: 6 },
  lbl: { fontSize: 12, color: C.muted, fontWeight: "600" },
  stepper: { flexDirection: "row", alignItems: "center", borderWidth: 1.5, borderColor: C.line, borderRadius: R.input, height: 48 },
  sBtn: { width: 44, height: 48, alignItems: "center", justifyContent: "center" },
  sT: { fontSize: 22, color: C.red, fontWeight: "700" },
  qty: { minWidth: 30, textAlign: "center", fontSize: 18, fontWeight: "800", color: C.ink },
  priceBox: { flexDirection: "row", alignItems: "center", height: 48, borderWidth: 1.5, borderColor: C.line, borderRadius: R.input, paddingHorizontal: 12, backgroundColor: C.card },
  priceIn: { flex: 1, fontSize: 18, fontWeight: "700", color: C.ink, padding: 0 },
  unit: { color: C.muted, fontSize: 12 },
  lineTotal: { marginTop: 8, color: C.muted, textAlign: "right" },
  add: { borderWidth: 1.5, borderStyle: "dashed", borderColor: C.muted, borderRadius: R.input, alignItems: "center", paddingVertical: 12, marginTop: 4 },
  addT: { color: C.ink, fontWeight: "700" },
  totalRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "baseline", marginTop: 14, paddingTop: 12, borderTopWidth: 2, borderTopColor: C.ink },
  totalLbl: { color: C.ink, fontWeight: "700", flex: 1 },
  total: { fontSize: 24, fontWeight: "800", color: C.ink },
  tx: { color: C.ink, lineHeight: 22, marginTop: 6 },
  pickHead: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 12 },
  pickTitle: { fontSize: 22, fontWeight: "800", color: C.ink },
  search: { height: 48, borderWidth: 1.5, borderColor: C.ink, borderRadius: R.input, paddingHorizontal: 14, fontSize: 16, color: C.ink, backgroundColor: C.card, marginBottom: 8 },
  pick: { paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: C.line },
  pickName: { color: C.ink, fontSize: 16, fontWeight: "600" },
});
