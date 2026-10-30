#!/bin/bash
# Chạy TRÊN EC2 (do GitHub Actions gọi qua SSM). Biến: REGION ACCOUNT API_IMAGE WEB_IMAGE
set -euo pipefail
cd /opt/app
for i in $(seq 1 60); do [ -f .ready ] && break; echo "cho EC2 khoi tao xong..."; sleep 5; done
[ -f .ready ] || { echo "EC2 chua san sang"; exit 1; }

aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$ACCOUNT.dkr.ecr.$REGION.amazonaws.com"
sed -i '/^API_IMAGE=/d;/^WEB_IMAGE=/d' .env
echo "API_IMAGE=$API_IMAGE" >> .env
echo "WEB_IMAGE=$WEB_IMAGE" >> .env

docker compose pull
docker compose up -d --remove-orphans

echo "Doi API khoe..."
for i in $(seq 1 40); do
  if curl -fsS http://localhost/api/health >/dev/null 2>&1; then echo "HEALTHY"; docker image prune -f >/dev/null; exit 0; fi
  sleep 5
done
docker compose logs --tail 80
echo "API khong len duoc"; exit 1
