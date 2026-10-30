#!/usr/bin/env bash
# Tạo project Expo mới nhất rồi chép code app vào. Chạy MỘT LẦN:  bash mobile/setup.sh
set -euo pipefail
cd "$(dirname "$0")"
if [ -d app ]; then echo "mobile/app đã tồn tại, bỏ qua bước tạo."; exit 0; fi
npx create-expo-app@latest app --template blank-typescript --no-install
cd app
npm install
npx expo install expo-audio expo-secure-store expo-keep-awake @react-native-async-storage/async-storage
cp -r ../overlay/App.tsx ../overlay/src .
node -e '
const fs=require("fs"); const p=JSON.parse(fs.readFileSync("app.json"));
p.expo.name="Voice Coach"; p.expo.slug="unilever-voice";
p.expo.ios={...(p.expo.ios||{}), bundleIdentifier:"com.example.unilevervoice", infoPlist:{NSMicrophoneUsageDescription:"Ghi âm cuộc tư vấn với khách hàng"}};
p.expo.android={...(p.expo.android||{}), package:"com.example.unilevervoice", permissions:["RECORD_AUDIO"]};
p.expo.plugins=[...(p.expo.plugins||[]).filter(x=>!(Array.isArray(x)?x[0]:x).match(/expo-audio|expo-secure-store/)),["expo-audio",{microphonePermission:"Ghi âm cuộc tư vấn với khách hàng"}],"expo-secure-store"];
fs.writeFileSync("app.json",JSON.stringify(p,null,2));
'
echo "Xong. Chạy:  cd mobile/app && npx expo start"
