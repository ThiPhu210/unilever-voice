# Unilever Voice Coach

Ghi âm hội thoại SA/BA – khách → dịch transcript → tự bắt SKU + số lượng từ câu chốt đơn mẫu → web Coach.
**Không dùng LLM** (ASR + regex/fuzzy matching).

| Thư mục | Nội dung |
|---|---|
| `backend/` | FastAPI, faster-whisper, parser SKU, SQLite, test (`pytest`) |
| `web/` | Web Coach (React + Vite + Recharts), build thành image Caddy |
| `mobile/` | App React Native (Expo): ghi âm, upload offline-queue, xác nhận/sửa SKU |
| `infra/` | CloudFormation: EC2 + ECR + IAM OIDC cho GitHub |
| `.github/workflows/` | `ci.yml` (test), `deploy.yml` (build → ECR → deploy EC2 qua SSM) |
| `docs/DEPLOY.md` | **Hướng dẫn deploy từng bước** |

## Chạy thử trên máy
```bash
cd backend && pip install -r requirements.txt && pytest -q
API_KEY=dev uvicorn app.main:app --reload        # API :8000
cd ../web && npm install && npm run dev          # Web :5173 (proxy /api -> :8000)
./scripts/seed_demo.sh http://localhost:8000 dev # dữ liệu mẫu
```
Hoặc `docker compose up --build` → http://localhost:8080 (API key: `devkey1234567890`).

Câu chốt đơn mẫu: *"Dạ em xin cảm ơn anh chị, vậy mình chốt 2 OMO 800g, 1 Clear Men 650ml."*

## Giá SKU (`gia_sku`)
Câu chốt đơn mẫu có giá: *"Dạ em xin cảm ơn anh chị, vậy mình chốt {n} {tên SKU} {giá} nghìn đồng, {m} {tên SKU} {giá} nghìn đồng…"*
- Parser đọc giá dạng chữ ("sáu mươi lăm nghìn"), số ("65 nghìn đồng", "65k", "65.000đ"), "nghìn rưỡi". Giá = **đơn giá / 1 đơn vị**, doanh thu dòng = SL × giá.
- Quên nói giá → `price = null`; app đánh dấu đỏ "Chưa có giá" và **khoá nút xác nhận** tới khi SA/BA nhập đủ (giá 0 được phép cho hàng tặng).
- SA/BA trên app có thể: đổi SKU, sửa số lượng, nhập/sửa giá (đơn vị nghìn đồng), thêm/xoá SKU, hoặc nhập đơn thủ công khi hệ thống không nghe thấy câu chốt.
- API mới: `PUT /api/orders/{id}/items` nhận `price`; `POST /api/sessions/{id}/orders`; `GET /api/stats/skus?days=` (xu hướng SKU theo ngày). Web có thêm trang **Sản phẩm** (xu hướng số lượng/doanh thu, giá TB).
- `scripts/seed_demo.sh` nạp dữ liệu mẫu trải 7 ngày (có vài đơn cố tình thiếu giá).
- Mobile: chạy lại `bash mobile/setup.sh` cho project mới, hoặc `cd mobile/app && npm install` (đã thêm `react-native-safe-area-context`).
