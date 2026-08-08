# ⚡ ForwardBot — To'liq O'rnatish

## Fayl tuzilmasi
```
forwardbot/
├── server.py          ← FastAPI + Telethon backend
├── tgbot.py           ← Telegram bot (Mini App launcher)
├── miniapp.html       ← Mini App UI (Netlify ga yuklang)
├── requirements_full.txt
├── .env.example       ← .env ga ko'chiring
└── data/              ← Avtomatik yaratiladi
```

## 1. API kalitlarini oling
1. [my.telegram.org](https://my.telegram.org) → API development tools → `API_ID` va `API_HASH`
2. [@BotFather](https://t.me/BotFather) → `/newbot` → `BOT_TOKEN`

## 2. .env fayl yarating
```bash
cp .env.example .env
# .env ni tahrirlang va kalitlarni kiriting
```

## 3. O'rnatish
```bash
pip install -r requirements_full.txt
```

## 4. Mini App joylash (Netlify — bepul)
1. miniapp.html faylini `index.html` deb saqlang
2. [app.netlify.com/drop](https://app.netlify.com/drop) ga boring
3. Faylni sudrab tashlang → URL oling
4. `.env` dagi `MINI_APP_URL` ni yangilang

## 5. Backend joylash (Railway — bepul)
```bash
# railway.app ga kiring, GitHub repo ulang
# Environment variables qo'shing (.env dan)
# Start command: python server.py
```

## 6. Ishga tushirish
```bash
# Backend (terminal 1)
python server.py

# Bot (terminal 2)
python tgbot.py
```

## Qanday ishlaydi?
1. Foydalanuvchi botni ochadi
2. Mini App ochiladi
3. Telefon raqam + OTP kod bilan ulanadi
4. Chatlar ro'yxatidan manba va manzil tanlaydi
5. Sozlamalar, filterlar o'rnatadi
6. Forward avtomatik boshlanadi! ✅

## Imkoniyatlar
| Funksiya | Holat |
|---------|-------|
| Userbot (Telethon) | ✅ |
| Barcha chat ro'yxati | ✅ |
| Copy / Forward rejimlar | ✅ |
| 12+ filter turi | ✅ |
| Kengaytirilgan sozlamalar | ✅ |
| Header / Footer | ✅ |
| Matn almashtirish | ✅ |
| Session saqlash | ✅ |
| Ko'p foydalanuvchi | ✅ |
| GPT integratsiya | 🔜 |
| Google Drive | 🔜 |
| Jadval (Schedule) | 🔜 |
