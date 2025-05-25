import os
import sqlite3
import uuid
from telegram import Update, InputMediaPhoto
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ContextTypes, ConversationHandler
)

TOKEN = "7962546126:AAFjNgrwm9dMG_aquR03ChmS_GijTlRg9Aw"
ADMIN_USERNAMES = {"ohne_u", "ANDERER_USERNAME"}

DB_FILE = "bot.db"
BILD_ORDNER = "bilder"
os.makedirs(BILD_ORDNER, exist_ok=True)

# ---- DB SETUP ----
conn = sqlite3.connect(DB_FILE)
c = conn.cursor()
c.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    telegram_id INTEGER,
    username TEXT,
    punkte INTEGER DEFAULT 0,
    is_admin INTEGER DEFAULT 0
)
""")
c.execute("""
CREATE TABLE IF NOT EXISTS meldungen (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    image_path TEXT,
    adresse TEXT,
    dauer TEXT,
    bestaetigungen INTEGER DEFAULT 0,
    FOREIGN KEY(user_id) REFERENCES users(id)
)
""")
conn.commit()
conn.close()

# ---- Conversation states ----
FOTO, ADRESSE, DAUER = range(3)

# ---- Hilfsfunktionen ----
def get_user_id(telegram_id, username):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE telegram_id = ?", (telegram_id,))
    row = c.fetchone()
    if row:
        user_id = row[0]
    else:
        is_admin = 1 if username in ADMIN_USERNAMES else 0
        c.execute("INSERT INTO users (telegram_id, username, punkte, is_admin) VALUES (?, ?, 0, ?)",
                  (telegram_id, username, is_admin))
        user_id = c.lastrowid
        conn.commit()
    conn.close()
    return user_id

# ---- COMMANDS ----
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    get_user_id(user.id, user.username or "")
    await update.message.reply_text("Du bist jetzt registriert. Nutze /melde, um Leerstand zu melden.")

async def melde_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bitte sende mir ein Foto des Leerstands.")
    return FOTO

async def foto_erhalten(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]
    file = await photo.get_file()
    dateiname = f"{uuid.uuid4()}.jpg"
    pfad = os.path.join(BILD_ORDNER, dateiname)
    await file.download_to_drive(pfad)
    context.user_data["bild"] = pfad
    await update.message.reply_text("Danke! Jetzt bitte die Adresse.")
    return ADRESSE

async def adresse_erhalten(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["adresse"] = update.message.text
    await update.message.reply_text("Wie lange steht die Wohnung deiner Schätzung nach schon leer?")
    return DAUER

async def dauer_erhalten(update: Update, context: ContextTypes.DEFAULT_TYPE):
    dauer = update.message.text
    user = update.effective_user
    user_id = get_user_id(user.id, user.username or "")
    bild = context.user_data["bild"]
    adresse = context.user_data["adresse"]

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO meldungen (user_id, image_path, adresse, dauer) VALUES (?, ?, ?, ?)",
              (user_id, bild, adresse, dauer))
    c.execute("UPDATE users SET punkte = punkte + 5 WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()

    await update.message.reply_text("Danke, deine Meldung wurde gespeichert. Du bekommst 5 Punkte!")
    return ConversationHandler.END

async def ranking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT username, punkte FROM users ORDER BY punkte DESC LIMIT 5")
    rows = c.fetchall()
    conn.close()

    text = "🏆 Bestenliste:\n\n"
    for i, (username, punkte) in enumerate(rows, 1):
        name = username if username else f"User {i}"
        text += f"{i}. {name}: {punkte} Punkte\n"
    await update.message.reply_text(text)

async def meldungen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, image_path, adresse, dauer, bestaetigungen FROM meldungen")
    rows = c.fetchall()
    conn.close()

    for id, pfad, adresse, dauer, bestaetigungen in rows:
        caption = f"Meldung #{id}\nAdresse: {adresse}\nDauer: {dauer}\nBestätigungen: {bestaetigungen}\n/bestaetige_{id}"
        try:
            with open(pfad, "rb") as f:
                await update.message.reply_photo(f, caption=caption)
        except:
            await update.message.reply_text(f"Meldung #{id} (Bild fehlt)\nAdresse: {adresse}")

async def bestaetige(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text.startswith("/bestaetige_"):
        return
    try:
        meldung_id = int(text.split("_")[1])
    except:
        return

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT user_id FROM meldungen WHERE id = ?", (meldung_id,))
    row = c.fetchone()
    if row:
        user_id = row[0]
        c.execute("UPDATE users SET punkte = punkte + 3 WHERE id = ?", (user_id,))
        c.execute("UPDATE meldungen SET bestaetigungen = bestaetigungen + 1 WHERE id = ?", (meldung_id,))
        conn.commit()
        await update.message.reply_text("Bestätigung gespeichert. Melder erhält 3 Punkte.")
    else:
        await update.message.reply_text("Meldung nicht gefunden.")
    conn.close()

async def loesche(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    username = user.username or ""
    if username not in ADMIN_USERNAMES:
        await update.message.reply_text("Du bist kein Admin.")
        return

    try:
        meldung_id = int(context.args[0])
    except:
        await update.message.reply_text("Verwende: /loesche <ID>")
        return

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT image_path FROM meldungen WHERE id = ?", (meldung_id,))
    row = c.fetchone()
    if row:
        pfad = row[0]
        if os.path.exists(pfad):
            os.remove(pfad)
        c.execute("DELETE FROM meldungen WHERE id = ?", (meldung_id,))
        conn.commit()
        await update.message.reply_text(f"Meldung #{meldung_id} gelöscht.")
    else:
        await update.message.reply_text("Meldung nicht gefunden.")
    conn.close()

# ---- Bot Setup ----
def main():
    app = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("melde", melde_start)],
        states={
            FOTO: [MessageHandler(filters.PHOTO, foto_erhalten)],
            ADRESSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, adresse_erhalten)],
            DAUER: [MessageHandler(filters.TEXT & ~filters.COMMAND, dauer_erhalten)],
        },
        fallbacks=[],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("ranking", ranking))
    app.add_handler(CommandHandler("meldungen", meldungen))
    app.add_handler(CommandHandler("loesche", loesche))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^/bestaetige_\d+"), bestaetige))

    print("Bot läuft ...")
    app.run_polling()

if __name__ == "__main__":
    main()
