# Hướng dẫn deploy lên AWS bằng GitHub Actions

Kiến trúc: **1 máy EC2** chạy Docker (API FastAPI + Web Coach qua Caddy), ảnh Docker lưu ở **ECR**,
GitHub Actions đăng nhập AWS bằng **OIDC** (không lưu access key) và deploy qua **SSM** (không mở SSH).

```
git push main ─► GitHub Actions ─► test ─► build 2 image ─► push ECR ─► SSM gửi lệnh ─► EC2 pull & up
                                                                                      │
 Mobile app (Expo) ──http(s)──► EC2:80/443 [Caddy] ─► /api → FastAPI (ASR + parser + SQLite)
 Web Coach (browser) ───────────────────────────────► / → React build
```

## Bước 1. Tạo repo GitHub (rỗng, chưa push)
GitHub → New repository → tên `unilever-voice` (Private) → Create. Ghi nhớ dạng `tenban/unilever-voice`.

## Bước 2. Tạo hạ tầng AWS bằng CloudFormation (1 lần)
1. Đăng nhập AWS Console, góc phải trên chọn region **Asia Pacific (Singapore) ap-southeast-1**.
2. Tìm **CloudFormation** → *Create stack* → *With new resources* → *Upload a template file* → chọn `infra/cloudformation.yml` → Next.
3. Stack name: `unilever-voice`. Điền tham số:
   - **GitHubRepo**: `tenban/unilever-voice`
   - **ApiKey**: chuỗi ≥16 ký tự chỉ gồm chữ và số (đây là mật khẩu cho web + app, hãy lưu lại)
   - **InstanceType**: `c6i.xlarge` (nếu báo lỗi giới hạn vCPU thì chọn `t3.large`)
   - các tham số còn lại để mặc định
4. Next → Next → tick ô *"I acknowledge that AWS CloudFormation might create IAM resources with custom names"* → Submit.
5. Chờ trạng thái **CREATE_COMPLETE** (3–5 phút). Mở tab **Outputs**, copy: `DeployRoleArn`, `Region`, `PublicIp`.

> Lỗi "OIDC provider already exists": tài khoản đã có provider GitHub. Xóa stack lỗi, tạo lại với `CreateGitHubOidcProvider = false`.
> Lỗi `VcpuLimitExceeded`: chọn `t3.large` hoặc xin tăng quota *Running On-Demand Standard instances*.

## Bước 3. Khai báo biến cho GitHub Actions
Repo GitHub → Settings → Secrets and variables → Actions → tab **Variables** → *New repository variable*:
| Name | Value |
|---|---|
| `AWS_ROLE_ARN` | giá trị `DeployRoleArn` |
| `AWS_REGION` | `ap-southeast-1` |

## Bước 4. Push code → tự deploy
```bash
cd unilever-voice
git init && git add . && git commit -m "init"
git branch -M main
git remote add origin https://github.com/tenban/unilever-voice.git
git push -u origin main
```
Vào tab **Actions** xem workflow *Deploy to AWS* (lần đầu ~6–10 phút). Xanh = xong.
Muốn deploy lại không cần sửa code: Actions → Deploy to AWS → *Run workflow*.

## Bước 5. Kiểm tra
- Mở `http://<PublicIp>` → đăng nhập bằng ApiKey.
- Nạp dữ liệu mẫu để xem dashboard: `./scripts/seed_demo.sh http://<PublicIp> <ApiKey>`
- Lần đầu API tải model Whisper (~500 MB cho `small`) nên cuộc ghi âm đầu tiên có thể chờ vài phút.
- Xem log trên server: EC2 Console → chọn instance → *Connect* → tab **Session Manager** → Connect, rồi:
  `cd /opt/app && sudo docker compose logs -f api`

## Bước 6. Cài app mobile
```bash
bash mobile/setup.sh            # tạo project Expo mới nhất + chép code (1 lần)
cd mobile/app && npx expo start
```
Cài **Expo Go** trên điện thoại, quét QR. Tab **Cài đặt** nhập: server `http://<PublicIp>`, ApiKey, mã/tên SA, cửa hàng → *Lưu*.
Sang tab **Ghi âm** → *Bắt đầu tư vấn* → nói thử câu chốt đơn mẫu → *Kết thúc*. Xem kết quả ở tab *Lịch sử* và trên web.

## Bước 7 (nên làm trước khi dùng thật). HTTPS bằng tên miền
1. Trỏ bản ghi DNS `A` của tên miền (vd `coach.congty.com`) về `PublicIp`.
2. Session Manager vào EC2: `sudo sed -i 's|^SITE_ADDRESS=.*|SITE_ADDRESS=coach.congty.com|' /opt/app/.env && cd /opt/app && sudo docker compose up -d`
3. Caddy tự xin chứng chỉ Let's Encrypt. Đổi địa chỉ server trong app thành `https://coach.congty.com`.

## Chi phí & dọn dẹp
- Tham khảo: EC2 `c6i.xlarge` ~ 130 USD/tháng nếu bật 24/7 (kiểm tra bảng giá AWS theo region). **Stop instance** khi không demo (EC2 Console → Instance state → Stop); container tự chạy lại khi Start. Nếu instance đang Stop thì workflow deploy sẽ báo không tìm thấy máy.
- Xóa toàn bộ: CloudFormation → Delete stack `unilever-voice` (mất cả dữ liệu SQLite/audio trên máy).

## Xử lý sự cố
| Triệu chứng | Cách xử lý |
|---|---|
| Actions: `Could not assume role` | Kiểm tra biến `AWS_ROLE_ARN`, tên repo trong tham số `GitHubRepo` phải đúng chữ hoa/thường, và push lên nhánh `main` |
| Actions: không tìm thấy EC2 | Instance đang Stop, hoặc sai region trong `AWS_REGION` |
| Actions: `API khong len duoc` | Xem log in ra ở cuối bước deploy; thường do thiếu RAM → dùng instance lớn hơn |
| App báo "API key không đúng" | Nhập đúng ApiKey đã đặt ở CloudFormation |
| Phiên ghi âm kẹt "Đang dịch" lâu | CPU xử lý chậm / đang tải model lần đầu; xem log API |
| iOS/Android bản build riêng không gọi được `http://` | Bản build thật cần HTTPS → làm Bước 7 |

## Việc cần làm trước khi chạy thật
- Thay `backend/data/sku_catalog.csv` bằng danh mục SKU thật + alias (cách gọi, cách ASR hay nghe sai).
- Biển thông báo/đồng ý ghi âm khách theo Nghị định 13/2023/NĐ-CP; chính sách lưu trữ audio.
- Nâng cấp: SQLite → RDS, audio → S3, thêm đăng nhập từng người dùng (Cognito), tách người nói.
