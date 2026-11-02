export type Settings = { server: string; apiKey: string; saId: string; saName: string; store: string };
export type Candidate = { sku_id: string; name: string; score: number };
export type Item = {
  sku_id: string; sku_name: string; qty: number; conf: number; need_confirm: boolean;
  raw?: string; candidates?: Candidate[]; manual?: boolean;
};
export type Order = {
  id: number; customer_confirm: "yes" | "no" | "none"; items: Item[]; needs_review: number; reviewed: number;
};
export type SessionRow = {
  id: string; created_at: string; status: string; duration: number | null;
  orders: number; units: number; pending_review: number;
};
export type SessionDetail = SessionRow & { transcript_text: string; orders: Order[]; error?: string };
export type CatalogItem = { sku_id: string; name: string; unit: string };
