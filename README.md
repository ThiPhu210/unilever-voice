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
