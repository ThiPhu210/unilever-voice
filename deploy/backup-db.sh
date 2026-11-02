#!/bin/bash
# Sao lưu PostgreSQL (chạy TRÊN EC2). Giữ 14 bản gần nhất trong /opt/app/backups.
# Đặt cron hằng ngày:  echo '0 2 * * * root /opt/app/backup-db.sh' | sudo tee /etc/cron.d/uv-backup
# Nên chép thêm thư mục backups lên S3 (aws s3 sync) hoặc chuyển sang Amazon RDS (có sẵn backup tự động).
set -euo pipefail
cd /opt/app
mkdir -p backups
f="backups/uv-$(date +%Y%m%d-%H%M%S).sql.gz"
docker compose exec -T db pg_dump -U uv uv | gzip > "$f"
ls -1t backups/uv-*.sql.gz | tail -n +15 | xargs -r rm --
echo "ok $f"
