#!/usr/bin/env bash
# Nạp hội thoại mẫu trải nhiều ngày để xem dashboard + xu hướng SKU ngay (không cần ghi âm).
# Dùng:  ./scripts/seed_demo.sh http://IP_CUA_BAN API_KEY
set -euo pipefail
URL="${1:?http://IP}"; KEY="${2:?API_KEY}"

post() { # sa_id sa_name store days_ago transcript
  printf '{"sa_id":"%s","sa_name":"%s","store":"%s","days_ago":%s,"transcript":"%s"}' "$1" "$2" "$3" "$4" "$5" |
    curl -fsS -X POST "$URL/api/sessions/text" -H "x-api-key: $KEY" \
      -H 'content-type: application/json; charset=utf-8' --data-binary @- >/dev/null && echo "ok: $2 (-$4 ngày)"
}
CT="Dạ em xin cảm ơn anh chị, vậy mình chốt"

post sa01 "Nguyễn Lan" "Co.opmart Q7" 6 "Xin chào chị, chị đang dùng loại bột giặt nào ạ? Bên em đang có khuyến mãi tặng kèm nước xả. $CT 2 OMO bột giặt 3kg 185 nghìn đồng, 1 Comfort 1.6l 85 nghìn đồng. Dạ ok em."
post sa02 "Trần Hoa" "Big C Gò Vấp" 6 "Chào chị, bên em có Dove đang ưu đãi. $CT 1 Dove 640ml 99 nghìn đồng. Dạ đúng rồi em."
post sa01 "Nguyễn Lan" "Co.opmart Q7" 5 "Chào anh, anh cần tìm dầu gội cho nam đúng không ạ? Clear Men đang giảm giá. $CT hai Clear Men 650ml 120 nghìn đồng, một Sunsilk 320ml 65 nghìn đồng. Dạ đúng rồi em."
post sa03 "Lê Minh" "WinMart Q1" 5 "$CT 2 OMO 800g 65 nghìn đồng. Ừ lấy đi em."
post sa02 "Trần Hoa" "Big C Gò Vấp" 4 "Xin chào anh, anh đang dùng hạt nêm nào ạ? $CT ba Knorr 400g 48 nghìn đồng, hai Sunlight 750g 39 nghìn đồng, một Lifebuoy 850g 78 nghìn đồng. Được rồi em."
post sa01 "Nguyễn Lan" "Co.opmart Q7" 3 "$CT 3 OMO 800g 65 nghìn đồng, 2 Comfort 1.6l 85 nghìn đồng. Dạ ok em."
post sa03 "Lê Minh" "WinMart Q1" 3 "Chào chị, chị cần tìm gì ạ? Bên em có combo tiết kiệm hơn. $CT 4 OMO 800g sáu mươi lăm nghìn đồng. Dạ đúng rồi em."
post sa02 "Trần Hoa" "Big C Gò Vấp" 2 "Chào chị, bên em có Dove đang ưu đãi. Chị thấy hơi đắt quá, để chị suy nghĩ. $CT 1 Dove 640ml 99 nghìn đồng. Thôi để chị xem lại."
post sa01 "Nguyễn Lan" "Co.opmart Q7" 2 "$CT 2 Clear Men 650ml 120 nghìn đồng, 2 OMO 800g 65 nghìn đồng. Dạ ok em."
post sa03 "Lê Minh" "WinMart Q1" 1 "Dạ em xin cảm ơn chị, vậy mình chốt 5 OMO 800g 65 nghìn đồng, 1 Sunsilk 650ml 110 nghìn đồng. Ừ lấy đi em."
post sa02 "Trần Hoa" "Big C Gò Vấp" 1 "Xin chào anh, anh đang dùng loại nào ạ? $CT hai Knorr 400g 48 nghìn đồng, hai Clear Men 650ml. Dạ ok em."
post sa01 "Nguyễn Lan" "Co.opmart Q7" 0 "Xin chào chị, chị đang dùng loại bột giặt nào ạ? Bên em đang có khuyến mãi tặng kèm nước xả. $CT 2 OMO bột giặt 3kg 185 nghìn đồng, 1 Comfort 1.6l. Dạ ok em."
post sa03 "Lê Minh" "WinMart Q1" 0 "$CT 3 OMO 800g, 1 Dove 640ml. Ừ lấy đi em."
