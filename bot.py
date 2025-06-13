import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# Konfiguriere das Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Beispiel-Datenbank (in der Realität solltest du eine echte Datenbank verwenden)
user_meldungen = {}  # Schlüssel: user_id, Wert: List von Meldungen

# Funktion, um Meldungen zu speichern
def add_meldung(user_id, meldung):
    if user_id not in user_meldungen:
        user_meldungen[user_id] = []
    user_meldungen[user_id].append(meldung)

# Funktion, um alle Meldungen eines Nutzers abzurufen
def get_user_meldungen(user_id):
    return user_meldungen.get(user_id, [])

# Funktion zum Erstellen des Menüs
def build_menu():
    keyboard = [
        [InlineKeyboardButton("Neue Meldung 📸", callback_data='neue_meldung')],
        [InlineKeyboardButton("Top 5 📈", callback_data='top5')],
        [InlineKeyboardButton("Meine Meldungen 📝", callback_data='meine_meldungen')]
    ]
    return InlineKeyboardMarkup(keyboard)

# /start Befehl
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Willkommen! Wähle eine Option:",
        reply_markup=build_menu()
    )

# Callback-Handler für Button-Klicks
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == 'neue_meldung':
        await query.edit_message_text("Bitte gib die Details deiner Wohnung und schick sie ab.")
        # Hier kannst du den nächsten Schritt starten, z.B. auf eine Nachricht warten
        # Für dieses Beispiel warten wir auf eine Nachricht vom Nutzer
        context.user_data['awaiting_meldung'] = True

    elif data == 'top5':
        # Beispiel: Top 5 anzeigen
        await query.edit_message_text("Hier sind die Top 5 Wohnungen:\n1. Wohnung A\n2. Wohnung B\n3. Wohnung C\n4. Wohnung D\n5. Wohnung E")
        
    elif data == 'meine_meldungen':
        meldungen = get_user_meldungen(update.effective_user.id)
        if meldungen:
            meldungen_text = "\n".join(f"{i+1}. {m}" for i, m in enumerate(meldungen))
            await query.edit_message_text(f"Deine Meldungen:\n{meldungen_text}")
        else:
            await query.edit_message_text("Du hast noch keine Meldungen.")

# Handler, um die Eingabe der neuen Meldung zu erfassen
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('awaiting_meldung'):
        meldung_text = update.message.text
        user_id = update.effective_user.id
        add_meldung(user_id, meldung_text)
        await update.message.reply_text("Deine Meldung wurde gespeichert!", reply_markup=build_menu())
        # Reset
        context.user_data['awaiting_meldung'] = False
    else:
        # Standardnachricht
        await update.message.reply_text("Bitte benutze die Buttons im Menü.")

async def main():
    # Ersetze 'YOUR_BOT_TOKEN' durch dein Bot-Token
    application = Application.builder().token('YOUR_BOT_TOKEN').build()

    # Handler hinzufügen
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    # Bot starten
    await application.run_polling()

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
