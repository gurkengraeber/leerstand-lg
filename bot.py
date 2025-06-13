import os, re, uuid, sqlite3, datetime
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, ReplyKeyboardMarkup
)
from telegram.ext import (
    Application, CommandHandler, ContextTypes, ConversationHandler,
    MessageHandler, filters
)
import json

with open("config.json") as f:
    config = json.load(f)

TOKEN = config["telegram_token"]

ADMIN_USERNAMES = {"ohne_u", "ANDERER_USERNAME"}   # zweite Admin-ID ergänzen

DB_FILE      = "bot.db"
BILDER_ORDNER = "bilder"
os.makedirs(BILDER_ORDNER, exist_ok=True)

# ──────────────────────────────────  Datenbank  ──────────────────────────────────
def init_db():
    with sqlite3.connect(DB_FILE) as con:
        c = con.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY,
            telegram_id INTEGER UNIQUE,
            alias TEXT,
            punkte INTEGER DEFAULT 0,
            is_admin INTEGER DEFAULT 0)""")
        c.execute("""CREATE TABLE IF NOT EXISTS meldungen(
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            image_path TEXT,
            adresse TEXT,
            dauer TEXT,
            wohnung TEXT,
            bestaetigungen INTEGER DEFAULT 0,
            FOREIGN KEY(user_id) REFERENCES users(id))""")
        con.commit()
init_db()

# ───────────────────────────── Conversation-States ──────────────────────────────
NAME, WOHNUNG, FOTO, ADRESSE, DAUER = range(5)

# ───────────────────────────── Hilfsfunktionen DB  ──────────────────────────────
def get_or_create_user(tg_id: int, tg_username: str):
    with sqlite3.connect(DB_FILE) as con:
        c = con.cursor()
        c.execute("SELECT id, alias FROM users WHERE telegram_id=?", (tg_id,))
        row = c.fetchone()
        if row:
            return row[0], row[1]
        is_admin = 1 if tg_username in ADMIN_USERNAMES else 0
        c.execute("INSERT INTO users(telegram_id,is_admin) VALUES(?,?)",
                  (tg_id, is_admin))
        con.commit()
        return c.lastrowid, None

def add_points(user_id: int, pts: int):
    with sqlite3.connect(DB_FILE) as con:
        con.execute("UPDATE users SET punkte = punkte + ? WHERE id=?",(pts,user_id))
        con.commit()

def top_five():
    with sqlite3.connect(DB_FILE) as con:
        c = con.cursor()
        c.execute("SELECT alias, punkte FROM users WHERE alias IS NOT NULL "
                  "ORDER BY punkte DESC LIMIT 5")
        return c.fetchall()

def save_meldung(user_id, img_path, adresse, dauer, wohnung):
    with sqlite3.connect(DB_FILE) as con:
        con.execute("""INSERT INTO meldungen
                       (user_id,image_path,adresse,dauer,wohnung)
                       VALUES(?,?,?,?,?)""",
                    (user_id,img_path,adresse,dauer,wohnung))
        con.commit()

def list_meldungen():
    with sqlite3.connect(DB_FILE) as con:
        c = con.cursor()
        c.execute("""SELECT id,image_path,adresse,dauer,wohnung,bestaetigungen
                     FROM meldungen""")
        return c.fetchall()

# ───────────────────────────── Inline-Bestenliste  ──────────────────────────────
def build_ranking_keyboard():
    rows = top_five()
    buttons = [
        [InlineKeyboardButton(f"{alias} – {pts} Pkt", callback_data="noop")]
        for alias, pts in rows
    ] or [[InlineKeyboardButton("Noch keine Einträge", callback_data="noop")]]
    return InlineKeyboardMarkup(buttons)

# ───────────────────────────────── Bot-Handler ──────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_user = update.effective_user
    uid, alias = get_or_create_user(tg_user.id, tg_user.username or "")

    # Buttons für den Start
    keyboard = [
        ["Neue Meldung 📸"],
        ["Top 5 📈"],
        ["Meine Meldungen 📝"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    if alias:
        await update.message.reply_text(
            f"Willkommen zurück, {alias}!",
            reply_markup=reply_markup)
        return ConversationHandler.END
    else:
        await update.message.reply_text(
            "Willkommen! Bitte wähle eine Option:", reply_markup=reply_markup)
        # Direkt die Frage nach der Wohnung stellen
        await update.message.reply_text(
            "Bitte gib die genauen Details deiner Wohnung an (z.B. Stockwerk, Seite, Vorder/Hinterhaus).")
        return WOHNUNG

async def wohnung_erhalten(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wohnung = update.message.text.strip()
    context.user_data["wohnung"] = wohnung
    await update.message.reply_text("Danke! Jetzt schicke ein Foto des Leerstands.")
    return FOTO

async def foto_erhalten(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("Bitte ein *Foto* senden.")
        return FOTO
    file = await update.message.photo[-1].get_file()
    fname = f"{uuid.uuid4()}.jpg"
    pfad = os.path.join(BILDER_ORDNER, fname)
    await file.download_to_drive(pfad)
    context.user_data["img"] = pfad
    await update.message.reply_text(
        "Danke! Jetzt die Adresse im Format:\n"
        "`Straße Hausnummer, Stadt`\n"
        "Beispiel: `Musterstraße 12, Berlin`", parse_mode="Markdown")
    return ADRESSE

def validate_address(addr: str):
    if "," not in addr:
        return "Komma zwischen Straße+Nr. und Stadt fehlt."
    street_part, city_part = [s.strip() for s in addr.split(",",1)]
    if not re.search(r"\d", street_part):
        return "Hausnummer fehlt."
    if len(city_part.split()) < 1:
        return "Stadtname fehlt."
    return None

async def adresse_erhalten(update: Update, context: ContextTypes.DEFAULT_TYPE):
    addr = update.message.text.strip()
    error = validate_address(addr)
    if error:
        await update.message.reply_text(
            f"❌ {error}\nBitte noch einmal korrekt eingeben.")
        return ADRESSE
    context.user_data["addr"] = addr
    await update.message.reply_text(
        "Geschätzte Dauer des Leerstands (z. B. 'seit 6 Monaten')?")
    return DAUER

async def dauer_erhalten(update: Update, context: ContextTypes.DEFAULT_TYPE):
    dauer = update.message.text.strip()
    tg_user  = update.effective_user
    uid, _   = get_or_create_user(tg_user.id, tg_user.username or "")
    wohnung = context.user_data.get("wohnung", "Unbekannt")
    save_meldung(uid, context.user_data["img"],
                 context.user_data["addr"], dauer, wohnung)
    add_points(uid, 5)
    await update.message.reply_text(
        "✅ Meldung gespeichert! (+5 Punkte)",
        reply_markup=build_ranking_keyboard())
    return ConversationHandler.END

# ── Bestehende Meldungen auflisten ──
async def meldungen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for mid, path, addr, dauer, wohnung, conf in list_meldungen():
        caption = (f"#{mid} – {addr}\n"
                   f"Wohnung: {wohnung}\n"
                   f"Stockwerk: {wohnung}\n"
                   f"Dauer: {dauer}\n"
                   f"Bestätigt: {conf}\n/bestaetige_{mid}")
        try:
            with open(path,"rb") as f:
                await update.message.reply_photo(f, caption=caption)
        except FileNotFoundError:
            await update.message.reply_text(caption)

# ── Bestätigen ──
async def bestaetige(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mid = int(update.message.text.split("_")[1])
    with sqlite3.connect(DB_FILE) as con:
        c = con.cursor()
        c.execute("SELECT user_id FROM meldungen WHERE id=?", (mid,))
        row = c.fetchone()
        if not row:
            await update.message.reply_text("Meldung nicht gefunden.")
            return
        melder = row[0]
        add_points(melder, 3)
        c.execute("UPDATE meldungen SET bestaetigungen = bestaetigungen + 1"
                  " WHERE id=?", (mid,))
        con.commit()
    await update.message.reply_text("Bestätigung gespeichert (+3 Punkte).",
                                    reply_markup=build_ranking_keyboard())

# ── Ranking-Befehl ──
async def ranking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏆 Aktuelle Top 5:",
                                    reply_markup=build_ranking_keyboard())

# ── Admin: löschen ──
async def loesche(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if (update.effective_user.username or "") not in ADMIN_USERNAMES:
        await update.message.reply_text("Nicht autorisiert.")
        return
    if not context.args:
        await update.message.reply_text("Verwendung: /loesche <ID>")
        return
    mid = int(context.args[0])
    with sqlite3.connect(DB_FILE) as con:
        c = con.cursor()
        c.execute("SELECT image_path FROM meldungen WHERE id=?", (mid,))
        row = c.fetchone()
        if not row:
            await update.message.reply_text("Meldung nicht gefunden.")
            return
        pfad = row[0]
        if os.path.exists(pfad):
            os.remove(pfad)
        c.execute("DELETE FROM meldungen WHERE id=?", (mid,))
        con.commit()
    await update.message.reply_text(f"Meldung #{mid} gelöscht.")

# ─────────────────────────────  Bot-Initialisierung  ────────────────────────────
def main():
    app = Application.builder().token(TOKEN).build()

    # Name-Festlegung beim ersten Start
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            WOHNUNG: [MessageHandler(filters.TEXT & ~filters.COMMAND, wohnung_erhalten)],
            FOTO:    [MessageHandler(filters.PHOTO, foto_erhalten)],
            ADRESSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, adresse_erhalten)],
            DAUER:   [MessageHandler(filters.TEXT & ~filters.COMMAND, dauer_erhalten)]
        },
        fallbacks=[],
        allow_reentry=True))

    # Melde-Dialog
    melde_conv = ConversationHandler(
        entry_points=[CommandHandler("melde", start)],
        states={
            WOHNUNG: [MessageHandler(filters.TEXT & ~filters.COMMAND, wohnung_erhalten)],
            FOTO:    [MessageHandler(filters.PHOTO, foto_erhalten)],
            ADRESSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, adresse_erhalten)],
            DAUER:   [MessageHandler(filters.TEXT & ~filters.COMMAND, dauer_erhalten)]
        },
        fallbacks=[],
    )
    app.add_handler(melde_conv)

    # Sonstige Commands
    app.add_handler(CommandHandler("meldungen", meldungen))
    app.add_handler(CommandHandler("ranking",   ranking))
    app.add_handler(CommandHandler("loesche",   loesche))
    app.add_handler(MessageHandler(filters.Regex(r"^/bestaetige_\d+$"), bestaetige))

    print("Bot läuft …")
    app.run_polling()

if __name__ == "__main__":
    main()
