import json
import sqlite3
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (Application, CommandHandler, MessageHandler,
                          filters, ConversationHandler, ContextTypes)
import os

# Nutzer-Status-Konstanten
CHOOSING, PHOTO, ADDRESS, DURATION = range(4)

# Admin-Usernamen
ADMINS = ["ohne_u"]

# Dauerhaft sichtbares Hauptmenü
main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        ["\ud83d\udce2 Neue Meldung", "\ud83c\udfc6 Bestenliste"],
        ["\u2139\ufe0f Hilfe"]
    ],
    resize_keyboard=True,
    one_time_keyboard=False
)

# Konfiguration laden
with open("config.json") as f:
    config = json.load(f)
TOKEN = config["telegram_token"]

# Datenbank initialisieren
conn = sqlite3.connect("bot.db")
c = conn.cursor()
c.execute('''
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    points INTEGER DEFAULT 0
)''')
c.execute('''
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    photo_id TEXT,
    address TEXT,
    duration TEXT
)''')
conn.commit()
conn.close()

# Benutzerregistrierung oder -aktualisierung
def register_user(user_id, username):
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    result = c.fetchone()
    if result is None:
        c.execute("INSERT INTO users (user_id, username, points) VALUES (?, ?, 0)", (user_id, username))
    else:
        c.execute("UPDATE users SET username=? WHERE user_id=?", (username, user_id))
    conn.commit()
    conn.close()

# Punkte vergeben
def add_points(user_id, amount):
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

# Bestenliste holen
def get_top_users():
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("SELECT username, points FROM users ORDER BY points DESC LIMIT 5")
    result = c.fetchall()
    conn.close()
    return result

# Formatprüfung Adresse
def validate_address(address):
    if len(address) < 5 or "," not in address:
        return False, "Bitte gib die Adresse im Format 'Stra\u00dfe Hausnummer, Stadt' an."
    return True, ""

# Startbefehl
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Willkommen beim Leerstandsmelder! Bitte gib einen Nutzernamen ein:",
        reply_markup=main_keyboard
    )
    return CHOOSING

# Benutzername setzen
async def choose_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.message.text.strip()
    user_id = update.effective_user.id
    register_user(user_id, username)
    await update.message.reply_text(
        f"Danke {username}! Du kannst jetzt eine \ud83d\udce2 Neue Meldung machen oder die \ud83c\udfc6 Bestenliste anschauen.",
        reply_markup=main_keyboard
    )
    return ConversationHandler.END

# Neue Meldung starten
async def new_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bitte sende ein Foto der leerstehenden Wohnung.")
    return PHOTO

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo_id = update.message.photo[-1].file_id
    context.user_data["photo_id"] = photo_id
    await update.message.reply_text("Danke! Jetzt bitte die Adresse im Format 'Stra\u00dfe Hausnummer, Stadt'.")
    return ADDRESS

async def handle_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    address = update.message.text.strip()
    valid, error = validate_address(address)
    if not valid:
        await update.message.reply_text(error)
        return ADDRESS
    context.user_data["address"] = address
    await update.message.reply_text("Wie lange steht die Wohnung vermutlich schon leer?")
    return DURATION

async def handle_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    duration = update.message.text.strip()
    user_id = update.effective_user.id
    photo_id = context.user_data["photo_id"]
    address = context.user_data["address"]

    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("INSERT INTO reports (user_id, photo_id, address, duration) VALUES (?, ?, ?, ?)",
              (user_id, photo_id, address, duration))
    conn.commit()
    conn.close()

    add_points(user_id, 5)
    await update.message.reply_text("Meldung gespeichert! Du hast 5 Punkte bekommen.", reply_markup=main_keyboard)
    return ConversationHandler.END

# Bestenliste anzeigen
async def show_bestenliste(update: Update, context: ContextTypes.DEFAULT_TYPE):
    top = get_top_users()
    msg = "\ud83c\udfc6 *Bestenliste:*\n"
    for i, (name, points) in enumerate(top, start=1):
        msg += f"{i}. {name} – {points} Punkte\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

# Hilfe
async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("\ud83d\udce2 Mit diesem Bot kannst du Leerstand melden. Nutze die Buttons, um loszulegen.")

# Button-Reaktionen
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "\ud83d\udce2 Neue Meldung":
        return await new_report(update, context)
    elif text == "\ud83c\udfc6 Bestenliste":
        return await show_bestenliste(update, context)
    elif text == "\u2139\ufe0f Hilfe":
        return await show_help(update, context)

# Hauptfunktion
def main():
    app = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSING: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_username)],
            PHOTO: [MessageHandler(filters.PHOTO, handle_photo)],
            ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_address)],
            DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_duration)],
        },
        fallbacks=[]
    )

    app.add_handler(conv_handler)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, button_handler))

    app.run_polling()

if __name__ == "__main__":
    main()
