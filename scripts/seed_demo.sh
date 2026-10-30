#!/usr/bin/env bash
# Nạp vài cuộc hội thoại mẫu để xem dashboard ngay (không cần ghi âm).
# Dùng:  ./scripts/seed_demo.sh http://IP_CUA_BAN API_KEY
set -euo pipefail
URL="${1:?http://IP}"; KEY="${2:?API_KEY}"

post() {
  printf '{"sa_id":"%s","sa_name":"%s","store":"%s","transcript":"%s"}' "$1" "$2" "$3" "$4" |
    curl -fsS -X POST "$URL/api/sessions/text" -H "x-api-key: $KEY" \
      -H 'content-type: application/json; charset=utf-8' --data-binary @- >/dev/null && echo "ok: $2"
}

post sa01 "Nguyễn Lan" "Co.opmart Q7" "Xin chào chị, chị đang dùng loại bột giặt nào ạ? Bên em đang có khuyến mãi tặng kèm nước xả. Chị lấy thêm một túi Comfort cho tiết kiệm nhé. Dạ em xin cảm ơn chị, vậy mình chốt 2 OMO bột giặt 3kg, 1 Comfort 1.6l. Dạ ok em."
post sa01 "Nguyễn Lan" "Co.opmart Q7" "Chào anh, anh cần tìm dầu gội cho nam đúng không ạ? Clear Men đang giảm giá. Dạ em xin cảm ơn anh, vậy mình chốt hai Clear Men 650ml, một Sunsilk 320ml. Dạ đúng rồi em."
post sa02 "Trần Hoa" "Big C Gò Vấp" "Chào chị, bên em có Dove đang ưu đãi. Chị thấy hơi đắt quá, để chị suy nghĩ. Dạ em xin cảm ơn chị, vậy mình chốt 1 Dove 640ml. Thôi để chị xem lại."
post sa02 "Trần Hoa" "Big C Gò Vấp" "Xin chào anh, anh đang dùng hạt nêm nào ạ? Dạ em xin cảm ơn anh, vậy mình chốt ba Knorr 400g, hai Sunlight 750g, một Lifebuoy 850g. Được rồi em."
post sa03 "Lê Minh" "WinMart Q1" "Dạ em xin cảm ơn chị, vậy mình chốt 2 omo. Ừ lấy đi em."
