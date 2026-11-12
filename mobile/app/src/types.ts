/** token: phiên đăng nhập do server cấp (lưu trong SecureStore). Rỗng = chưa đăng nhập. */
export type Settings = {
  server: string; token: string; saId: string; saName: string; store: string;
  /** Nhận dạng offline (không gửi âm thanh cho Google/Apple). Chỉ có hiệu lực khi gói vi-VN đã cài trên máy. */
  offlineStt?: boolean;
};
/** Kết quả dò mã BA: unknown = chưa được cấp, set_password = lần đầu (tự đặt mật khẩu), login = đã có mật khẩu. */
export type AuthStatus = "unknown" | "set_password" | "login";
export type AuthResult = { token: string; sa_id: string; sa_name?: string; store?: string };
export type Candidate = { sku_id: string; name: string; score: number };
export type Item = {
  sku_id: string; sku_name: string; qty: number; price: number | null; conf: number; need_confirm: boolean;
  raw?: string; candidates?: Candidate[]; manual?: boolean;
};
export type Order = {
  id: number; customer_confirm: "yes" | "no" | "none"; items: Item[]; needs_review: number; reviewed: number;
  missing_price: number; total: number;
};
export type SessionRow = {
  id: string; store: string; created_at: string; status: string; duration: number | null;
  orders: number; units: number; revenue: number; pending_review: number; missing_price: number;
};
export type SessionDetail = SessionRow & { transcript_text: string; orders: Order[]; error?: string };
export type CatalogItem = { sku_id: string; name: string; unit: string };
export type LineIn = { sku_id: string; qty: number; price: number | null };
