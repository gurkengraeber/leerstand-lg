import os, re, uuid, sqlite3, json
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    Application, CommandHandler, ContextTypes,
    MessageHandler, filters, CallbackQueryHandler
)

# Laden der Konfiguration
with open("config.json") as f:
    config = json.load(f)

TOKEN = config["telegram_token"]
ADMIN_USERNAMES = {"ohne_u", "ANDERER_USERNAME"}  # Ergänze hier deine Admin-Namen

DB_FILE = "bot.db"
BILDER_ORDNER = "bilder"
os.makedirs(BILDER_ORDNER, exist_ok=True)

# Datenbank initialisieren
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
            bestaetigungen INTEGER DEFAULT 0,
            FOREIGN KEY(user_id) REFERENCES users(id))""")
        con.commit()

init_db()

# Status-States
NAME, ADRESSE, FOTO, DAUER = range(4)

# Hilfsfunktionen für DB
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

def set_user_alias(user_id: int, alias: str):
    with sqlite3.connect(DB_FILE) as con:
        con.execute("UPDATE users SET alias = ? WHERE id = ?", (alias, user_id))
        con.commit()

def add_points(user_id: int, pts: int):
    with sqlite3.connect(DB_FILE) as con:
        con.execute("UPDATE users SET punkte = punkte + ? WHERE id=?", (pts, user_id))
        con.commit()

def top_five():
    with sqlite3.connect(DB_FILE) as con:
        c = con.cursor()
        c.execute("SELECT alias, punkte FROM users WHERE alias IS NOT NULL ORDER BY punkte DESC LIMIT 5")
        return c.fetchall()

def save_meldung(user_id, img_path, adresse, dauer):
    try:
        with sqlite3.connect(DB_FILE) as con:
            con.execute("""INSERT INTO meldungen (user_id, image_path, adresse, dauer)
                           VALUES (?, ?, ?, ?)""",
                        (user_id, img_path, adresse, dauer))
            con.commit()
    except Exception as e:
        raise Exception(f"Fehler beim Speichern in die Datenbank: {e}")

def list_meldungen():
    with sqlite3.connect(DB_FILE) as con:
        c = con.cursor()
        c.execute("""SELECT id, image_path, adresse, dauer, bestaetigungen FROM meldungen""")
        return c.fetchall()

def get_user_meldungen(user_id):
    with sqlite3.connect(DB_FILE) as con:
        c = con.cursor()
        c.execute("""SELECT id, image_path, adresse, dauer, bestaetigungen 
                     FROM meldungen WHERE user_id = ? ORDER BY id DESC""", (user_id,))
        return c.fetchall()

# Hauptmenü erstellen
def build_main_menu():
    keyboard = [
        [InlineKeyboardButton("🏠 Neue Meldung", callback_data='neue_meldung')],
        [InlineKeyboardButton("🏆 Bestenliste", callback_data='bestenliste')],
        [InlineKeyboardButton("📋 Meine Meldungen", callback_data='meine_meldungen')]
    ]
    return InlineKeyboardMarkup(keyboard)

def build_back_menu():
    keyboard = [[InlineKeyboardButton("🔙 Zurück zum Menü", callback_data='back_to_menu')]]
    return InlineKeyboardMarkup(keyboard)

def build_ranking_keyboard():
    rows = top_five()
    buttons = []
    if rows:
        medals = ["🥇", "🥈", "🥉", "4.", "5."]
        for i, (alias, pts) in enumerate(rows):
            medal = medals[i] if i < len(medals) else f"{i+1}."
            buttons.append([InlineKeyboardButton(f"{medal} {alias} – {pts} Pkt", callback_data="noop")])
    else:
        buttons.append([InlineKeyboardButton("Noch keine Einträge", callback_data="noop")])
    buttons.append([InlineKeyboardButton("🔙 Zurück zum Menü", callback_data='back_to_menu')])
    return InlineKeyboardMarkup(buttons)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_user = update.effective_user
    uid, alias = get_or_create_user(tg_user.id, tg_user.username or "")
    reply_markup = build_main_menu()
    welcome_text = "🏠 *Leerstand-Melde-Bot*\n\nWähle eine Option:"
    if alias:
        welcome_text = f"Willkommen zurück, {alias}! 👋\n\n" + welcome_text
    else:
        welcome_text = "Willkommen! 👋\n\n" + welcome_text
    await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    tg_user = update.effective_user
    uid, alias = get_or_create_user(tg_user.id, tg_user.username or "")
    if data == 'neue_meldung':
        if not alias:
            await query.edit_message_text(
                "Willkommen! 👋\n\nDu bist neu hier. Wie soll ich dich nennen?\n"
                "Bitte gib deinen gewünschten Nutzernamen ein:"
            )
            context.user_data['waiting_for_name'] = True
            return
        else:
            await query.edit_message_text(
                f"Hallo {alias}! 🏠\n\n"
                "Bitte gib die Adresse des Leerstands ein (Format: Straße Hausnummer):"
            )
            context.user_data['meldung_step'] = 'adresse'
            return
    elif data == 'bestenliste':
        await query.edit_message_text("🏆 *Aktuelle Bestenliste:*", 
                                    reply_markup=build_ranking_keyboard(), 
                                    parse_mode='Markdown')
    elif data == 'meine_meldungen':
        meldungen = get_user_meldungen(uid)
        if not meldungen:
            await query.edit_message_text(
                "📋 *Meine Meldungen*\n\nDu hast noch keine Meldungen abgegeben.",
                reply_markup=build_back_menu(),
                parse_mode='Markdown'
            )
            return
        await query.edit_message_text(
            f"📋 *Meine Meldungen* ({len(meldungen)} insgesamt)\n\nWerden gesendet...",
            reply_markup=build_back_menu(),
            parse_mode='Markdown'
        )
        for m in meldungen:
            mid, path, addr, dauer, conf = m
            caption = f"#{mid} – {addr}\n⏰ Dauer: {dauer}\n✅ Bestätigt: {conf}x"
            try:
                with open(path, "rb") as f:
                    await update.effective_chat.send_photo(f, caption=caption)
            except Exception as e:
                await update.effective_chat.send_message(f"❌ Foto nicht verfügbar\n{caption}")
    elif data == 'back_to_menu':
        await query.edit_message_text(
            "🏠 *Leerstand-Melde-Bot*\n\nWähle eine Option:",
            reply_markup=build_main_menu(),
            parse_mode='Markdown'
        )
        context.user_data.clear()
    elif data == 'noop':
        pass

def validate_address(addr: str):
    # Nur Straße und Hausnummer (z.B. Musterstraße 12)
    if not re.match(r"^[^\d]+ \d+[a-zA-Z]?$", addr.strip()):
        return "Format ungültig. Beispiel: Musterstraße 12"
    return None

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    tg_user = update.effective_user
    uid, alias = get_or_create_user(tg_user.id, tg_user.username or "")

    if context.user_data.get('waiting_for_name'):
        if len(text) < 2 or len(text) > 30:
            await update.message.reply_text(
                "❌ Der Username muss zwischen 2 und 30 Zeichen lang sein.\n"
                "Bitte versuche es erneut:"
            )
            return
        set_user_alias(uid, text)
        context.user_data['waiting_for_name'] = False
        await update.message.reply_text(
            f"Perfekt, {text}! ✅\n\n"
            "Jetzt zur Meldung: Bitte gib die Adresse des Leerstands ein (Format: Straße Hausnummer):"
        )
        context.user_data['meldung_step'] = 'adresse'
        return

    step = context.user_data.get('meldung_step')

    if step == 'adresse':
        error = validate_address(text)
        if error:
            await update.message.reply_text(f"❌ {error}\nBitte nochmals eingeben:")
            return
        context.user_data['adresse'] = text
        await update.message.reply_text("📸 Danke! Jetzt bitte ein Foto des Leerstands schicken.")
        context.user_data['meldung_step'] = 'foto'
    elif step == 'dauer':
        dauer = text.strip()
        adresse = context.user_data.get('adresse')
        img_path = context.user_data.get('img_path')
        # Prüfe, ob alle Daten vorhanden sind
        if not adresse or not img_path or not dauer:
            await update.message.reply_text(
                "❌ Es fehlen Angaben! Bitte beginne die Meldung erneut.",
                reply_markup=build_main_menu()
            )
            context.user_data.clear()
            return
        try:
            save_meldung(uid, img_path, adresse, dauer)
            add_points(uid, 5)
        except Exception as e:
            await update.message.reply_text(
                f"❌ Fehler beim Speichern: {e}",
                reply_markup=build_main_menu()
            )
            context.user_data.clear()
            return
        await update.message.reply_text(
            "✅ *Meldung erfolgreich gespeichert!*\n\n"
            f"📍 **Adresse:** {adresse}\n"
            f"⏰ **Dauer:** {dauer}\n\n"
            "Vielen Dank für deine Meldung! (+5 Punkte) 🙏",
            reply_markup=build_main_menu(),
            parse_mode='Markdown'
        )
        context.user_data.clear()
    else:
        await update.message.reply_text(
            "Bitte benutze die Buttons im Menü:",
            reply_markup=build_main_menu()
        )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('meldung_step') == 'foto':
        file = await update.message.photo[-1].get_file()
        fname = f"{uuid.uuid4()}.jpg"
        pfad = os.path.join(BILDER_ORDNER, fname)
        await file.download_to_drive(pfad)
        context.user_data['img_path'] = pfad
        await update.message.reply_text(
            "⏰ Danke! Wie lange steht die Wohnung schon leer? (z.B. 'seit 6 Monaten')"
        )
        context.user_data['meldung_step'] = 'dauer'
    else:
        await update.message.reply_text(
            "Bitte starte zuerst eine neue Meldung über das Menü:",
            reply_markup=build_main_menu()
        )

async def meldungen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    all_meldungen = list_meldungen()
    if not all_meldungen:
        await update.message.reply_text("Noch keine Meldungen vorhanden.")
        return
    for mid, path, addr, dauer, conf in all_meldungen:
        caption = f"#{mid} – {addr}\n⏰ Dauer: {dauer}\n✅ Bestätigt: {conf}x"
        try:
            with open(path, "rb") as f:
                await update.message.reply_photo(f, caption=caption)
        except:
            await update.message.reply_text(f"❌ Foto nicht verfügbar\n{caption}")

async def bestaetige(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Verwende /bestaetige <ID>")
        return
    try:
        mid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Ungültige ID")
        return
    with sqlite3.connect(DB_FILE) as con:
        c = con.cursor()
        c.execute("SELECT user_id FROM meldungen WHERE id=?", (mid,))
        row = c.fetchone()
        if not row:
            await update.message.reply_text("❌ Meldung nicht gefunden.")
            return
        melder = row[0]
        add_points(melder, 3)
        c.execute("UPDATE meldungen SET bestaetigungen = bestaetigungen + 1 WHERE id=?", (mid,))
        con.commit()
    await update.message.reply_text(
        f"✅ Meldung #{mid} bestätigt! (+3 Punkte für den Melder)",
        reply_markup=build_main_menu()
    )

async def ranking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏆 *Aktuelle Bestenliste:*", 
                                  reply_markup=build_ranking_keyboard(),
                                  parse_mode='Markdown')

async def loesche(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if (update.effective_user.username or "") not in ADMIN_USERNAMES:
        await update.message.reply_text("❌ Nicht autorisiert.")
        return
    if not context.args:
        await update.message.reply_text("Verwendung: /loesche <ID>")
        return
    try:
        mid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Ungültige ID")
        return
    with sqlite3.connect(DB_FILE) as con:
        c = con.cursor()
        c.execute("SELECT image_path FROM meldungen WHERE id=?", (mid,))
        row = c.fetchone()
        if not row:
            await update.message.reply_text("❌ Meldung nicht gefunden.")
            return
        pfad = row[0]
        if os.path.exists(pfad):
            os.remove(pfad)
        c.execute("DELETE FROM meldungen WHERE id=?", (mid,))
        con.commit()
    await update.message.reply_text(f"✅ Meldung #{mid} gelöscht.")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CommandHandler("meldungen", meldungen))
    app.add_handler(CommandHandler("ranking", ranking))
    app.add_handler(CommandHandler("loesche", loesche))
    app.add_handler(CommandHandler("bestaetige", bestaetige))
    print("🚀 Bot läuft...")
    app.run_polling()

if __name__ == "__main__":
    main()
