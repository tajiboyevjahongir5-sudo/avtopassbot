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

from fastapi import FastAPI, HTTPException, Request
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

BOT_TOKEN = os.getenv("BOT_TOKEN", "8603403010:AAFjbwFfZrtuVvhGMCSCw8-cY_ezUCTu6tE")
MINI_APP_URL = os.getenv("MINI_APP_URL", "https://jahongirsteam1-ux.github.io/tezlashtiramiz/")
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

# PTB Bot ilovasi
ptb_app = Application.builder().token(BOT_TOKEN).build()

async def start_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    
    subs = load_subs()
    uid_str = str(u.id)
    if uid_str not in subs:
        now = datetime.now().timestamp()
        subs[uid_str] = {"expires_at": now + (7 * 24 * 3600), "trial": True, "registered_at": now}
    subs[uid_str]["name"] = u.first_name
    if u.username:
        subs[uid_str]["username"] = u.username
    save_subs(subs)

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🚀 Tizimga kirish", web_app=WebAppInfo(url=MINI_APP_URL))
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
            "registered_at": now
        }
        save_subs(subs)
        return True
    return datetime.now().timestamp() < user_sub.get("expires_at", 0)

def load(uid):
    uid = str(uid)
    doc = db.users.find_one({"_id": uid})
    if doc:
        doc.pop("_id", None)
        return doc
    return {"session": None, "phone": None, "connected": False, "rules": []}

def save(uid, data):
    uid = str(uid)
    db.users.update_one({"_id": uid}, {"$set": data}, upsert=True)

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
def check_filters(msg_text: str, views: int, reactions: int, sender_name: str, filters: list) -> bool:
    if not filters:
        return True
    for f in filters:
        if not f.get("enabled", True):
            continue
        ftype = f.get("type", "exact")
        val = str(f.get("value", "")).strip()
        if not val:
            continue
        if ftype == "exact":
            if val.lower() not in msg_text.lower():
                return False
        elif ftype == "regex":
            try:
                if not re.search(val, msg_text, re.IGNORECASE):
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

def register_handler(uid: str, client: TelegramClient):
    """Foydalanuvchi uchun BIR MARTA handler ro'yxatga olish"""
    if uid in handlers_registered:
        log.info(f"[{uid}] Handler allaqachon ro'yxatda, o'tkazib yuborildi")
        return

    @client.on(events.NewMessage())
    async def handler(event):
        data = load(uid)
        chat_id = str(event.chat_id)

        for i, rule in enumerate(data.get("rules", [])):
            if not rule.get("active", True):
                continue
            if rule["source_id"] != chat_id:
                continue

            msg = event.message
            text = msg.text or msg.caption or ""
            views = getattr(msg, "views", 0) or 0
            reactions = 0
            if hasattr(msg, "reactions") and msg.reactions:
                try: reactions = sum(r.count for r in msg.reactions.results)
                except: pass
            sender_name = ""
            try:
                sender = await event.get_sender()
                if sender:
                    parts = [getattr(sender, "first_name", ""), getattr(sender, "last_name", ""), getattr(sender, "username", "")]
                    sender_name = " ".join(p for p in parts if p)
            except: pass

            if not check_sub(uid):
                continue
            if not check_filters(text, views, reactions, sender_name, rule.get("filters", [])):
                continue

            dest_id = rule["dest_id"]
            delivery = rule.get("delivery", "copy_bot")
            settings = rule.get("settings", {})

            try:
                # Header / Footer
                header = settings.get("header", "").strip()
                footer = settings.get("footer", "").strip()

                # Matn almashtirish
                replacements = settings.get("replacements_list", [])
                modified_text = text
                for rep in replacements:
                    if rep.get("from") and rep.get("to") is not None:
                        modified_text = modified_text.replace(rep["from"], rep["to"])

                if header: modified_text = header + "\n\n" + modified_text
                if footer: modified_text = modified_text + "\n\n" + footer

                dest = int(dest_id)

                if delivery in ("copy_bot", "copy_acc", "copy_flood"):
                    if msg.media:
                        await client.send_file(dest, msg.media, caption=modified_text or None)
                    elif modified_text:
                        await client.send_message(dest, modified_text)
                elif delivery in ("fwd_acc", "fwd_copy"):
                    try:
                        await client.forward_messages(dest, msg, event.chat_id)
                    except Exception:
                        # copy if restricted
                        if msg.media:
                            await client.send_file(dest, msg.media, caption=modified_text or None)
                        elif modified_text:
                            await client.send_message(dest, modified_text)
                else:
                    await client.forward_messages(dest, msg, event.chat_id)

                # Hisoblagich
                data["rules"][i]["count"] = data["rules"][i].get("count", 0) + 1
                save(uid, data)
                log.info(f"[{uid}] Forwarded: {chat_id} → {dest_id} (delivery={delivery})")

            except ChatAdminRequiredError:
                log.warning(f"[{uid}] Bot admin emas: {dest_id}")
            except FloodWaitError as e:
                log.warning(f"[{uid}] FloodWait {e.seconds}s")
                await asyncio.sleep(e.seconds)
                try:
                    await client.forward_messages(int(dest_id), msg, event.chat_id)
                except: pass
            except Exception as e:
                log.error(f"[{uid}] Forward error: {e}")

    handlers_registered.add(uid)
    log.info(f"[{uid}] Handler ro'yxatga olindi ✅")

async def get_client(uid: str) -> Optional[TelegramClient]:
    """Mavjud clientni qaytaradi yoki sessiondan tiklaydi"""
    if uid in clients:
        c = clients[uid]
        try:
            if c.is_connected() and await c.is_user_authorized():
                return c
        except: pass

    data = load(uid)
    if not data.get("session"):
        return None

    c = TelegramClient(StringSession(data["session"]), API_ID, API_HASH)
    try:
        await c.connect()
        if await c.is_user_authorized():
            clients[uid] = c
            register_handler(uid, c)
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

    # Barcha saqlangan sessionlarni tiklash
    for f in DATA_DIR.glob("*.json"):
        uid = f.stem
        try:
            data = json.loads(f.read_text("utf-8"))
            if data.get("session") and data.get("connected"):
                c = await get_client(uid)
                if c:
                    log.info(f"Session tiklandi: {uid}")
        except Exception as e:
            log.error(f"Startup restore {uid}: {e}")
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
        data.update({"session": session, "connected": True})
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

@app.get("/stats/{uid}")
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
    subs[uid] = user_sub
    save_subs(subs)
    return {"ok": True}

@app.get("/admin/payments")
async def admin_payments(password: str = ""):
    cfg = load_admin()
    if password != cfg.get("password", "admin"):
        raise HTTPException(403, "Ruxsat yo'q")
    return load_pending()

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

@app.get("/health")
async def health():
    return {"status": "ok", "clients": len(clients), "pending": len(pending)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
