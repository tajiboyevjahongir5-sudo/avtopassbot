import os, logging
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request
from telegram import Update, WebAppInfo, InlineKeyboardButton, InlineKeyboardMarkup, MenuButtonWebApp
from telegram.ext import Application, CommandHandler, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN", "8881052991:AAFop1tZG0q4s8vnIkK76GSHCwE9X5qp9aM")
MINI_APP_URL = os.getenv("MINI_APP_URL", "https://jahongirsteam1-ux.github.io/avtopass_bot/")
WEBHOOK_URL = "https://avtopassbot-production.up.railway.app"  # sizning URL

logging.basicConfig(level=logging.INFO)
app = FastAPI()

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🚀 Tizimga kirish", web_app=WebAppInfo(url=MINI_APP_URL))
    ]])
    text = (
        f"<b>👋 Salom, {u.first_name}!</b>\n\n"
        "<b>Auto Chek Bot</b> ga xush kelibsiz.\n"
        "<i>Tizimga kirish uchun quyidagi tugmani bosing:</i>"
    )
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=kb)

# PTB Application
ptb_app = Application.builder().token(BOT_TOKEN).build()
ptb_app.add_handler(CommandHandler("start", start))

@app.on_event("startup")
async def startup():
    await ptb_app.bot.set_webhook(f"{WEBHOOK_URL}/webhook")
    await ptb_app.initialize()
    await ptb_app.start()
    print("Webhook o'rnatildi!")

@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, ptb_app.bot)
    await ptb_app.process_update(update)
    return {"ok": True}

@app.get("/")
async def root():
    return {"status": "Bot ishlayapti!"}
