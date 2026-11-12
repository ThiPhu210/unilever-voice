# Nhận dạng giọng nói + tạo đơn ngay trên điện thoại

## Luồng

```
SA bấm ghi ──► expo-speech-recognition (Siri / Google): vừa nhận dạng vừa ghi file WAV 16 kHz
            ──► dừng ghi: có transcript ngay (không chờ server)
            ──► parser TypeScript (src/parser) tách đơn: SKU · số lượng · giá · khách chốt/từ chối
            ──► màn "Chờ gửi": nghe lại + xem nhanh transcript và các dòng hàng
            ──► "Tạo đơn & gửi":
                  1. POST /api/sessions/sync   (JSON: transcript + đơn)     -> phiên 'done' ngay, mở màn xác nhận đơn
                  2. POST /api/sessions/{id}/audio (WAV)                    -> server nén AAC 24 kbps -> S3
            Mất mạng: lưu hàng đợi trên máy, có mạng thì tự gửi (retry an toàn nhờ client_id)
```

Máy **không đủ điều kiện** (Android ≤ 12, không có dịch vụ giọng nói Google, không bật Siri, bản build thiếu module…)
hoặc bộ nhận dạng trả rỗng → luồng cũ: ghi m4a, gửi audio, server dịch bằng PhoWhisper. `sttSupport()` quyết định lúc chạy,
nên không cần danh sách máy cố định.

## Cài đặt app

```bash
cd mobile/app
npm install                      # package.json đã thêm expo-speech-recognition; chạy `npx expo install --fix` nếu expo-doctor báo lệch bản
npx expo prebuild                # hoặc: npx expo run:android | run:ios | eas build --profile development
```

Module nhận dạng là **native** → không chạy trong Expo Go, cần development build / EAS build.

## Triển khai server

1. Cập nhật stack CloudFormation (thêm `AudioBucket` + quyền IAM cho `InstanceRole`; tham số `AudioRetentionDays`, 0 = giữ mãi).
2. **Instance đang chạy**: user-data chỉ chạy lần đầu, nên thêm tay vào `/opt/app/.env` rồi `docker compose up -d`:
   `AUDIO_BUCKET=<tên bucket (output AudioBucketName)>` và `AWS_REGION=ap-southeast-1`.
3. DB tự thêm cột/chỉ mục khi API khởi động (`client_id`, `source`, `asr_engine`, `parser_version`, `parser_match`).
4. App cũ vẫn dùng `POST /api/sessions` như trước (không phải đổi gì).

Không đặt `AUDIO_BUCKET` thì audio lưu ổ đĩa như cũ (dev/local).

## Kiểm tra parser trên máy = parser server

```bash
cd backend && python scripts/export_parser_fixtures.py ../mobile/app/scripts/fixtures
cd ../mobile/app && npm run test:parser     # 1.732 ca: phải "lệch 0"
```
CI chạy lệnh này mỗi PR. **Sửa luật parser ở Python thì phải sửa cả `src/parser/*.ts`.** Chỉ mục SKU do server dựng
(`GET /api/catalog/index`, ETag), app chỉ cần so khớp.

Trong lúc triển khai, cột `sessions.parser_match` cho biết đơn app tách có trùng đơn server tự parse từ cùng transcript không:
`SELECT avg(parser_match) FROM sessions WHERE source='device';` (nên ≈ 1.0).

## Việc phải làm trước khi tin con số

* **Chất lượng nhận dạng tiếng Việt của Google/Siri trên hội thoại thật chưa được đo.** Thu 50–100 cuộc ghi thật, so đơn app
  tách với đơn SA đã xác nhận (SKU/số lượng/giá), trên iPhone + Android tầm trung + Android rẻ nhất trong đội.
* Chỉnh `PAUSE_MS` trong `src/stt.ts` (khoảng nghỉ giữa hai SKU, mặc định 800 ms) theo thực tế.
* Tốc độ parser trên Hermes thật (đo ms/lần sau khi bấm dừng) và RAM trên máy yếu.

## Giới hạn đã biết

* Android 12 trở xuống: không ghi file kèm nhận dạng → luôn dùng luồng server.
* Gửi âm thanh tới Google/Apple để nhận dạng (online-first). Muốn riêng tư hơn: bật `requiresOnDeviceRecognition`
  (Android cần tải gói ngôn ngữ vi-VN offline; chất lượng khác).
* Đơn tạo lúc offline chỉ xem được ở màn "Chờ gửi" trước khi bấm gửi; sau đó nằm trong hàng đợi đến khi có mạng.
* Đã bỏ tách người nói (SA/khách) ở luồng trên máy: `coaching` chạy trên toàn văn như phiên chưa đăng ký giọng.
